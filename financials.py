"""GreenLens — Financial Health Module (v3): Smooth scoring + weighted components."""
import yfinance as yf


def fetch_financials(ticker: str) -> dict:
    try:
        info = yf.Ticker(ticker).info
        return {
            "trailingPE":       info.get("trailingPE"),
            "debtToEquity":     info.get("debtToEquity"),
            "revenueGrowth":    info.get("revenueGrowth"),
            "profitMargins":    info.get("profitMargins"),
            "returnOnEquity":   info.get("returnOnEquity"),
            "marketCap":        info.get("marketCap"),
            "totalRevenue":     info.get("totalRevenue"),
            "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
            "fiftyTwoWeekLow":  info.get("fiftyTwoWeekLow"),
            "currentPrice":     info.get("currentPrice") or info.get("regularMarketPrice"),
            "currency":         info.get("currency", "INR"),
        }
    except Exception:
        return {}


# ── Smooth scoring helpers ──────────────────────────────────────────────────

def _clamp(val, lo=0.0, hi=100.0):
    return max(lo, min(hi, val))


def _linear_map(val, bad, good):
    """
    Map val linearly: bad → 10, good → 90.
    Values beyond good → up to 95, beyond bad → down to 5.
    """
    if good == bad:
        return 50.0
    ratio = (val - bad) / (good - bad)
    return _clamp(10 + ratio * 80, 5, 95)


# ── Component scorers (all return 0-100) ────────────────────────────────────

def _score_pe(pe):
    """P/E: sweet spot ~15. Too high = overvalued, too low = problems."""
    if pe is None or pe <= 0:
        return 50.0
    if pe <= 25:
        # 5 → 85, 15 → 80, 25 → 60  (low-mid PE is good)
        return _clamp(85 - (pe - 5) * 1.25, 55, 90)
    else:
        # 25 → 60, 50 → 30, 100+ → 10
        return _clamp(60 - (pe - 25) * 0.8, 5, 60)


def _score_de(de):
    """Debt/Equity: lower is better. yfinance returns as percentage (e.g. 45 = 45%)."""
    if de is None or de < 0:
        return 50.0
    # 0 → 95, 50 → 70, 100 → 50, 200 → 25, 400+ → 5
    return _clamp(95 - de * 0.45, 5, 95)


def _score_rev_growth(rg):
    """Revenue growth: higher is better. Comes as decimal (0.15 = 15%)."""
    if rg is None:
        return 50.0
    pct = rg * 100  # convert to percentage
    # -20% → 10, 0% → 40, 10% → 60, 25% → 80, 40%+ → 95
    return _clamp(40 + pct * 2, 5, 95)


def _score_profit_margin(pm):
    """Profit margin: higher is better. Comes as decimal."""
    if pm is None:
        return 50.0
    pct = pm * 100
    # -10% → 10, 0% → 30, 10% → 55, 20% → 75, 35%+ → 95
    return _clamp(30 + pct * 2.5, 5, 95)


def _score_roe(roe):
    """ROE: higher is better. Comes as decimal."""
    if roe is None:
        return 50.0
    pct = roe * 100
    # -10% → 10, 0% → 30, 10% → 55, 20% → 75, 30%+ → 90
    return _clamp(30 + pct * 2.5, 5, 95)


def _score_52w_position(data):
    """How close is current price to 52-week high? Higher = healthier."""
    high = data.get("fiftyTwoWeekHigh")
    low = data.get("fiftyTwoWeekLow")
    price = data.get("currentPrice")
    if not all([high, low, price]) or high == low:
        return 50.0
    position = (price - low) / (high - low)  # 0 = at low, 1 = at high
    return _clamp(20 + position * 70, 10, 95)


# ── Main scorer ─────────────────────────────────────────────────────────────

# Weights reflect ESG-relevance: debt discipline and returns matter more
COMPONENT_WEIGHTS = {
    "P/E Ratio":        0.15,
    "Debt/Equity":      0.25,   # leverage = risk
    "Revenue Growth":   0.15,
    "Profit Margins":   0.15,
    "ROE":              0.20,   # capital efficiency
    "52-Week Health":   0.10,
}


def score_financials(data: dict) -> dict:
    """
    Financial health score 0-100 with weighted components.

    Returns dict with:
      - score: float (0-100)
      - components: list of {name, score, weight} for dashboard bars
      - raw: original data for display
    """
    components = [
        ("P/E Ratio",       _score_pe(data.get("trailingPE"))),
        ("Debt/Equity",     _score_de(data.get("debtToEquity"))),
        ("Revenue Growth",  _score_rev_growth(data.get("revenueGrowth"))),
        ("Profit Margins",  _score_profit_margin(data.get("profitMargins"))),
        ("ROE",             _score_roe(data.get("returnOnEquity"))),
        ("52-Week Health",  _score_52w_position(data)),
    ]

    weighted_sum = sum(
        score * COMPONENT_WEIGHTS[name] for name, score in components
    )
    total_weight = sum(COMPONENT_WEIGHTS[name] for name, _ in components)
    final_score = weighted_sum / total_weight if total_weight else 50.0

    return {
        "score": round(final_score, 2),
        "components": [
            {
                "name": name,
                "score": round(score, 2),
                "weight": COMPONENT_WEIGHTS[name],
            }
            for name, score in components
        ],
        "raw": data,
    }


# ── Formatting (unchanged) ──────────────────────────────────────────────────

def format_large_number(n, currency="INR") -> str:
    if n is None:
        return "—"
    if currency == "INR":
        if n >= 1_000_000_000_000:
            return f"₹{n / 1_000_000_000_000:.2f}L Cr"
        if n >= 10_000_000:
            return f"₹{n / 10_000_000:.0f} Cr"
        return f"₹{n:,.0f}"
    else:
        if n >= 1_000_000_000_000:
            return f"${n / 1_000_000_000_000:.2f}T"
        if n >= 1_000_000_000:
            return f"${n / 1_000_000_000:.2f}B"
        if n >= 1_000_000:
            return f"${n / 1_000_000:.2f}M"
        return f"${n:,.0f}"