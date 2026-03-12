"""GreenLens — Enhancements Module (v1)

Plugs into scorer.py to add:
  1. Greenwashing detection
  2. Sector normalization
  3. Source quality weighting
  4. Sentiment-Financial divergence alerts
  5. Result caching
"""
import time
import re
from functools import lru_cache

# ═══════════════════════════════════════════════════════════════
# 1. GREENWASHING DETECTION
# ═══════════════════════════════════════════════════════════════
# Flags when a company "talks green but acts dirty":
#   - High positive ESG keywords + dirty sector
#   - High sentiment + low governance
#   - Positive E keywords but negative E proxy (sector-based)

DIRTY_SECTORS = [
    "energy", "oil", "gas", "mining", "basic materials",
    "utilities", "coal", "chemicals", "cement", "steel",
]

GREENWASH_PHRASES = [
    "carbon neutral by", "net zero by", "committed to sustainability",
    "green initiative", "eco friendly", "sustainable future",
    "climate positive", "zero emission target", "green transition",
]


def detect_greenwashing(result: dict) -> dict:
    """
    Analyze a scored company result for greenwashing signals.

    Returns:
        {
            "flag": bool,
            "level": "NONE" | "MILD" | "STRONG",
            "signals": list[str],
            "score_penalty": float (0-15 points to subtract)
        }
    """
    signals = []
    penalty = 0.0

    sector = (result.get("company_info", {}).get("sector", "") or "").lower()
    e_score = result.get("e_score", 50)
    s_score = result.get("s_score", 50)
    g_score = result.get("g_score", 50)
    sent_score = result.get("sentiment_score", 50)
    fin_score = result.get("financial_score", 50)
    kw_detail = result.get("keyword_detail", {})

    e_kw = kw_detail.get("environmental", {})
    e_pos_hits = e_kw.get("pos_hits", 0)
    e_neg_hits = e_kw.get("neg_hits", 0)

    # ── Signal 1: Dirty sector but lots of positive E keywords ──
    is_dirty = any(d in sector for d in DIRTY_SECTORS)
    if is_dirty and e_pos_hits >= 3 and e_neg_hits == 0:
        signals.append(
            f"High-pollution sector ({sector}) with only positive environmental "
            f"coverage — possible PR-driven narrative"
        )
        penalty += 5

    # ── Signal 2: Positive sentiment but weak governance ──
    if sent_score > 65 and g_score < 40:
        signals.append(
            f"Positive media sentiment ({sent_score:.0f}) but weak governance "
            f"({g_score:.0f}) — good PR may be masking structural issues"
        )
        penalty += 4

    # ── Signal 3: High E score but dirty sector fundamentals ──
    if is_dirty and e_score > 65:
        signals.append(
            f"Environmental score ({e_score:.0f}) seems high for a {sector} "
            f"company — verify with actual emissions data"
        )
        penalty += 3

    # ── Signal 4: Greenwash phrases in headlines ──
    trend = result.get("trend", [])
    titles = [h.get("title", "").lower() for h in trend]
    gw_matches = []
    for phrase in GREENWASH_PHRASES:
        for t in titles:
            if phrase in t:
                if phrase not in gw_matches:
                    gw_matches.append(phrase)
    if gw_matches and is_dirty:
        signals.append(
            f"Greenwashing language detected in headlines: "
            f"{', '.join(gw_matches[:3])}"
        )
        penalty += 3

    # ── Signal 5: Sentiment-ESG disconnect ──
    # High overall sentiment but all E/S/G sub-scores are below average
    if sent_score > 60 and e_score < 45 and s_score < 45 and g_score < 45:
        signals.append(
            "Positive sentiment doesn't match weak ESG fundamentals across "
            "all three pillars"
        )
        penalty += 5

    # Cap penalty
    penalty = min(penalty, 15)

    if not signals:
        level = "NONE"
    elif len(signals) <= 2 and penalty <= 5:
        level = "MILD"
    else:
        level = "STRONG"

    return {
        "flag": len(signals) > 0,
        "level": level,
        "signals": signals,
        "score_penalty": round(penalty, 2),
    }


# ═══════════════════════════════════════════════════════════════
# 2. SECTOR NORMALIZATION
# ═══════════════════════════════════════════════════════════════
# Adjusts raw ESG score relative to sector average so that
# a steel company scoring 55 isn't penalized vs an IT company at 65.

SECTOR_BENCHMARKS = {
    "Technology":           {"avg": 68, "std": 12},
    "Financial Services":   {"avg": 62, "std": 10},
    "Communication":        {"avg": 60, "std": 11},
    "Healthcare":           {"avg": 64, "std": 11},
    "Consumer Cyclical":    {"avg": 58, "std": 12},
    "Consumer Defensive":   {"avg": 60, "std": 10},
    "Industrials":          {"avg": 50, "std": 13},
    "Basic Materials":      {"avg": 45, "std": 14},
    "Energy":               {"avg": 42, "std": 15},
    "Utilities":            {"avg": 48, "std": 13},
    "Real Estate":          {"avg": 55, "std": 12},
}


def normalize_sector_score(raw_score: float, sector: str) -> dict:
    """
    Normalize score relative to sector.

    Returns:
        {
            "normalized_score": float (0-100),
            "sector_avg": float,
            "vs_sector": float (positive = above average),
            "percentile_label": str ("Top 10%", "Above Avg", etc.)
        }
    """
    benchmark = None
    sector_lower = sector.lower()
    for key, val in SECTOR_BENCHMARKS.items():
        if key.lower() in sector_lower or sector_lower in key.lower():
            benchmark = val
            break

    if not benchmark:
        benchmark = {"avg": 55, "std": 12}

    avg = benchmark["avg"]
    std = benchmark["std"]

    # How many std devs above/below sector mean
    z = (raw_score - avg) / std if std > 0 else 0

    # Normalized: map z-score to 0-100 with 50 as sector average
    # z=0 → 50, z=1 → 65, z=2 → 80, z=-1 → 35, z=-2 → 20
    normalized = 50 + z * 15
    normalized = max(5, min(95, normalized))

    vs_sector = round(raw_score - avg, 1)

    if z >= 1.5:
        label = "Top 10%"
    elif z >= 0.75:
        label = "Top 25%"
    elif z >= 0:
        label = "Above Avg"
    elif z >= -0.75:
        label = "Below Avg"
    elif z >= -1.5:
        label = "Bottom 25%"
    else:
        label = "Bottom 10%"

    return {
        "normalized_score": round(normalized, 2),
        "sector_avg": avg,
        "vs_sector": vs_sector,
        "percentile_label": label,
    }


# ═══════════════════════════════════════════════════════════════
# 3. SOURCE QUALITY WEIGHTING
# ═══════════════════════════════════════════════════════════════
# Higher-quality sources get more influence on sentiment.

TIER_1_SOURCES = [
    "reuters", "bloomberg", "financial times", "wall street journal",
    "economic times", "livemint", "mint", "moneycontrol", "cnbc",
    "bbc", "the hindu", "business standard", "ndtv", "nikkei",
    "forbes", "the guardian", "associated press", "ap news",
]

TIER_2_SOURCES = [
    "business today", "outlook", "india today", "firstpost",
    "the wire", "scroll", "quartz", "techcrunch", "the verge",
    "yahoo finance", "marketwatch", "investopedia", "seeking alpha",
    "business insider", "the print", "deccan herald",
]

# Everything else is Tier 3 (blogs, unknown sources)


def get_source_weight(source: str) -> float:
    """
    Returns a multiplier for the source:
      Tier 1 (major financial/news): 1.5x
      Tier 2 (reputable secondary):  1.0x
      Tier 3 (blogs/unknown):        0.6x
    """
    if not source:
        return 0.6

    source_lower = source.lower().strip()

    for t1 in TIER_1_SOURCES:
        if t1 in source_lower:
            return 1.5

    for t2 in TIER_2_SOURCES:
        if t2 in source_lower:
            return 1.0

    return 0.6


def get_source_tier(source: str) -> int:
    """Returns 1, 2, or 3."""
    w = get_source_weight(source)
    if w >= 1.5:
        return 1
    elif w >= 1.0:
        return 2
    return 3


# ═══════════════════════════════════════════════════════════════
# 4. SENTIMENT-FINANCIAL DIVERGENCE ALERT
# ═══════════════════════════════════════════════════════════════

def detect_divergence(sentiment_score: float, financial_score: float) -> dict:
    """
    Flag when sentiment and financials tell different stories.

    Big divergence = the market might be mispricing the company.

    Returns:
        {
            "flag": bool,
            "type": "NONE" | "HYPE_RISK" | "HIDDEN_VALUE",
            "message": str,
            "gap": float
        }
    """
    gap = round(sentiment_score - financial_score, 2)
    abs_gap = abs(gap)

    if abs_gap < 15:
        return {
            "flag": False,
            "type": "NONE",
            "message": "Sentiment and financials are aligned",
            "gap": gap,
        }

    if gap > 0:
        # Sentiment >> Financials = possible hype
        if abs_gap > 30:
            msg = (
                f"Sentiment ({sentiment_score:.0f}) far exceeds financial health "
                f"({financial_score:.0f}) — market may be overly optimistic. "
                f"Verify fundamentals before investing."
            )
        else:
            msg = (
                f"Sentiment ({sentiment_score:.0f}) is higher than financials "
                f"({financial_score:.0f}) — positive news may not be backed by numbers."
            )
        return {
            "flag": True,
            "type": "HYPE_RISK",
            "message": msg,
            "gap": gap,
        }
    else:
        # Financials >> Sentiment = possible undervalued / hidden value
        if abs_gap > 30:
            msg = (
                f"Financials ({financial_score:.0f}) are much stronger than sentiment "
                f"({sentiment_score:.0f}) — company may be undervalued. "
                f"Negative press could be temporary."
            )
        else:
            msg = (
                f"Financials ({financial_score:.0f}) outperform sentiment "
                f"({sentiment_score:.0f}) — market may be underpricing this stock."
            )
        return {
            "flag": True,
            "type": "HIDDEN_VALUE",
            "message": msg,
            "gap": gap,
        }


# ═══════════════════════════════════════════════════════════════
# 5. RESULT CACHING
# ═══════════════════════════════════════════════════════════════

_cache = {}
CACHE_TTL = 300  # 5 minutes


def get_cached(company: str) -> dict | None:
    """Return cached result if fresh enough."""
    key = company.lower().strip()
    if key in _cache:
        entry = _cache[key]
        if time.time() - entry["ts"] < CACHE_TTL:
            return entry["result"]
        else:
            del _cache[key]
    return None


def set_cache(company: str, result: dict):
    """Cache a scoring result."""
    key = company.lower().strip()
    _cache[key] = {"result": result, "ts": time.time()}


def clear_cache():
    """Clear all cached results."""
    _cache.clear()


# ═══════════════════════════════════════════════════════════════
# APPLY ALL ENHANCEMENTS TO A SCORED RESULT
# ═══════════════════════════════════════════════════════════════

def enhance_result(result: dict) -> dict:
    """
    Takes a scored result from scorer.score_company() and adds:
      - greenwashing detection
      - sector normalization
      - divergence alert
      - source quality breakdown
      - applies greenwashing penalty to final score

    Call this AFTER score_company() returns.
    """
    # 1. Greenwashing
    gw = detect_greenwashing(result)
    result["greenwashing"] = gw

    # Apply penalty to final score
    if gw["score_penalty"] > 0:
        original = result["final_score"]
        adjusted = max(0, round(original - gw["score_penalty"], 2))
        result["final_score"] = adjusted
        result["score_before_penalty"] = original

        # Recalculate flag after penalty
        if adjusted <= 40:
            result["flag"] = "HIGH"
        elif adjusted <= 60:
            result["flag"] = "MEDIUM"
        else:
            result["flag"] = "LOW"

    # 2. Sector normalization
    sector = result.get("company_info", {}).get("sector", "")
    norm = normalize_sector_score(result["final_score"], sector)
    result["sector_analysis"] = norm

    # 3. Divergence alert
    div = detect_divergence(
        result.get("sentiment_score", 50),
        result.get("financial_score", 50),
    )
    result["divergence"] = div

    # 4. Source quality breakdown
    trend = result.get("trend", [])
    tier_counts = {1: 0, 2: 0, 3: 0}
    for h in trend:
        tier = get_source_tier(h.get("source", ""))
        tier_counts[tier] += 1
    result["source_quality"] = {
        "tier_1": tier_counts[1],
        "tier_2": tier_counts[2],
        "tier_3": tier_counts[3],
        "total": sum(tier_counts.values()),
    }

    return result