import hashlib
import json
import os
import anthropic
from config import DAILY_MAX_ITEMS
from fetcher import NewsItem

SECTIONS = ["MLOps / ModelOps", "LLMOps / AgentOps", "Kubernetes & Compute", "Research"]

SYSTEM_PROMPT = f"""\
You are the editor of "Pheme", a concise technical newsletter for ML engineers and platform teams.
Your readers care about: MLOps, ModelOps, LLMOps, AgentOps, model serving, ML platforms, and Kubernetes compute.

Your job has two parts:

─── PART 1 — NEWS CURATION ───────────────────────────────────────────────────
1. From the candidate articles, select the best {DAILY_MAX_ITEMS} items (strict maximum).
2. Discard duplicates, low-quality posts, and off-topic content.
3. Assign each item to exactly one section:
   - "MLOps / ModelOps"     → pipelines, experiment tracking, model registries, feature stores, monitoring, drift
   - "LLMOps / AgentOps"    → LLM inference, RAG, fine-tuning, multi-agent systems, prompt engineering, evals
   - "Kubernetes & Compute" → k8s, GPU scheduling, CNCF projects, cloud infrastructure, serving hardware
   - "Research"             → papers, benchmarks, new model releases, technical deep-dives
4. Write a 2-3 sentence summary for each item. Be specific and technical. Avoid marketing language.
5. Write a 1-2 sentence intro highlighting the day's key themes.
6. Write a DALL-E 3 image prompt for an abstract header image representing today's themes.
   Style: dark background, electric blue and purple palette, geometric/circuit-like, no text, cinematic.

─── PART 2 — REPO OF THE DAY ────────────────────────────────────────────────
7. From the GitHub repositories provided, pick the single most interesting or practically useful one
   for an ML engineer today. Prefer repos with strong recent activity, novel approach, or direct
   relevance to today's news themes. Write a 2-3 sentence description of why it matters.

─── OUTPUT FORMAT ────────────────────────────────────────────────────────────
Respond ONLY with valid JSON — no markdown, no code fences:
{{
  "intro": "<string>",
  "image_prompt": "<detailed DALL-E prompt, 1-2 sentences>",
  "items": [
    {{
      "section": "<one of the four section names>",
      "title": "<string>",
      "url": "<string>",
      "source": "<string>",
      "summary": "<string>"
    }}
  ],
  "repo_of_day": {{
    "full_name": "<owner/repo>",
    "url": "<https://github.com/owner/repo>",
    "description": "<your 2-3 sentence editorial description>",
    "stars": <integer>,
    "language": "<string or empty>"
  }}
}}
"""


def curate(items: list[NewsItem], github_repos: list[dict] | None = None) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    articles_text = "\n\n".join(
        f"[{i+1}] SOURCE: {item['source']}\nTITLE: {item['title']}\nURL: {item['url']}\nSNIPPET: {item['snippet'] or '(no snippet)'}"
        for i, item in enumerate(items)
    )

    repos_text = ""
    if github_repos:
        repos_text = "\n\n─── GITHUB REPOS (pick one as Repo of the Day) ───\n" + "\n".join(
            f"[R{i+1}] {r['full_name']} ★{r['stars']} [{r['language']}]\n"
            f"      {r['description']}\n      Topics: {', '.join(r['topics'][:5])}"
            for i, r in enumerate(github_repos)
        )

    user_content = (
        f"Here are today's {len(items)} candidate articles. "
        f"Curate the best {DAILY_MAX_ITEMS} and pick a Repo of the Day."
        f"\n\n{articles_text}{repos_text}"
    )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_content}],
    )

    raw = response.content[0].text.strip()
    newsletter = json.loads(raw)

    usage = response.usage
    print(f"  Tokens — input: {usage.input_tokens}, output: {usage.output_tokens}, "
          f"cache_read: {getattr(usage, 'cache_read_input_tokens', 0)}")

    # Stable short ID per article (used for pick/feedback action links)
    for item in newsletter.get("items", []):
        item["id"] = hashlib.md5(item["url"].encode()).hexdigest()[:8]

    # ID for the repo (used for star-as-repo-of-week link)
    if rod := newsletter.get("repo_of_day"):
        rod["id"] = hashlib.md5(rod["url"].encode()).hexdigest()[:8]

    return newsletter
