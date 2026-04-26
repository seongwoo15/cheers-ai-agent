from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from mcp.server import Server
from mcp.server.sse import SseServerTransport
import mcp.types as types
import uvicorn
from automation import search_receipts, batch_download

server = Server("cheers-ai-agent-web-server")
app = FastAPI()
sse = SseServerTransport("/messages")


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
    args = arguments or {}
    if name == "automated_receipt_search":
        return await search_receipts(args.get("start_date", ""), args.get("end_date", ""), args.get("keyword", ""))
    if name == "smart_batch_download":
        return await batch_download()
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
                    <input type="text" id="endD" value="30/11/2025">
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
    async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())


@app.post("/messages")
async def handle_messages(request: Request):
    await sse.handle_post_message(request.scope, request.receive, request._send)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
