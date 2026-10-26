"""Persistence for previously-featured Substack posts in the "News" section.

Substack candidates are drawn from a 7-day window, so without a history the
same post would be picked several days in a row. Mirrors repo_history.py,
keyed by post URL.

Storage: data/featured_news.json — a list of {url, date} entries (gitignored).
"""
from __future__ import annotations
import json
from datetime import date, timedelta
from pathlib import Path

DEDUP_WINDOW_DAYS = 30

_HISTORY_PATH = Path(__file__).parent / "data" / "featured_news.json"


def _load() -> list[dict]:
    if not _HISTORY_PATH.exists():
        return []
    try:
        return json.loads(_HISTORY_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def _key(url: str) -> str:
    return url.rstrip("/").lower()


def filter_news(posts: list[dict], window_days: int = DEDUP_WINDOW_DAYS) -> list[dict]:
    """Drop posts already featured within `window_days`. Preserves order."""
    cutoff = (date.today() - timedelta(days=window_days)).isoformat()
    excluded = {e["url"] for e in _load() if e.get("date", "") >= cutoff}
    return [p for p in posts if _key(p["url"]) not in excluded]


def record_news(urls: list[str], on: str | None = None) -> None:
    """Append featured post URLs to the history file (idempotent for same-day repeats)."""
    entries = _load()
    today = on or date.today().isoformat()
    for url in urls:
        if not any(e.get("url") == _key(url) and e.get("date") == today for e in entries):
            entries.append({"url": _key(url), "date": today})
    # Prune entries older than 1 year to keep the file small
    prune_cutoff = (date.today() - timedelta(days=365)).isoformat()
    entries = [e for e in entries if e.get("date", "") >= prune_cutoff]
    _HISTORY_PATH.parent.mkdir(exist_ok=True)
    _HISTORY_PATH.write_text(json.dumps(entries, indent=2))
