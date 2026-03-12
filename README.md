[README.md](https://github.com/user-attachments/files/25926285/README.md)
# GreenLens

GreenLens is an ESG Risk Intelligence Terminal that helps users evaluate companies through a combination of news sentiment, financial health, governance-related indicators, sector benchmarking, and stock momentum. It is designed as a decision-support prototype that makes ESG analysis more transparent, visual, and easier to interpret.

## Problem Statement

Traditional ESG scoring is often:
- hard to interpret
- slow to update with real-world news
- disconnected from market sentiment and financial context
- inaccessible to everyday users and retail investors

GreenLens addresses this by creating a live, explainable ESG analysis workflow that combines multiple signals into one practical interface.

## What GreenLens Does

GreenLens allows a user to:
- search for a company and generate an ESG score
- analyze news sentiment using FinBERT
- evaluate financial health and stock momentum
- view Environmental, Social, and Governance breakdowns
- compare companies side by side
- analyze a portfolio of holdings
- detect divergence between sentiment and fundamentals
- flag potential greenwashing signals
- export the analysis as a PDF report

## Key Features

### 1. ESG Scorecard
Shows:
- final ESG score
- risk flag
- peer average comparison
- confidence level
- sector benchmark position
- timestamp

### 2. News Sentiment Analysis
Uses FinBERT-based sentiment scoring on company-related headlines to classify:
- positive
- neutral
- negative

### 3. Financial Snapshot
Displays metrics such as:
- market cap
- revenue
- P/E ratio
- ROE
- debt-to-equity ratio
- 52-week high/low
- stock price

### 4. Score Derivation
Breaks down how the final ESG score is formed using weighted components:
- Sentiment
- Financial Health
- Governance / E-S-G
- Stock Momentum

### 5. Sector Context
Compares the company against sector benchmarks and broader sector rankings.

### 6. Compare Mode
Allows side-by-side comparison of two companies with:
- score difference
- momentum
- winner badge
- head-to-head bar chart

### 7. Portfolio Mode
Evaluates a basket of holdings and computes a weighted ESG profile.

### 8. PDF Export
Generates a polished ESG summary report for sharing and presentation.

## Innovation

GreenLens is not just a static ESG dashboard. Its novelty comes from combining:

- real-time news sentiment
- financial fundamentals
- sector-relative interpretation
- explainable score derivation
- greenwashing and divergence cues
- decision-support output through PDF export

This makes the system more practical than a plain score and more understandable than a black-box rating.

## Tech Stack

### Frontend
- HTML
- CSS
- JavaScript
- Plotly.js

### Backend
- Python
- Flask

### Data / Analysis
- FinBERT
- yfinance
- RSS / news feeds
- custom ESG scoring logic

### Reporting
- ReportLab PDF generation

## Project Structure

```text
GreenLens/
├── flask_app.py
├── scorer.py
├── sentiment.py
├── financials.py
├── governance.py
├── stock_analysis.py
├── portfolio.py
├── enhancements.py
├── eli5.py
├── pdf_export.py
├── requirements.txt
├── .python-version
└── templates/
    └── index.html
```

## How the Scoring Works

The final ESG score is calculated from weighted components:

- Sentiment (News): 50%
- Financial Health: 25%
- Governance / E-S-G Composite: 20%
- Stock Momentum: 5%

Additional penalties may be applied for greenwashing-related contradictions or adverse signals.

## Local Setup

### 1. Clone the repository
```bash
git clone https://github.com/hrishikeshraosathish-jpg/GreenLens.git
cd GreenLens
```

### 2. Create and activate virtual environment
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the Flask app
```bash
python flask_app.py
```

### 5. Open in browser
```text
http://127.0.0.1:5000
```

## Deployment Note

A hosted prototype was explored, but transformer-based inference on free/serverless hosting introduces resource and cold-start limitations. For the most reliable live demonstration, the stable local build is recommended.

## Evaluation Mapping

### 1. Technical Execution
- functional end-to-end working prototype
- modular Python backend
- integrated frontend with live charts and scoring workflow

### 2. Scalability & Efficiency
- modular design with separate scoring, sentiment, financial, and reporting layers
- suitable for extension into API-driven or cloud-backed architecture

### 3. Practical Usability
- clear terminal-like interface
- intuitive workflow for search, compare, and portfolio analysis
- PDF output for real-world reporting use

### 4. Innovation & Creativity
- combines ESG with real-time sentiment and market context
- adds explainability instead of only producing a score
- includes divergence and greenwashing cues

### 5. Live Demonstration
- searchable company analysis
- company comparison
- portfolio evaluation
- PDF export
- clear workflow explanation

## Use Cases

GreenLens can be useful for:
- retail investors
- ESG-conscious analysts
- student finance projects
- hackathon demonstrations
- investment research prototypes

## Limitations

- prototype scale, not full market-wide production deployment
- dependent on available news and financial data feeds
- heavy ML inference may require stronger infrastructure for large-scale public deployment
- should be treated as a decision-support tool, not final financial advice

## Future Improvements

- lighter cloud inference pipeline
- database-backed watchlist and history
- broader company coverage
- faster cached scoring
- role-based login and persistence
- improved deployment using dedicated inference backend

## Disclaimer

GreenLens is a prototype for ESG decision support and research demonstration. It is not financial advice.

## Author

Done by **Hrishikesh Sathish**.
