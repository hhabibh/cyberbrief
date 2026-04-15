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


def generate_tldr(article: dict) -> str:
    """
    Generate a 2-3 sentence, factual TLDR for a single article.
    Uses full article text if available, falls back to RSS summary.
    """
    body = article.get("full_text") or article.get("rss_summary", "")
    if not body:
        return _rss_excerpt(article)

    system_prompt = (
        "You are a senior cybersecurity analyst writing a news digest for business leaders and security professionals globally. "
        "Write a single paragraph of continuous prose summarising the article. "
        "Cover: what happened and to whom, the real-world business or operational consequence, and what it signals for the industry. "
        "STRICT WORD LIMIT: 60 to 70 words. Count every word carefully — stop at 70 words. "
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
        "Write the 60-80 word summary:"
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


# Deterministic opener rotation — one per article slot (0-indexed)
# Ensures no two articles in the same digest share the same opening word
_TALK_TRACK_OPENERS = [
    ("What",          "Start the question with the word 'What'."),
    ("To what extent", "Start the question with the phrase 'To what extent'."),
    ("Where",         "Start the question with the word 'Where'."),
    ("Which",         "Start the question with the word 'Which'."),
    ("How",           "Start the question with the word 'How'."),
]


def generate_talk_track(article: dict, position: int = 0) -> str | None:
    """
    Generate a single-sentence seller conversation starter for qualifying articles.
    Returns None if the article doesn't qualify or Groq fails.
    """
    if not _qualifies_for_talk_track(article):
        return None

    tldr = article.get("tldr", "").strip()
    if not tldr:
        return None

    _, opener_instruction = _TALK_TRACK_OPENERS[position % len(_TALK_TRACK_OPENERS)]

    system_prompt = (
        "You are a trusted cybersecurity advisor. You've just shared a news story with a client. "
        "Write ONE open-ended question (15–20 words) that invites the client to reflect on their own situation. "
        "The question must stand alone — no offer of help, no 'happy to', no next steps, no follow-up suggestions. "
        "It should make the client think and want to respond. "
        f"{opener_instruction} "
        "Never start with 'This article', 'I', 'We', or 'As a business leader'. "
        "No product mentions. Plain British English. Write the question directly."
    )

    user_prompt = (
        f"Article title: {article['title']}\n\n"
        f"Summary: {tldr}\n\n"
        "Write the single-sentence advisor talk track:"
    )

    try:
        return _call_bridge(system_prompt, user_prompt, max_tokens=50)
    except Exception as e:
        print(f"  ⚠️  Bridge talk track failed for '{article['title']}': {e}")
        return None


def summarise_all(articles: list[dict]) -> tuple[list[dict], str]:
    """
    Summarise all articles and generate the context line.
    Returns (articles_with_tldrs, context_line).
    """
    for i, article in enumerate(articles):
        article["tldr"] = generate_tldr(article)
        article["talk_track"] = generate_talk_track(article, position=i)

    context_line = generate_context_line(articles)
    return articles, context_line
