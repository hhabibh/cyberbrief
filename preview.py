"""
preview.py
Fetches and formats a digest preview — prints to terminal only.
No messages are sent to Webex or Telegram. sent_history.json is NOT updated.
Run with: python preview.py
"""

import sys
from dotenv import load_dotenv
load_dotenv()

import json
from fetch_news import fetch_all_articles
from summarize import summarise_all
from format_message import format_webex, format_webex_card, format_telegram

print("📡 Fetching articles from RSS feeds...")
articles = fetch_all_articles()

if not articles:
    print("⚠️  No new articles found after deduplication.")
    sys.exit(0)

print(f"📰 Selected {len(articles)} articles. Generating summaries via Groq...")
articles, context_line = summarise_all(articles)

print("\n" + "═" * 60)
print("WEBEX PREVIEW (Markdown fallback)")
print("═" * 60)
print(format_webex(articles, context_line))

print("\n" + "═" * 60)
print("WEBEX CARD PREVIEW (Adaptive Card JSON)")
print("═" * 60)
card = format_webex_card(articles, context_line)
print(json.dumps(card, indent=2, ensure_ascii=False))

print("\n" + "═" * 60)
print("TELEGRAM PREVIEW")
print("═" * 60)
print(format_telegram(articles, context_line))
print("═" * 60)
print("\n✅ Preview complete — nothing was sent.")
