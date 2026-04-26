import base64
import mcp.types as types
from browser import ensure_page
from config import ROW_SELECTOR, DL_SELECTOR, DOWNLOAD_DIR


async def search_receipts(start_date: str, end_date: str, keyword: str) -> list:
    page = await ensure_page()
    await page.goto("https://app.lightyear.cloud/archive")
    await page.wait_for_load_state("networkidle")

    try:
        await page.get_by_role("button", name="search").first.click()
        await page.wait_for_timeout(1000)

        inputs = page.locator("input")
        if start_date:
            await inputs.nth(0).type(start_date)
        if end_date:
            await inputs.nth(1).type(end_date)

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

        await page.locator(
            "button.mat-flat-button:has-text('Search'), [data-cy='search-btn']"
        ).filter(visible=True).last.click()

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


async def batch_download() -> list:
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
