"""GreenLens - Professional PDF Export (layout-safe)."""
from __future__ import annotations

import io
from html import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# - Palette -----------------------------------------------------------------
C_BG = colors.HexColor("#FFFFFF")
C_DARK = colors.HexColor("#0F172A")
C_BODY = colors.HexColor("#334155")
C_MUTED = colors.HexColor("#94A3B8")
C_BORDER = colors.HexColor("#E2E8F0")
C_ROW_ALT = colors.HexColor("#F8FAFC")
C_ACCENT = colors.HexColor("#0F766E")
C_ACCENT2 = colors.HexColor("#E0F2F1")
C_GREEN = colors.HexColor("#16A34A")
C_AMBER = colors.HexColor("#D97706")
C_RED = colors.HexColor("#DC2626")
C_GREEN_BG = colors.HexColor("#F0FDF4")
C_AMBER_BG = colors.HexColor("#FFFBEB")
C_RED_BG = colors.HexColor("#FEF2F2")
C_NOTE_BG = colors.HexColor("#F8FAFC")

W, H = A4


def _fc(flag: str):
    return C_GREEN if flag == "LOW" else C_AMBER if flag == "MEDIUM" else C_RED


def _fbg(flag: str):
    return C_GREEN_BG if flag == "LOW" else C_AMBER_BG if flag == "MEDIUM" else C_RED_BG


def _s(name, **kw):
    return ParagraphStyle(
        name,
        fontName=kw.pop("font", "Helvetica"),
        textColor=kw.pop("color", C_BODY),
        **kw,
    )


def _hr(color=C_BORDER, thickness=0.5):
    return HRFlowable(width="100%", thickness=thickness, color=color, spaceAfter=4, spaceBefore=4)


def _section_title(text, styles):
    return [Paragraph(escape(text.upper()), styles["section"]), _hr(C_ACCENT, 1), Spacer(1, 5)]


def _safe_text(val, default="-"):
    if val is None:
        return default
    text = str(val).strip()
    if not text:
        return default
    # Helvetica in base ReportLab often misses the rupee glyph.
    text = text.replace("₹", "Rs ")
    return text


def _fmt_num(val, digits=1, default="-"):
    try:
        return f"{float(val):.{digits}f}"
    except Exception:
        return default


def _ellipsize_canvas_text(c: rl_canvas.Canvas, text: str, max_width: float, font: str, size: float) -> str:
    txt = _safe_text(text, "")
    if not txt:
        return ""
    if c.stringWidth(txt, font, size) <= max_width:
        return txt
    ell = "..."
    while txt and c.stringWidth(txt + ell, font, size) > max_width:
        txt = txt[:-1]
    return txt + ell


def _para(text: str, style: ParagraphStyle, align: int | None = None):
    if align is not None:
        style = ParagraphStyle(f"{style.name}_tmp_{align}", parent=style, alignment=align)
    return Paragraph(escape(_safe_text(text)), style)


HEADER_STYLE = _s(
    "tbl_hdr",
    font="Helvetica-Bold",
    fontSize=7.6,
    leading=9.2,
    color=C_BG,
    alignment=TA_CENTER,
    wordWrap="LTR",
)
BODY_STYLE = _s(
    "tbl_body",
    fontSize=8.0,
    leading=10.2,
    color=C_BODY,
    alignment=TA_LEFT,
    wordWrap="LTR",
)
BODY_CENTER = ParagraphStyle("tbl_body_center", parent=BODY_STYLE, alignment=TA_CENTER)
BODY_RIGHT = ParagraphStyle("tbl_body_right", parent=BODY_STYLE, alignment=TA_RIGHT)


def _tbl(data, widths, aligns=None, header_color=C_ACCENT, top_pad=5, bottom_pad=5):
    """ReportLab table with forced wrapping and safe padding."""
    aligns = aligns or ["left"] * len(widths)

    cooked = []
    for r, row in enumerate(data):
        cooked_row = []
        for c, cell in enumerate(row):
            if hasattr(cell, "wrap"):
                cooked_row.append(cell)
                continue
            if r == 0:
                cooked_row.append(_para(cell, HEADER_STYLE, TA_CENTER))
            else:
                alg = aligns[c] if c < len(aligns) else "left"
                style = BODY_STYLE
                if alg == "center":
                    style = BODY_CENTER
                elif alg == "right":
                    style = BODY_RIGHT
                cooked_row.append(_para(cell, style))
        cooked.append(cooked_row)

    t = Table(cooked, colWidths=widths, repeatRows=1, splitByRow=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), header_color),
                ("TEXTCOLOR", (0, 0), (-1, 0), C_BG),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_BG, C_ROW_ALT]),
                ("GRID", (0, 0), (-1, -1), 0.35, C_BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), top_pad),
                ("BOTTOMPADDING", (0, 0), (-1, -1), bottom_pad),
            ]
        )
    )
    return t


def _draw_header(c, company_name, timestamp):
    c.saveState()
    c.setFillColor(C_ACCENT)
    c.rect(0, H - 14 * mm, W, 14 * mm, fill=1, stroke=0)

    c.setFont("Helvetica-Bold", 13)
    c.setFillColor(C_BG)
    c.drawString(20 * mm, H - 9.5 * mm, "GreenLens")

    c.setFont("Helvetica", 7)
    c.setFillColor(colors.HexColor("#A7F3D0"))
    c.drawString(46 * mm, H - 9.5 * mm, "ESG Risk Intelligence")

    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(C_BG)
    max_w = 82 * mm
    label = _ellipsize_canvas_text(c, _safe_text(company_name).upper(), max_w, "Helvetica-Bold", 8)
    c.drawRightString(W - 20 * mm, H - 9.5 * mm, label)
    c.restoreState()


def _draw_footer(c, timestamp, page_num):
    c.saveState()
    c.setFillColor(C_BORDER)
    c.rect(0, 0, W, 10 * mm, fill=1, stroke=0)
    c.setFont("Helvetica", 6.5)
    c.setFillColor(C_MUTED)
    footer = f"GreenLens ESG Terminal  -  {timestamp}  -  Data: FinBERT + yfinance + RSS"
    footer = _ellipsize_canvas_text(c, footer, W - 55 * mm, "Helvetica", 6.5)
    c.drawString(20 * mm, 3.5 * mm, footer)
    c.setFont("Helvetica-Bold", 7)
    c.setFillColor(C_ACCENT)
    c.drawRightString(W - 20 * mm, 3.5 * mm, f"Page {page_num}")
    c.restoreState()


class _PageDeco:
    def __init__(self, company_name, timestamp):
        self.company = company_name
        self.ts = timestamp
        self.page = 0

    def __call__(self, c, doc):
        self.page += 1
        _draw_header(c, self.company, self.ts)
        _draw_footer(c, self.ts, self.page)


def generate_pdf(result: dict, eli5_text: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=23 * mm,
        bottomMargin=16 * mm,
        title=f"GreenLens ESG Report - {_safe_text(result.get('company'))}",
        author="GreenLens",
    )

    flag = result.get("flag", "MEDIUM")
    fc = _fc(flag)
    fbg = _fbg(flag)
    info = result.get("company_info", {}) or {}
    score = _fmt_num(result.get("final_score"), 2)
    fin = result.get("fin_formatted", {}) or {}
    drivers = result.get("drivers", []) or []
    improv = result.get("improvements", []) or drivers
    company = _safe_text(info.get("name") or result.get("company"), "Company")
    ticker = _safe_text(result.get("ticker"))
    timestamp = _safe_text(result.get("timestamp"))
    deco = _PageDeco(company, timestamp)

    ST = {
        "h1": _s("h1", font="Helvetica-Bold", fontSize=21, leading=24, color=C_DARK, alignment=TA_CENTER, spaceAfter=2),
        "h2": _s("h2", font="Helvetica-Bold", fontSize=12.5, leading=15, color=C_DARK, alignment=TA_CENTER, spaceAfter=2),
        "section": _s("sec", font="Helvetica-Bold", fontSize=9, leading=11, color=C_ACCENT, spaceBefore=6, spaceAfter=2),
        "body": _s("bd", fontSize=8.5, leading=12.5, color=C_BODY, spaceAfter=3),
        "small": _s("sm", fontSize=7.2, leading=9.2, color=C_MUTED, alignment=TA_CENTER, spaceAfter=2),
        "driver": _s("dr", fontSize=8.4, leading=12.2, color=C_BODY, spaceAfter=3),
        "imp": _s("im", fontSize=8.4, leading=12.2, color=C_GREEN, spaceAfter=3),
        "warn": _s("wn", font="Helvetica-Bold", fontSize=8.3, leading=11.2, color=C_RED, spaceAfter=4),
        "score": _s("sc", font="Helvetica-Bold", fontSize=31, leading=34, color=fc, alignment=TA_CENTER, spaceAfter=0),
        "flag": _s("fl", font="Helvetica-Bold", fontSize=12, leading=14, color=fc, alignment=TA_CENTER, spaceAfter=0),
        "meta": _s("mt", fontSize=8, leading=10.5, color=C_MUTED, alignment=TA_CENTER, spaceAfter=3),
        "callout": _s("co", fontSize=8.4, leading=12.0, color=C_BODY, alignment=TA_LEFT),
    }

    blurb = {
        "LOW": "Strong ESG profile. Suitable for ESG-focused portfolios.",
        "MEDIUM": "Moderate ESG risk. Monitor sentiment trend before allocation.",
        "HIGH": "Significant ESG risk flags. Further due diligence is recommended.",
    }.get(flag, "Moderate ESG profile.")

    weights = result.get("score_weights", {
        "sentiment": 0.50,
        "financial": 0.25,
        "governance": 0.20,
        "momentum": 0.05,
    })
    gov_score = result.get("governance_score", result.get("g_score", 50))
    momentum_score = result.get("momentum_score", 50)
    greenwashing = result.get("greenwashing", {}) or {}
    penalty = float(greenwashing.get("score_penalty", 0) or 0)

    hero_html = (
        f'<para align="center">'
        f'<font name="Helvetica-Bold" size="31" color="{fc.hexval()}">{score}</font><br/>'
        f'<font name="Helvetica-Bold" size="12" color="{fc.hexval()}">{flag} RISK</font><br/>'
        f'<font name="Helvetica" size="7.2" color="{C_MUTED.hexval()}">{escape(blurb)}</font>'
        f'</para>'
    )

    score_card = Table(
        [[Paragraph(hero_html, ST["body"])]],
        colWidths=[doc.width],
    )
    score_card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), fbg),
                ("BOX", (0, 0), (-1, -1), 0.7, fc),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )

    company_meta = "  |  ".join(
        [
            f"Ticker: {ticker}",
            f"Sector: {_safe_text(info.get('sector'))}",
            f"Country: {_safe_text(info.get('country'))}",
            f"Updated: {timestamp}",
        ]
    )

    story = [
        Spacer(1, 4),
        Paragraph(escape(company.upper()), ST["h1"]),
        Paragraph(escape(company_meta), ST["meta"]),
        Spacer(1, 8),
        score_card,
        Spacer(1, 12),
    ]

    derivation_rows = [
        ["COMPONENT", "RAW SCORE", "WEIGHT", "CONTRIBUTION"],
        [
            "Sentiment (News)",
            f"{_fmt_num(result.get('sentiment_score'))} / 100",
            f"{int(weights['sentiment'] * 100)}%",
            f"{float(result.get('sentiment_score', 0)) * weights['sentiment']:.1f} pts",
        ],
        [
            "Financial Health",
            f"{_fmt_num(result.get('financial_score'))} / 100",
            f"{int(weights['financial'] * 100)}%",
            f"{float(result.get('financial_score', 0)) * weights['financial']:.1f} pts",
        ],
        [
            "Governance (Avg E/S/G)",
            f"{_fmt_num(gov_score)} / 100",
            f"{int(weights['governance'] * 100)}%",
            f"{float(gov_score) * weights['governance']:.1f} pts",
        ],
        [
            "Stock Momentum",
            f"{_fmt_num(momentum_score)} / 100",
            f"{int(weights['momentum'] * 100)}%",
            f"{float(momentum_score) * weights['momentum']:.1f} pts",
        ],
    ]
    if penalty > 0:
        derivation_rows.append([
            "Greenwash Penalty",
            f"-{penalty:.1f} pts",
            "Applied after sum",
            f"-{penalty:.1f} pts",
        ])
    derivation_rows.append([
        "TOTAL ESG SCORE",
        f"{score} / 100",
        "100%",
        f"{score} pts",
    ])

    story += [
        *_section_title("Score Overview", ST),
        _tbl(
            derivation_rows,
            [75 * mm, 34 * mm, 25 * mm, 40 * mm],
            aligns=["left", "center", "center", "center"],
        ),
        Spacer(1, 10),
        *_section_title("E / S / G Breakdown", ST),
        _tbl(
            [
                ["ENVIRONMENTAL", "SOCIAL", "GOVERNANCE", "COMBINED"],
                [
                    f"{_fmt_num(result.get('e_score'))} / 100",
                    f"{_fmt_num(result.get('s_score'))} / 100",
                    f"{_fmt_num(result.get('g_score'))} / 100",
                    f"{_fmt_num(gov_score)} / 100",
                ],
            ],
            [44 * mm, 44 * mm, 44 * mm, 40 * mm],
            aligns=["center", "center", "center", "center"],
        ),
        Spacer(1, 10),
    ]

    if fin:
        story += [
            *_section_title("Financial Snapshot", ST),
            _tbl(
                [
                    ["METRIC", "VALUE", "METRIC", "VALUE"],
                    ["Market Cap", _safe_text(fin.get("market_cap")), "Revenue", _safe_text(fin.get("revenue"))],
                    ["P/E Ratio", _safe_text(fin.get("pe")), "ROE", _safe_text(fin.get("roe"))],
                    ["D/E Ratio", _safe_text(fin.get("de_ratio")), "Price", _safe_text(fin.get("price"))],
                    ["52W High", _safe_text(fin.get("52w_high")), "52W Low", _safe_text(fin.get("52w_low"))],
                ],
                [38 * mm, 47 * mm, 38 * mm, 47 * mm],
                aligns=["left", "center", "left", "center"],
            ),
            Spacer(1, 10),
        ]

    story += [
        *_section_title("Executive Summary", ST),
        Paragraph(escape(_safe_text(eli5_text, blurb)), ST["body"]),
    ]

    extra_notes = []
    if result.get("alert"):
        extra_notes.append(f"Alert: {_safe_text(result.get('alert_reason'))}")
    div = result.get("divergence", {}) or {}
    if div.get("flag"):
        extra_notes.append(_safe_text(div.get("message")))
    if greenwashing.get("flag") and greenwashing.get("signals"):
        extra_notes.extend([_safe_text(s) for s in greenwashing.get("signals", [])[:2]])

    if extra_notes:
        notes_tbl = Table(
            [[Paragraph("<br/>".join([escape(n) for n in extra_notes if n]), ST["callout"])]],
            colWidths=[doc.width],
        )
        notes_tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), C_NOTE_BG),
                    ("BOX", (0, 0), (-1, -1), 0.5, C_BORDER),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story += [Spacer(1, 8), *_section_title("Risk Notes", ST), notes_tbl]

    story.append(PageBreak())

    story += [
        Spacer(1, 4),
        Paragraph("Detailed ESG Analysis", ST["h2"]),
        Paragraph(escape(company), ST["meta"]),
        Spacer(1, 10),
        *_section_title("What Drove This Score", ST),
    ]
    for d in (drivers or ["No specific drivers available."]):
        story.append(Paragraph(escape(f"• {d}"), ST["driver"]))

    story += [Spacer(1, 6), *_section_title("Improvement Recommendations", ST)]
    for imp in (improv or ["No recommendations available."]):
        story.append(Paragraph(escape(f"→ {imp}"), ST["imp"]))

    methodology = (
        "GreenLens ESG scores are computed using a weighted composite formula. "
        f"News Sentiment ({int(weights['sentiment'] * 100)}%) uses ProsusAI/FinBERT to classify recent headlines as positive, negative, or neutral. "
        f"Financial Health ({int(weights['financial'] * 100)}%) evaluates valuation, leverage, growth, profitability, and balance-sheet strength using yfinance data. "
        f"Governance ({int(weights['governance'] * 100)}%) is the combined E, S, and G proxy score derived from company information and headline context. "
        f"Stock Momentum ({int(weights['momentum'] * 100)}%) reflects recent market trend signals. "
        "When contradiction signals suggest possible greenwashing, a penalty is applied after the weighted sum."
    )

    story += [
        Spacer(1, 10),
        *_section_title("Scoring Methodology", ST),
        Paragraph(escape(methodology), ST["body"]),
        Spacer(1, 10),
        *_section_title("Risk Classification", ST),
        _tbl(
            [
                ["RISK LEVEL", "SCORE RANGE", "DESCRIPTION", "RECOMMENDATION"],
                ["LOW", "66 - 100", "Strong ESG profile", "Suitable for ESG-focused portfolios"],
                ["MEDIUM", "41 - 65", "Moderate ESG risk", "Monitor before allocation"],
                ["HIGH", "0 - 40", "Significant risk flags", "Further due diligence required"],
            ],
            [24 * mm, 26 * mm, 54 * mm, 66 * mm],
            aligns=["center", "center", "left", "left"],
        ),
    ]

    doc.build(story, onFirstPage=deco, onLaterPages=deco)
    return buf.getvalue()