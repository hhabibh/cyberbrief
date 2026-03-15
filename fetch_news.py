"""
fetch_news.py
Fetches RSS feeds, filters by recency, deduplicates against sent history,
scores by keyword relevance, and returns the top 5 articles.
"""

import json
import os
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import feedparser
import requests
from bs4 import BeautifulSoup

from sources import FEEDS, KEYWORDS, PILLAR_TARGETS, LOOKBACK_HOURS

HISTORY_FILE = Path(__file__).parent / "sent_history.json"

HEADERS = {
    "User-Agent": (
        "CyberBriefBot/1.0 (automated news digest; "
        "contact: your-email@example.com)"
    )
}

SCRAPE_TIMEOUT = 10  # seconds per article fetch


def load_sent_history() -> set:
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return set(data.get("sent_urls", []))
    return set()


def load_previous_digest_articles() -> list[dict]:
    """Return the article stubs (url, source, bitly_id) from the last digest run."""
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return data.get("last_digest", [])
    return []


def save_sent_history(urls: set, articles: list[dict] | None = None, is_sunday: bool = False) -> None:
    existing_data: dict = {}
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, "r", encoding="utf-8-sig") as f:
            existing_data = json.load(f)

    existing_urls = set(existing_data.get("sent_urls", []))
    merged = existing_urls | urls
    # Keep last 500 URLs to avoid unbounded growth
    trimmed = list(merged)[-500:]

    payload: dict = {"sent_urls": trimmed}

    if is_sunday:
        # Sunday run: preserve last_digest, clear the weekly accumulation after consuming it
        payload["last_digest"] = existing_data.get("last_digest", [])
        payload["last_week_digest"] = []
    elif articles is not None:
        # Store minimal stubs needed for engagement polling
        payload["last_digest"] = [
            {"url": a["url"], "source": a["source"], "bitly_id": a.get("bitly_id")}
            for a in articles
        ]
        # Accumulate weekly stubs for Sunday leaderboard (keep last 35 = max 7 days × 5)
        existing_week = existing_data.get("last_week_digest", [])
        new_stubs = [
            {
                "url": a["url"],
                "title": a["title"],
                "source": a["source"],
                "bitly_id": a.get("bitly_id"),
                "tldr": a.get("tldr", ""),
                "published": a.get("published"),
            }
            for a in articles
        ]
        payload["last_week_digest"] = (existing_week + new_stubs)[-35:]
    else:
        if "last_digest" in existing_data:
            payload["last_digest"] = existing_data["last_digest"]
        if "last_week_digest" in existing_data:
            payload["last_week_digest"] = existing_data["last_week_digest"]

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def load_weekly_digest_articles() -> list[dict]:
    """Return accumulated article stubs from the current week for Sunday leaderboard."""
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return data.get("last_week_digest", [])
    return []


def _parse_published(entry) -> datetime | None:
    """Return a timezone-aware UTC datetime from a feedparser entry, or None."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        return datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
    return None


def _score_article(title: str, summary: str, pillar: str, engagement_mult: float = 1.0) -> dict:
    """
    Score an article against all keyword buckets.
    Returns a dict with per-bucket scores and a total.
    engagement_mult: per-source multiplier derived from historical click data (default 1.0).
    """
    text = (title + " " + summary).lower()
    scores = {}
    for bucket, keywords in KEYWORDS.items():
        bucket_score = sum(1 for kw in keywords if kw.lower() in text)
        scores[bucket] = bucket_score
    scores["total"] = sum(scores.values())
    # Boost score if the article's native pillar matches the strongest bucket
    strongest_bucket = max(scores, key=lambda k: scores[k] if k != "total" else -1)
    if strongest_bucket == pillar or (
        pillar == "threat_intel" and strongest_bucket == "cyber"
    ):
        scores["total"] += 2
    # Apply engagement multiplier (rounded to avoid float noise in comparisons)
    scores["total"] = round(scores["total"] * engagement_mult, 3)
    return scores


def fetch_article_text(url: str) -> str:
    """
    Attempt to fetch and extract the main body text of an article.
    Returns extracted text, or empty string on failure.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=SCRAPE_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        # Remove nav, footer, aside, script, style noise
        for tag in soup(["script", "style", "nav", "footer", "aside", "header"]):
            tag.decompose()
        # Prefer article tag, then main, then body
        for selector in ["article", "main", "body"]:
            container = soup.find(selector)
            if container:
                text = container.get_text(separator=" ", strip=True)
                # Collapse whitespace
                text = re.sub(r"\s+", " ", text)
                return text[:4000]  # cap at 4000 chars for summarization
        return ""
    except Exception:
        return ""


def fetch_all_articles(engagement_scores: dict[str, float] | None = None) -> list[dict]:
    """
    Fetch all RSS feeds, filter by recency, deduplicate, score, and return
    a ranked list of article dicts ready for summarization.

    engagement_scores: optional {source_name: multiplier} from tracking.py.
    Sources with higher historical click rates get a score boost, nudging
    the selection algorithm to favour them.
    """
    now = datetime.now(timezone.utc)
    # Monday (weekday 0): extend lookback to cover the full weekend gap (~72h)
    # All other weekdays: 36h is enough to cover since yesterday's digest
    lookback = 72 if now.weekday() == 0 else LOOKBACK_HOURS
    cutoff = now - timedelta(hours=lookback)
    print(f"  📅 Lookback window: {lookback}h ({'Monday — extended for weekend' if lookback == 72 else 'weekday'})")
    sent_urls = load_sent_history()
    candidates = []
    eng = engagement_scores or {}

    for source_name, feed_url, pillar in FEEDS:
        feed_candidates = []
        mult = eng.get(source_name, 1.0)
        try:
            parsed = feedparser.parse(feed_url)
        except Exception as e:
            print(f"  ⚠️  Feed error [{source_name}]: {e}")
            continue

        if not parsed.entries:
            print(f"  ⚠️  Feed returned 0 entries [{source_name}]: {feed_url}")
            continue

        for entry in parsed.entries:
            url = entry.get("link", "")
            if not url or url in sent_urls:
                continue

            published = _parse_published(entry)
            if published and published < cutoff:
                continue

            title = entry.get("title", "").strip()
            # Use RSS summary as fallback text for scoring.
            # Wrap in <span> to ensure BeautifulSoup always treats input as markup,
            # not a filename, suppressing MarkupResemblesLocatorWarning.
            raw_summary = entry.get("summary", entry.get("description", "")) or ""
            summary = BeautifulSoup(
                f"<span>{raw_summary}</span>", "html.parser"
            ).get_text()

            scores = _score_article(title, summary, pillar, engagement_mult=mult)

            candidates.append(
                {
                    "title": title,
                    "url": url,
                    "source": source_name,
                    "pillar": pillar,
                    "published": published.isoformat() if published else None,
                    "rss_summary": summary[:500],
                    "full_text": "",  # populated later for selected articles only
                    "scores": scores,
                    "tldr": "",  # populated by summarize.py
                }
            )
            feed_candidates.append(url)

        if feed_candidates:
            mult_label = f" [engagement: {mult:.2f}x]" if mult != 1.0 else ""
            print(f"  ✓  {source_name}: {len(feed_candidates)} article(s) in window{mult_label}")
        else:
            print(f"  ⚠️  No qualifying articles [{source_name}] (all outside {LOOKBACK_HOURS}h window or already sent)")

        # Polite crawl delay
        time.sleep(0.5)

    return _select_top_articles(candidates)


def _topic_key(title: str) -> str:
    """
    Reduce a title to a short 'topic fingerprint' for similarity checking.
    Strips common words and punctuation, lowercases, takes first 4 meaningful words.
    Two articles about the same story will usually share most of these words.
    """
    stopwords = {
        "a", "an", "the", "in", "on", "at", "to", "for", "of", "and", "or",
        "but", "is", "are", "was", "were", "be", "been", "by", "with", "as",
        "it", "its", "that", "this", "from", "have", "has", "how", "why",
        "what", "new", "after", "over", "into", "about", "more",
    }
    words = re.sub(r"[^a-z0-9 ]", "", title.lower()).split()
    meaningful = [w for w in words if w not in stopwords and len(w) > 2]
    return " ".join(meaningful[:4])


def _is_duplicate_topic(title: str, seen_keys: list[str], threshold: int = 2) -> bool:
    """
    Returns True if this title shares >= threshold meaningful words with any
    already-selected article, indicating it covers the same story.
    """
    candidate_words = set(_topic_key(title).split())
    for key in seen_keys:
        overlap = len(candidate_words & set(key.split()))
        if overlap >= threshold:
            return True
    return False


MAX_PER_SOURCE = 2  # No single feed can contribute more than this many articles


def _select_top_articles(candidates: list[dict]) -> list[dict]:
    """
    Select 5 articles respecting pillar targets, topic diversity, and a
    per-source cap (MAX_PER_SOURCE) to prevent any single feed dominating.
    Falls back to top-scored articles if pillar quotas can't be filled.
    """
    candidates.sort(key=lambda a: a["scores"]["total"], reverse=True)

    selected = []
    pillar_counts = {p: 0 for p in PILLAR_TARGETS}
    seen_topic_keys: list[str] = []
    source_counts: dict[str, int] = {}

    # First pass: fill pillar quotas, skipping duplicate topics and capping per source
    for article in candidates:
        p = article["pillar"]
        src = article["source"]
        target = PILLAR_TARGETS.get(p, 1)
        if pillar_counts.get(p, 0) < target:
            if source_counts.get(src, 0) < MAX_PER_SOURCE:
                if not _is_duplicate_topic(article["title"], seen_topic_keys):
                    selected.append(article)
                    pillar_counts[p] = pillar_counts.get(p, 0) + 1
                    source_counts[src] = source_counts.get(src, 0) + 1
                    seen_topic_keys.append(_topic_key(article["title"]))
        if len(selected) == 5:
            break

    # Second pass: fill remaining slots, still skipping duplicate topics and capping per source
    if len(selected) < 5:
        selected_urls = {a["url"] for a in selected}
        for article in candidates:
            src = article["source"]
            if article["url"] not in selected_urls:
                if source_counts.get(src, 0) < MAX_PER_SOURCE:
                    if not _is_duplicate_topic(article["title"], seen_topic_keys):
                        selected.append(article)
                        selected_urls.add(article["url"])
                        source_counts[src] = source_counts.get(src, 0) + 1
                        seen_topic_keys.append(_topic_key(article["title"]))
            if len(selected) == 5:
                break

    # Third pass: relax topic dedup but keep per-source cap
    if len(selected) < 5:
        selected_urls = {a["url"] for a in selected}
        for article in candidates:
            src = article["source"]
            if article["url"] not in selected_urls:
                if source_counts.get(src, 0) < MAX_PER_SOURCE:
                    selected.append(article)
                    selected_urls.add(article["url"])
                    source_counts[src] = source_counts.get(src, 0) + 1
            if len(selected) == 5:
                break

    # Fourth pass: last resort — relax both topic dedup and per-source cap to reach 5
    if len(selected) < 5:
        selected_urls = {a["url"] for a in selected}
        for article in candidates:
            if article["url"] not in selected_urls:
                selected.append(article)
                selected_urls.add(article["url"])
            if len(selected) == 5:
                break

    # Fetch full text for selected articles only
    for article in selected:
        article["full_text"] = fetch_article_text(article["url"])

    return selected
