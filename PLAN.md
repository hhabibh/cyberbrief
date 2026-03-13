# CyberBrief — Automated News Digest Bot

## Overview
Automated news digest bot that fetches cybersecurity/tech/geopolitical RSS feeds,
AI-summarizes top 5 articles into TLDRs, and delivers a formatted digest to Webex
(private space) and a public Telegram Channel on Mon/Wed/Fri.
Entirely free to run.

---

## Platforms
- **Webex** — primary delivery (private space, invite-only)
- **Telegram Channel** — public broadcast (anyone subscribes via shareable link)
- **WhatsApp** — excluded (no native group broadcast API)

---

## Send Schedule (UK time, BST/GMT aware)

| Day              | UK Time | Cron entries (UTC)                           |
|------------------|---------|----------------------------------------------|
| Monday–Friday    | 10:00   | `0 9 * * 1-5` (BST) and `0 10 * * 1-5` (GMT) |

Both cron entries run year-round. `main.py` checks the actual UK local time
(`pytz`, `Europe/London`) at startup and exits early if the hour doesn't match
the intended send time — so only one of the two daily triggers ever executes.

---

## LLM: Groq Free Tier
- **Model:** Llama 3.3 70B
- **Cost:** Free (1,000 requests/day limit — we use ~15/week)
- **Speed:** Extremely fast inference
- **Fallback:** Google Gemini Flash (also free) if Groq is unavailable
- Sign up at: https://console.groq.com

---

## News Sources

| Pillar                  | Region        | Sources                                                                 |
|-------------------------|---------------|-------------------------------------------------------------------------|
| Cybersecurity core      | Global        | CyberScoop, Bleeping Computer, Krebs on Security, SecurityAffairs, SC Magazine |
| Cybersecurity core      | EMEA          | NCSC UK, Infosecurity Magazine                                          |
| Cybersecurity core      | APAC/Global   | CyberNews (European HQ, global + APAC reporting)                       |
| Threat intelligence     | Global        | The Record (Recorded Future), The Register Security, Unit 42 (Palo Alto) |
| Threat intelligence     | APAC-aware    | The Record — strong Asia/China/Japan/SEA coverage                      |
| Geopolitical context    | Global        | SANS ISC                                                                |
| Tech / AI / Business    | Global        | Ars Technica Security, SecurityWeek                                     |

All sources use open/scraping-friendly RSS feeds. Sensationalist or bot-blocked
sources (Reuters, Wired, BBC, Guardian, TechCrunch) are excluded.
CISA ICS advisories removed — too US-centric and technically deep for this audience.

---

## Article Selection Logic
1. Fetch all RSS feeds, filter to articles published in the last 48–72 hours
2. Deduplicate against `sent_history.json`
3. Score by weighted keyword matching across three buckets:
   - **Cyber:** `breach, CVE, ransomware, vulnerability, exploit, APT, zero-day`
   - **Business/financial:** `stock, SEC, fine, regulation, M&A, compliance`
   - **Geopolitical:** `war, sanctions, nation-state, Ukraine, China, Iran, crypto`
4. Select top 5: ~3 cybersecurity + 1 tech/AI + 1 global/business impact

---

## Message Format

```
🔐 CyberBrief | Wednesday, 11 March

🌍 Context: [1-sentence world events framing]
━━━━━━━━━━━━━━━
📰 1. [Article Title]
🏷 Source: Bleeping Computer
TLDR: [2–3 sentence AI summary]
🔗 Read more → [URL]

📰 2–5. [same format]
━━━━━━━━━━━━━━━
⚡ 5 articles · ~4 min read
```

---

## Project File Structure

```
news-bot/
├── PLAN.md               # This file
├── main.py               # Orchestrator + timezone guard
├── sources.py            # RSS feed URL config
├── fetch_news.py         # Fetch, filter, deduplicate, score articles
├── summarize.py          # Groq TLDR + "Context This Week" generation
├── format_message.py     # Digest formatter (Webex Markdown + Telegram HTML)
├── deliver.py            # Webex + Telegram delivery functions
├── sent_history.json     # Tracks sent article URLs (committed after each run)
├── requirements.txt      # Python dependencies
├── .env.example          # Template for local secrets
└── .github/
    └── workflows/
        └── news_bot.yml  # GitHub Actions scheduler
```

---

## Required Secrets (GitHub Actions → Settings → Secrets)

| Secret               | Where to get it                              |
|----------------------|----------------------------------------------|
| `GROQ_API_KEY`       | https://console.groq.com                     |
| `WEBEX_BOT_TOKEN`    | https://developer.webex.com → Create Bot     |
| `WEBEX_ROOM_ID`      | Webex API or from bot's first message log    |
| `TELEGRAM_BOT_TOKEN` | @BotFather on Telegram → /newbot             |
| `TELEGRAM_CHAT_ID`   | Add bot to channel, use getUpdates API       |

---

## Setup Steps

### 1. Create the Groq API key
1. Sign up at https://console.groq.com
2. Create an API key and save it as `GROQ_API_KEY`

### 2. Create the Webex Bot
1. Go to https://developer.webex.com → Create a Bot
2. Copy the bot access token → `WEBEX_BOT_TOKEN`
3. Add the bot to your Webex Space
4. Get the room ID: `GET https://webexapis.com/v1/rooms` with the bot token
5. Save as `WEBEX_ROOM_ID`

### 3. Create the Telegram Bot & Channel
1. Message @BotFather on Telegram → `/newbot`
2. Save the token → `TELEGRAM_BOT_TOKEN`
3. Create a Telegram Channel (e.g. @CyberBriefDaily)
4. Add the bot as an administrator of the channel
5. Get the chat ID: post a message to the channel, then call
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
6. Save the channel's `chat.id` → `TELEGRAM_CHAT_ID`

### 4. GitHub Repository
1. Push this project to a GitHub repository
2. Go to Settings → Secrets and variables → Actions
3. Add all 5 secrets listed above
4. The workflow will trigger automatically on schedule

### 5. Local Testing
1. Copy `.env.example` to `.env` and fill in real values
2. Run `pip install -r requirements.txt`
3. Run `python main.py --force` to bypass the timezone guard for testing

---

## Cost
- **Everything free** — Groq free tier, GitHub Actions free tier, Webex bot, Telegram bot

---

## Future Enhancements (not in scope yet)
- Keyword subscription per user (personalised digests)
- Web dashboard to view past digests
- Slack delivery channel
- Severity scoring using CVE database lookup
