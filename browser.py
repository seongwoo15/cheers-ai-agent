from playwright.async_api import async_playwright, Page
from config import USER_DATA_DIR

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
