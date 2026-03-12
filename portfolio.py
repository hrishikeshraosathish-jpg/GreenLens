"""GreenLens — Portfolio Module"""
import yfinance as yf
from scorer import score_company

def parse_manual(input_str: str) -> list:
    holdings = []
    parts = input_str.replace(";", ",").split(",")
    for part in parts:
        part = part.strip()
        if not part:
            continue
        bits = part.split()
        if len(bits) >= 2:
            try:
                holdings.append({"ticker": bits[0].upper(), "quantity": int(bits[1])})
            except ValueError:
                pass
    return holdings

def parse_csv(file) -> list:
    import csv, io
    content = file.read().decode("utf-8")
    reader  = csv.DictReader(io.StringIO(content))
    return [
        {"ticker": row.get("ticker","").strip().upper(),
         "quantity": int(row.get("quantity", 1))}
        for row in reader if row.get("ticker")
    ]

def score_portfolio(holdings: list) -> dict:
    if not holdings:
        return {}
    results   = []
    total_val = 0.0
    for h in holdings:
        try:
            info  = yf.Ticker(h["ticker"]).info
            price = (info.get("currentPrice") or info.get("regularMarketPrice") or info.get("navPrice") or 1)
            val   = price * h["quantity"]
            r     = score_company(h["ticker"], h["ticker"])
            results.append({
                "ticker":   h["ticker"],
                "quantity": h["quantity"],
                "price":    price,
                "value":    val,
                "score":    r["final_score"],
                "flag":     r["flag"],
                "alert":    r["alert"],
            })
            total_val += val
        except Exception:
            continue
    if not results:
        return {}
    if total_val == 0:
        total_val = len(results)
        for r in results:
            r["value"] = 1
    weighted = round(sum(r["score"]*r["value"] for r in results) / total_val, 2)
    flag     = "HIGH" if weighted<=40 else "MEDIUM" if weighted<=65 else "LOW"
    riskiest = min(results, key=lambda x: x["score"])["ticker"]
    breakdown = [{
        "ticker":   r["ticker"],
        "score":    r["score"],
        "flag":     r["flag"],
        "alert":    r["alert"],
        "weight_%": round(r["value"]/total_val*100, 1),
    } for r in results]
    recs = []
    for r in results:
        if r["flag"]=="HIGH":
            recs.append(f"Consider reducing exposure to {r['ticker']} — HIGH ESG risk")
        elif r["flag"]=="MEDIUM":
            recs.append(f"Monitor {r['ticker']} — MEDIUM ESG risk")
    return {
        "weighted_score":  weighted,
        "flag":            flag,
        "riskiest":        riskiest,
        "breakdown":       breakdown,
        "recommendations": recs[:3],
    }