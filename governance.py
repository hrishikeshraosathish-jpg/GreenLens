"""GreenLens — ESG Sub-Score Module (v3)

Each pillar (E, S, G) is scored 0-100 by combining:
  - Keyword sentiment from news headlines (what the press says)
  - Structural proxies from yfinance company info (what the data shows)

v3 changes:
  - Fuzzy keyword matching (handles plurals, hyphens, word reordering)
  - Expanded keyword lists (India-specific: SEBI, BRSR, CSR, POSH)
  - Accepts pre-fetched yfinance info dict (no duplicate API call)
  - Smoother proxy scoring
"""
import re
import yfinance as yf

# ── Keyword lists (expanded for India + global) ───────────────

E_POS = [
    "renewable", "solar", "wind", "emission reduction", "carbon neutral",
    "sustainability", "green energy", "climate action", "net zero",
    "clean energy", "recycling", "circular economy", "biodiversity",
    "ev", "electric vehicle", "carbon credit", "green bond",
    "water conservation", "waste management", "energy efficient",
    "sustainable development", "esg compliant", "carbon footprint",
    "brsr", "green hydrogen", "afforestation",
]
E_NEG = [
    "pollution", "oil spill", "carbon emission", "fossil fuel",
    "deforestation", "environmental fine", "toxic waste", "hazardous",
    "environmental violation", "water contamination", "greenhouse gas",
    "ngt penalty", "environmental clearance denied", "effluent",
    "air quality", "norms violation", "waste dumping", "coal",
    "emission exceed", "cpcb notice", "pollution control",
]

S_POS = [
    "diversity", "inclusion", "community investment", "employee welfare",
    "workplace safety", "human rights", "fair wage", "social impact",
    "employee satisfaction", "health benefit", "philanthropy",
    "csr", "corporate social responsibility", "skill development",
    "women empowerment", "posh compliance", "employee engagement",
    "livelihood", "rural development", "education initiative",
]
S_NEG = [
    "lawsuit", "discrimination", "harassment", "mass layoff",
    "worker strike", "forced labour", "child labour", "unsafe working",
    "employee protest", "wage theft", "labour violation",
    "layoff", "retrenchment", "labor unrest", "sexual harassment",
    "posh complaint", "factory accident", "worker death",
    "sweatshop", "human trafficking", "unfair dismissal",
]

G_POS = [
    "transparency", "independent audit", "compliance", "good governance",
    "board diversity", "accountability", "ethics committee",
    "shareholder rights", "whistleblower", "anti-corruption",
    "sebi compliant", "independent director", "corporate governance",
    "audit committee", "risk management", "succession plan",
    "stakeholder engagement", "regulatory compliance", "disclosure",
]
G_NEG = [
    "fraud", "corruption", "bribery", "accounting scandal",
    "insider trading", "regulatory investigation", "data breach",
    "executive misconduct", "related party transaction", "audit failure",
    "sec investigation", "governance failure",
    "sebi penalty", "sebi ban", "promoter pledge", "loan default",
    "auditor resignation", "qualified opinion", "money laundering",
    "shell company", "round tripping", "pledge shares",
]


# ── Fuzzy keyword matching ─────────────────────────────────────

def _normalize(text: str) -> str:
    """Lowercase, strip hyphens/special chars, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[-–—/]", " ", text)
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _keyword_match(text_norm: str, keyword: str) -> bool:
    """Check if keyword (or its constituent words) appear in text."""
    kw_norm = _normalize(keyword)
    # Direct substring match
    if kw_norm in text_norm:
        return True
    # For multi-word keywords, check if all words appear (handles reordering)
    words = kw_norm.split()
    if len(words) > 1 and all(w in text_norm for w in words):
        return True
    return False


def _keyword_score(titles: list[str], pos: list[str], neg: list[str]) -> dict:
    """
    Count keyword hits with fuzzy matching.
    Returns None score if no keywords match.
    """
    pos_hits = 0
    neg_hits = 0
    matched_pos = []
    matched_neg = []

    for t in titles:
        t_norm = _normalize(t)
        for kw in pos:
            if _keyword_match(t_norm, kw):
                pos_hits += 1
                if kw not in matched_pos:
                    matched_pos.append(kw)
        for kw in neg:
            if _keyword_match(t_norm, kw):
                neg_hits += 1
                if kw not in matched_neg:
                    matched_neg.append(kw)

    total = pos_hits + neg_hits
    if total == 0:
        return {"score": None, "pos_hits": 0, "neg_hits": 0,
                "matched_pos": [], "matched_neg": []}

    raw = (pos_hits / total) * 100
    return {
        "score":       round(raw, 2),
        "pos_hits":    pos_hits,
        "neg_hits":    neg_hits,
        "matched_pos": matched_pos,
        "matched_neg": matched_neg,
    }


# ── Structural proxy scores ───────────────────────────────────

SECTOR_ENV_SCORES = {
    "technology":           70,
    "financial services":   65,
    "communication":        65,
    "healthcare":           60,
    "consumer cyclical":    55,
    "consumer defensive":   55,
    "real estate":          50,
    "industrials":          40,
    "basic materials":      35,
    "utilities":            35,
    "energy":               30,
}


def _environmental_proxy(info: dict) -> float:
    sector = (info.get("sector") or "").lower()
    # Check for yfinance ESG scores first (sometimes available)
    esg = info.get("esgScores") or {}
    if esg.get("environmentScore") is not None:
        return round(100 - esg["environmentScore"], 2)

    # Sector-based with smoother mapping
    for key, score in SECTOR_ENV_SCORES.items():
        if key in sector:
            return float(score)
    return 50.0


def _social_proxy(info: dict) -> float:
    employees = info.get("fullTimeEmployees") or 0
    sector = (info.get("sector") or "").lower()

    esg = info.get("esgScores") or {}
    if esg.get("socialScore") is not None:
        return round(100 - esg["socialScore"], 2)

    # Smooth curve based on employee count
    import math
    if employees > 0:
        # log scale: 100 emp → 40, 1k → 48, 10k → 55, 100k → 63, 1M → 70
        base = 32 + math.log10(max(employees, 10)) * 8
    else:
        base = 45.0

    if "technology" in sector or "health" in sector:
        base += 5
    elif "energy" in sector or "mining" in sector:
        base -= 5

    return round(min(max(base, 10), 90), 2)


def _governance_proxy(info: dict) -> float:
    esg = info.get("esgScores") or {}
    if esg.get("governanceScore") is not None:
        return round(100 - esg["governanceScore"], 2)

    score = 50.0

    risk_fields = {
        "auditRisk":        12,
        "boardRisk":        12,
        "overallRisk":      8,
        "compensationRisk": 8,
    }

    for field, max_delta in risk_fields.items():
        val = info.get(field)
        if val is not None:
            # 1-10 scale: 1 → +max_delta, 5 → 0, 10 → -max_delta
            adjustment = max_delta * (5 - val) / 4
            score += adjustment

    return round(min(max(score, 10), 90), 2)


# ── Fetch company info ─────────────────────────────────────────

def fetch_company_info(ticker: str, preloaded_info: dict = None) -> dict:
    """
    Get company info. Pass preloaded_info from financials.py
    to avoid a duplicate yfinance API call.
    """
    try:
        info = preloaded_info or yf.Ticker(ticker).info
        return {
            "name":      info.get("longName", ticker),
            "sector":    info.get("sector", "—"),
            "industry":  info.get("industry", "—"),
            "country":   info.get("country", "—"),
            "employees": info.get("fullTimeEmployees", "—"),
            "website":   info.get("website", ""),
            "_raw":      info,
        }
    except Exception:
        return {"name": ticker, "sector": "—", "industry": "—",
                "country": "—", "employees": "—", "website": "", "_raw": {}}


# ── Main ESG scoring function ──────────────────────────────────

def score_governance(ticker: str, trend: list, preloaded_info: dict = None) -> dict:
    """
    Compute E, S, G sub-scores by blending:
      - Keyword analysis from news headlines (60% weight when available)
      - Structural proxy from company data (40% weight, or 100% if no keywords)

    Args:
        ticker: NSE/BSE ticker string
        trend: list of dicts with 'title' key (from sentiment module)
        preloaded_info: optional yfinance info dict to avoid duplicate call

    Returns e_score, s_score, g_score, governance_score, drivers.
    """
    company_info = fetch_company_info(ticker, preloaded_info)
    raw_info = company_info.get("_raw", {})

    titles = [h["title"] for h in trend if h.get("title")]

    # Keyword scores
    e_kw = _keyword_score(titles, E_POS, E_NEG)
    s_kw = _keyword_score(titles, S_POS, S_NEG)
    g_kw = _keyword_score(titles, G_POS, G_NEG)

    # Structural proxy scores
    e_proxy = _environmental_proxy(raw_info)
    s_proxy = _social_proxy(raw_info)
    g_proxy = _governance_proxy(raw_info)

    # Blend: 60% keyword + 40% proxy when keywords exist
    def _blend(kw_result, proxy):
        if kw_result["score"] is not None:
            return round(kw_result["score"] * 0.6 + proxy * 0.4, 2)
        return round(proxy, 2)

    e_score = _blend(e_kw, e_proxy)
    s_score = _blend(s_kw, s_proxy)
    g_score = _blend(g_kw, g_proxy)

    gov_score = round((e_score + s_score + g_score) / 3, 2)

    # Build drivers
    drivers = []
    for name, kw, score in [("Environmental", e_kw, e_score),
                             ("Social", s_kw, s_score),
                             ("Governance", g_kw, g_score)]:
        if kw["neg_hits"] > 0:
            drivers.append(f"{name}: {kw['neg_hits']} negative signals "
                           f"({', '.join(kw['matched_neg'][:3])})")
        if kw["pos_hits"] > 0:
            drivers.append(f"{name}: {kw['pos_hits']} positive signals "
                           f"({', '.join(kw['matched_pos'][:3])})")
        if kw["score"] is None:
            drivers.append(f"{name}: no keyword matches — "
                           f"score based on sector/structure ({score:.0f})")

    clean_info = {k: v for k, v in company_info.items() if k != "_raw"}

    return {
        "e_score":          e_score,
        "s_score":          s_score,
        "g_score":          g_score,
        "governance_score": gov_score,
        "company_info":     clean_info,
        "drivers":          drivers,
        "keyword_detail": {
            "environmental": e_kw,
            "social":        s_kw,
            "governance":    g_kw,
        },
    }