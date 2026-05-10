"""
Captures a screenshot of a GitHub repo's rendered README using Playwright.
Gracefully returns None if Playwright is not installed or the page fails.

One-time setup:
    pip install playwright
    playwright install chromium
"""
from io import BytesIO

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False

from PIL import Image

_EMAIL_WIDTH  = 640
_MAX_HEIGHT   = 480   # show roughly one viewport of the README


def screenshot_readme(full_name: str) -> bytes | None:
    """Return a JPEG screenshot of the repo README, resized for email, or None on failure."""
    if not _PLAYWRIGHT_AVAILABLE:
        print("  [repo] Playwright not installed — skipping README screenshot")
        return None

    url = f"https://github.com/{full_name}"
    raw: bytes | None = None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                viewport={"width": 1280, "height": 900},
                color_scheme="light",
            )
            page.goto(url, wait_until="domcontentloaded", timeout=20_000)

            # Try to clip to just the README article element
            readme_sel = "#readme article"
            try:
                page.wait_for_selector(readme_sel, timeout=8_000)
                elem = page.query_selector(readme_sel)
                raw = elem.screenshot(type="png") if elem else page.screenshot(type="png")
            except PWTimeout:
                raw = page.screenshot(type="png")

            browser.close()
    except Exception as exc:
        print(f"  [repo] Screenshot failed for {full_name}: {exc}")
        return None

    if not raw:
        return None

    img = Image.open(BytesIO(raw)).convert("RGB")
    w, h = img.size
    scale  = _EMAIL_WIDTH / w
    new_h  = int(h * scale)
    img    = img.resize((_EMAIL_WIDTH, new_h), Image.LANCZOS)

    if new_h > _MAX_HEIGHT:
        img = img.crop((0, 0, _EMAIL_WIDTH, _MAX_HEIGHT))

    out = BytesIO()
    img.save(out, format="JPEG", quality=85)
    return out.getvalue()
