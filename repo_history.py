"""Persistence for previously-featured Repo of the Day picks.

Pheme picks one "Repo of the Day" per run. Without a history, the LLM keeps
picking the same high-star repositories every day (litellm, langfuse, …).
This module keeps a rolling list of what's been featured so we can exclude
recent picks from the candidate pool before curation.

Storage: data/featured_repos.json — a list of {full_name, date} entries.
data/ is gitignored, so history is per-install and stays out of the PR.
"""
from __future__ import annotations
import json
from datetime import date, datetime, timedelta
from pathlib import Path

# Days a repo stays on the exclusion list after being featured.
# Balances freshness against candidate-pool size (~15/day).
DEDUP_WINDOW_DAYS = 30

_HISTORY_PATH = Path(__file__).parent / "data" / "featured_repos.json"


def _load() -> list[dict]:
    if not _HISTORY_PATH.exists():
        return []
    try:
        return json.loads(_HISTORY_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def _save(entries: list[dict]) -> None:
    _HISTORY_PATH.parent.mkdir(exist_ok=True)
    _HISTORY_PATH.write_text(json.dumps(entries, indent=2))


def recent_featured(window_days: int = DEDUP_WINDOW_DAYS) -> set[str]:
    """Return full_names featured within the last `window_days`."""
    cutoff = (date.today() - timedelta(days=window_days)).isoformat()
    return {e["full_name"] for e in _load() if e.get("date", "") >= cutoff}


def filter_candidates(repos: list[dict], window_days: int = DEDUP_WINDOW_DAYS) -> list[dict]:
    """Drop repos already featured within `window_days`. Preserves order."""
    excluded = recent_featured(window_days)
    return [r for r in repos if r.get("full_name") not in excluded]


def record_featured(full_name: str, on: str | None = None) -> None:
    """Append a featured pick to the history file (idempotent for same-day repeats)."""
    entries = _load()
    today = on or date.today().isoformat()
    # Idempotent: no-op if this repo was already recorded today
    if any(e.get("full_name") == full_name and e.get("date") == today for e in entries):
        return
    entries.append({"full_name": full_name, "date": today})
    # Prune entries older than 1 year to keep the file small
    prune_cutoff = (date.today() - timedelta(days=365)).isoformat()
    entries = [e for e in entries if e.get("date", "") >= prune_cutoff]
    _save(entries)
