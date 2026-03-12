"""GreenLens — Sentiment Module (v3): RSS headlines + FinBERT scoring (optimized)."""
import feedparser
from datetime import datetime, timedelta
from transformers import pipeline
from email.utils import parsedate_to_datetime
import math

RSS_BASE = "https://news.google.com/rss/search?q={query}&hl=en&gl=IN&ceid=IN:en"

# ── FinBERT loader ──────────────────────────────────────────────────────────

def load_finbert():
    return pipeline(
        "text-classification",
        model="ProsusAI/finbert",
        truncation=True,
        max_length=512,
        batch_size=16,          # batch inference — much faster
    )


# ── Headline fetching ───────────────────────────────────────────────────────

# Negative-leaning queries so we don't only get PR fluff
QUERY_TEMPLATES = [
    "{company} ESG sustainability",
    "{company} stock news",
    "{company} controversy scandal",
    "{company} regulation fine penalty",
    "{company} emissions pollution environment",
    "{company} labor rights employee",
    "{company} governance fraud audit",
    "{company} greenwashing",
]


def _parse_pub_date(date_str: str):
    """Try to parse RSS published date into datetime."""
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        pass
    # fallback: try common formats
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%a, %d %b %Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except Exception:
            continue
    return None


def fetch_headlines(company: str, days_ago: int = 30) -> list[dict]:
    """
    Fetch headlines from multiple ESG-relevant angles.
    Deduplicates by title, filters by date, caps at 50.
    """
    cutoff = datetime.now() - timedelta(days=days_ago) if days_ago else None
    seen_titles = set()
    headlines = []

    for template in QUERY_TEMPLATES:
        query = template.format(company=company)
        url = RSS_BASE.format(query=query.replace(" ", "+"))

        try:
            feed = feedparser.parse(url)
        except Exception:
            continue

        for entry in feed.entries[:10]:
            title = entry.get("title", "").strip()
            title_lower = title.lower()

            if not title or title_lower in seen_titles:
                continue

            # Parse date and filter old articles
            pub_date = _parse_pub_date(entry.get("published", ""))
            if cutoff and pub_date:
                # Make cutoff offset-aware if pub_date is
                cutoff_cmp = cutoff
                if pub_date.tzinfo is not None:
                    from datetime import timezone
                    cutoff_cmp = cutoff.replace(tzinfo=timezone.utc)
                if pub_date < cutoff_cmp:
                    continue

            seen_titles.add(title_lower)

            # Extract source
            source = ""
            try:
                src = entry.get("source", {})
                if isinstance(src, dict):
                    source = src.get("title", "") or ""
                elif hasattr(src, "title"):
                    source = getattr(src, "title", "") or ""
            except Exception:
                source = ""

            headlines.append({
                "title": title,
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
                "pub_date": pub_date,
                "source": source,
            })

    return headlines[:50]


# ── Classification ──────────────────────────────────────────────────────────

CONFIDENCE_FLOOR = 0.55   # ignore predictions below this


def _classify_headlines(headlines: list[dict], pipe) -> list[dict]:
    """
    Batch-classify headlines with FinBERT.
    Filters out low-confidence predictions.
    """
    titles = [h["title"] for h in headlines if h.get("title", "").strip()]
    if not titles:
        return []

    # Batch inference — single call instead of N calls
    try:
        outputs = pipe(titles, truncation=True, max_length=512)
    except Exception:
        return []

    results = []
    for h, out in zip(headlines, outputs):
        label = out["label"].lower()
        conf = out["score"]

        # Skip low-confidence noise
        if conf < CONFIDENCE_FLOOR:
            continue

        results.append({
            "title": h["title"],
            "link": h.get("link", ""),
            "published": h.get("published", ""),
            "pub_date": h.get("pub_date"),
            "source": h.get("source", ""),
            "label": label,
            "confidence": round(conf, 4),
        })

    return results


# ── Scoring ─────────────────────────────────────────────────────────────────

def _recency_weight(pub_date, now, half_life_days=10):
    """
    Exponential decay: articles from today ≈ 1.0,
    articles from half_life_days ago ≈ 0.5.
    """
    if pub_date is None:
        return 0.5  # unknown date gets half weight

    if pub_date.tzinfo is not None:
        from datetime import timezone
        now = now.replace(tzinfo=timezone.utc)

    age_days = max((now - pub_date).total_seconds() / 86400, 0)
    return math.exp(-0.693 * age_days / half_life_days)


def score_sentiment(headlines: list[dict], pipe) -> dict:
    """
    Score sentiment from headlines.

    Improvements over v2:
      - Recency-weighted (recent articles count more)
      - Confidence-gated (low-conf predictions filtered)
      - Batch inference (faster)
      - Better neutral handling (neutrals nudged toward 45 instead of 50
        because "no news is not great news" in ESG context)

    Returns score 0-100 where:
      100 = all recent positive with high confidence
        0 = all recent negative with high confidence
       50 = balanced / no data
    """
    classified = _classify_headlines(headlines, pipe)

    if not classified:
        return {
            "score": 50.0,
            "confidence": "LOW",
            "delta": 0.0,
            "trend": [],
            "breakdown": {"positive": 0, "negative": 0, "neutral": 0, "total": 0},
        }

    # Neutral gets 0.45 instead of 0.5 — slight pessimism for ESG
    label_val = {"positive": 1.0, "neutral": 0.45, "negative": 0.0}
    now = datetime.now()

    # Import source quality weighting (lazy to avoid circular import)
    try:
        from enhancements import get_source_weight
    except ImportError:
        get_source_weight = lambda s: 1.0  # fallback if enhancements not present

    w_sum = 0.0
    w_total = 0.0

    for h in classified:
        val = label_val.get(h["label"], 0.45)
        conf = h["confidence"]
        recency = _recency_weight(h.get("pub_date"), now, half_life_days=10)
        source_w = get_source_weight(h.get("source", ""))

        weight = conf * recency * source_w
        w_sum += val * weight
        w_total += weight

    raw_score = (w_sum / w_total) * 100 if w_total else 50.0

    # ── Confidence assessment ───────────────────────────────────────────
    n = len(classified)
    pos_n = sum(1 for h in classified if h["label"] == "positive")
    neg_n = sum(1 for h in classified if h["label"] == "negative")
    neu_n = n - pos_n - neg_n

    dominant_ratio = max(pos_n, neg_n, neu_n) / n if n else 0

    if n < 5:
        confidence = "LOW"
    elif n < 15:
        confidence = "MEDIUM" if dominant_ratio > 0.45 else "LOW"
    else:
        confidence = "HIGH" if dominant_ratio > 0.5 else "MEDIUM"

    # ── Delta: compare recent 7d vs older ───────────────────────────────
    week_ago = now - timedelta(days=7)
    recent_scores, older_scores = [], []
    for h in classified:
        val = label_val.get(h["label"], 0.45) * 100
        pd = h.get("pub_date")
        if pd is None:
            older_scores.append(val)
        elif pd.replace(tzinfo=None) >= week_ago:
            recent_scores.append(val)
        else:
            older_scores.append(val)

    if recent_scores and older_scores:
        delta = round(
            sum(recent_scores) / len(recent_scores)
            - sum(older_scores) / len(older_scores),
            2,
        )
    else:
        delta = 0.0

    # ── Trend for chart ─────────────────────────────────────────────────
    trend = []
    for h in classified:
        val = label_val.get(h["label"], 0.45)
        trend.append({
            "title": h["title"],
            "link": h["link"],
            "published": h["published"],
            "source": h.get("source", ""),
            "label": h["label"],
            "score": round(val * 100, 2),
            "confidence": h["confidence"],
        })

    return {
        "score": round(raw_score, 2),
        "confidence": confidence,
        "delta": delta,
        "trend": trend,
        "breakdown": {
            "positive": pos_n,
            "negative": neg_n,
            "neutral": neu_n,
            "total": n,
        },
    }