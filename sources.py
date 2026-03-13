# RSS feed sources for CyberBrief
# Each entry: (display_name, feed_url, pillar)
# Pillars: "cyber" | "threat_intel" | "tech_business" | "geopolitical"

FEEDS = [
    # --- Cybersecurity / Breach News (global focus) ---
    # CISA ICS advisories removed — too US-centric and technically deep.
    # Replaced with breach and business-impact focused sources.
    ("CyberScoop", "https://cyberscoop.com/feed/", "cyber"),
    ("Bleeping Computer", "https://www.bleepingcomputer.com/feed/", "cyber"),
    ("Krebs on Security", "https://krebsonsecurity.com/feed/", "cyber"),
    ("SecurityAffairs", "https://securityaffairs.com/feed", "cyber"),
    # Dark Reading: replaces SC Magazine (rebranded to SC World, feed broken) — broad global cyber coverage
    ("Dark Reading", "https://www.darkreading.com/rss.xml", "cyber"),

    # --- EMEA Sources ---
    # NCSC UK: official UK government cybersecurity advisories and alerts
    ("NCSC UK", "https://www.ncsc.gov.uk/api/1/services/v1/report-rss-feed.xml", "cyber"),
    # Infosecurity Magazine: UK-headquartered, strong EMEA enterprise security coverage
    ("Infosecurity Magazine", "https://www.infosecurity-magazine.com/rss/news/", "cyber"),

    # --- Asia-Pacific / Global Sources ---
    # The Record (Recorded Future): strong APAC and Asia/China/Japan/SEA coverage alongside global
    ("The Record", "https://therecord.media/feed", "threat_intel"),
    # Help Net Security: replaces CyberNews (403 blocked) — Slovenian-based, strong EMEA + global coverage
    ("Help Net Security", "https://www.helpnetsecurity.com/feed/", "cyber"),

    # --- Threat Intelligence & Global Context ---
    ("SANS ISC", "https://isc.sans.edu/rssfeed_full.xml", "geopolitical"),
    ("The Register Security", "https://www.theregister.com/security/headlines.atom", "threat_intel"),
    ("Unit 42 (Palo Alto)", "https://unit42.paloaltonetworks.com/feed/", "threat_intel"),

    # --- Tech / AI / Business Impact ---
    ("Ars Technica Security", "https://arstechnica.com/security/feed/", "tech_business"),
    ("SecurityWeek", "https://feeds.feedburner.com/securityweek", "tech_business"),
]

# Keyword scoring weights per pillar.
# Deliberately focuses on breach/incident/business impact — not raw vulnerability advisories.
KEYWORDS = {
    "cyber": [
        # Incident & breach terms (high value)
        "breach", "data breach", "hacked", "hack", "stolen", "leaked", "exposed",
        "ransomware", "extortion", "attack", "incident", "intrusion",
        # Threat actor context
        "APT", "threat actor", "gang", "group", "campaign", "espionage",
        # Malware / methods
        "malware", "phishing", "zero-day", "zero day", "exploit",
    ],
    "tech_business": [
        # Financial / regulatory impact
        "fine", "penalty", "lawsuit", "settlement", "regulatory", "regulation",
        "compliance", "GDPR", "SEC", "ICO", "NIS2", "Dora",
        # Business consequences
        "impact", "cost", "billion", "million", "shares", "stock", "market",
        "M&A", "acquisition", "insurance", "liability", "supply chain",
        # Tech trends
        "AI", "artificial intelligence", "cloud", "data privacy",
    ],
    "geopolitical": [
        "war", "sanctions", "nation-state", "state-sponsored",
        "Ukraine", "Russia", "China", "Iran", "North Korea",
        "cyber warfare", "critical infrastructure", "government",
        "crypto", "bitcoin", "stock market", "tariff", "geopolitical", "global",
    ],
}

# Target article counts per pillar in each digest
PILLAR_TARGETS = {
    "cyber": 3,
    "threat_intel": 1,
    "tech_business": 1,
    "geopolitical": 0,  # geopolitical articles compete in all slots via score
}

# How far back to look for articles (hours)
LOOKBACK_HOURS = 36
