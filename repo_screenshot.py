from __future__ import annotations
"""
Renders a GitHub repo README as a JPEG for the newsletter.

Fetches the raw README.md via the GitHub API (no browser navigation),
converts markdown → styled HTML, and screenshots the local HTML with
Playwright. Falls back gracefully if either library is missing.
"""
import os
import tempfile
from io import BytesIO
from pathlib import Path

import requests

try:
    import markdown as md_lib
    _MARKDOWN_AVAILABLE = True
except ImportError:
    _MARKDOWN_AVAILABLE = False

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False

from PIL import Image

_EMAIL_WIDTH = 640
_MAX_HEIGHT  = 480

_CSS = """
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  font-size: 14px; line-height: 1.6; color: #24292e;
  background: #ffffff; padding: 24px 32px; max-width: 860px;
}
h1,h2,h3 { border-bottom: 1px solid #eaecef; padding-bottom: .3em; margin-top: 1.2em; }
code { background: #f6f8fa; border-radius: 3px; padding: .2em .4em; font-size: 85%; }
pre  { background: #f6f8fa; border-radius: 6px; padding: 16px; overflow: auto; }
pre code { background: none; padding: 0; }
a    { color: #0366d6; text-decoration: none; }
img  { max-width: 100%; }
"""


def _fetch_readme(full_name: str) -> str | None:
    """Return raw README markdown for owner/repo, or None on failure."""
    headers = {"Accept": "application/vnd.github.v3.raw"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{full_name}/readme",
            headers=headers, timeout=15,
        )
        resp.raise_for_status()
        return resp.text
    except Exception as exc:
        print(f"  [repo] README fetch failed for {full_name}: {exc}")
        return None


def screenshot_readme(full_name: str) -> bytes | None:
    """Return a JPEG screenshot of the repo README rendered from markdown, or None."""
    if not _PLAYWRIGHT_AVAILABLE:
        print("  [repo] Playwright not installed — skipping README screenshot")
        return None
    if not _MARKDOWN_AVAILABLE:
        print("  [repo] markdown library not installed — skipping README screenshot")
        return None

    raw_md = _fetch_readme(full_name)
    if not raw_md:
        return None

    # Trim to first ~150 lines so the screenshot shows the intro, not the full doc
    lines = raw_md.splitlines()
    trimmed = "\n".join(lines[:150])
    body_html = md_lib.markdown(trimmed, extensions=["fenced_code", "tables"])
    html = f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{_CSS}</style></head><body>{body_html}</body></html>"

    raw_png: bytes | None = None
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as f:
        f.write(html)
        tmp_path = f.name

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 860, "height": 900})
            page.goto(f"file://{tmp_path}", wait_until="domcontentloaded")
            raw_png = page.screenshot(type="png", full_page=False)
            browser.close()
    except Exception as exc:
        print(f"  [repo] Screenshot failed for {full_name}: {exc}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    if not raw_png:
        return None

    img = Image.open(BytesIO(raw_png)).convert("RGB")
    w, h = img.size
    scale = _EMAIL_WIDTH / w
    new_h = int(h * scale)
    img = img.resize((_EMAIL_WIDTH, new_h), Image.LANCZOS)
    if new_h > _MAX_HEIGHT:
        img = img.crop((0, 0, _EMAIL_WIDTH, _MAX_HEIGHT))

    out = BytesIO()
    img.save(out, format="JPEG", quality=85)
    return out.getvalue()
