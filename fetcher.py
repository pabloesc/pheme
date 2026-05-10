import os
import feedparser
import requests
import time
from datetime import datetime, timedelta, timezone
from typing import TypedDict


class NewsItem(TypedDict):
    title: str
    url: str
    source: str
    snippet: str


RSS_FEEDS = [
    ("MLOps Community",      "https://mlops.community/feed/"),
    ("The New Stack",        "https://thenewstack.io/feed/"),
    ("Kubernetes Blog",      "https://kubernetes.io/feed.xml"),
    ("CNCF Blog",            "https://www.cncf.io/feed/"),
    ("DeepLearning.AI Batch","https://www.deeplearning.ai/the-batch/feed/"),
    ("Hugging Face Blog",    "https://huggingface.co/blog/feed.xml"),
]

KEYWORDS = {
    "mlops", "modelops", "llmops", "agentops", "agent ops",
    "kubernetes", " k8s", "model serving", "ml platform", "mlflow",
    "kubeflow", "ray serve", "triton", "vllm", "ollama",
    "llm", "inference", "gpu cluster", "model deployment",
    "feature store", "model registry", "data drift", "model monitoring",
    "rag", "retrieval augmented", "fine-tun", "lora", "rlhf",
    "multi-agent", "agentic", "ai agent", "workflow orchestrat",
}

REDDIT_SUBS = ["mlops", "MachineLearning", "kubernetes", "LocalLLaMA"]
HN_QUERIES  = ["mlops", "llmops", "kubernetes ml", "model serving", "llm inference", "ai agents"]


def _keyword_match(text: str) -> bool:
    low = text.lower()
    return any(kw in low for kw in KEYWORDS)


def _truncate(text: str, max_chars: int = 300) -> str:
    text = " ".join(text.split())
    return text[:max_chars] + "…" if len(text) > max_chars else text


def _entry_published(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def fetch_rss(cutoff_hours: int = 24) -> list[NewsItem]:
    cutoff = datetime.now(timezone.utc).timestamp() - cutoff_hours * 3600
    items: list[NewsItem] = []

    for source, url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url, request_headers={"User-Agent": "newsletter-bot/1.0"})
            for entry in feed.entries:
                pub = _entry_published(entry)
                if pub and pub.timestamp() < cutoff:
                    continue
                title   = entry.get("title", "").strip()
                link    = entry.get("link", "").strip()
                summary = entry.get("summary", entry.get("description", "")).strip()
                snippet = _truncate(feedparser.HTMLSanitizer(summary, "utf-8").output if hasattr(feedparser, "HTMLSanitizer") else summary)

                if not title or not link:
                    continue
                if not _keyword_match(title + " " + snippet):
                    continue

                items.append({"title": title, "url": link, "source": source, "snippet": snippet})
        except Exception:
            pass

    return items


def fetch_hackernews(cutoff_hours: int = 24) -> list[NewsItem]:
    cutoff_ts = int(time.time()) - cutoff_hours * 3600
    items: list[NewsItem] = []
    seen: set[int] = set()

    for query in HN_QUERIES:
        try:
            resp = requests.get(
                "https://hn.algolia.com/api/v1/search_by_date",
                params={"query": query, "tags": "story", "numericFilters": f"created_at_i>{cutoff_ts}", "hitsPerPage": 20},
                timeout=10,
            )
            for hit in resp.json().get("hits", []):
                oid = hit.get("objectID")
                if oid in seen:
                    continue
                seen.add(oid)
                title = hit.get("title", "").strip()
                url   = hit.get("url") or f"https://news.ycombinator.com/item?id={oid}"
                if not title:
                    continue
                items.append({"title": title, "url": url, "source": "Hacker News", "snippet": ""})
        except Exception:
            pass

    return items


def fetch_reddit(cutoff_hours: int = 24) -> list[NewsItem]:
    cutoff_ts = time.time() - cutoff_hours * 3600
    items: list[NewsItem] = []
    headers = {"User-Agent": "newsletter-bot/1.0"}

    for sub in REDDIT_SUBS:
        try:
            resp = requests.get(
                f"https://www.reddit.com/r/{sub}/top.json",
                params={"t": "day", "limit": 15},
                headers=headers,
                timeout=10,
            )
            for child in resp.json().get("data", {}).get("children", []):
                post = child["data"]
                if post.get("created_utc", 0) < cutoff_ts:
                    continue
                title   = post.get("title", "").strip()
                url     = post.get("url", "").strip()
                snippet = _truncate(post.get("selftext", ""))

                if not title or not _keyword_match(title + " " + snippet):
                    continue
                items.append({"title": title, "url": url, "source": f"r/{sub}", "snippet": snippet})
        except Exception:
            pass

    return items


_GITHUB_TOPICS = [
    "mlops", "llmops", "llm-inference", "model-serving",
    "kubeflow", "ray-serve", "llm-agent", "kubernetes-ai",
]


def fetch_github_repos(cutoff_days: int = 3) -> list[dict]:
    """Return recently active GitHub repos for relevant topics, sorted by stars."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "pheme-bot/1.0"}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"

    cutoff = (datetime.now(timezone.utc) - timedelta(days=cutoff_days)).strftime("%Y-%m-%d")
    repos: list[dict] = []
    seen:  set[str]   = set()

    for topic in _GITHUB_TOPICS:
        try:
            resp = requests.get(
                "https://api.github.com/search/repositories",
                params={"q": f"topic:{topic} pushed:>{cutoff}", "sort": "stars", "order": "desc", "per_page": 5},
                headers=headers,
                timeout=10,
            )
            if resp.status_code != 200:
                continue
            for r in resp.json().get("items", []):
                fn = r["full_name"]
                if fn in seen:
                    continue
                seen.add(fn)
                repos.append({
                    "full_name":   fn,
                    "description": (r.get("description") or "").strip(),
                    "stars":       r["stargazers_count"],
                    "language":    r.get("language") or "",
                    "url":         r["html_url"],
                    "topics":      r.get("topics", []),
                })
        except Exception:
            pass

    return sorted(repos, key=lambda r: r["stars"], reverse=True)[:15]


def fetch_all(cutoff_hours: int = 24) -> list[NewsItem]:
    items = fetch_rss(cutoff_hours) + fetch_hackernews(cutoff_hours) + fetch_reddit(cutoff_hours)

    seen: set[str] = set()
    unique: list[NewsItem] = []
    for item in items:
        key = item["url"].rstrip("/").lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique
