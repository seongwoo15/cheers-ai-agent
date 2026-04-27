from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from mcp.server import Server
from mcp.server.sse import SseServerTransport
import mcp.types as types
import uvicorn
from automation import search_receipts, batch_download, fetch_all_options, fetch_companies, switch_company

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
                    "supplier": {"type": "string"},
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
        return await search_receipts(args.get("start_date", ""), args.get("end_date", ""), args.get("keywords", []), args.get("suppliers", []), args.get("line_desc", ""), args.get("line_desc_match", "contains"), args.get("company", ""))
    if name == "smart_batch_download":
        return await batch_download()
    raise ValueError(f"Unknown tool: {name}")


@app.get("/", response_class=HTMLResponse)
async def get_index():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Cheers AI - 영수증 마스터</title>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body { font-family: 'Segoe UI', sans-serif; background: #f0f4f8; padding: 40px; display: flex; justify-content: center; }
            .card { background: white; padding: 36px; border-radius: 24px; box-shadow: 0 15px 35px rgba(0,0,0,0.1); width: 660px; }
            h2 { color: #1a73e8; font-weight: 800; margin-bottom: 28px; text-align: center; font-size: 1.4rem; }
            .section { margin-bottom: 20px; }
            label.field-label { display: block; font-weight: 600; color: #444; margin-bottom: 8px; font-size: 0.9rem; }
            .date-row { display: flex; gap: 12px; }
            .date-row input { flex: 1; }
            input[type=date] { width: 100%; padding: 12px 14px; border: 2px solid #eef2f6; border-radius: 12px; font-size: 1rem; transition: 0.2s; }
            input[type=date]:focus { border-color: #1a73e8; outline: none; }
            .checkbox-panel-wrap { border: 2px solid #eef2f6; border-radius: 12px; overflow: hidden; }
            .checkbox-search { width: 100%; padding: 10px 14px; border: none; border-bottom: 2px solid #eef2f6; font-size: 0.9rem; outline: none; }
            .checkbox-search:focus { border-bottom-color: #1a73e8; }
            .checkbox-panel { padding: 10px 14px; max-height: 160px; overflow-y: auto; }
            .checkbox-panel label { display: flex; align-items: center; gap: 8px; padding: 5px 0; font-size: 0.95rem; cursor: pointer; }
            .checkbox-panel label:hover { color: #1a73e8; }
            .checkbox-panel label.hidden { display: none; }
            .load-btn { background: none; border: 2px solid #1a73e8; color: #1a73e8; padding: 8px 16px; border-radius: 10px; font-weight: 600; cursor: pointer; font-size: 0.85rem; margin-bottom: 10px; }
            .load-btn:hover { background: #e8f0fe; }
            .company-bar { display: flex; align-items: center; gap: 10px; background: #f0f4f8; border-radius: 12px; padding: 10px 16px; margin-bottom: 24px; }
            .company-bar select { flex: 1; border: none; background: transparent; font-size: 0.95rem; font-weight: 600; color: #333; outline: none; cursor: pointer; }
            .company-bar button { background: #1a73e8; color: white; border: none; padding: 7px 14px; border-radius: 8px; font-weight: 600; cursor: pointer; font-size: 0.85rem; white-space: nowrap; }
            .company-bar button:hover { background: #1558c0; }
            .main-btn { background: #1a73e8; color: white; border: none; padding: 16px; border-radius: 14px; font-weight: 700; cursor: pointer; width: 100%; font-size: 1.05rem; margin-top: 8px; }
            .main-btn:hover { background: #1558c0; }
            .download-btn { background: #00c853; color: white; border: none; padding: 16px; border-radius: 14px; font-weight: 700; cursor: pointer; width: 100%; margin-top: 12px; display: none; font-size: 1.05rem; }
            #status { margin-top: 20px; padding: 18px; background: #f8f9fa; border-radius: 14px; font-size: 0.95rem; line-height: 1.6; color: #333; }
        </style>
    </head>
    <body>
        <div class="card">
            <h2>🍹 Cheers 영수증 마스터</h2>

            <div class="company-bar">
                <span>🏢</span>
                <select id="companySelect"><option value="">-- ↺ 버튼으로 목록 불러오기 --</option></select>
                <button onclick="loadCompanies(true)">↺</button>
            </div>

            <div class="section">
                <label class="field-label">📅 날짜 범위</label>
                <div class="date-row">
                    <input type="date" id="startD" value="2025-10-01">
                    <input type="date" id="endD" value="2025-11-30">
                </div>
            </div>

            <div class="section">
                <label class="field-label">🔤 Line Desc</label>
                <div style="display:flex; gap:10px; align-items:center;">
                    <input type="text" id="lineDesc" placeholder="검색어 입력..." style="flex:1; padding:12px 14px; border:2px solid #eef2f6; border-radius:12px; font-size:1rem; outline:none;" onfocus="this.style.borderColor='#1a73e8'" onblur="this.style.borderColor='#eef2f6'">
                    <div style="display:flex; border:2px solid #eef2f6; border-radius:12px; overflow:hidden; flex-shrink:0;">
                        <button id="matchExact" onclick="setMatch('exact')" style="padding:10px 14px; border:none; background:white; color:#888; font-weight:600; cursor:pointer; font-size:0.85rem;">Exact Match</button>
                        <button id="matchContains" onclick="setMatch('contains')" style="padding:10px 14px; border:none; background:#1a73e8; color:white; font-weight:600; cursor:pointer; font-size:0.85rem;">Contains</button>
                    </div>
                </div>
            </div>

            <div class="section">
                <label class="field-label">🏪 Supplier</label>
                <div class="checkbox-panel-wrap">
                    <input class="checkbox-search" type="text" placeholder="검색..." oninput="filterPanel('supplier-panel', this.value)">
                    <div class="checkbox-panel" id="supplier-panel"><i style="color:#999">불러오는 중...</i></div>
                </div>
            </div>

            <div class="section">
                <label class="field-label">🏷️ Classes</label>
                <div class="checkbox-panel-wrap">
                    <input class="checkbox-search" type="text" placeholder="검색..." oninput="filterPanel('keyword-panel', this.value)">
                    <div class="checkbox-panel" id="keyword-panel"><i style="color:#999">불러오는 중...</i></div>
                </div>
            </div>

            <button class="main-btn" onclick="runSearch()">🔍 영수증 검색</button>
            <button id="dlBtn" class="download-btn" onclick="runDownload()">📥 모든 영수증 PC에 저장하기</button>
            <div id="status">날짜를 설정하고 검색하세요. 필터는 선택사항입니다.</div>
        </div>
        <script>
            async function loadOptions(refresh) {
                ['supplier-panel', 'keyword-panel'].forEach(id => {
                    document.getElementById(id).innerHTML = '<i style="color:#999">불러오는 중...</i>';
                });
                if (refresh) {
                    document.getElementById('status').innerText = '브라우저 창에서 드롭다운이 열립니다. 직접 스크롤해주세요. 3초간 변화가 없으면 다음 항목으로 넘어갑니다.';
                }
                const res = await fetch('/api/options' + (refresh ? '?refresh=true' : ''));
                const data = await res.json();
                renderCheckboxes('supplier-panel', data.suppliers);
                renderCheckboxes('keyword-panel', data.keywords);
                if (refresh) {
                    document.getElementById('status').innerText = `✅ Supplier ${data.suppliers.length}개 / Classes ${data.keywords.length}개 수집 완료`;
                }
            }

            function renderCheckboxes(panelId, items) {
                if (!items || !items.length) {
                    document.getElementById(panelId).innerHTML = '<i style="color:#999">목록 없음</i>';
                    return;
                }
                document.getElementById(panelId).innerHTML = items.map(item =>
                    `<label><input type="checkbox" value="${item}"> ${item}</label>`
                ).join('');
            }

            function filterPanel(panelId, query) {
                const q = query.trim().toLowerCase();
                document.querySelectorAll(`#${panelId} label`).forEach(label => {
                    label.classList.toggle('hidden', q !== '' && !label.textContent.toLowerCase().includes(q));
                });
            }

            function getChecked(panelId) {
                return Array.from(document.querySelectorAll(`#${panelId} input:checked`)).map(el => el.value);
            }

            let matchMode = 'contains';
            function setMatch(mode) {
                matchMode = mode;
                document.getElementById('matchExact').style.background = mode === 'exact' ? '#1a73e8' : 'white';
                document.getElementById('matchExact').style.color = mode === 'exact' ? 'white' : '#888';
                document.getElementById('matchContains').style.background = mode === 'contains' ? '#1a73e8' : 'white';
                document.getElementById('matchContains').style.color = mode === 'contains' ? 'white' : '#888';
            }

            function toDisplayDate(isoDate) {
                if (!isoDate) return '';
                const [y, m, d] = isoDate.split('-');
                return `${d}/${m}/${y}`;
            }

            async function runSearch() {
                const s = toDisplayDate(document.getElementById('startD').value);
                const e = toDisplayDate(document.getElementById('endD').value);
                const suppliers = getChecked('supplier-panel');
                const keywords = getChecked('keyword-panel');
                const status = document.getElementById('status'), dlBtn = document.getElementById('dlBtn');
                status.innerText = "🔍 로봇이 영수증을 찾고 있습니다. 브라우저 창을 확인해 주세요...";
                dlBtn.style.display = 'none';
                const res = await fetch('/api/auto_search', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ start_date: s, end_date: e, keywords, suppliers, line_desc: document.getElementById('lineDesc').value.trim(), line_desc_match: matchMode, company: document.getElementById('companySelect').value })
                });
                const data = await res.json();
                status.innerText = data.text;
if (data.text.includes('찾았습니다')) dlBtn.style.display = 'block';
            }

            async function runDownload() {
                const status = document.getElementById('status');
                status.innerText = "📥 다운로드 중입니다... 브라우저 창을 확인해 주세요.";
                const res = await fetch('/api/batch_download', { method: 'POST' });
                const data = await res.json();
                status.innerText = data.text;
            }
            async function loadCompanies(refresh = false) {
                const res = await fetch('/api/companies' + (refresh ? '?refresh=true' : ''));
                const data = await res.json();
                const sel = document.getElementById('companySelect');
                sel.innerHTML = data.companies.length
                    ? data.companies.map(c => `<option${c === data.current ? ' selected' : ''}>${c}</option>`).join('')
                    : '<option>항목 없음</option>';
            }

            async function switchCompany() {
                const company = document.getElementById('companySelect').value;
                document.getElementById('status').innerText = `🔄 ${company} 로 전환 중...`;
                const res = await fetch('/api/switch_company', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ company })
                });
                const data = await res.json();
                document.getElementById('status').innerText = data.text;
            }

            window.addEventListener('load', () => { loadOptions(false); loadCompanies(); });
        </script>
    </body>
    </html>
    """


@app.get("/api/companies")
async def api_companies(refresh: bool = False):
    if not refresh:
        from automation import load_options_cache
        cache = load_options_cache()
        if cache.get("companies"):
            return {"companies": cache["companies"], "current": cache.get("current_company", "")}
        return {"companies": [], "current": ""}
    return await fetch_companies(force=True)


@app.post("/api/switch_company")
async def api_switch_company(req: Request):
    data = await req.json()
    text = await switch_company(data.get("company", ""))
    return {"text": text}


@app.get("/api/options")
async def api_options(refresh: bool = False):
    return await fetch_all_options(force=refresh)


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
