"""
format_message.py
Formats the digest into two variants:
  - Webex: Markdown (subset supported by Webex)
  - Telegram: HTML (supported by Telegram Bot API with parse_mode=HTML)
"""

from datetime import datetime, timezone
import pytz

LONDON_TZ = pytz.timezone("Europe/London")


def _age_label(published_iso: str | None) -> str:
    """Return age in hours always, wrapped in brackets e.g. '(2 hrs ago)', '(47 hrs ago)'."""
    if not published_iso:
        return ""
    try:
        pub = datetime.fromisoformat(published_iso)
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta_hours = int((now - pub).total_seconds() / 3600)
        if delta_hours < 1:
            return "(just now)"
        elif delta_hours == 1:
            return "(1 hr ago)"
        else:
            return f"({delta_hours} hrs ago)"
    except Exception:
        return ""

# Keyword → emoji mapping. Checked in order; first match wins. Fallback is 📰.
_TITLE_EMOJI_RULES = [
    # Vehicles & energy
    (["ev ", "electric vehicle", "charger", "charging", "evse"],        "⚡"),
    (["solar", "wind farm", "power grid", "energy"],                    "🔋"),
    # Healthcare / pharma
    (["hospital", "medtech", "nhs", "healthcare", "patient", "pharma",
      "medical", "health"],                                             "🏥"),
    # Finance / banking / crypto
    (["bank", "banking", "financial", "finance", "stock", "market",
      "crypto", "bitcoin", "wallet", "payment", "fraud"],              "🏦"),
    (["ransomware", "extortion", "ransom"],                             "💰"),
    # Government / espionage / military
    (["espionage", "military", "intelligence", "government", "ministry",
      "defence", "defense", "apt", "nation-state", "state-sponsored"], "🕵️"),
    (["war", "warfare", "conflict", "weapon"],                          "⚔️"),
    # Supply chain / software
    (["supply chain", "polyfill", "dependency", "package", "npm",
      "pypi", "open source"],                                           "⛓️"),
    # Cloud / infrastructure
    (["cloud", "aws", "azure", "gcp", "s3", "bucket"],                 "☁️"),
    (["critical infrastructure", "power", "water", "utility",
      "industrial", "ics", "scada"],                                    "🏭"),
    # AI / technology
    (["ai ", "artificial intelligence", "llm", "copilot", "gpt",
      "machine learning", "deepfake"],                                  "🤖"),
    # Data breach / leak
    (["breach", "leak", "exposed", "stolen", "data theft",
      "database", "records"],                                           "💧"),
    # Phishing / social engineering
    (["phish", "smish", "social engineering", "credential"],           "🎣"),
    # Malware / exploit
    (["malware", "wiper", "trojan", "botnet", "zero-day", "zero day",
      "exploit", "backdoor", "rootkit"],                                "🦠"),
    # Regulation / compliance / legal
    (["fine", "penalty", "gdpr", "ico", "sec ", "regulation",
      "compliance", "lawsuit", "ruling", "court"],                     "⚖️"),
    # Authentication / access
    (["password", "mfa", "authentication", "identity", "access",
      "credential"],                                                    "🔑"),
    # Mobile / apps
    (["android", "ios", "mobile", "app store", "smartphone"],         "📱"),
    # Generic cyber fallback
    (["hack", "attack", "cyber", "vulnerability", "security",
      "incident", "intrusion"],                                         "🔓"),
]


def _title_emoji(title: str) -> str:
    """Return a contextually relevant emoji based on keywords in the article title."""
    lower = title.lower()
    for keywords, emoji in _TITLE_EMOJI_RULES:
        if any(kw in lower for kw in keywords):
            return emoji
    return "📰"


_FALLBACK_EMOJIS = ["📰", "🌐", "📡", "🛡️", "🔍"]


def _assign_unique_emojis(articles: list[dict]) -> list[str]:
    """
    Assign one emoji per article ensuring no two articles in the digest share the same icon.
    For each article, walks all matching rules in order and picks the first emoji not yet used.
    Falls back to _FALLBACK_EMOJIS if all rule matches are exhausted.
    """
    used: set[str] = set()
    result: list[str] = []
    for article in articles:
        lower = article["title"].lower()
        assigned = None
        # Try each rule in order; skip if emoji already used
        for keywords, emoji in _TITLE_EMOJI_RULES:
            if any(kw in lower for kw in keywords) and emoji not in used:
                assigned = emoji
                break
        # If all matching rule emojis are taken, try fallbacks
        if assigned is None:
            for fb in _FALLBACK_EMOJIS:
                if fb not in used:
                    assigned = fb
                    break
        # Last resort (more than 5 + fallback clashes — practically impossible)
        if assigned is None:
            assigned = "📰"
        used.add(assigned)
        result.append(assigned)
    return result


# Average adult reading speed (words per minute)
_WPM = 238


def _word_count(text: str) -> int:
    return len(text.split()) if text else 0


def _read_time_min(words: int) -> int:
    """Return reading time in whole minutes, minimum 1."""
    return max(1, round(words / _WPM))


def _reading_times(articles: list[dict]) -> tuple[int, int]:
    """
    Returns (full_article_minutes, tldr_minutes).
    Full article uses scraped body text (falls back to RSS summary if unavailable).
    TLDR uses the generated summary text.
    """
    full_words = sum(
        _word_count(a.get("full_text") or a.get("rss_summary", ""))
        for a in articles
    )
    tldr_words = sum(
        _word_count(a.get("tldr", "")) + _word_count(a.get("talk_track") or "")
        for a in articles
    )
    return _read_time_min(full_words), _read_time_min(tldr_words)


def _uk_date_string() -> str:
    now = datetime.now(LONDON_TZ)
    return f"{now.strftime('%A')}, {now.day} {now.strftime('%B %Y')}"  # e.g. "Wednesday, 11 March 2026"


# ── Sunday Engagement Digest ──────────────────────────────────────────────────

def format_webex_card_sunday(top_articles: list[dict]) -> dict:
    """Adaptive Card for the Sunday 'Most Read This Week' digest."""
    date_str = _uk_date_string()
    medals = ["🥇", "🥈", "🥉"]
    body = [
        {"type": "TextBlock", "text": f"🏆 CyberBrief | Most Read This Week · {date_str}",
         "weight": "Bolder", "size": "Large", "wrap": True, "color": "Accent"},
        {"type": "TextBlock", "text": "Here's what your peers clicked most this week.",
         "wrap": True, "isSubtle": True, "spacing": "Small"},
        {"type": "Separator", "spacing": "Medium"},
    ]
    for i, article in enumerate(top_articles):
        medal = medals[i] if i < len(medals) else f"#{i+1}"
        link_url = article.get("short_url") or article["url"]
        clicks = article.get("clicks", 0)
        read_min = _read_time_min(_word_count(article.get("full_text") or article.get("tldr", "")))
        click_label = f"{clicks} click{'s' if clicks != 1 else ''}"
        block = {
            "type": "Container", "style": "emphasis", "spacing": "Medium",
            "items": [
                {"type": "TextBlock", "text": f"{medal} {article['title']}",
                 "weight": "Default", "color": "Accent", "wrap": True, "size": "Medium"},
                {"type": "TextBlock",
                 "text": f"· {article['source']}  👁 {click_label}  ⏱ {read_min} min read",
                 "isSubtle": True, "wrap": True, "spacing": "None", "size": "Small"},
                {"type": "TextBlock",
                 "text": f"{article.get('tldr', '')} [→]({link_url})",
                 "wrap": True, "spacing": "Small"},
            ],
        }
        body.append(block)
    body.append({"type": "TextBlock",
                 "text": "👀 Next week's leaderboard starts Monday — click what catches your eye.",
                 "isSubtle": True, "wrap": True, "spacing": "Medium", "size": "Small"})
    return {"contentType": "application/vnd.microsoft.card.adaptive",
            "content": {"type": "AdaptiveCard", "version": "1.3", "body": body}}


def format_webex_sunday(top_articles: list[dict]) -> str:
    """Markdown fallback for Sunday Webex delivery."""
    date_str = _uk_date_string()
    medals = ["🥇", "🥈", "🥉"]
    lines = [f"### 🏆 CyberBrief | Most Read This Week · {date_str}", "",
             "Here's what your peers clicked most this week.", "", "---", ""]
    for i, article in enumerate(top_articles):
        medal = medals[i] if i < len(medals) else f"#{i+1}"
        link_url = article.get("short_url") or article["url"]
        clicks = article.get("clicks", 0)
        read_min = _read_time_min(_word_count(article.get("full_text") or article.get("tldr", "")))
        click_label = f"{clicks} click{'s' if clicks != 1 else ''}"
        lines += [f"**{medal} {article['title']}** *· {article['source']}  👁 {click_label}  ⏱ {read_min} min read*",
                  "", f"{article.get('tldr', '')} [→]({link_url})", ""]
    lines.append("👀 *Next week's leaderboard starts Monday — click what catches your eye.*")
    return "\n".join(lines)


def format_telegram_sunday(top_articles: list[dict]) -> str:
    """HTML-formatted Sunday leaderboard for Telegram."""
    date_str = _uk_date_string()
    medals = ["🥇", "🥈", "🥉"]
    lines = [f"🏆 <b>CyberBrief | Most Read This Week · {date_str}</b>", "",
             "Here's what your peers clicked most this week.", "", "━━━━━━━━━━━━━━━", ""]
    for i, article in enumerate(top_articles):
        medal = medals[i] if i < len(medals) else f"#{i+1}"
        link_url = article.get("short_url") or article["url"]
        clicks = article.get("clicks", 0)
        read_min = _read_time_min(_word_count(article.get("full_text") or article.get("tldr", "")))
        click_label = f"{clicks} click{'s' if clicks != 1 else ''}"
        lines += [
            f"{medal} <b>{_escape_html(article['title'])}</b>",
            f"<i>· {_escape_html(article['source'])}  👁 {click_label}  ⏱ {read_min} min read</i>",
            "", f"{_escape_html(article.get('tldr', ''))} <a href=\"{link_url}\">→</a>", "",
        ]
    lines += ["━━━━━━━━━━━━━━━",
              "👀 <i>Next week's leaderboard starts Monday — click what catches your eye.</i>"]
    return "\n".join(lines)


# ── Weekday digest ─────────────────────────────────────────────────────────────

def format_webex(articles: list[dict], context_line: str) -> str:
    """
    Returns a Markdown-formatted string for Webex.
    Webex supports: bold (**), italic (*_), links [text](url), bullet lists (-)
    Used as fallback text for clients that don't render Adaptive Cards.
    """
    date_str = _uk_date_string()
    lines = [
        f"### 🔐 CyberBrief | {date_str}",
        "",
        f"🌍 **Context:** {context_line}",
        "",
        "---",
        "",
    ]

    for i, (article, emoji) in enumerate(zip(articles, _assign_unique_emojis(articles)), start=1):
        age = _age_label(article.get("published"))
        link_url = article.get('short_url') or article['url']
        tldr_linked = f"{article['tldr']} [→]({link_url})"
        source_part = f"{article['source']} {age}" if age else article['source']
        title_line = f"**{emoji} {i}. {article['title']}** *· {source_part}*"
        lines += [title_line, "", f"{tldr_linked}"]
        talk_track = article.get("talk_track")
        if talk_track:
            lines += ["", f"💬 *Talk track:* {talk_track}"]
        lines.append("")

    full_min, tldr_min = _reading_times(articles)
    lines += [
        "---",
        f"💡 *{len(articles)} articles · Full read: ~{full_min} min · This digest: ~{tldr_min} min*",
        "",
        "👀 *Curious what your peers clicked most this week? Find out Sunday.*",
    ]

    return "\n".join(lines)


def format_webex_card(articles: list[dict], context_line: str) -> dict:
    """
    Returns an Adaptive Card JSON payload for Webex.
    Renders as a bordered card with a header, context line, and one styled
    block per article. Falls back to plain markdown for older clients.
    """
    date_str = _uk_date_string()
    full_min, tldr_min = _reading_times(articles)
    emojis = _assign_unique_emojis(articles)

    # Header block
    body = [
        {
            "type": "TextBlock",
            "text": f"🔐 CyberBrief | {date_str}",
            "weight": "Bolder",
            "size": "Large",
            "wrap": True,
            "color": "Accent",
        },
        {
            "type": "TextBlock",
            "text": f"🌍 {context_line}",
            "wrap": True,
            "isSubtle": True,
            "spacing": "Small",
        },
        {
            "type": "Separator",
            "spacing": "Medium",
        },
    ]

    # One Container per article — gives the bordered block effect
    for i, (article, emoji) in enumerate(zip(articles, emojis), start=1):
        age = _age_label(article.get("published"))
        link_url = article.get("short_url") or article["url"]
        source_part = f"{article['source']} {age}" if age else article["source"]

        article_block = {
            "type": "Container",
            "style": "emphasis",
            "spacing": "Medium",
            "items": [
                {
                    "type": "TextBlock",
                    "text": f"{emoji} {i}. {article['title']}",
                    "weight": "Default",
                    "color": "Accent",
                    "wrap": True,
                    "size": "Medium",
                },
                {
                    "type": "TextBlock",
                    "text": f"· {source_part}",
                    "isSubtle": True,
                    "wrap": True,
                    "spacing": "None",
                    "size": "Small",
                },
                {
                    "type": "TextBlock",
                    "text": f"{article['tldr']} [→]({link_url})",
                    "wrap": True,
                    "spacing": "Small",
                },
            ],
        }
        talk_track = article.get("talk_track")
        if talk_track:
            article_block["items"].append({
                "type": "TextBlock",
                "text": f"💬 **Talk track:** {talk_track}",
                "wrap": True,
                "spacing": "Small",
                "isSubtle": True,
            })
        body.append(article_block)

    # Footer
    body.append(
        {
            "type": "TextBlock",
            "text": f"💡 {len(articles)} articles · Full read: ~{full_min} min · This digest: ~{tldr_min} min",
            "isSubtle": True,
            "wrap": True,
            "spacing": "Medium",
            "size": "Small",
        }
    )
    body.append(
        {
            "type": "TextBlock",
            "text": "👀 Curious what your peers clicked most this week? Find out Sunday.",
            "isSubtle": True,
            "wrap": True,
            "spacing": "None",
            "size": "Small",
        }
    )

    return {
        "contentType": "application/vnd.microsoft.card.adaptive",
        "content": {
            "type": "AdaptiveCard",
            "version": "1.3",
            "body": body,
        },
    }


def format_telegram(articles: list[dict], context_line: str) -> str:
    """
    Returns an HTML-formatted string for Telegram.
    Telegram HTML supports: <b>, <i>, <a href="">, <code>, <pre>
    """
    date_str = _uk_date_string()
    lines = [
        f"🔐 <b>CyberBrief | {date_str}</b>",
        "",
        f"🌍 <b>Context:</b> {_escape_html(context_line)}",
        "",
        "━━━━━━━━━━━━━━━",
        "",
    ]

    for i, (article, emoji) in enumerate(zip(articles, _assign_unique_emojis(articles)), start=1):
        age = _age_label(article.get("published"))
        link_url = article.get('short_url') or article['url']
        tldr_linked = f"{_escape_html(article['tldr'])} <a href=\"{link_url}\">→</a>"
        source_part = f"{_escape_html(article['source'])} {age}" if age else _escape_html(article['source'])
        title_line = f"{emoji} <b>{i}. {_escape_html(article['title'])}</b> <i>· {source_part}</i>"
        lines += [title_line, "", tldr_linked]
        talk_track = article.get("talk_track")
        if talk_track:
            lines += ["", f"💬 <i>Talk track: {_escape_html(talk_track)}</i>"]
        lines.append("")

    full_min, tldr_min = _reading_times(articles)
    lines += [
        "━━━━━━━━━━━━━━━",
        f"💡 <i>{len(articles)} articles · Full read: ~{full_min} min · This digest: ~{tldr_min} min</i>",
        "",
        "👀 <i>Curious what your peers clicked most this week? Find out Sunday.</i>",
    ]

    return "\n".join(lines)


def _escape_html(text: str) -> str:
    """Escape characters that would break Telegram HTML parsing."""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )
