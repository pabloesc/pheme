# Pheme

> *In Greek mythology, Pheme was the goddess of fame, rumor, and news — with a hundred eyes, a hundred ears, and a hundred mouths, she spread word of events across the world.*

**Pheme** is a self-improving MLOps news agent that curates daily briefings and weekly digests covering MLOps, LLMOps, AgentOps, ModelOps, and Kubernetes compute — delivered straight to your inbox, with a unique AI-generated header image every day.

- **Daily**: a curated briefing (max 12 stories) sent to you alone, powered by Claude + DALL-E 3
- **Weekly**: a hand-picked digest sent to your whole team via Resend Audiences (5–150 people)
- **Self-improving**: your 👍/👎 feedback trains the curation prompt and keyword filters over time

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Daily (8am)                          │
│                                                             │
│  fetcher.py ──► processor.py ──► image_gen.py ──► mailer.py │
│  RSS + HN       Claude API       DALL-E 3          Resend   │
│  + Reddit       curate 12        header image    → you only │
│  ~60 items      + image prompt                              │
│                      │                                      │
│                      └──► data/history/YYYY-MM-DD.json      │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                 Background (always on)                      │
│                                                             │
│  server.py  :8765                                           │
│  ├─ /pick?id=...      ──► data/picks.json                   │
│  ├─ /feedback?id=...  ──► data/feedback.json                │
│  └─ /health                                                 │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                     Sunday (9am)                            │
│                                                             │
│  refine.py                                                  │
│  └─ reads feedback.json → Claude → proposes changes         │
│     to keywords + curation prompt → shows diff              │
│     → applies on approval                                   │
│                                                             │
│  weekly.py                                                  │
│  └─ reads picks.json                                        │
│     ├─ ≥5 picks → max 20 items → curated digest            │
│     └─ <5 picks → max 12 items → auto-fill from history    │
│     → Resend Broadcast → Audience (team)                    │
└─────────────────────────────────────────────────────────────┘
```

---

## How it works

### Daily flow

1. **Fetch** — `fetcher.py` collects the last 24 hours from:
   - 6 RSS feeds: MLOps Community, The New Stack, Kubernetes Blog, CNCF, DeepLearning.AI, Hugging Face
   - Hacker News Algolia API (6 topic queries)
   - Reddit: `r/mlops`, `r/MachineLearning`, `r/kubernetes`, `r/LocalLLaMA`
2. **Pre-filter** — keyword matching removes off-topic items before touching any paid API
3. **Curate** — a single Claude `claude-sonnet-4-6` call (system prompt cached) selects up to 12 items, assigns sections, writes 2–3 sentence summaries, and generates a DALL-E image prompt
4. **Generate image** — `image_gen.py` calls DALL-E 3 with the prompt, downloads and resizes to 640×320 JPEG
5. **Send** — HTML email with inline header image delivered via Resend
6. **Archive** — full JSON saved to `data/history/YYYY-MM-DD.json`

Each email contains per-item links (handled by the background server):
- ⭐ **Save for weekly** — marks the story for Sunday's team digest
- 👍 / 👎 — feedback signals used to improve curation over time

### Weekly digest & fallback logic

`weekly.py` runs every Sunday morning with this logic:

```
picks = load starred items from the week

if len(picks) >= 5:          # curated mode
    send up to 20 items
    intro: "X editor picks this week"
else:                        # fallback mode
    take all picks (however few)
    fill remainder from history JSONs (highest-ranked daily items, deduplicated)
    cap at 12 total items
    intro: "X editor picks + Y top stories from the week"
```

Fallback items are taken in daily-rank order (Claude's implicit ranking within each day's newsletter).

### Feedback loop (Sundays)

`refine.py` reads a week of 👍/👎 signals and asks Claude to propose:
- Changes to `KEYWORDS` in `fetcher.py` (add/remove/adjust)
- Changes to `RSS_FEEDS` (add sources that perform well, drop noisy ones)
- Updates to the curation system prompt in `processor.py`

You review the diff in your terminal and approve or reject. Nothing is applied automatically.

---

## Post limits

Configured in `config.py`:

| Constant | Default | Meaning |
|--|--|--|
| `DAILY_MAX_ITEMS` | 12 | Max stories per daily newsletter |
| `WEEKLY_MAX_ITEMS` | 20 | Max stories in a curated weekly (≥5 picks) |
| `WEEKLY_FALLBACK_ITEMS` | 12 | Max stories when fallback triggers (<5 picks) |
| `WEEKLY_MIN_PICKS` | 5 | Star threshold before fallback kicks in |

---

## Project structure

```
newsletter-agent/
├── main.py              # Daily orchestrator
├── fetcher.py           # News sources (RSS, HN, Reddit)
├── processor.py         # Claude API curation + image prompt
├── image_gen.py         # DALL-E 3 header image generation
├── mailer.py            # HTML rendering + Resend send (inline image)
├── config.py            # Post limits and tunable constants
├── server.py            # Background server (:8765) for picks/feedback
├── weekly.py            # Weekly digest compiler + Resend Broadcast
├── refine.py            # Feedback analysis + self-improvement
├── subscribers.py       # CLI for managing team subscriber list
│
├── data/
│   ├── history/         # Daily newsletter archives (YYYY-MM-DD.json)
│   ├── picks.json       # Stories starred for the weekly digest
│   └── feedback.json    # Thumbs up/down log
│
├── com.mlops.daily.plist    # macOS launchd: daily at 8am
├── com.mlops.server.plist   # macOS launchd: background server (always on)
├── com.mlops.weekly.plist   # macOS launchd: Sunday at 9am
│
├── .env                 # Your secrets (gitignored)
├── .env.example         # Reference template
└── requirements.txt
```

---

## Configuration

### 1. Install dependencies

```bash
cd ~/newsletter-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Set up secrets

```bash
cp .env.example .env
```

Edit `.env` — required keys:

| Variable | Where to get it | Required for |
|--|--|--|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) | Daily curation |
| `OPENAI_API_KEY` | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) | Header image |
| `RESEND_API_KEY` | [resend.com/api-keys](https://resend.com/api-keys) | Email delivery |
| `RESEND_FROM` | Your verified sender | Daily email |
| `RESEND_FROM_WEEKLY` | Verified domain (see below) | Weekly email to team |
| `RESEND_AUDIENCE_ID` | Created via `subscribers.py init` | Weekly recipients |

### 3. Image generation (DALL-E 3)

Each newsletter gets a unique abstract header image generated by DALL-E 3. Claude writes the prompt based on the day's themes; `image_gen.py` calls DALL-E 3, downloads the result, and resizes it to a newsletter-friendly 640×320 JPEG embedded directly in the email (no external hosting needed).

**Cost**: $0.04 per image → ~$1.20/month for a daily newsletter.

To disable image generation (e.g. to save cost during testing), run:
```bash
python main.py --dry-run   # skips image + email entirely
```
Or remove `OPENAI_API_KEY` from `.env` — Pheme will fall back gracefully and send the newsletter without an image.

### 4. Test the daily

```bash
# Dry run — no email, no image API call, prints JSON
python main.py --dry-run

# Full run — generates image and sends to your inbox
python main.py
```

### 5. Start the background server

```bash
python server.py
# Listening on http://localhost:8765
```

The server must be running for ⭐/👍/👎 links in your email to register. It's started automatically by launchd once configured.

### 6. Schedule with launchd (macOS)

```bash
# Daily newsletter at 8am
cp com.mlops.daily.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.mlops.daily.plist

# Background pick/feedback server (always on)
cp com.mlops.server.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.mlops.server.plist

# Sunday weekly digest at 9am
cp com.mlops.weekly.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.mlops.weekly.plist
```

Logs: `~/newsletter-agent/newsletter.log`

---

## Subscriber management

Pheme uses **Resend Audiences** for the weekly digest — proper mailing list infrastructure with per-recipient unsubscribe links. `data/subscribers.json` is the local source of truth, kept in sync with Resend automatically.

### First-time setup

```bash
# Creates the Audience in Resend and writes RESEND_AUDIENCE_ID to .env
python subscribers.py init
```

### Managing team members

```bash
python subscribers.py add "Alice <alice@yourcompany.com>"
python subscribers.py add alice@yourcompany.com
python subscribers.py remove alice@yourcompany.com
python subscribers.py list
```

Each command updates `data/subscribers.json` and calls the Resend Contacts API immediately.

### Unsubscribes

When a team member clicks "Unsubscribe" in a weekly email, Resend marks them inactive. `subscribers.py list` shows status. To re-add, use `subscribers.py add` again.

### Scale & cost

Resend's free tier covers 3,000 emails/month. At one weekly send:

| Team size | Emails/month | Tier |
|--|--|--|
| 5 people | 20 | Free |
| 50 people | 200 | Free |
| 150 people | 600 | Free |

---

## Domain setup for the weekly

The daily email works with Resend's sandbox (`onboarding@resend.dev`) — but sandbox delivery is restricted to your own verified email and won't reach teammates.

To send the weekly to your team:

1. Go to [resend.com/domains](https://resend.com/domains) → **Add domain**
2. Add the DNS records shown (propagates in ~5 minutes)
3. Update `.env`: `RESEND_FROM_WEEKLY=Pheme Weekly <weekly@yourdomain.com>`
4. Run `python subscribers.py init` to create the Audience and populate `RESEND_AUDIENCE_ID`

Until `RESEND_FROM_WEEKLY` is set, `weekly.py` compiles and prints the digest locally with a clear message — no emails sent.

---

## Token usage & cost

| | Tokens | Cost/day |
|--|--|--|
| Claude input (system prompt cached) | ~20,000 | ~$0.060 |
| Claude output | ~6,500 | ~$0.098 |
| DALL-E 3 image | 1 image | $0.040 |
| **Total** | | **~$0.20/day** |
| **Monthly** | | **~$6.00/month** |

System prompt caching reduces Claude input cost ~10–15% after the first run each day.

---

## Self-improvement

Every Sunday before sending the weekly, `refine.py` runs automatically:

```
Analyzing 7 days of feedback (42 👍, 18 👎)...

Proposed changes:
  fetcher.py — add source: "Chip Huyen's Newsletter" (3 starred items this week)
  fetcher.py — remove keyword: "quantum" (0 hits, 0 starred)
  processor.py — system prompt: deprioritize vendor blog posts unless technically deep

Apply changes? [y/N/partial]
```

Type `y` to apply all, `n` to skip, or `partial` to review each change individually.
