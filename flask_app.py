"""GreenLens — Flask Backend API"""
from flask import Flask, jsonify, request, render_template, send_file
from flask_cors import CORS
import sys, io, time
sys.path.insert(0, ".")

from scorer import score_company, score_peers, company_to_ticker
from eli5 import generate_eli5
from portfolio import parse_manual, parse_csv, score_portfolio
from pdf_export import generate_pdf
from stock_analysis import get_chart_data

app = Flask(__name__)
CORS(app)

# Demo-focused in-memory caches to avoid recomputing the same company repeatedly
API_CACHE = {}
TICKER_CACHE = {}
CHART_CACHE = {}
API_CACHE_TTL = 1800   # 30 minutes
CHART_CACHE_TTL = 900  # 15 minutes


def _cache_get(store, key, ttl):
    entry = store.get(key)
    if not entry:
        return None
    if time.time() - entry["ts"] > ttl:
        store.pop(key, None)
        return None
    return entry["value"]


def _cache_set(store, key, value):
    store[key] = {"value": value, "ts": time.time()}


def _company_key(company: str) -> str:
    return f"company:{(company or '').strip().lower()}"


def _ticker_key(ticker: str) -> str:
    return f"ticker:{(ticker or '').strip().upper()}"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/score", methods=["POST"])
def api_score():
    data = request.json or {}
    company = data.get("company", "").strip()
    ticker = data.get("ticker", "").strip() or None
    if not company:
        return jsonify({"error": "Company name required"}), 400
    try:
        if not ticker:
            cached_ticker = _cache_get(TICKER_CACHE, _company_key(company), API_CACHE_TTL)
            if cached_ticker:
                ticker = cached_ticker
            else:
                ticker = company_to_ticker(company)
                _cache_set(TICKER_CACHE, _company_key(company), ticker)

        cache_keys = [_company_key(company), _ticker_key(ticker)]
        for key in cache_keys:
            cached_payload = _cache_get(API_CACHE, key, API_CACHE_TTL)
            if cached_payload:
                return jsonify({**cached_payload, "cached": True})

        result = score_company(company, ticker)
        peers = score_peers(ticker)
        eli5 = generate_eli5(result)
        payload = {
            "result": result,
            "peers": peers,
            "eli5": eli5,
            "improvements": result["improvements"],
        }

        for key in cache_keys:
            _cache_set(API_CACHE, key, payload)

        return jsonify({**payload, "cached": False})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/stock_chart", methods=["GET"])
def api_stock_chart():
    ticker = request.args.get("ticker", "").strip()
    period = request.args.get("period", "1y").strip()
    if not ticker:
        return jsonify({"error": "Ticker required"}), 400
    try:
        cache_key = f"{ticker.upper()}::{period}"
        cached_data = _cache_get(CHART_CACHE, cache_key, CHART_CACHE_TTL)
        if cached_data:
            return jsonify({**cached_data, "cached": True})

        data = get_chart_data(ticker, period)
        if "error" in data:
            return jsonify(data), 404

        _cache_set(CHART_CACHE, cache_key, data)
        return jsonify({**data, "cached": False})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/portfolio", methods=["POST"])
def api_portfolio():
    data     = request.json
    holdings = data.get("holdings", [])
    if not holdings:
        return jsonify({"error": "No holdings provided"}), 400
    try:
        result = score_portfolio(holdings)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/compare", methods=["POST"])
def api_compare():
    data = request.json
    co1  = data.get("company1", "").strip()
    co2  = data.get("company2", "").strip()
    if not co1 or not co2:
        return jsonify({"error": "Two companies required"}), 400
    try:
        t1 = company_to_ticker(co1)
        t2 = company_to_ticker(co2)
        r1 = score_company(co1, t1)
        r2 = score_company(co2, t2)
        return jsonify({
            "company1": {**r1, "eli5": generate_eli5(r1)},
            "company2": {**r2, "eli5": generate_eli5(r2)},
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/pdf", methods=["POST"])
def api_pdf():
    data   = request.json
    result = data.get("result")
    eli5   = data.get("eli5", "")
    if not result:
        return jsonify({"error": "No result provided"}), 400
    try:
        pdf_bytes = generate_pdf(result, eli5)
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"GreenLens_{result.get('ticker','report')}.pdf"
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)