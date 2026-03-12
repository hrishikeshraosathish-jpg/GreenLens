"""GreenLens — Stock Trend Analysis Module

Provides:
  1. Momentum score (0-100) based on price vs moving averages + RSI
  2. Chart data for frontend (OHLCV with period filter)
  3. Trend signals for the analysis panel
"""
import yfinance as yf
import math


# ── Momentum Scoring ───────────────────────────────────────────

def _compute_sma(prices, window):
    """Simple moving average."""
    if len(prices) < window:
        return None
    return sum(prices[-window:]) / window


def _compute_rsi(prices, period=14):
    """Relative Strength Index."""
    if len(prices) < period + 1:
        return None
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    recent = deltas[-period:]
    gains = [d for d in recent if d > 0]
    losses = [-d for d in recent if d < 0]
    avg_gain = sum(gains) / period if gains else 0
    avg_loss = sum(losses) / period if losses else 0.001
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _compute_volatility(prices, window=20):
    """Annualised volatility from daily returns."""
    if len(prices) < window + 1:
        return None
    returns = [(prices[i] / prices[i-1]) - 1 for i in range(-window, 0)]
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / len(returns)
    daily_vol = math.sqrt(variance)
    return daily_vol * math.sqrt(252)  # annualised


def score_momentum(ticker: str) -> dict:
    """
    Compute momentum score 0-100 from price history.

    Components:
      - Price vs SMA50 (above = bullish)
      - Price vs SMA200 (above = long-term bullish)
      - RSI (30-70 is healthy, extremes penalised)
      - 3-month return (positive = good)
      - Volatility (lower = more stable)

    Returns:
      {
        "score": float,
        "signals": list[str],
        "components": dict,
        "trend": "BULLISH" | "BEARISH" | "NEUTRAL"
      }
    """
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1y")
        if hist.empty or len(hist) < 50:
            return {"score": 50.0, "signals": ["Insufficient price history"],
                    "components": {}, "trend": "NEUTRAL"}

        closes = hist["Close"].tolist()
        current = closes[-1]

        # Moving averages
        sma50 = _compute_sma(closes, 50)
        sma200 = _compute_sma(closes, 200)

        # RSI
        rsi = _compute_rsi(closes, 14)

        # 3-month return
        if len(closes) >= 63:
            ret_3m = (current / closes[-63] - 1) * 100
        else:
            ret_3m = None

        # Volatility
        vol = _compute_volatility(closes, 20)

        # ── Score each component ──

        components = {}
        signals = []

        # 1. Price vs SMA50 (25% weight)
        if sma50:
            pct_above_50 = ((current - sma50) / sma50) * 100
            if pct_above_50 > 5:
                score_50 = min(80 + pct_above_50, 95)
                signals.append(f"Trading {pct_above_50:.1f}% above 50-day MA — short-term bullish")
            elif pct_above_50 > 0:
                score_50 = 60 + pct_above_50 * 4
            elif pct_above_50 > -5:
                score_50 = 40 + pct_above_50 * 4
                signals.append(f"Trading {abs(pct_above_50):.1f}% below 50-day MA — under pressure")
            else:
                score_50 = max(10, 40 + pct_above_50 * 2)
                signals.append(f"Trading {abs(pct_above_50):.1f}% below 50-day MA — bearish signal")
            components["vs_sma50"] = {"score": round(score_50, 1), "value": f"{pct_above_50:+.1f}%"}
        else:
            score_50 = 50
            components["vs_sma50"] = {"score": 50, "value": "N/A"}

        # 2. Price vs SMA200 (25% weight)
        if sma200:
            pct_above_200 = ((current - sma200) / sma200) * 100
            if pct_above_200 > 10:
                score_200 = min(80 + pct_above_200 * 0.5, 95)
                signals.append(f"Well above 200-day MA — strong long-term trend")
            elif pct_above_200 > 0:
                score_200 = 60 + pct_above_200 * 2
            elif pct_above_200 > -10:
                score_200 = 40 + pct_above_200 * 2
            else:
                score_200 = max(10, 40 + pct_above_200)
                signals.append(f"Below 200-day MA — long-term downtrend")
            components["vs_sma200"] = {"score": round(score_200, 1), "value": f"{pct_above_200:+.1f}%"}
        else:
            score_200 = 50
            components["vs_sma200"] = {"score": 50, "value": "N/A"}

        # 3. RSI (20% weight)
        if rsi is not None:
            if 40 <= rsi <= 60:
                score_rsi = 70  # healthy middle
            elif 30 <= rsi <= 70:
                score_rsi = 60
            elif rsi < 30:
                score_rsi = 35  # oversold — could bounce but risky
                signals.append(f"RSI at {rsi:.0f} — oversold, potential reversal")
            else:
                score_rsi = 40  # overbought
                signals.append(f"RSI at {rsi:.0f} — overbought, correction risk")
            components["rsi"] = {"score": round(score_rsi, 1), "value": f"{rsi:.0f}"}
        else:
            score_rsi = 50
            components["rsi"] = {"score": 50, "value": "N/A"}

        # 4. 3-month return (15% weight)
        if ret_3m is not None:
            if ret_3m > 20:
                score_ret = 90
            elif ret_3m > 10:
                score_ret = 75
            elif ret_3m > 0:
                score_ret = 60
            elif ret_3m > -10:
                score_ret = 40
            else:
                score_ret = 20
                signals.append(f"Down {abs(ret_3m):.1f}% in 3 months")
            components["return_3m"] = {"score": round(score_ret, 1), "value": f"{ret_3m:+.1f}%"}
        else:
            score_ret = 50
            components["return_3m"] = {"score": 50, "value": "N/A"}

        # 5. Volatility (15% weight) — lower is better
        if vol is not None:
            vol_pct = vol * 100
            if vol_pct < 20:
                score_vol = 80
            elif vol_pct < 30:
                score_vol = 65
            elif vol_pct < 45:
                score_vol = 50
            else:
                score_vol = 30
                signals.append(f"High volatility ({vol_pct:.0f}% annualised) — unstable")
            components["volatility"] = {"score": round(score_vol, 1), "value": f"{vol_pct:.0f}%"}
        else:
            score_vol = 50
            components["volatility"] = {"score": 50, "value": "N/A"}

        # ── Weighted total ──
        total = (
            score_50  * 0.25 +
            score_200 * 0.25 +
            score_rsi * 0.20 +
            score_ret * 0.15 +
            score_vol * 0.15
        )
        total = round(max(5, min(95, total)), 2)

        # Trend label
        if total >= 65:
            trend = "BULLISH"
        elif total >= 40:
            trend = "NEUTRAL"
        else:
            trend = "BEARISH"

        return {
            "score": total,
            "signals": signals[:4],
            "components": components,
            "trend": trend,
        }

    except Exception as e:
        return {"score": 50.0, "signals": [f"Error: {str(e)}"],
                "components": {}, "trend": "NEUTRAL"}


# ── Chart Data Provider ────────────────────────────────────────

def get_chart_data(ticker: str, period: str = "1y") -> dict:
    """
    Get OHLCV data for charting.

    Args:
        ticker: Stock ticker
        period: "1d", "5d", "1mo", "3mo", "6mo", "1y", "3y", "5y", "max"

    Returns dict with dates, ohlcv arrays, currency, moving averages,
    and day_boundaries for short periods.
    """
    valid_periods = ["1d", "5d", "1mo", "3mo", "6mo", "1y", "3y", "5y", "max"]
    if period not in valid_periods:
        period = "1y"

    # Use intraday intervals for short periods
    interval_map = {
        "1d":  "5m",    # 5-minute bars for 1 day
        "5d":  "15m",   # 15-minute bars for 7 days
        "1mo": "1h",    # hourly bars for 1 month
    }
    interval = interval_map.get(period, "1d")

    try:
        t = yf.Ticker(ticker)
        hist = t.history(period=period, interval=interval)
        if hist.empty:
            return {"error": "No data available"}

        # Format dates based on interval
        if interval in ("5m", "15m", "1h"):
            dates = hist.index.strftime("%Y-%m-%d %H:%M").tolist()
        else:
            dates = hist.index.strftime("%Y-%m-%d").tolist()

        closes = hist["Close"].tolist()

        # Compute day boundaries (for vertical dotted lines on short periods)
        day_boundaries = []
        if interval in ("5m", "15m", "1h"):
            prev_day = None
            for i, idx in enumerate(hist.index):
                day = idx.strftime("%Y-%m-%d")
                if prev_day and day != prev_day:
                    day_boundaries.append(dates[i])
                prev_day = day

        # Compute moving averages (skip for intraday — not meaningful)
        sma20, sma50, sma200 = [], [], []
        if interval == "1d":
            for i in range(len(closes)):
                sma20.append(
                    round(sum(closes[max(0,i-19):i+1]) / min(i+1, 20), 2)
                    if i >= 19 else None
                )
                sma50.append(
                    round(sum(closes[max(0,i-49):i+1]) / min(i+1, 50), 2)
                    if i >= 49 else None
                )
                sma200.append(
                    round(sum(closes[max(0,i-199):i+1]) / min(i+1, 200), 2)
                    if i >= 199 else None
                )

        return {
            "dates":   dates,
            "open":    [round(v, 2) for v in hist["Open"].tolist()],
            "high":    [round(v, 2) for v in hist["High"].tolist()],
            "low":     [round(v, 2) for v in hist["Low"].tolist()],
            "close":   [round(v, 2) for v in closes],
            "volume":  hist["Volume"].tolist(),
            "sma20":   sma20 if sma20 else None,
            "sma50":   sma50 if sma50 else None,
            "sma200":  sma200 if sma200 else None,
            "day_boundaries": day_boundaries,
            "interval": interval,
            "currency": t.info.get("currency", "INR"),
        }

    except Exception as e:
        return {"error": str(e)}