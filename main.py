#!/usr/bin/env python3
"""
Pheme — daily MLOps newsletter agent.
Run manually:  python main.py
Dry-run:       python main.py --dry-run   (no email, no external API calls beyond Claude)
Test mode:     python main.py --test      (3 articles, 2 repos, fast model output)
"""
import os
import sys
from datetime import date
from dotenv import load_dotenv

load_dotenv()

from fetcher import fetch_all, fetch_github_repos
from processor import curate, ensure_model_loaded, unload_model
from config import DAILY_CANDIDATE_ITEMS
from image_gen import generate_header_image
from repo_screenshot import screenshot_readme
from mailer import send_newsletter


def main(dry_run: bool = False, test_mode: bool = False) -> None:
    today = date.today().isoformat()
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    print(f"[{today}] Pheme — starting{'  [TEST MODE]' if test_mode else ''}")

    print("  Fetching news...")
    items = fetch_all()
    print(f"  Fetched {len(items)} candidate articles")

    print("  Fetching GitHub repos...")
    github_repos = fetch_github_repos()
    print(f"  Fetched {len(github_repos)} candidate repos")

    items = items[:DAILY_CANDIDATE_ITEMS]
    print(f"  Using top {len(items)} candidates")

    if test_mode:
        items = items[:3]
        github_repos = (github_repos or [])[:2]
        print(f"  [test] Trimmed to {len(items)} articles, {len(github_repos)} repos")

    if not items:
        print("  No articles found — skipping.")
        return

    if provider == "local":
        ensure_model_loaded()

    print("  Curating with Claude...")
    newsletter = curate(items, github_repos)

    if provider == "local":
        unload_model()
    selected  = len(newsletter.get("items", []))
    sections  = len({i["section"] for i in newsletter["items"]})
    repo      = newsletter.get("repo_of_day")
    print(f"  Selected {selected} items across {sections} sections")
    if repo:
        print(f"  Repo of the Day: {repo['full_name']}")

    if dry_run:
        import json
        print("\n--- DRY RUN: newsletter JSON ---")
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

    readme_bytes = None
    if repo:
        print(f"  Screenshotting README for {repo['full_name']}...")
        readme_bytes = screenshot_readme(repo["full_name"])
        if readme_bytes:
            print(f"  README screenshot ready ({len(readme_bytes) // 1024} KB)")
        else:
            print("  README screenshot unavailable — continuing without")

    print("  Sending email...")
    send_newsletter(newsletter, image_bytes=image_bytes, readme_bytes=readme_bytes)
    print(f"[{today}] Done.")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv, test_mode="--test" in sys.argv)
