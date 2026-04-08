"""
tracking.py
Dub.co URL shortening + click-based engagement tracking.

If DUB_API_TOKEN is not set, all functions degrade gracefully:
  - URLs are passed through unchanged
  - Click counts default to 0

Dub.co free tier: 1,000 links / month.
Add DUB_API_TOKEN as a GitHub Actions secret and a local .env variable.
"""

import os

import requests

DUB_API_BASE = "https://api.dub.co"
DUB_SHORTEN_URL = f"{DUB_API_BASE}/links"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _shorten(url: str, token: str) -> tuple[str, str | None]:
    """Call Dub.co API to shorten one URL. Returns (short_url, link_id) or (original_url, None) on failure."""
    try:
        resp = requests.post(
            DUB_SHORTEN_URL,
            headers=_headers(token),
            json={"url": url, "domain": "dub.sh"},
            timeout=10,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            return data.get("shortLink", url), data.get("id")
        print(f"  ⚠️  Dub.co returned {resp.status_code} for {url} — using original URL")
        return url, None
    except Exception as e:
        print(f"  ⚠️  Dub.co error for {url}: {e} — using original URL")
        return url, None


def _get_clicks(link_id: str, token: str) -> int:
    """Fetch total click count for a single Dub.co link ID."""
    try:
        resp = requests.get(
            f"{DUB_API_BASE}/analytics",
            headers=_headers(token),
            params={"linkId": link_id, "event": "clicks", "interval": "30d"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            # Dub.co returns a plain number for total clicks
            if isinstance(data, (int, float)):
                return int(data)
    except Exception:
        pass
    return 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def add_tracking_urls(articles: list[dict]) -> list[dict]:
    """
    Populate each article's 'short_url' field using Dub.co.
    Also stores the Dub.co link ID on the article as 'bitly_id' for later
    click retrieval.  If DUB_API_TOKEN is absent, short_url = url (pass-through).
    Modifies articles in-place and returns the list.
    """
    token = os.environ.get("DUB_API_TOKEN", "").strip()

    if not token:
        for article in articles:
            article["short_url"] = article["url"]
            article["bitly_id"] = None
        return articles

    print(f"  🔗 Shortening {len(articles)} URLs via Dub.co...")
    for article in articles:
        short, link_id = _shorten(article["url"], token)
        article["short_url"] = short
        article["bitly_id"] = link_id

    return articles


def get_weekly_top_articles(weekly_articles: list[dict], top_n: int = 3) -> list[dict]:
    """
    Given the week's accumulated article stubs (from last_week_digest in sent_history.json),
    query Dub.co for click counts and return the top_n sorted by clicks descending.
    Articles without a link_id get 0 clicks.
    """
    token = os.environ.get("DUB_API_TOKEN", "").strip()

    results = []
    for article in weekly_articles:
        clicks = 0
        if token and article.get("bitly_id"):
            clicks = _get_clicks(article["bitly_id"], token)
        results.append({**article, "clicks": clicks})

    results.sort(key=lambda a: a["clicks"], reverse=True)
    top = results[:top_n]

    print(f"  🏆 Weekly top {top_n} articles:")
    for a in top:
        print(f"     {a['clicks']} clicks — {a['title'][:60]}")

    return top
