"""
tracking.py
Bitly URL shortening + click-based source engagement scoring.

If BITLY_API_TOKEN is not set, all functions degrade gracefully:
  - URLs are passed through unchanged
  - Source engagement scores default to 1.0 (no adjustment)

Bitly free tier: 1,000 shortened links / month.
Add BITLY_API_TOKEN as a GitHub Actions secret and a local .env variable.

Engagement scoring:
  After enough digests have been sent, get_source_engagement_scores() queries
  Bitly for click counts on the previous digest's links and returns a per-source
  multiplier (e.g. {"NCSC UK": 1.4, "SecurityWeek": 0.8}) that fetch_news.py
  applies when scoring candidate articles.  Scores converge gradually — a source
  needs at least MIN_SAMPLES clicks events before it influences selection.
"""

import json
import os
from pathlib import Path

import requests

BITLY_API_BASE = "https://api-ssl.bitly.com/v4"
BITLY_SHORTEN_URL = f"{BITLY_API_BASE}/shorten"

# Minimum total clicks recorded for a source before its multiplier deviates from 1.0.
# Prevents a single viral article skewing the weights permanently.
MIN_SAMPLES = 3

# Clamp multipliers to this range to avoid any source being starved or monopolising.
MULTIPLIER_MIN = 0.6
MULTIPLIER_MAX = 2.0

_ENGAGEMENT_FILE = Path(__file__).parent / "engagement.json"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _shorten(url: str, token: str) -> str:
    """Call Bitly API to shorten one URL. Returns original URL on any failure."""
    try:
        resp = requests.post(
            BITLY_SHORTEN_URL,
            headers=_headers(token),
            json={"long_url": url, "domain": "bit.ly"},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("link", url)
        if resp.status_code == 422:
            # Already a bit.ly link or invalid URL
            return url
        print(f"  ⚠️  Bitly returned {resp.status_code} for {url} — using original URL")
        return url
    except Exception as e:
        print(f"  ⚠️  Bitly error for {url}: {e} — using original URL")
        return url


def _get_clicks(bitly_id: str, token: str) -> int:
    """Fetch total click count for a single Bitly link ID (e.g. '3abc123')."""
    try:
        resp = requests.get(
            f"{BITLY_API_BASE}/bitlinks/bit.ly/{bitly_id}/clicks/summary",
            headers=_headers(token),
            params={"unit": "month", "units": 3},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("total_clicks", 0)
    except Exception:
        pass
    return 0


def _load_engagement() -> dict:
    """Load persistent engagement store: {source: {clicks, count}}."""
    if _ENGAGEMENT_FILE.exists():
        with open(_ENGAGEMENT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_engagement(data: dict) -> None:
    with open(_ENGAGEMENT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def add_tracking_urls(articles: list[dict]) -> list[dict]:
    """
    Populate each article's 'short_url' field using Bitly.
    Also stores the Bitly link ID on the article as 'bitly_id' for later
    click retrieval.  If BITLY_API_TOKEN is absent, short_url = url (pass-through).
    Modifies articles in-place and returns the list.
    """
    token = os.environ.get("BITLY_API_TOKEN", "").strip()

    if not token:
        for article in articles:
            article["short_url"] = article["url"]
            article["bitly_id"] = None
        return articles

    print(f"  🔗 Shortening {len(articles)} URLs via Bitly...")
    for article in articles:
        short = _shorten(article["url"], token)
        article["short_url"] = short
        # Extract the path component: "https://bit.ly/3abc123" → "3abc123"
        article["bitly_id"] = short.rstrip("/").split("/")[-1] if short != article["url"] else None

    return articles


def update_engagement_from_previous_digest(previous_articles: list[dict]) -> None:
    """
    Query Bitly for click counts on articles from the previous digest and
    accumulate per-source totals in engagement.json.

    Call this at the START of a new run, passing the articles that were sent
    in the last digest (loaded from sent_history.json).
    No-op if BITLY_API_TOKEN is absent or no bitly_ids are stored.
    """
    token = os.environ.get("BITLY_API_TOKEN", "").strip()
    if not token:
        return

    articles_with_ids = [a for a in previous_articles if a.get("bitly_id")]
    if not articles_with_ids:
        return

    print(f"  📊 Fetching click data for {len(articles_with_ids)} previous article(s)...")
    engagement = _load_engagement()

    for article in articles_with_ids:
        source = article["source"]
        clicks = _get_clicks(article["bitly_id"], token)
        if source not in engagement:
            engagement[source] = {"total_clicks": 0, "count": 0}
        engagement[source]["total_clicks"] += clicks
        engagement[source]["count"] += 1
        print(f"     {source}: {clicks} click(s) (running total: {engagement[source]['total_clicks']})")

    _save_engagement(engagement)


def get_source_engagement_scores() -> dict[str, float]:
    """
    Return a dict of {source_name: score_multiplier} based on accumulated
    click data.  Sources with fewer than MIN_SAMPLES recorded articles get a
    neutral multiplier of 1.0.

    Multiplier formula:
      avg_clicks_for_source / avg_clicks_across_all_sources
    Clamped to [MULTIPLIER_MIN, MULTIPLIER_MAX].
    """
    engagement = _load_engagement()
    if not engagement:
        return {}

    # Only include sources that have enough data
    qualified = {
        src: data for src, data in engagement.items()
        if data["count"] >= MIN_SAMPLES
    }
    if not qualified:
        return {}

    avg_per_source = {
        src: data["total_clicks"] / data["count"]
        for src, data in qualified.items()
    }
    global_avg = sum(avg_per_source.values()) / len(avg_per_source)
    if global_avg == 0:
        return {}

    multipliers = {}
    for src, avg in avg_per_source.items():
        raw = avg / global_avg
        multipliers[src] = max(MULTIPLIER_MIN, min(MULTIPLIER_MAX, raw))

    # Log the active multipliers so they're visible in the Actions run log
    print("  📈 Source engagement multipliers:")
    for src, mult in sorted(multipliers.items(), key=lambda x: -x[1]):
        bar = "▲" if mult > 1.0 else ("▼" if mult < 1.0 else "─")
        print(f"     {bar} {src}: {mult:.2f}x")

    return multipliers
