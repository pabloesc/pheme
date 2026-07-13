from __future__ import annotations
import hashlib
import json
import os
import subprocess
import time
import anthropic
import httpx
import openai
import requests
from config import DAILY_MAX_ITEMS
from fetcher import NewsItem

_LMS = "/Applications/LM Studio.app/Contents/Resources/app/.webpack/lms"
_LMS_API = "http://localhost:1234"


def _lms_loaded_model() -> str | None:
    """Return the identifier of the currently loaded LLM, or None."""
    try:
        data = requests.get(f"{_LMS_API}/api/v0/models", timeout=5).json()
        for m in data.get("data", []):
            if m.get("type") == "llm" and m.get("state") == "loaded":
                return m["id"]
    except Exception:
        pass
    return None


def ensure_model_loaded(model_id: str | None = None) -> str:
    """Load the LLM into LM Studio if not already loaded. Returns the model identifier."""
    model_id = model_id or os.environ.get("LLM_MODEL", "qwen2.5-72b-instruct")
    loaded = _lms_loaded_model()
    if loaded:
        print(f"  [lms] Model already loaded: {loaded}")
        return loaded
    ctx = os.environ.get("LLM_CONTEXT_LENGTH", "8192")
    print(f"  [lms] Loading model {model_id} (context {ctx}) …")
    result = subprocess.run(
        [_LMS, "load", model_id, "-y", "--gpu", "max", "-c", ctx],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"lms load failed: {result.stderr.strip()}")
    # Wait until it appears as loaded
    for _ in range(60):
        if _lms_loaded_model():
            print(f"  [lms] Model loaded.")
            return model_id
        time.sleep(3)
    raise RuntimeError("Model did not become ready after load.")


def unload_model() -> None:
    """Unload the LLM from LM Studio to free memory."""
    if not _lms_loaded_model():
        return
    print("  [lms] Unloading model to free memory …")
    result = subprocess.run(
        [_LMS, "unload", "--all"],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode == 0:
        print("  [lms] Model unloaded.")
    else:
        print(f"  [lms] Unload warning: {result.stderr.strip()}")

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
   for an ML engineer today. Write a 2-3 sentence description of why it matters.

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
    "stars": 0,
    "language": "<string or empty>"
  }}
}}
"""


def _build_user_message(items: list[NewsItem], github_repos: list[dict] | None, max_items: int = DAILY_MAX_ITEMS) -> str:
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
    return (
        f"Here are today's {len(items)} candidate articles. "
        f"Curate the best {max_items} and pick a Repo of the Day."
        f"\n\n{articles_text}{repos_text}"
    )


def _add_ids(newsletter: dict) -> dict:
    for item in newsletter.get("items", []):
        item["id"] = hashlib.md5(item["url"].encode()).hexdigest()[:8]
    if rod := newsletter.get("repo_of_day"):
        rod["id"] = hashlib.md5(rod["url"].encode()).hexdigest()[:8]
    return newsletter


def _curate_anthropic(user_content: str) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_content}],
    )
    usage = response.usage
    print(f"  Tokens — input: {usage.input_tokens}, output: {usage.output_tokens}, "
          f"cache_read: {getattr(usage, 'cache_read_input_tokens', 0)}")
    return json.loads(response.content[0].text.strip())


_NEWSLETTER_SCHEMA = {
    "type": "object",
    "properties": {
        "intro":        {"type": "string"},
        "image_prompt": {"type": "string"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "section": {"type": "string", "enum": SECTIONS},
                    "title":   {"type": "string"},
                    "url":     {"type": "string"},
                    "source":  {"type": "string"},
                    "summary": {"type": "string"},
                },
                "required": ["section", "title", "url", "source", "summary"],
            },
        },
        "repo_of_day": {
            "type": "object",
            "properties": {
                "full_name":   {"type": "string"},
                "url":         {"type": "string"},
                "description": {"type": "string"},
                "stars":       {"type": "integer"},
                "language":    {"type": "string"},
            },
            "required": ["full_name", "url", "description", "stars", "language"],
        },
    },
    "required": ["intro", "image_prompt", "items", "repo_of_day"],
}


def _curate_local(user_content: str) -> dict:
    client = openai.OpenAI(
        base_url=os.environ.get("LLM_BASE_URL", "http://localhost:1234/v1"),
        api_key="lm-studio",
        timeout=httpx.Timeout(connect=30.0, read=1800.0, write=60.0, pool=10.0),
    )
    model = os.environ.get("LLM_MODEL", "qwen2.5-72b-instruct")
    # Stream tokens so httpx doesn't fire a read-timeout during the long prefill phase.
    # response_format with a JSON schema forces LM Studio into guided generation, so
    # smaller models can't produce structurally-broken JSON.
    chunks: list[str] = []
    prompt_tokens = completion_tokens = 0
    with client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ],
        max_tokens=int(os.environ.get("LLM_MAX_TOKENS", "4096")),
        temperature=0.3,
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "newsletter", "schema": _NEWSLETTER_SCHEMA, "strict": True},
        },
        stream=True,
        stream_options={"include_usage": True},
    ) as stream:
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                chunks.append(chunk.choices[0].delta.content)
            if hasattr(chunk, "usage") and chunk.usage:
                prompt_tokens = chunk.usage.prompt_tokens
                completion_tokens = chunk.usage.completion_tokens
    raw = "".join(chunks).strip()
    print(f"  Tokens — input: {prompt_tokens}, output: {completion_tokens}")
    # Strip markdown code fences the model sometimes adds despite instructions
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]          # drop opening ```json line
        raw = raw.rsplit("```", 1)[0].strip()  # drop closing ```
    return json.loads(raw)


def curate(items: list[NewsItem], github_repos: list[dict] | None = None, max_items: int | None = None) -> dict:
    user_content = _build_user_message(items, github_repos, max_items=max_items or DAILY_MAX_ITEMS)
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()

    print(f"  Provider: {provider}")
    if provider == "local":
        newsletter = _curate_local(user_content)
    else:
        newsletter = _curate_anthropic(user_content)

    return _add_ids(newsletter)
