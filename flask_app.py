"""GreenLens — Flask Backend API"""
from flask import Flask, jsonify, request, render_template, send_file
from flask_cors import CORS
import sys, io
sys.path.insert(0, ".")

from scorer import score_company, score_peers, company_to_ticker
from eli5 import generate_eli5
from portfolio import parse_manual, parse_csv, score_portfolio
from pdf_export import generate_pdf
from stock_analysis import get_chart_data

app = Flask(__name__)
CORS(app)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/score", methods=["POST"])
def api_score():
    data    = request.json
    company = data.get("company", "").strip()
    ticker  = data.get("ticker", "").strip() or None
    if not company:
        return jsonify({"error": "Company name required"}), 400
    try:
        if not ticker:
            ticker = company_to_ticker(company)
        result = score_company(company, ticker)
        peers  = score_peers(ticker)
        eli5   = generate_eli5(result)
        imps   = result["improvements"]
        return jsonify({
            "result": result,
            "peers":  peers,
            "eli5":   eli5,
            "improvements": imps,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/stock_chart", methods=["GET"])
def api_stock_chart():
    ticker = request.args.get("ticker", "").strip()
    period = request.args.get("period", "1y").strip()
    if not ticker:
        return jsonify({"error": "Ticker required"}), 400
    try:
        data = get_chart_data(ticker, period)
        if "error" in data:
            return jsonify(data), 404
        return jsonify(data)
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