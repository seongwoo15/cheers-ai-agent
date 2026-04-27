import base64
import json
from pathlib import Path
import mcp.types as types
from browser import ensure_page
from config import ROW_SELECTOR, DL_SELECTOR, DOWNLOAD_DIR

DEBUG_DIR = Path(__file__).parent / "debug"
OPTIONS_CACHE = Path(__file__).parent / "options_cache.json"


def load_options_cache() -> dict:
    if OPTIONS_CACHE.exists():
        return json.loads(OPTIONS_CACHE.read_text(encoding="utf-8"))
    return {}


def save_options_cache(data: dict):
    OPTIONS_CACHE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


async def _save_debug(page):
    DEBUG_DIR.mkdir(exist_ok=True)
    html = await page.content()
    (DEBUG_DIR / "page.html").write_text(html, encoding="utf-8")
    screenshot = await page.screenshot(type="png", full_page=True)
    (DEBUG_DIR / "screenshot.png").write_bytes(screenshot)


def _strip_email(text: str) -> str:
    """이메일 주소가 포함된 줄을 제거하고 첫 번째 줄만 반환."""
    return next((line.strip() for line in text.splitlines() if line.strip() and "@" not in line), text.strip())


async def fetch_companies(force: bool = False) -> dict:
    """회사 피커를 열어 선택 가능한 회사 목록과 현재 선택된 회사를 반환. 캐시 우선."""
    cache = load_options_cache()
    if not force and cache.get("companies"):
        return {"companies": cache["companies"], "current": cache.get("current_company", "")}

    page = await ensure_page()
    picker = page.locator("[data-cy='company-picker-dropdown']")

    current = _strip_email(await picker.inner_text())

    await picker.click()
    await page.wait_for_timeout(800)

    rows = page.locator("mat-row[data-cy='company-picker-table-row-btn']")
    count = await rows.count()

    companies = [current]
    for i in range(count):
        name_cell = rows.nth(i).locator(".cdk-column-companyName div")
        text = (await name_cell.inner_text()).strip()
        if text and text not in companies:
            companies.append(text)

    await page.keyboard.press("Escape")
    await page.wait_for_timeout(300)

    cache["companies"] = companies
    cache["current_company"] = current
    save_options_cache(cache)

    return {"companies": companies, "current": current}


async def switch_company(company_name: str) -> str:
    """회사 피커에서 지정한 회사로 전환."""
    page = await ensure_page()
    await page.locator("[data-cy='company-picker-dropdown']").click(timeout=5000)
    await page.wait_for_timeout(800)

    rows = page.locator("mat-row[data-cy='company-picker-table-row-btn']")
    count = await rows.count()
    for i in range(count):
        row = rows.nth(i)
        name_cell = row.locator(".cdk-column-companyName div")
        text = (await name_cell.inner_text()).strip()
        if text == company_name:
            await name_cell.click()
            await page.wait_for_load_state("networkidle")
            return f"✅ {text} 로 전환됐습니다."

    await page.keyboard.press("Escape")
    return f"❌ '{company_name}' 를 찾을 수 없습니다."


async def _collect_while_user_scrolls(page, idle_seconds=3) -> list:
    """드롭다운을 열어둔 채로 폴링하며 수집. 사용자가 스크롤하면 됨.
    idle_seconds 동안 새 항목이 없으면 자동 종료."""
    collected = set()
    idle_count = 0
    polls_per_second = 2
    idle_limit = idle_seconds * polls_per_second
    while idle_count < idle_limit:
        texts = await page.locator(".cdk-overlay-container mat-option").all_inner_texts()
        before = len(collected)
        collected.update(t.strip() for t in texts if t.strip())
        idle_count = 0 if len(collected) > before else idle_count + 1
        await page.wait_for_timeout(1000 // polls_per_second)
    return sorted(collected, key=str.casefold)


async def fetch_all_options(force: bool = False) -> dict:
    cache = load_options_cache()
    if not force and cache.get("suppliers") and cache.get("keywords"):
        return cache

    page = await ensure_page()
    if "lightyear.cloud/archive" not in page.url:
        await page.goto("https://app.lightyear.cloud/archive")
        await page.wait_for_load_state("networkidle")
        await page.get_by_role("button", name="search").first.click()
        await page.wait_for_timeout(1000)

    result = {}
    for key, data_cy in [("suppliers", "supplier-dropdown"), ("keywords", "cat-2-dropdown")]:
        await page.locator(f"[data-cy='{data_cy}'] mat-select").click()
        await page.wait_for_timeout(1500)
        print(f"[{key}] 드롭다운이 열렸습니다. 직접 스크롤하세요. 3초간 변화 없으면 자동 종료됩니다.")
        result[key] = await _collect_while_user_scrolls(page)
        print(f"[{key}] {len(result[key])}개 수집 완료")
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)

    save_options_cache(result)
    return result


async def _select_dropdown(page, data_cy: str, values: list):
    await page.locator(f"[data-cy='{data_cy}'] mat-select").click()
    await page.wait_for_timeout(1500)

    overlay = page.locator(".cdk-overlay-container")

    for value in values:
        search_in = overlay.locator("input").first
        if await search_in.is_visible():
            await search_in.click()
            await search_in.type(value)
            await page.wait_for_timeout(800)

        option = overlay.locator("mat-option, .mat-mdc-option").filter(has_text=value).first
        if await option.count() > 0:
            await option.click()
        await page.wait_for_timeout(300)

    await page.keyboard.press("Escape")
    await page.wait_for_timeout(300)


async def search_receipts(start_date: str, end_date: str, keywords: list, suppliers: list, line_desc: str = "", line_desc_match: str = "contains", company: str = "") -> list:
    page = await ensure_page()
    await page.goto("https://app.lightyear.cloud/archive")
    await page.wait_for_load_state("networkidle")
    if company:
        current = _strip_email(await page.locator("[data-cy='company-picker-dropdown']").inner_text())
        if company != current:
            await switch_company(company)
    await _save_debug(page)

    try:
        await page.get_by_role("button", name="search").first.click()
        await page.wait_for_timeout(1000)

        inputs = page.locator("input")
        if start_date:
            await inputs.nth(0).type(start_date)
        if end_date:
            await inputs.nth(1).type(end_date)

        if suppliers:
            await _select_dropdown(page, "supplier-dropdown", suppliers)

        if keywords:
            await _select_dropdown(page, "cat-2-dropdown", keywords)

        if line_desc:
            await page.locator("[data-cy='line-desc-input']").fill(line_desc)
            btn_index = "0" if line_desc_match == "exact" else "1"
            await page.locator(f"[data-cy='line-desc-criteria'] [data-cy='radio-btn-{btn_index}']").click()
            await page.wait_for_timeout(300)

        await page.locator(
            "button.mat-flat-button:has-text('Search'), [data-cy='search-btn']"
        ).filter(visible=True).last.click()

        try:
            await page.wait_for_selector(ROW_SELECTOR, timeout=15000)
        except Exception:
            return [types.TextContent(type="text", text="❌ 검색 결과가 없거나 로딩 시간이 초과됐습니다.")]

        paginator = page.locator(".mat-mdc-paginator-range-label, .mat-paginator-range-label")
        if await paginator.count() > 0:
            label = await paginator.first.inner_text()
            # "1 – 50 of 68" 형태에서 총 개수 추출
            total_text = label.strip().split()[-1]
            count = int(total_text) if total_text.isdigit() else await page.locator(ROW_SELECTOR).count()
        else:
            count = await page.locator(ROW_SELECTOR).count()
        print(f"검색 결과: {count}개")

        screenshot = await page.screenshot(type="png")
        return [
            types.TextContent(type="text", text=f"🎉 {count}개의 영수증을 찾았습니다! 아래 버튼을 눌러 저장하세요."),
            types.ImageContent(type="image", data=base64.b64encode(screenshot).decode(), mimeType="image/png"),
        ]
    except Exception as e:
        return [types.TextContent(type="text", text=f"❌ 오류 발생: {e}")]


NEXT_BTN = "mat-paginator button[aria-label='Next page']"


async def _download_current_page(page, downloaded: int, failed: int):
    rows = page.locator(ROW_SELECTOR)
    total_on_page = await rows.count()

    for i in range(total_on_page):
        try:
            if i == 0:
                await page.wait_for_function(
                    "() => !!document.querySelector('#print-section embed')?.src",
                    timeout=15000
                )
            else:
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
            print(f"✅ {dl.suggested_filename}")
            downloaded += 1

        except Exception as e:
            print(f"⚠️ 오류: {e}")
            failed += 1

    return downloaded, failed


async def batch_download() -> list:
    page = await ensure_page()

    if "lightyear.cloud/archive" not in page.url:
        return [types.TextContent(type="text", text="❌ 먼저 영수증 검색을 실행하세요.")]

    if await page.locator(ROW_SELECTOR).count() == 0:
        return [types.TextContent(type="text", text="❌ 검색 결과가 없습니다. 먼저 검색을 실행하세요.")]

    downloaded = 0
    failed = 0

    while True:
        downloaded, failed = await _download_current_page(page, downloaded, failed)

        next_btn = page.locator(NEXT_BTN).first
        if await next_btn.count() == 0 or await next_btn.get_attribute("aria-disabled") == "true":
            break

        old_first_text = await page.locator(ROW_SELECTOR).first.inner_text()
        await next_btn.click()
        await page.wait_for_function(
            """(oldText) => {
                const row = document.querySelector('mat-row:not(.read-only)');
                return row && row.innerText !== oldText;
            }""",
            arg=old_first_text,
            timeout=15000
        )

    msg = f"✅ {downloaded}개 저장 완료 → {DOWNLOAD_DIR}"
    if failed:
        msg += f"  (실패: {failed}개)"
    return [types.TextContent(type="text", text=msg)]
