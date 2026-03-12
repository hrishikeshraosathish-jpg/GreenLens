"""GreenLens — Scorer (v5)

Final Score =
    50% Sentiment (news)
  + 25% Financial Health
  + 20% Governance (combined E/S/G)
  +  5% Stock Momentum

Greenwashing penalty is applied afterward when triggered.

Risk flag:
  0–40   -> HIGH
  41–60  -> MEDIUM
  61–100 -> LOW
"""

from datetime import datetime

import yfinance as yf

from sentiment import fetch_headlines, load_finbert, score_sentiment
from financials import fetch_financials, score_financials, format_large_number
from governance import score_governance
from enhancements import enhance_result, get_cached, set_cache
from stock_analysis import score_momentum


# ── Unified score weights ──────────────────────────────────────
SCORE_WEIGHTS = {
    "sentiment": 0.50,
    "financial": 0.25,
    "governance": 0.20,
    "momentum": 0.05,
}


# ── Sector peer map ────────────────────────────────────────────
SECTOR_PEERS = {
    "Technology": ["TCS.NS", "INFY.NS", "WIPRO.NS", "HCLTECH.NS", "TECHM.NS"],
    "Financial Services": ["HDFCBANK.NS", "ICICIBANK.NS", "AXISBANK.NS", "KOTAKBANK.NS"],
    "Energy": ["ONGC.NS", "BPCL.NS", "RELIANCE.NS", "IOC.NS"],
    "Automobile": ["TATAMOTORS.NS", "MARUTI.NS", "BAJAJ-AUTO.NS", "HEROMOTOCO.NS"],
    "Pharmaceuticals": ["SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS", "DIVISLAB.NS"],
    "Consumer Defensive": ["HINDUNILVR.NS", "ITC.NS", "NESTLEIND.NS", "DABUR.NS"],
    "Consumer Cyclical": ["TITAN.NS", "TRENT.NS", "DMART.NS", "JUBLFOOD.NS"],
    "Industrials": ["LT.NS", "SIEMENS.NS", "ABB.NS", "BHEL.NS"],
    "Basic Materials": ["TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS", "COALINDIA.NS"],
    "Communication": ["BHARTIARTL.NS", "IDEA.NS", "TATACOMM.NS"],
    "Healthcare": ["APOLLOHOSP.NS", "MAXHEALTH.NS", "FORTIS.NS"],
    "Utilities": ["POWERGRID.NS", "NTPC.NS", "ADANIGREEN.NS"],
    "Real Estate": ["DLF.NS", "GODREJPROP.NS", "OBEROIRLTY.NS"],
}


# ── Known company → ticker map ────────────────────────────────
KNOWN = {
    "infosys": "INFY.NS",
    "tcs": "TCS.NS",
    "tata consultancy": "TCS.NS",
    "wipro": "WIPRO.NS",
    "hdfc": "HDFCBANK.NS",
    "hdfc bank": "HDFCBANK.NS",
    "icici": "ICICIBANK.NS",
    "icici bank": "ICICIBANK.NS",
    "reliance": "RELIANCE.NS",
    "ongc": "ONGC.NS",
    "tata motors": "TATAMOTORS.NS",
    "maruti": "MARUTI.NS",
    "sun pharma": "SUNPHARMA.NS",
    "sunpharma": "SUNPHARMA.NS",
    "dr reddy": "DRREDDY.NS",
    "hindustan unilever": "HINDUNILVR.NS",
    "hul": "HINDUNILVR.NS",
    "itc": "ITC.NS",
    "apple": "AAPL",
    "microsoft": "MSFT",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "amazon": "AMZN",
    "tesla": "TSLA",
    "meta": "META",
    "nvidia": "NVDA",
    "samsung": "005930.KS",
    "adani": "ADANIENT.NS",
    "bajaj finance": "BAJFINANCE.NS",
    "asian paints": "ASIANPAINT.NS",
    "kotak": "KOTAKBANK.NS",
    "larsen": "LT.NS",
    "l&t": "LT.NS",
    "axis bank": "AXISBANK.NS",
    "airtel": "BHARTIARTL.NS",
    "bharti airtel": "BHARTIARTL.NS",
    "tata steel": "TATASTEEL.NS",
    "nestle": "NESN.SW",
    "toyota": "TM",
    "sony": "SONY",
    "tsmc": "TSM",
    "alibaba": "BABA",
    "hcl": "HCLTECH.NS",
    "hcl tech": "HCLTECH.NS",
    "tech mahindra": "TECHM.NS",
    "mrf": "MRF.NS",
    "titan": "TITAN.NS",
    "zomato": "ZOMATO.NS",
    "paytm": "PAYTM.NS",
    "sbi": "SBIN.NS",
    "state bank": "SBIN.NS",
    "bajaj auto": "BAJAJ-AUTO.NS",
    "hero motocorp": "HEROMOTOCO.NS",
    "cipla": "CIPLA.NS",
    "divis lab": "DIVISLAB.NS",
    "power grid": "POWERGRID.NS",
    "ntpc": "NTPC.NS",
    "coal india": "COALINDIA.NS",
    "jsw steel": "JSWSTEEL.NS",
    "hindalco": "HINDALCO.NS",
    "dlf": "DLF.NS",
    "godrej properties": "GODREJPROP.NS",
    "nestle india": "NESTLEIND.NS",
    "dabur": "DABUR.NS",
    "siemens": "SIEMENS.NS",
    "abb": "ABB.NS",
    "bhel": "BHEL.NS",
    "trent": "TRENT.NS",
    "dmart": "DMART.NS",
}


# ── Small helpers ──────────────────────────────────────────────
def _risk_flag(score: float) -> str:
    if score <= 40:
        return "HIGH"
    if score <= 60:
        return "MEDIUM"
    return "LOW"


# ── Ticker resolution ──────────────────────────────────────────
def company_to_ticker(company: str) -> str:
    key = company.lower().strip()

    for suffix in [" ltd", " limited", " inc", " corp", " corporation"]:
        key = key.replace(suffix, "").strip()

    if key in KNOWN:
        return KNOWN[key]

    attempts = [
        key.upper(),
        key.upper() + ".NS",
        key.upper().replace(" ", "") + ".NS",
        key.upper().replace(" ", ""),
    ]

    for attempt in attempts:
        try:
            info = yf.Ticker(attempt).info
            if info.get("symbol") and info.get("regularMarketPrice"):
                return attempt
        except Exception:
            continue

    try:
        results = yf.Search(company, max_results=1)
        if results.quotes:
            return results.quotes[0]["symbol"]
    except Exception:
        pass

    raise ValueError(
        f"Could not find ticker for: {company}. Try entering the ticker manually."
    )


# ── Investor-friendly analysis generators ──────────────────────
def generate_drivers(result: dict) -> list[str]:
    """What drove this score — plain English for investors."""
    drivers = []

    sent = result["sentiment_score"]
    fin = result["financial_score"]
    e, s, g = result["e_score"], result["s_score"], result["g_score"]
    fin_data = result.get("fin_data", {})
    bd = result.get("sentiment_breakdown", {})

    pos_n = bd.get("positive", 0)
    neg_n = bd.get("negative", 0)
    total = bd.get("total", 0)

    # ── Sentiment ──
    if total > 0:
        if neg_n > pos_n * 2:
            drivers.append(
                f"Recent news coverage is largely negative — "
                f"{neg_n} of {total} articles flagged concerns"
            )
        elif neg_n > pos_n:
            drivers.append(
                f"More negative than positive press in recent weeks "
                f"({neg_n} negative vs {pos_n} positive)"
            )
        elif pos_n > neg_n * 2:
            drivers.append(
                f"Strong positive media coverage — "
                f"{pos_n} of {total} recent articles are favorable"
            )
        elif pos_n > neg_n:
            drivers.append(
                f"Slightly more positive than negative press "
                f"({pos_n} positive vs {neg_n} negative)"
            )
        else:
            drivers.append(
                f"Mixed media sentiment — no clear trend in {total} recent articles"
            )

    # ── Financials ──
    de = fin_data.get("debtToEquity")
    pm = fin_data.get("profitMargins")
    roe = fin_data.get("returnOnEquity")
    rg = fin_data.get("revenueGrowth")

    if de is not None:
        if de < 50:
            drivers.append(
                f"Low debt levels (D/E: {de:.0f}) — company is financially conservative"
            )
        elif de > 150:
            drivers.append(
                f"High debt load (D/E: {de:.0f}) — could be a risk in downturns"
            )

    if pm is not None:
        if pm > 0.15:
            drivers.append(
                f"Healthy profit margins ({pm * 100:.1f}%) indicate strong pricing power"
            )
        elif pm < 0.05:
            drivers.append(
                f"Thin profit margins ({pm * 100:.1f}%) suggest competitive pressure"
            )

    if roe is not None and roe > 0.20:
        drivers.append(
            f"High return on equity ({roe * 100:.1f}%) — efficient use of shareholder capital"
        )
    elif roe is not None and roe < 0.05:
        drivers.append(
            f"Low return on equity ({roe * 100:.1f}%) — capital efficiency needs improvement"
        )

    if rg is not None:
        if rg > 0.15:
            drivers.append(f"Revenue growing at {rg * 100:.1f}% — strong business momentum")
        elif rg < 0:
            drivers.append(f"Revenue declining ({rg * 100:.1f}%) — business may be contracting")

    # ── ESG pillars ──
    pillar_scores = [("Environmental", e), ("Social", s), ("Governance", g)]
    best = max(pillar_scores, key=lambda x: x[1])
    worst = min(pillar_scores, key=lambda x: x[1])

    if best[1] - worst[1] > 20:
        drivers.append(
            f"Performs best on {best[0].lower()} practices, "
            f"weakest on {worst[0].lower()}"
        )
    elif best[1] > 70:
        drivers.append("Solid across all ESG pillars — no major red flags")
    else:
        drivers.append("Room for improvement across all ESG dimensions")

    # ── Momentum ──
    momentum_score = result.get("momentum_score", 50)
    if momentum_score < 40:
        drivers.append("Weak stock momentum is dragging the overall score lower")
    elif momentum_score > 65:
        drivers.append("Positive stock momentum supports the broader ESG story")

    return drivers[:5]


def generate_improvements(result: dict) -> list[str]:
    """Actionable, investor-readable recommendations."""
    improvements = []

    sent = result["sentiment_score"]
    fin = result["financial_score"]
    e, s, g = result["e_score"], result["s_score"], result["g_score"]
    fin_data = result.get("fin_data", {})

    areas = sorted(
        [
            (sent, "sentiment"),
            (fin, "financial"),
            (e, "environmental"),
            (s, "social"),
            (g, "governance"),
        ],
        key=lambda x: x[0],
    )

    for score, area in areas[:3]:
        if area == "sentiment":
            if score < 40:
                improvements.append(
                    "Address negative press — consider public statements on flagged issues"
                )
            elif score < 60:
                improvements.append(
                    "Boost transparency with regular ESG progress updates to improve perception"
                )
            else:
                improvements.append(
                    "Maintain positive media relations and proactive sustainability communications"
                )

        elif area == "financial":
            de = fin_data.get("debtToEquity")
            pm = fin_data.get("profitMargins")
            if de is not None and de > 100:
                improvements.append(
                    f"Reduce debt levels (currently D/E: {de:.0f}) to lower financial risk"
                )
            elif pm is not None and pm < 0.10:
                improvements.append(
                    f"Improve profit margins (currently {pm * 100:.1f}%) through cost optimization"
                )
            else:
                improvements.append(
                    "Continue strengthening balance sheet and capital efficiency"
                )

        elif area == "environmental":
            if score < 40:
                improvements.append(
                    "Urgently address environmental risks — publish emissions data and set targets"
                )
            elif score < 60:
                improvements.append(
                    "Set measurable environmental goals (carbon reduction, renewable energy)"
                )
            else:
                improvements.append(
                    "Expand environmental disclosures to maintain investor confidence"
                )

        elif area == "social":
            if score < 40:
                improvements.append(
                    "Address workforce concerns — invest in employee welfare and diversity"
                )
            elif score < 60:
                improvements.append(
                    "Strengthen social programs — diversity reporting, fair labor, community impact"
                )
            else:
                improvements.append(
                    "Continue investing in workforce development and social responsibility"
                )

        elif area == "governance":
            if score < 40:
                improvements.append(
                    "Serious governance gaps — improve board independence and audit transparency"
                )
            elif score < 60:
                improvements.append(
                    "Strengthen governance — more independent directors, better disclosures"
                )
            else:
                improvements.append(
                    "Maintain strong governance standards and shareholder communication"
                )

    return improvements


# ── Singleton FinBERT ──────────────────────────────────────────
_finbert_pipe = None


def get_finbert():
    global _finbert_pipe
    if _finbert_pipe is None:
        _finbert_pipe = load_finbert()
    return _finbert_pipe


# ── Main scoring function ──────────────────────────────────────
def score_company(company: str, ticker: str | None = None) -> dict:
    cached = get_cached(company)
    if cached:
        return cached

    if not ticker:
        ticker = company_to_ticker(company)

    pipe = get_finbert()

    # 1. Sentiment
    headlines = fetch_headlines(company, days_ago=30)
    sent = score_sentiment(headlines, pipe)

    # 2. Financial health
    fin_raw = fetch_financials(ticker)
    fin_result = score_financials(fin_raw)
    fin_score = fin_result["score"]

    # 3. Governance / E-S-G proxies
    try:
        yf_info = yf.Ticker(ticker).info
    except Exception:
        yf_info = {}

    gov = score_governance(ticker, sent["trend"], preloaded_info=yf_info)

    # 4. Stock momentum
    momentum = score_momentum(ticker)

    # ── Final composite score before penalty ──
    final_before_penalty = round(
        (sent["score"] * SCORE_WEIGHTS["sentiment"])
        + (fin_score * SCORE_WEIGHTS["financial"])
        + (gov["governance_score"] * SCORE_WEIGHTS["governance"])
        + (momentum["score"] * SCORE_WEIGHTS["momentum"]),
        2,
    )

    flag = _risk_flag(final_before_penalty)

    # ── Alert logic ──
    bd = sent.get("breakdown", {})
    neg_count = bd.get("negative", 0)
    total_h = bd.get("total", 0)

    alert = flag == "HIGH" or (total_h > 0 and neg_count / total_h > 0.6)
    alert_reason = ""
    if flag == "HIGH":
        alert_reason = "Overall ESG score is in HIGH risk zone"
    elif alert:
        alert_reason = f"{neg_count} of {total_h} headlines are negative"

    result = {
        "company": company,
        "ticker": ticker,
        "final_score": final_before_penalty,
        "flag": flag,
        "score_weights": SCORE_WEIGHTS,
        "sentiment_score": sent["score"],
        "financial_score": fin_score,
        "governance_score": gov["governance_score"],
        "financial_components": fin_result.get("components", []),
        "momentum_score": momentum["score"],
        "momentum_trend": momentum["trend"],
        "momentum_signals": momentum["signals"],
        "momentum_components": momentum.get("components", {}),
        "e_score": gov["e_score"],
        "s_score": gov["s_score"],
        "g_score": gov["g_score"],
        "alert": alert,
        "alert_reason": alert_reason,
        "confidence": sent["confidence"],
        "delta": sent["delta"],
        "trend": sent["trend"],
        "sentiment_breakdown": sent.get("breakdown", {}),
        "company_info": gov["company_info"],
        "headline_count": len(headlines),
        "timestamp": datetime.now().strftime("%H:%M, %d %b %Y"),
        "fin_data": fin_raw,
        "keyword_detail": gov.get("keyword_detail", {}),
        "esg_drivers": gov.get("drivers", []),
        "fin_formatted": {
            "market_cap": format_large_number(
                fin_raw.get("marketCap"), fin_raw.get("currency", "INR")
            ),
            "revenue": format_large_number(
                fin_raw.get("totalRevenue"), fin_raw.get("currency", "INR")
            ),
            "pe": round(fin_raw.get("trailingPE") or 0, 1),
            "roe": f"{round((fin_raw.get('returnOnEquity') or 0) * 100, 1)}%",
            "52w_high": fin_raw.get("fiftyTwoWeekHigh", "—"),
            "52w_low": fin_raw.get("fiftyTwoWeekLow", "—"),
            "price": fin_raw.get("currentPrice", "—"),
            "de_ratio": round(fin_raw.get("debtToEquity") or 0, 1),
        },
    }

    result["drivers"] = generate_drivers(result)
    result["improvements"] = generate_improvements(result)

    # Apply enhancements: greenwashing, sector normalization, divergence, source quality
    result = enhance_result(result)

    # Cache for instant re-analysis
    set_cache(company, result)

    return result


# ── Lightweight peer scoring (NO FinBERT — fast) ──────────────
def _quick_score(ticker: str) -> dict | None:
    """
    Score a peer using only financials + governance proxies.
    No FinBERT, no RSS — runs fast for compare/peer panels.

    Sentiment and momentum are both assumed neutral (50) so the
    weighting logic stays consistent with the main scoring formula.
    """
    try:
        info = yf.Ticker(ticker).info
        if not info.get("regularMarketPrice"):
            return None

        fin_raw = {
            "trailingPE": info.get("trailingPE"),
            "debtToEquity": info.get("debtToEquity"),
            "revenueGrowth": info.get("revenueGrowth"),
            "profitMargins": info.get("profitMargins"),
            "returnOnEquity": info.get("returnOnEquity"),
            "marketCap": info.get("marketCap"),
            "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
            "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow"),
            "currentPrice": info.get("currentPrice") or info.get("regularMarketPrice"),
            "currency": info.get("currency", "INR"),
        }

        fin_result = score_financials(fin_raw)
        fin_score = fin_result["score"]

        gov = score_governance(ticker, [], preloaded_info=info)

        peer_sentiment_proxy = 50.0
        peer_momentum_proxy = 50.0

        final = round(
            (peer_sentiment_proxy * SCORE_WEIGHTS["sentiment"])
            + (fin_score * SCORE_WEIGHTS["financial"])
            + (gov["governance_score"] * SCORE_WEIGHTS["governance"])
            + (peer_momentum_proxy * SCORE_WEIGHTS["momentum"]),
            2,
        )

        return {
            "ticker": ticker,
            "name": info.get("longName", ticker),
            "score": final,
            "flag": _risk_flag(final),
            "company_info": {
                "name": info.get("longName", ticker),
                "sector": info.get("sector", "—"),
                "industry": info.get("industry", "—"),
            },
            "market_cap": info.get("marketCap", 0) or 0,
        }
    except Exception:
        return None


def score_peers(ticker: str) -> list[dict]:
    """
    Score sector peers using lightweight method.
    """
    try:
        info = yf.Ticker(ticker).info
        sector = info.get("sector", "Technology")
    except Exception:
        sector = "Technology"

    peers = SECTOR_PEERS.get(sector)

    if not peers:
        for key in SECTOR_PEERS:
            if key.lower() in sector.lower() or sector.lower() in key.lower():
                peers = SECTOR_PEERS[key]
                break

    if not peers:
        peers = ["INFY.NS", "TCS.NS", "WIPRO.NS"]

    peers = [p for p in peers if p.upper() != ticker.upper()][:4]

    results = []
    for peer_ticker in peers:
        peer_result = _quick_score(peer_ticker)
        if peer_result:
            results.append(peer_result)

    return results