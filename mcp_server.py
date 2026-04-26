from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from mcp.server import Server
from mcp.server.sse import SseServerTransport
import mcp.types as types
import uvicorn
import base64
import os
from pathlib import Path
from playwright.async_api import async_playwright, Page

server = Server("cheers-ai-agent-web-server")
app = FastAPI()
sse = SseServerTransport("/messages")

BASE_DIR = Path(__file__).parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
USER_DATA_DIR = BASE_DIR / "browser_data"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(USER_DATA_DIR, exist_ok=True)

ROW_SELECTOR = "mat-row, tr.mat-mdc-row, .mat-mdc-row"
DL_SELECTOR = "[data-cy='panel3-download-btn']"

# 단일 사용자 툴이므로 전역 브라우저 컨텍스트 유지
_playwright = None
_context = None
_page: Page | None = None


async def ensure_page() -> Page:
    global _playwright, _context, _page
    if _page is None or _page.is_closed():
        _playwright = await async_playwright().start()
        _context = await _playwright.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR, headless=False
        )
        _page = await _context.new_page()
    return _page


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="automated_receipt_search",
            description="날짜 범위와 키워드로 영수증 검색",
            inputSchema={
                "type": "object",
                "properties": {
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "keyword": {"type": "string"},
                },
            },
        ),
        types.Tool(
            name="smart_batch_download",
            description="검색된 모든 영수증을 다운로드",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent | types.ImageContent]:
    if name == "automated_receipt_search":
        start_date = (arguments or {}).get("start_date", "")
        end_date   = (arguments or {}).get("end_date", "")
        keyword    = (arguments or {}).get("keyword", "")

        page = await ensure_page()
        await page.goto("https://app.lightyear.cloud/archive")
        await page.wait_for_load_state("networkidle")

        try:
            # 1. Search 탭
            await page.get_by_role("button", name="search").first.click()
            await page.wait_for_timeout(1000)

            # 2. 날짜 입력
            inputs = page.locator("input")
            if start_date:
                await inputs.nth(0).type(start_date)
            if end_date:
                await inputs.nth(1).type(end_date)

            # 3. Classes 드롭다운
            if keyword:
                label = page.get_by_text("Classes", exact=True).last
                box = await label.bounding_box()
                if box:
                    await page.mouse.click(box['x'] + 200, box['y'] + box['height'] / 2)
                    await page.wait_for_timeout(1500)

                    search_in = page.locator(".cdk-overlay-container input[placeholder*='Search']").last
                    if await search_in.is_visible():
                        await search_in.type(keyword)
                        await page.wait_for_timeout(800)

                    await page.evaluate("""
                        (text) => {
                            const opt = Array.from(document.querySelectorAll(
                                'mat-option, .mat-mdc-option, [role="option"]'
                            )).find(el => el.innerText.toLowerCase().includes(text.toLowerCase()));
                            if (opt) opt.click();
                        }
                    """, keyword)
                    await page.wait_for_timeout(500)
                    await page.keyboard.press("Escape")

            # 4. 검색 실행
            await page.locator(
                "button.mat-flat-button:has-text('Search'), [data-cy='search-btn']"
            ).filter(visible=True).last.click()

            # 결과 행이 실제로 나타날 때까지 대기 (최대 15초)
            try:
                await page.wait_for_selector(ROW_SELECTOR, timeout=15000)
            except Exception:
                return [types.TextContent(type="text", text="❌ 검색 결과가 없거나 로딩 시간이 초과됐습니다.")]

            count = await page.locator(ROW_SELECTOR).count()
            print(f"검색 결과: {count}개")

            screenshot = await page.screenshot(type="png")
            return [
                types.TextContent(type="text", text=f"🎉 {count}개의 영수증을 찾았습니다! 아래 버튼을 눌러 저장하세요."),
                types.ImageContent(type="image", data=base64.b64encode(screenshot).decode(), mimeType="image/png"),
            ]
        except Exception as e:
            return [types.TextContent(type="text", text=f"❌ 오류 발생: {e}")]

    if name == "smart_batch_download":
        page = await ensure_page()

        if "lightyear.cloud/archive" not in page.url:
            return [types.TextContent(type="text", text="❌ 먼저 영수증 검색을 실행하세요.")]

        rows = page.locator(ROW_SELECTOR)
        total = await rows.count()

        if total == 0:
            return [types.TextContent(type="text", text="❌ 검색 결과가 없습니다. 먼저 검색을 실행하세요.")]

        downloaded = 0
        failed = 0

        for i in range(total):
            try:
                if i == 0:
                    # 첫 번째 행은 자동 선택됨 — PDF 뷰어에 로드될 때까지 대기
                    await page.wait_for_function(
                        "() => !!document.querySelector('#print-section embed')?.src",
                        timeout=15000
                    )
                else:
                    # 현재 embed src 기록 → 클릭 → src가 바뀔 때까지 대기
                    old_src = await page.evaluate(
                        "document.querySelector('#print-section embed')?.src || ''"
                    )
                    async with page.expect_response(
                        lambda r: "/api/v1/documents/" in r.url,
                        timeout=10000
                    ) as resp_info:
                        await rows.nth(i).click()
                    await resp_info.value
                    await page.wait_for_function(
                        """(oldSrc) => {
                            const s = document.querySelector('#print-section embed')?.src || '';
                            return s && s !== oldSrc;
                        }""",
                        arg=old_src,
                        timeout=15000
                    )

                dl_btn = page.locator(DL_SELECTOR)
                async with page.expect_download(timeout=15000) as dl_info:
                    await dl_btn.click()
                dl = await dl_info.value
                await dl.save_as(DOWNLOAD_DIR / dl.suggested_filename)
                print(f"✅ {i+1}/{total}: {dl.suggested_filename}")
                downloaded += 1

            except Exception as e:
                print(f"⚠️ {i+1}/{total} 오류: {e}")
                failed += 1
                continue

        msg = f"✅ {downloaded}/{total}개 저장 완료 → {DOWNLOAD_DIR}"
        if failed:
            msg += f"  (실패: {failed}개)"
        return [types.TextContent(type="text", text=msg)]

    raise ValueError(f"Unknown tool: {name}")


@app.get("/", response_class=HTMLResponse)
async def get_index():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Cheers AI - Pro Dashboard</title>
        <style>
            body { font-family: 'Segoe UI', sans-serif; background: #f0f4f8; padding: 40px; display: flex; flex-direction: column; align-items: center; }
            .card { background: white; padding: 35px; border-radius: 24px; box-shadow: 0 15px 35px rgba(0,0,0,0.1); width: 600px; }
            h2 { color: #1a73e8; font-weight: 800; margin-bottom: 30px; text-align: center; }
            .input-box { margin-bottom: 20px; }
            input { width: 100%; padding: 14px; border: 2px solid #eef2f6; border-radius: 12px; box-sizing: border-box; font-size: 1rem; transition: 0.3s; }
            input:focus { border-color: #1a73e8; outline: none; }
            .main-btn { background: #1a73e8; color: white; border: none; padding: 16px; border-radius: 14px; font-weight: 700; cursor: pointer; width: 100%; font-size: 1.1rem; }
            .download-btn { background: #00c853; color: white; border: none; padding: 16px; border-radius: 14px; font-weight: 700; cursor: pointer; width: 100%; margin-top: 15px; display: none; }
            #status { margin-top: 25px; padding: 20px; background: #f8f9fa; border-radius: 15px; font-size: 0.95rem; line-height: 1.6; }
            img { width: 100%; margin-top: 20px; border-radius: 15px; display: none; border: 1px solid #ddd; }
        </style>
    </head>
    <body>
        <div class="card">
            <h2>🍹 Cheers 영수증 마스터</h2>
            <div class="input-box">
                <div style="display:flex; gap:10px; margin-bottom:10px;">
                    <input type="text" id="startD" value="01/10/2025">
                    <input type="text" id="endD" value="01/11/2025">
                </div>
                <input type="text" id="keyword" value="Products - Beverages">
            </div>
            <button class="main-btn" onclick="runSearch()">영수증 검색 및 분석</button>
            <button id="dlBtn" class="download-btn" onclick="runDownload()">📥 모든 영수증 PC에 저장하기</button>
            <div id="status">검색 조건을 확인하고 버튼을 누르세요.</div>
            <img id="screenshot">
        </div>
        <script>
            async function runSearch() {
                const s = document.getElementById('startD').value, e = document.getElementById('endD').value, k = document.getElementById('keyword').value;
                const status = document.getElementById('status'), img = document.getElementById('screenshot'), dlBtn = document.getElementById('dlBtn');
                status.innerText = "🔍 로봇이 영수증을 찾고 있습니다. 브라우저 창을 확인해 주세요...";
                dlBtn.style.display = 'none'; img.style.display = 'none';
                const res = await fetch('/api/auto_search', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ start_date: s, end_date: e, keyword: k })
                });
                const data = await res.json();
                status.innerText = data.text;
                if (data.image) { img.src = "data:image/png;base64," + data.image; img.style.display = 'block'; }
                if (data.text.includes('찾았습니다')) dlBtn.style.display = 'block';
            }
            async function runDownload() {
                const status = document.getElementById('status');
                status.innerText = "📥 다운로드 중입니다... 브라우저 창을 확인해 주세요.";
                const res = await fetch('/api/batch_download', { method: 'POST' });
                const data = await res.json();
                status.innerText = data.text;
            }
        </script>
    </body>
    </html>
    """


@app.post("/api/auto_search")
async def api_auto_search(req: Request):
    data = await req.json()
    result = await handle_call_tool("automated_receipt_search", data)
    return {"text": result[0].text, "image": result[1].data if len(result) > 1 else None}


@app.post("/api/batch_download")
async def api_batch_download():
    result = await handle_call_tool("smart_batch_download", {})
    return {"text": result[0].text}


@app.get("/sse")
async def handle_sse(request: Request):
    async with sse.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())


@app.post("/messages")
async def handle_messages(request: Request):
    await sse.handle_post_message(request.scope, request.receive, request._send)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
