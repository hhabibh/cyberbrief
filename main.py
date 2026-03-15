"""
main.py
Orchestrator for CyberBrief.

Timezone guard:
  - Runs on Mon/Wed/Fri via GitHub Actions (two cron triggers per day: BST + GMT offsets)
  - Checks actual UK local time and exits early if the hour doesn't match the
    intended send time — ensuring only one of the two daily triggers executes.

Usage:
  python main.py           # Normal run with timezone guard
  python main.py --force   # Bypass timezone guard (for local testing)
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pytz
from dotenv import load_dotenv

# Load .env file for local development (no-op in GitHub Actions where secrets are env vars)
load_dotenv()

from fetch_news import fetch_all_articles, save_sent_history, load_previous_digest_articles, load_weekly_digest_articles
from summarize import summarise_all
from format_message import format_webex, format_webex_card, format_telegram, format_webex_card_sunday, format_webex_sunday, format_telegram_sunday
from deliver import send_webex, send_telegram
from tracking import add_tracking_urls, update_engagement_from_previous_digest, get_source_engagement_scores, get_weekly_top_articles

LONDON_TZ = pytz.timezone("Europe/London")

# weekday() returns 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
SEND_SCHEDULE = {
    0: 10,  # Monday    10:00 UK
    1: 10,  # Tuesday   10:00 UK
    2: 10,  # Wednesday 10:00 UK
    3: 10,  # Thursday  10:00 UK
    4: 10,  # Friday    10:00 UK
    6: 10,  # Sunday    10:00 UK — engagement leaderboard
}


def timezone_guard() -> bool:
    """
    Returns True if the current UK time matches a scheduled send window.
    The GitHub Actions cron fires at both UTC offsets (BST and GMT) for each day.
    This guard ensures only one actually runs.
    """
    now_uk = datetime.now(LONDON_TZ)
    weekday = now_uk.weekday()
    hour = now_uk.hour

    expected_hour = SEND_SCHEDULE.get(weekday)
    if expected_hour is None:
        print(
            f"⏭ Timezone guard: today ({now_uk.strftime('%A')}) is not a send day. Exiting."
        )
        return False

    if hour != expected_hour:
        print(
            f"⏭ Timezone guard: current UK time is {now_uk.strftime('%H:%M')} but "
            f"send window for {now_uk.strftime('%A')} is {expected_hour:02d}:00. Exiting."
        )
        return False

    print(f"✅ Timezone guard passed: {now_uk.strftime('%A %H:%M %Z')}")
    return True


def run_sunday_digest():
    """Fetch weekly top articles by click count and deliver the Sunday leaderboard digest."""
    print("📊 Sunday digest — fetching weekly top articles...")
    weekly_articles = load_weekly_digest_articles()
    if not weekly_articles:
        print("⚠️  No weekly articles accumulated. Nothing to send.")
        sys.exit(0)

    top_articles = get_weekly_top_articles(weekly_articles, top_n=3)
    if not top_articles:
        print("⚠️  Could not determine top articles. Nothing to send.")
        sys.exit(0)

    print("✍️  Formatting Sunday digest...")
    webex_msg = format_webex_sunday(top_articles)
    webex_card = format_webex_card_sunday(top_articles)
    telegram_msg = format_telegram_sunday(top_articles)

    print("📤 Sending Sunday digest to Webex...")
    webex_ok = send_webex(webex_msg, card=webex_card)

    print("📤 Sending Sunday digest to Telegram...")
    telegram_ok = send_telegram(telegram_msg)

    if webex_ok or telegram_ok:
        print("💾 Clearing weekly accumulation...")
        save_sent_history(set(), is_sunday=True)
        print("✅ Sunday digest sent.")
    else:
        print("❌ Sunday delivery failed.")
        sys.exit(1)


def run():
    parser = argparse.ArgumentParser(description="CyberBrief news digest bot")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass timezone guard (for local testing)",
    )
    parser.add_argument(
        "--telegram-only",
        action="store_true",
        help="Send to Telegram only, skip Webex (for testing)",
    )
    args = parser.parse_args()

    if not args.force:
        if not timezone_guard():
            sys.exit(0)

    # Sunday: send engagement leaderboard instead of normal digest
    # Skipped when --telegram-only is set so the weekday pipeline can be tested on a Sunday
    now_uk = datetime.now(LONDON_TZ)
    if not args.telegram_only:
        if args.force:
            if now_uk.weekday() == 6:
                run_sunday_digest()
                return
        elif now_uk.weekday() == 6:
            run_sunday_digest()
            return

    print("📊 Loading click data from previous digest...")
    print("📡 Fetching articles from RSS feeds...")
    previous_articles = load_previous_digest_articles()
    update_engagement_from_previous_digest(previous_articles)
    engagement_scores = get_source_engagement_scores()
    articles = fetch_all_articles(engagement_scores=engagement_scores)

    if not articles:
        print("⚠️  No new articles found after deduplication. Nothing to send.")
        sys.exit(0)

    print(f"📰 Selected {len(articles)} articles. Generating summaries...")
    articles, context_line = summarise_all(articles)

    print("🔗 Adding tracking URLs...")
    articles = add_tracking_urls(articles)

    print("✍️  Formatting messages...")
    webex_msg = format_webex(articles, context_line)
    webex_card = format_webex_card(articles, context_line)
    telegram_msg = format_telegram(articles, context_line)

    if not args.telegram_only:
        print("📤 Sending to Webex...")
        webex_ok = send_webex(webex_msg, card=webex_card)
    else:
        print("⏭  Webex skipped (--telegram-only)")
        webex_ok = False

    print("📤 Sending to Telegram...")
    telegram_ok = send_telegram(telegram_msg)

    if webex_ok or telegram_ok:
        if args.telegram_only:
            print("⏭  Skipping history update (--telegram-only test run).")
        else:
            print("💾 Saving sent article URLs to history...")
            save_sent_history({a["url"] for a in articles}, articles=articles)
        print("✅ Done.")
    else:
        print("❌ All deliveries failed. Not updating sent history.")
        sys.exit(1)


if __name__ == "__main__":
    run()
