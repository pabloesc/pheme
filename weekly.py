#!/usr/bin/env python3
"""
Pheme — weekly digest.
Run manually:  python weekly.py
Dry-run:       python weekly.py --dry-run

Logic:
  1. Collect picks (⭐) from data/picks.json for the past 7 days.
  2. Look up the full item details from the saved daily newsletters (data/YYYY-MM-DD.json).
  3. If >= WEEKLY_MIN_PICKS picks found → use them as the digest (up to WEEKLY_MAX_ITEMS).
  4. Otherwise → fallback: fetch fresh articles and curate WEEKLY_FALLBACK_ITEMS.
  5. Send email to the configured recipient.
"""
from __future__ import annotations
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from config import WEEKLY_MAX_ITEMS, WEEKLY_FALLBACK_ITEMS, WEEKLY_MIN_PICKS
from fetcher import fetch_all, fetch_github_repos
from processor import curate, ensure_model_loaded, unload_model
from image_gen import generate_header_image
from repo_screenshot import screenshot_readme
from mailer import send_newsletter

DATA_DIR = Path(__file__).parent / "data"


def _collect_picks() -> tuple[list[dict], int]:
    """Return (resolved_items, raw_pick_count) for picks in the past 7 days."""
    picks_path = DATA_DIR / "picks.json"
    if not picks_path.exists():
        return [], 0

    picks_by_day: dict = json.loads(picks_path.read_text())
    today = date.today()
    window = {(today - timedelta(days=i)).isoformat() for i in range(7)}

    raw_count = sum(len(picks_by_day.get(day, [])) for day in window)

    # Build a lookup: item_id → item dict from saved daily newsletters
    id_to_item: dict[str, dict] = {}
    for day in sorted(window, reverse=True):
        daily_path = DATA_DIR / f"{day}.json"
        if not daily_path.exists():
            continue
        newsletter = json.loads(daily_path.read_text())
        for item in newsletter.get("items", []):
            id_to_item[item["id"]] = item

    picked: list[dict] = []
    for day in sorted(window, reverse=True):
        for item_id in picks_by_day.get(day, []):
            if item_id in id_to_item and item_id not in {p["id"] for p in picked}:
                picked.append(id_to_item[item_id])

    if raw_count > 0 and not picked:
        print(f"  ⚠️  {raw_count} pick(s) found but no saved daily newsletters to resolve them — "
              f"run main.py first so future picks are resolvable.")

    return picked[:WEEKLY_MAX_ITEMS], raw_count


def _build_weekly_newsletter(items: list[dict], source: str) -> dict:
    """Wrap items in the newsletter envelope expected by the mailer."""
    from datetime import date as _date
    today = _date.today()
    start = (today - timedelta(days=6)).strftime("%b %d")
    end   = today.strftime("%b %d, %Y")
    return {
        "intro": f"Your weekly picks from Pheme ({source}), {start}–{end}.",
        "image_prompt": "Dark background, electric blue and purple geometric shapes, "
                        "weekly digest theme, circuit-like, cinematic, no text.",
        "items": items,
        "repo_of_day": None,
    }


def main(dry_run: bool = False) -> None:
    today = date.today().isoformat()
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    print(f"[{today}] Pheme Weekly — starting")

    DATA_DIR.mkdir(exist_ok=True)
    picks, raw_pick_count = _collect_picks()
    print(f"  Found {len(picks)} resolvable picks ({raw_pick_count} total ⭐) this week (need {WEEKLY_MIN_PICKS})")

    if len(picks) >= WEEKLY_MIN_PICKS:
        print(f"  Using {len(picks)} picks for digest")
        newsletter = _build_weekly_newsletter(picks, "starred picks")
    else:
        print(f"  Not enough picks — falling back to fresh curation ({WEEKLY_FALLBACK_ITEMS} items)")
        if provider == "local":
            ensure_model_loaded()
        items = fetch_all()[:WEEKLY_FALLBACK_ITEMS * 3]
        github_repos = fetch_github_repos()
        newsletter = curate(items, github_repos, max_items=WEEKLY_FALLBACK_ITEMS)
        if provider == "local":
            unload_model()

    selected = len(newsletter.get("items", []))
    print(f"  Digest has {selected} items")

    if dry_run:
        print("\n--- DRY RUN: weekly JSON ---")
        print(json.dumps(newsletter, indent=2))
        print("--- end ---")
        return

    print("  Generating header image...")
    try:
        image_bytes = generate_header_image(newsletter["image_prompt"])
        print(f"  Header image ready ({len(image_bytes) // 1024} KB)")
    except Exception as e:
        print(f"  Header image failed ({e}) — continuing without")
        image_bytes = None

    recipient = os.environ.get("RESEND_TO_WEEKLY", os.environ.get("RESEND_TO", "elterry1@gmail.com"))
    print(f"  Sending weekly digest to {recipient}...")
    send_newsletter(
        newsletter,
        image_bytes=image_bytes,
        readme_bytes=None,
        recipient=recipient,
        subject_prefix="Pheme Weekly",
        show_actions=False,
    )
    print(f"[{today}] Weekly done.")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
