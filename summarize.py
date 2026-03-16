"""
summarize.py
Uses Groq (Llama 3.3 70B, free tier) to generate:
  - A 2-3 sentence TLDR for each article
  - A 1-sentence "Context This Week" framing line for the digest header
"""

import os
import random
from datetime import datetime, timezone
from groq import Groq

_client: Groq | None = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GROQ_API_KEY environment variable is not set. "
                "Sign up at https://console.groq.com to get a free key."
            )
        _client = Groq(api_key=api_key)
    return _client


def _call_groq(system_prompt: str, user_prompt: str, max_tokens: int = 200) -> str:
    client = _get_client()
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()


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
        "Rules: between 60 and 80 words — no more, no less. "
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
        return _call_groq(system_prompt, user_prompt, max_tokens=200)
    except Exception as e:
        print(f"  ⚠️  Groq TLDR failed for '{article['title']}': {e} — using RSS excerpt")
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
        return _call_groq(system_prompt, user_prompt, max_tokens=80)
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
    text = (article.get("title", "") + " " + article.get("rss_summary", "")).lower()
    tech_business_score = article.get("scores", {}).get("tech_business", 0)
    if tech_business_score >= 2:
        return True
    return any(kw in text for kw in _BUSINESS_IMPACT_KEYWORDS)


def generate_talk_track(article: dict) -> str | None:
    """
    Generate a single-sentence seller conversation starter for qualifying articles.
    Returns None if the article doesn't qualify or Groq fails.
    """
    if not _qualifies_for_talk_track(article):
        return None

    tldr = article.get("tldr", "").strip()
    if not tldr:
        return None

    # ~40% of the time, nudge toward a gentle offer of help; otherwise pure observation/question
    offer_help = random.random() < 0.4
    help_instruction = (
        "End with a brief, natural offer to help them think through their own exposure — "
        "e.g. 'happy to walk through what this means for you' or similar. Keep it warm, not salesy. "
        if offer_help else
        "Do not offer help or mention next steps — just surface the risk or question."
    )

    system_prompt = (
        "You are a trusted cybersecurity advisor. You've just shared a news story with a client. "
        "Write ONE sentence (15–20 words) that you would say next — not to sell anything, "
        "but to genuinely check whether this story is relevant to the client's situation. "
        "Lead with the risk, challenge, or a direct question. "
        "Vary how you open: sometimes a direct question, sometimes an observation, sometimes a 'have you considered'. "
        "Never start with 'This article', 'I', 'We', or 'As a business leader'. "
        f"{help_instruction} "
        "No product mentions. Plain British English. Write the sentence directly."
    )

    user_prompt = (
        f"Article title: {article['title']}\n\n"
        f"Summary: {tldr}\n\n"
        "Write the single-sentence advisor talk track:"
    )

    try:
        return _call_groq(system_prompt, user_prompt, max_tokens=50)
    except Exception as e:
        print(f"  ⚠️  Groq talk track failed for '{article['title']}': {e}")
        return None


def summarise_all(articles: list[dict]) -> tuple[list[dict], str]:
    """
    Summarise all articles and generate the context line.
    Returns (articles_with_tldrs, context_line).
    """
    for article in articles:
        article["tldr"] = generate_tldr(article)
        article["talk_track"] = generate_talk_track(article)

    context_line = generate_context_line(articles)
    return articles, context_line
