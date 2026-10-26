<div align="center">
  <img src="assets/pheme-logo.png" width="180" alt="Pheme">
</div>

# Pheme

> *In Greek mythology, Pheme was the goddess of fame, rumor, and news — with a hundred eyes, a hundred ears, and a hundred mouths, she spread word of events across the world.*

**Pheme** is an MLOps news agent that emails you a short daily briefing on MLOps, LLMOps, AgentOps, ModelOps, and Kubernetes compute — plus a GitHub "Repo of the Day" and an AI-generated header image.

- **Daily**: 4 curated stories across the sections, 1–3 Substack picks in **News**, and a Repo of the Day, sent to you, powered by Claude (or a local model) + DALL-E 3
- **Weekly**: a digest of the stories you starred during the week
- **Feedback**: ⭐ / 👍 / 👎 links in each email are recorded by a small local server
- **Local mode**: run the curation on a Mac (Apple Silicon) with LM Studio — zero API cost

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         Daily (launchd)                          │
│                                                                  │
│  fetcher.py ──► processor.py ──► image_gen.py ──► mailer.py      │
│  RSS + HN       Claude or        DALL-E 3          Resend        │
│  + Reddit       LM Studio        header image      → RESEND_TO   │
│  + GitHub       pick 4 stories                                   │
│  + Substack     + 1–3 News      repo_screenshot.py               │
│                 + Repo of the Day  README image                  │
│                      │                                           │
│                      ├──► data/YYYY-MM-DD.json                   │
│                      ├──► repo_history.py (30-day no-repeat)     │
│                      └──► news_history.py (30-day no-repeat)     │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                     Background (optional)                        │
│                                                                  │
│  server.py  :8765                                                │
│  ├─ /pick?id=...      ──► data/picks.json                        │
│  ├─ /feedback?id=...  ──► data/feedback.json                     │
│  └─ /health                                                      │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                     Weekly (run manually)                        │
│                                                                  │
│  weekly.py                                                       │
│  └─ reads picks.json                                             │
│     ├─ ≥5 picks → up to 20 starred items                         │
│     └─ <5 picks → fetch fresh news, curate 12                    │
│     → Resend → RESEND_TO_WEEKLY (or RESEND_TO)                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## How it works

### Daily flow (`main.py`)

1. **Fetch** — `fetcher.py` collects the last 24 hours from:
   - 6 RSS feeds: MLOps Community, The New Stack, Kubernetes Blog, CNCF, DeepLearning.AI, Hugging Face
   - Hacker News Algolia API (6 topic queries)
   - Reddit: `r/mlops`, `r/MachineLearning`, `r/kubernetes`, `r/LocalLLaMA`
   - GitHub: recently active repos on MLOps/LLMOps topics (candidates for Repo of the Day)
   - Substack: the last 7 days from 14 newsletters (up to 3 recent posts each), listed in `SUBSTACK_FEEDS` in `fetcher.py` — 7 in English (Latent Space, Interconnects, Ahead of AI, Gradient Flow, SemiAnalysis, The Sequence, Anthony Maio) and 7 in Spanish
2. **Pre-filter** — keyword matching removes off-topic items; the top 12 candidates go to the model. Repos and Substack posts featured in the last 30 days are excluded. Substack posts skip the keyword filter (they're hand-picked sources).
3. **Curate** — one LLM call selects 4 stories, assigns each to a section, picks 1–3 Substack posts for **News** (summarized in English, even when the post is in Spanish), writes 2–3 sentence summaries, picks the Repo of the Day, and writes an image prompt
4. **Generate image** — `image_gen.py` calls DALL-E 3 and resizes to a 640×320 JPEG (skipped with `IMAGE_PROVIDER=none`)
5. **Screenshot** — `repo_screenshot.py` renders the Repo of the Day's README with headless Chromium
6. **Send** — HTML email with inline images delivered via Resend to `RESEND_TO`
7. **Archive** — full JSON saved to `data/YYYY-MM-DD.json` (used by the weekly digest)

Sections: **MLOps / ModelOps**, **LLMOps / AgentOps**, **Kubernetes & Compute**, **Research**, **News** (Substack).

To add or remove a Substack, edit `SUBSTACK_FEEDS` in `fetcher.py` — every publication has a feed at `<publication URL>/feed`. Paid posts only expose their free preview, so the summary is based on that.

Each email contains per-item links (handled by the background server):
- ⭐ **Save for weekly** — marks the story for the weekly digest
- 👍 / 👎 — feedback signals, stored in `data/feedback.json`

### Weekly digest (`weekly.py`)

```
picks = starred items from the past 7 days

if len(picks) >= 5:          # curated mode
    send up to 20 starred items
else:                        # fallback mode
    fetch fresh news and curate 12 items
```

---

## Post limits

Configured in `config.py`:

| Constant | Default | Meaning |
|--|--|--|
| `DAILY_CANDIDATE_ITEMS` | 12 | Candidate articles sent to the model |
| `DAILY_MAX_ITEMS` | 4 | Stories per daily newsletter (not counting News) |
| `NEWS_MIN_ITEMS` / `NEWS_MAX_ITEMS` | 1 / 3 | Substack posts in the News section |
| `NEWS_LOOKBACK_DAYS` | 7 | How far back to look for Substack posts |
| `WEEKLY_MAX_ITEMS` | 20 | Max stories in a curated weekly (≥5 picks) |
| `WEEKLY_FALLBACK_ITEMS` | 12 | Stories when fallback triggers (<5 picks) |
| `WEEKLY_MIN_PICKS` | 5 | Star threshold before fallback kicks in |

---

## Project structure

```
pheme/
├── main.py              # Daily orchestrator
├── fetcher.py           # News sources (RSS, HN, Reddit, GitHub, Substack)
├── processor.py         # LLM curation (Claude or LM Studio) + image prompt
├── image_gen.py         # DALL-E 3 header image generation
├── repo_screenshot.py   # README screenshot for the Repo of the Day
├── repo_history.py      # 30-day exclusion so Repo of the Day doesn't repeat
├── news_history.py      # 30-day exclusion so a Substack post isn't featured twice
├── mailer.py            # HTML rendering + Resend send (inline images)
├── config.py            # Post limits and tunable constants
├── server.py            # Background server (:8765) for picks/feedback
├── weekly.py            # Weekly digest
├── templates/daily.html # Email template
├── assets/              # Logo
│
├── data/                # Runtime data (gitignored)
│   ├── YYYY-MM-DD.json  # Daily newsletter archives
│   ├── picks.json       # Stories starred for the weekly digest
│   └── feedback.json    # Thumbs up/down log
│
├── com.mlops.daily.plist    # macOS launchd: daily schedule
├── .env                 # Your settings and secrets (gitignored)
├── .env.example         # Reference template
└── requirements.txt
```

---

## Setup

### 1. Install dependencies

```bash
git clone https://github.com/pabloesc/pheme ~/pheme
cd ~/pheme
python3.12 -m venv .venv          # or: uv venv --python 3.12 .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium       # for the README screenshot
```

### 2. Configure `.env`

```bash
cp .env.example .env
```

| Variable | Where to get it | Required for |
|--|--|--|
| `RESEND_API_KEY` | [resend.com/api-keys](https://resend.com/api-keys) | Email delivery |
| `RESEND_FROM` | Your verified sender (or `onboarding@resend.dev` sandbox) | Daily email |
| `RESEND_TO` | Your email address | Daily email recipient |
| `RESEND_TO_WEEKLY` | Optional — defaults to `RESEND_TO` | Weekly email recipient |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) | Curation (cloud mode) |
| `OPENAI_API_KEY` | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) | Header image |
| `IMAGE_PROVIDER` | `openai` (default) or `none` | Skip the header image |
| `GITHUB_TOKEN` | [github.com/settings/tokens](https://github.com/settings/tokens) — no scopes | Optional, raises GitHub rate limit |

`.env` is gitignored, so your email address and keys stay on your machine.

> With Resend's sandbox sender (`onboarding@resend.dev`), mail is only delivered to the address on your own Resend account. To send to anyone else, verify a domain at [resend.com/domains](https://resend.com/domains).

### 3. Test the daily

```bash
# Dry run — fetch + curate, prints JSON. No image, no screenshot, no email.
python main.py --dry-run

# Test mode — trims input to 3 articles and 2 repos for a fast run
python main.py --dry-run --test

# Full run — generates image and sends to RESEND_TO
python main.py
```

### 4. Start the background server (optional)

```bash
python server.py
# Listening on http://localhost:8765
```

The server must be running for ⭐/👍/👎 links in your email to register.

### 5. Schedule with launchd (macOS)

`com.mlops.daily.plist` runs `run_daily.sh` every day at 06:00 local time. Edit the paths and time to match your machine, then:

```bash
mkdir -p ~/Library/LaunchAgents
cp com.mlops.daily.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.mlops.daily.plist
```

- If the Mac is asleep at the scheduled time, launchd runs the job when it wakes. `run_daily.sh` then waits up to ~3 minutes for the network and LM Studio before starting.
- If the Mac is shut down at the scheduled time, that day's run is skipped.
- Logs go to `newsletter.log` in the repo folder.

---

## Cost (cloud mode)

- **Curation**: one Claude call per day — a few cents with ~12 candidate articles
- **Header image**: one DALL-E 3 image (1792×1024, standard) per day — see [OpenAI pricing](https://openai.com/api/pricing/); set `IMAGE_PROVIDER=none` to skip
- **Email**: Resend's free tier covers 3,000 emails/month

---

## Running locally on a Mac — zero API cost

On Apple Silicon, LM Studio can run an open model that replaces Claude for curation. Unified memory lets a 48 GB Mac hold models that would need a large server GPU elsewhere.

### Step 1 — Install LM Studio

Download from [lmstudio.ai](https://lmstudio.ai) (free). It exposes an **OpenAI-compatible API**, by default at `http://localhost:1234/v1`. Start the server from the **Developer / Local Server** tab and download a model from **Discover**.

Model guidance: pick the largest instruction-tuned model that fits comfortably in memory. Pheme forces JSON output with a schema, so mid-size models (~30B) work well. Example: `qwen/qwen3.6-35b-a3b` on an M5 Pro with 48 GB.

### Step 2 — Configure `.env` for local mode

```env
LLM_PROVIDER=local                  # anthropic | local
LLM_BASE_URL=http://localhost:1234/v1  # use the port shown in LM Studio
LLM_MODEL=qwen/qwen3.6-35b-a3b      # must match the model id in LM Studio
LLM_CONTEXT_LENGTH=32768            # used if Pheme has to load the model
LLM_MAX_TOKENS=16384                # reasoning tokens count toward this
LLM_UNLOAD_AFTER=false              # true = unload the model after each run
IMAGE_PROVIDER=none                 # no local image model yet
```

Before curating, Pheme makes sure LM Studio is ready, using its `lms` CLI (found automatically in `~/.lmstudio/bin`, or set `LMS_PATH`):
- if the server isn't running, it starts it
- if no model is loaded, it loads `LLM_MODEL`
- it leaves the model loaded afterwards, unless `LLM_UNLOAD_AFTER=true`

Text-only and multimodal ("vlm") models both work.

There is no automatic fallback: if `LLM_PROVIDER=local` and LM Studio isn't reachable, the run fails.

### Step 3 — Start LM Studio at login

In LM Studio → **Settings**, enable starting at login and starting the server on launch, so the API is ready when the launchd job fires.

---

## Roadmap

Ideas not implemented yet:
- **Self-improvement**: a weekly `refine.py` that reads 👍/👎 feedback and proposes changes to keywords, feeds and the curation prompt for approval
- **Team weekly**: send the weekly to a Resend Audience with subscriber management
- **Local header image**: FLUX / SDXL via `diffusers` instead of DALL-E 3
