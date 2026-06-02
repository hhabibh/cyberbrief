"""
summarize.py
Uses the Cisco ChatAI Bridge (Gemini) to generate:
  - A 2-3 sentence TLDR for each article
  - A 1-sentence "Context This Week" framing line for the digest header
"""

import json
import os
import threading
import time
from datetime import datetime, timezone

import requests

# ---------------------------------------------------------------------------
# Cisco ChatAI Bridge — OAuth2 token + HTTP client
# ---------------------------------------------------------------------------

_CLIENT_ID     = os.getenv("BRIDGE_API_CLIENT_ID", "")
_CLIENT_SECRET = os.getenv("BRIDGE_API_CLIENT_SECRET", "")
_APP_KEY       = os.getenv("BRIDGE_API_APP_KEY", "")
_TOKEN_URL     = "https://id.cisco.com/oauth2/default/v1/token"
_BRIDGE_URL    = "https://chat-ai.cisco.com/openai/deployments/gemini-3.1-flash-lite/chat/completions"
_MODEL         = "gemini-3.1-flash-lite"

_token_cache = {"token": None, "expires_at": 0}
_token_lock  = threading.Lock()


def _get_access_token() -> str:
    with _token_lock:
        if _token_cache["token"] and time.time() < _token_cache["expires_at"] - 60:
            return _token_cache["token"]
        resp = requests.post(
            _TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(_CLIENT_ID, _CLIENT_SECRET),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        _token_cache["token"]      = data["access_token"]
        _token_cache["expires_at"] = time.time() + int(data.get("expires_in", 3600))
        return _token_cache["token"]


def _call_bridge(system_prompt: str, user_prompt: str, max_tokens: int = 200) -> str:
    if not _CLIENT_ID or not _CLIENT_SECRET or not _APP_KEY:
        raise EnvironmentError(
            "BRIDGE_API_CLIENT_ID, BRIDGE_API_CLIENT_SECRET and BRIDGE_API_APP_KEY "
            "must all be set."
        )
    payload = {
        "model":       _MODEL,
        "messages":    [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "temperature": 0.4,
        "max_tokens":  max_tokens,
        "user":        json.dumps({"appkey": _APP_KEY}),
        "stop":        ["<|im_end|>"],
    }
    headers = {
        "Content-Type": "application/json",
        "api-key":      _get_access_token(),
    }
    resp = requests.post(_BRIDGE_URL, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _rss_excerpt(article: dict) -> str:
    """Return a trimmed RSS summary (~60 words) as a plain-text fallback TLDR."""
    text = article.get("rss_summary", "").strip()
    if not text:
        return "No summary available."
    words = text.split()
    if len(words) <= 65:
        return text
    return " ".join(words[:62]) + "…"


# TLDR word targets by weekday (Monday=0 … Friday=4).
# Monday/Friday feel slightly richer; midweek is punchy.
_TLDR_WORD_TARGETS = {0: 50, 1: 38, 2: 45, 3: 38, 4: 50}


def generate_tldr(article: dict, target_words: int = 45) -> str:
    """
    Generate a factual TLDR for a single article.
    target_words controls prose density; caller sets this per-day.
    Uses full article text if available, falls back to RSS summary.
    """
    body = article.get("full_text") or article.get("rss_summary", "")
    if not body:
        return _rss_excerpt(article)

    system_prompt = (
        "You are a senior cybersecurity analyst writing a news digest for business leaders and security professionals globally. "
        "Write a single paragraph of continuous prose summarising the article. "
        "Cover: what happened and to whom, the real-world business or operational consequence, and what it signals for the industry. "
        f"STRICT WORD LIMIT: {target_words} to {target_words + 8} words. Count every word carefully — do not exceed {target_words + 8} words. "
        "Include specific numbers, figures, or statistics from the article where available (e.g. number of users affected, financial losses, scale of attack). "
        "No bullet points, no headers, no labels. "
        "Global perspective — avoid US-only framing. "
        "Focus on breach impact and business consequences, not raw technical CVE details. "
        "Factual and neutral — no sensationalism. "
        "Plain British English. "
        "Do not start with 'This article'. "
        "End the paragraph naturally — do not add a call to action or sign-off phrase at the end."
    )

    user_prompt = (
        f"Article title: {article['title']}\n"
        f"Source: {article['source']}\n\n"
        f"Article text:\n{body}\n\n"
        f"Write the {target_words}–{target_words + 8} word summary:"
    )

    try:
        return _call_bridge(system_prompt, user_prompt, max_tokens=200)
    except Exception as e:
        print(f"  ⚠️  Bridge TLDR failed for '{article['title']}': {e} — using RSS excerpt")
        return _rss_excerpt(article)


def generate_context_line(articles: list[dict]) -> str:
    """
    Generate a single sentence that contextualises this digest within
    current world events (geopolitical, economic, tech trends).
    """
    today = datetime.now(timezone.utc).strftime("%d %B %Y")
    titles = "\n".join(f"- {a['title']}" for a in articles)

    # Extract notable geopolitical/financial actors from titles to give the model specifics
    geo_keywords = [
        "Russia", "China", "Iran", "North Korea", "Ukraine", "NATO",
        "SEC", "GDPR", "NIS2", "bitcoin", "crypto", "stock", "tariff",
        "war", "sanctions",
    ]
    themes_found = [kw for kw in geo_keywords if any(
        kw.lower() in a["title"].lower() for a in articles
    )]
    themes_note = (
        f"Themes detected in today's articles: {', '.join(themes_found)}."
        if themes_found else ""
    )

    system_prompt = (
        "You are a senior cybersecurity analyst writing the opening line of a news digest. "
        "Write exactly one sentence (25–40 words) that frames today's cybersecurity stories "
        "within the specific real-world backdrop visible in the article titles — "
        "name specific actors, countries, or trends where present. "
        "Avoid generic phrases like 'the cybersecurity landscape continues to evolve'. "
        "Be concrete, factual, and neutral. Plain British English."
    )

    user_prompt = (
        f"Today's date: {today}\n"
        f"{themes_note}\n\n"
        f"Today's digest covers:\n{titles}\n\n"
        "Write the single context sentence:"
    )

    try:
        return _call_bridge(system_prompt, user_prompt, max_tokens=80)
    except Exception:
        return "This week's digest covers the latest developments across cybersecurity, technology, and global events."


# Keywords that signal a business/customer-impact article worth generating a talk track for
_BUSINESS_IMPACT_KEYWORDS = [
    "breach", "fine", "penalty", "gdpr", "compliance", "regulation", "lawsuit",
    "supply chain", "ransomware", "data theft", "stolen", "exposed", "leaked",
    "cost", "billion", "million", "insurance", "liability", "acquisition",
    "m&a", "settlement", "nis2", "dora", "sec ", "ico", "nist",
]


def _qualifies_for_talk_track(article: dict) -> bool:
    """Return True if the article has enough business/customer-impact signal."""
    text = (
        article.get("title", "") + " " +
        article.get("rss_summary", "") + " " +
        article.get("full_text", "") + " " +
        article.get("tldr", "")
    ).lower()
    tech_business_score = article.get("scores", {}).get("tech_business", 0)
    if tech_business_score >= 2:
        return True
    return any(kw in text for kw in _BUSINESS_IMPACT_KEYWORDS)


# Deterministic opener rotation — one per article slot (0-indexed).
# Model writes ONLY the tail; Python prepends the opener — guaranteed rotation.
_TALK_TRACK_OPENERS = ["What", "To what extent", "Where", "Which", "How"]


def generate_talk_track(article: dict, position: int = 0) -> str | None:
    """
    Generate a short spoken conversation-starter for a qualifying article.
    Returns None if the article doesn't qualify or the Bridge call fails.
    """
    if not _qualifies_for_talk_track(article):
        return None

    tldr = article.get("tldr", "").strip()
    if not tldr:
        return None

    opener_word = _TALK_TRACK_OPENERS[position % len(_TALK_TRACK_OPENERS)]

    system_prompt = (
        "You are a cybersecurity advisor opening a conversation with a customer. "
        "You will be given an opening word and a news summary. "
        "Write ONLY the words that follow the opening word to complete a short, direct spoken question. "
        "The full question (opening word + your tail) must be 8 to 12 words total and end with a question mark. "
        "The question should invite the customer to reflect on their own organisation — "
        "not the company in the news story. "
        "Do NOT use: strategy, posture, landscape, resilience, adapt, withstand, protocols, frameworks. "
        "Do NOT include the opening word in your output. "
        "Plain British English. Output ONLY the tail — nothing else.\n\n"
        "Examples of the correct style (notice: concrete, references testing/detection/visibility/risk, not vague 'steps'):\n"
        "  What  →  visibility do you have into how customer data is classified and protected?\n"
        "  To what extent  →  could your team detect this kind of intrusion early?\n"
        "  Where  →  would a penetration test most likely expose gaps in your credential controls?\n"
        "  Which  →  of your systems would take longest to recover from a similar attack?\n"
        "  How  →  regularly does your team audit who has access to your most sensitive accounts?"
    )

    user_prompt = (
        f"Article title: {article['title']}\n\n"
        f"Summary: {tldr}\n\n"
        f"Opening word: '{opener_word}'\n"
        f"Write ONLY the words that follow '{opener_word}'."
    )

    try:
        tail = _call_bridge(system_prompt, user_prompt, max_tokens=40).strip()
        # Strip opener if the model included it despite instructions
        if tail.lower().startswith(opener_word.lower()):
            tail = tail[len(opener_word):].lstrip()
        return f"{opener_word} {tail}"
    except Exception as e:
        print(f"  ⚠️  Bridge talk track failed for '{article['title']}': {e}")
        return None


def summarise_all(articles: list[dict]) -> tuple[list[dict], str]:
    """
    Summarise all articles and generate the context line.
    Returns (articles_with_tldrs, context_line).
    """
    today_weekday = datetime.now(timezone.utc).weekday()  # 0=Mon … 4=Fri
    target_words = _TLDR_WORD_TARGETS.get(today_weekday, 45)
    for i, article in enumerate(articles):
        article["tldr"] = generate_tldr(article, target_words=target_words)
        article["talk_track"] = generate_talk_track(article, position=i)

    context_line = generate_context_line(articles)
    return articles, context_line
