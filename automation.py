import base64
from pathlib import Path
import mcp.types as types
from browser import ensure_page
from config import ROW_SELECTOR, DL_SELECTOR, DOWNLOAD_DIR

DEBUG_DIR = Path(__file__).parent / "debug"


async def _save_debug(page):
    DEBUG_DIR.mkdir(exist_ok=True)
    html = await page.content()
    (DEBUG_DIR / "page.html").write_text(html, encoding="utf-8")
    screenshot = await page.screenshot(type="png", full_page=True)
    (DEBUG_DIR / "screenshot.png").write_bytes(screenshot)


async def _select_dropdown(page, data_cy: str, value: str):
    await page.locator(f"[data-cy='{data_cy}'] mat-select").click()
    await page.wait_for_timeout(1500)

    search_in = page.locator(".cdk-overlay-container input[placeholder*='Search']").last
    if await search_in.is_visible():
        await search_in.type(value)
        await page.wait_for_timeout(800)

    await page.evaluate("""
        (text) => {
            const opt = Array.from(document.querySelectorAll(
                'mat-option, .mat-mdc-option, [role="option"]'
            )).find(el => el.innerText.toLowerCase().includes(text.toLowerCase()));
            if (opt) opt.click();
        }
    """, value)
    await page.wait_for_timeout(500)
    await page.keyboard.press("Escape")


async def search_receipts(start_date: str, end_date: str, keyword: str, supplier: str = "") -> list:
    page = await ensure_page()
    await page.goto("https://app.lightyear.cloud/archive")
    await page.wait_for_load_state("networkidle")
    await _save_debug(page)

    try:
        await page.get_by_role("button", name="search").first.click()
        await page.wait_for_timeout(1000)

        inputs = page.locator("input")
        if start_date:
            await inputs.nth(0).type(start_date)
        if end_date:
            await inputs.nth(1).type(end_date)

        if supplier:
            await _select_dropdown(page, "supplier-dropdown", supplier)

        if keyword:
            await _select_dropdown(page, "cat-2-dropdown", keyword)

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
