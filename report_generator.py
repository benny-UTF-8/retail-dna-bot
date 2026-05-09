"""
report_generator.py
====================
Generates a professional 10-page PDF business diagnostic report for the
Retail DNA Bot.  Built with ReportLab (Platypus high-level layout engine).

Public API
----------
generate_pdf_report(data: dict, chat_id: int) -> str
    Build the PDF and return the file path.
"""

import os
import json
import math
import logging
from datetime import datetime

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table,
    TableStyle, Image, HRFlowable, PageBreak, KeepTogether,
)
from reportlab.platypus.flowables import Flowable

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Brand palette
# ─────────────────────────────────────────────
NAVY        = colors.HexColor('#0D1B2A')
TEAL        = colors.HexColor('#1B998B')
AMBER       = colors.HexColor('#FFBC42')
RED         = colors.HexColor('#D62839')
LIGHT_GREY  = colors.HexColor('#F4F6F8')
MID_GREY    = colors.HexColor('#BDC3C7')
DARK_GREY   = colors.HexColor('#4A4A4A')
WHITE       = colors.white
GREEN       = colors.HexColor('#27AE60')
ORANGE      = colors.HexColor('#E67E22')

PAGE_W, PAGE_H = A4          # 595.27 × 841.89 pts
MARGIN = 1.8 * cm

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _fmt_dollar(v: float) -> str:
    if abs(v) >= 1_000_000:
        return f"${v/1_000_000:.2f}M"
    if abs(v) >= 1_000:
        return f"${v:,.0f}"
    return f"${v:.2f}"


def _fmt_pct(v: float) -> str:
    return f"{v:.1f}%"


def _lever_status(score: float) -> tuple:
    """Return (emoji_text, color) based on score."""
    if score < 40:
        return ("● CRITICAL", RED)
    if score < 70:
        return ("● WARNING",  ORANGE)
    return ("● HEALTHY",  GREEN)


def _annualise(data: dict) -> float:
    tf = data.get('timeframe', 'weekly')
    return {'weekly': 52, 'monthly': 12, 'yearly': 1}.get(tf, 52)


def _period_revenue(data: dict) -> float:
    return (data.get('customers', 0) *
            data.get('frequency', 0) *
            data.get('avg_spend', 0))


def _annual_revenue(data: dict) -> float:
    return _period_revenue(data) * _annualise(data)


def _annual_profit(data: dict) -> float:
    return _annual_revenue(data) * (data.get('net_profit', 0) / 100)


def _scores_from_data(data: dict) -> dict:
    """Re-derive lever scores (mirrors main.py logic)."""
    customers    = data.get('customers', 0)
    frequency    = data.get('frequency', 0)
    avg_spend    = data.get('avg_spend', 0)
    gross_margin = data.get('gross_margin', 0)
    return {
        'Customer Base':     min(100, round((customers    / 500) * 100, 1)),
        'Frequency':         min(100, round((frequency    / 3)   * 100, 1)),
        'Transaction Value': min(100, round((avg_spend    / 100) * 100, 1)),
        'Margin':            min(100, round((gross_margin / 50)  * 100, 1)),
    }


def _bottleneck(scores: dict) -> str:
    return min(scores, key=scores.get)


# ─────────────────────────────────────────────
# Matplotlib chart helpers (saved as PNG, embedded in PDF)
# ─────────────────────────────────────────────

def _chart_lever_bars(scores: dict, bottleneck: str, path: str) -> str:
    levers = list(scores.keys())
    values = [scores[l] for l in levers]
    bar_colors = ['#D62839' if l == bottleneck else '#1B998B' for l in levers]

    fig, ax = plt.subplots(figsize=(7, 3.2))
    fig.patch.set_facecolor('#F4F6F8')
    ax.set_facecolor('#F4F6F8')

    bars = ax.barh(levers, values, color=bar_colors, edgecolor='white',
                   linewidth=0.8, height=0.55)
    ax.set_xlim(0, 115)
    ax.set_xlabel('Score (0 – 100)', fontsize=9, color='#4A4A4A')
    ax.set_title('Retail DNA — Lever Scores', fontsize=11,
                 fontweight='bold', color='#0D1B2A', pad=8)
    ax.tick_params(colors='#4A4A4A', labelsize=9)
    ax.spines[['top', 'right', 'bottom']].set_visible(False)
    ax.spines['left'].set_color('#BDC3C7')

    for bar, val in zip(bars, values):
        ax.text(val + 2, bar.get_y() + bar.get_height() / 2,
                f'{val:.0f}', va='center', fontsize=9,
                fontweight='bold', color='#0D1B2A')

    ax.axvline(x=70, color='#FFBC42', linestyle='--', linewidth=1.2)
    ax.text(71, -0.55, 'Target 70', color='#FFBC42', fontsize=7.5)

    legend_handles = [
        mpatches.Patch(color='#D62839', label='Bottleneck'),
        mpatches.Patch(color='#1B998B', label='Other levers'),
    ]
    ax.legend(handles=legend_handles, loc='lower right', fontsize=8,
              framealpha=0.6)

    plt.tight_layout(pad=0.8)
    plt.savefig(path, dpi=130, bbox_inches='tight')
    plt.close()
    return path


def _chart_profit_waterfall(data: dict, path: str) -> str:
    annual_rev   = _annual_revenue(data)
    cogs_val     = annual_rev * (data.get('cogs', 70) / 100)
    gross_profit = annual_rev * (data.get('gross_margin', 30) / 100)
    net_profit   = annual_rev * (data.get('net_profit', 4) / 100)

    labels = ['Revenue', 'COGS', 'Gross Profit', 'Net Profit']
    values = [annual_rev, cogs_val, gross_profit, net_profit]
    bar_colors = ['#1B998B', '#D62839', '#27AE60', '#FFBC42']

    fig, ax = plt.subplots(figsize=(7, 3.2))
    fig.patch.set_facecolor('#F4F6F8')
    ax.set_facecolor('#F4F6F8')

    bars = ax.bar(labels, values, color=bar_colors, edgecolor='white',
                  linewidth=0.8, width=0.55)
    ax.set_title('Annual Financial Snapshot', fontsize=11,
                 fontweight='bold', color='#0D1B2A', pad=8)
    ax.set_ylabel('Dollars ($)', fontsize=9, color='#4A4A4A')
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f'${x:,.0f}'))
    ax.tick_params(colors='#4A4A4A', labelsize=8)
    ax.spines[['top', 'right']].set_visible(False)
    ax.spines[['left', 'bottom']].set_color('#BDC3C7')

    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height() * 0.93,
                f'${val:,.0f}', ha='center', va='top',
                color='white', fontsize=8, fontweight='bold')

    plt.tight_layout(pad=0.8)
    plt.savefig(path, dpi=130, bbox_inches='tight')
    plt.close()
    return path


def _chart_scenario(scenario_rows: list, path: str) -> str:
    """Horizontal bar chart: revenue impact per lever at +10%."""
    levers  = [r['lever'] for r in scenario_rows]
    impacts = [r['rev_impact'] for r in scenario_rows]
    bar_colors = ['#D62839' if i == impacts.index(max(impacts))
                  else '#1B998B' for i in range(len(impacts))]

    fig, ax = plt.subplots(figsize=(7, 2.8))
    fig.patch.set_facecolor('#F4F6F8')
    ax.set_facecolor('#F4F6F8')

    bars = ax.barh(levers, impacts, color=bar_colors, edgecolor='white',
                   linewidth=0.8, height=0.5)
    ax.set_xlabel('Additional Annual Revenue ($)', fontsize=9, color='#4A4A4A')
    ax.set_title('+10% Improvement — Revenue Impact by Lever', fontsize=10,
                 fontweight='bold', color='#0D1B2A', pad=8)
    ax.xaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f'${x:,.0f}'))
    ax.tick_params(colors='#4A4A4A', labelsize=8)
    ax.spines[['top', 'right', 'bottom']].set_visible(False)
    ax.spines['left'].set_color('#BDC3C7')

    for bar, val in zip(bars, impacts):
        ax.text(val + max(impacts) * 0.01,
                bar.get_y() + bar.get_height() / 2,
                f'${val:,.0f}', va='center', fontsize=8,
                fontweight='bold', color='#0D1B2A')

    plt.tight_layout(pad=0.8)
    plt.savefig(path, dpi=130, bbox_inches='tight')
    plt.close()
    return path


# ─────────────────────────────────────────────
# ReportLab custom flowables
# ─────────────────────────────────────────────

class ColorRect(Flowable):
    """A solid-colour rectangle used as a section header background."""
    def __init__(self, width, height, fill_color, radius=4):
        super().__init__()
        self.width  = width
        self.height = height
        self.fill_color = fill_color
        self.radius = radius

    def draw(self):
        self.canv.setFillColor(self.fill_color)
        self.canv.roundRect(0, 0, self.width, self.height,
                            self.radius, stroke=0, fill=1)


# ─────────────────────────────────────────────
# Style factory
# ─────────────────────────────────────────────

def _make_styles():
    base = getSampleStyleSheet()

    def ps(name, **kw):
        defaults = dict(fontName='Helvetica', fontSize=10,
                        textColor=DARK_GREY, leading=14, spaceAfter=4)
        defaults.update(kw)
        return ParagraphStyle(name, **defaults)

    styles = {
        'cover_title': ps('cover_title', fontName='Helvetica-Bold',
                          fontSize=32, textColor=WHITE,
                          alignment=TA_CENTER, leading=38, spaceAfter=8),
        'cover_sub':   ps('cover_sub', fontName='Helvetica',
                          fontSize=14, textColor=AMBER,
                          alignment=TA_CENTER, leading=18, spaceAfter=6),
        'cover_meta':  ps('cover_meta', fontName='Helvetica',
                          fontSize=11, textColor=WHITE,
                          alignment=TA_CENTER, leading=16, spaceAfter=4),
        'section_hdr': ps('section_hdr', fontName='Helvetica-Bold',
                          fontSize=14, textColor=WHITE,
                          alignment=TA_LEFT, leading=18, spaceAfter=0),
        'h2':          ps('h2', fontName='Helvetica-Bold',
                          fontSize=12, textColor=NAVY,
                          leading=16, spaceAfter=4),
        'h3':          ps('h3', fontName='Helvetica-Bold',
                          fontSize=10, textColor=TEAL,
                          leading=14, spaceAfter=2),
        'body':        ps('body', fontSize=9, leading=13, spaceAfter=3),
        'body_bold':   ps('body_bold', fontName='Helvetica-Bold',
                          fontSize=9, leading=13, spaceAfter=3),
        'small':       ps('small', fontSize=8, textColor=MID_GREY,
                          leading=11, spaceAfter=2),
        'table_hdr':   ps('table_hdr', fontName='Helvetica-Bold',
                          fontSize=8, textColor=WHITE,
                          alignment=TA_CENTER, leading=11),
        'table_cell':  ps('table_cell', fontSize=8,
                          alignment=TA_CENTER, leading=11),
        'table_left':  ps('table_left', fontSize=8,
                          alignment=TA_LEFT, leading=11),
        'kpi_value':   ps('kpi_value', fontName='Helvetica-Bold',
                          fontSize=18, textColor=TEAL,
                          alignment=TA_CENTER, leading=22),
        'kpi_label':   ps('kpi_label', fontSize=8, textColor=DARK_GREY,
                          alignment=TA_CENTER, leading=11),
        'rec_action':  ps('rec_action', fontName='Helvetica-Bold',
                          fontSize=9, textColor=NAVY, leading=13),
        'rec_detail':  ps('rec_detail', fontSize=8, textColor=DARK_GREY,
                          leading=12),
        'footer':      ps('footer', fontSize=7, textColor=MID_GREY,
                          alignment=TA_CENTER, leading=10),
        'appendix':    ps('appendix', fontSize=8.5, leading=13, spaceAfter=3),
    }
    return styles


# ─────────────────────────────────────────────
# Section-header helper
# ─────────────────────────────────────────────

def _section_header(title: str, styles: dict, page_width: float) -> list:
    """Return a list of flowables that render a coloured section header bar."""
    usable = page_width - 2 * MARGIN
    rect   = ColorRect(usable, 22, NAVY)
    para   = Paragraph(title, styles['section_hdr'])
    tbl    = Table([[para]], colWidths=[usable])
    tbl.setStyle(TableStyle([
        ('BACKGROUND',  (0, 0), (-1, -1), NAVY),
        ('TOPPADDING',  (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('ROUNDEDCORNERS', [4]),
    ]))
    return [tbl, Spacer(1, 6)]


# ─────────────────────────────────────────────
# Page-level header / footer callbacks
# ─────────────────────────────────────────────

def _on_page(canvas, doc, business_name: str, report_date: str):
    canvas.saveState()
    # Top accent bar
    canvas.setFillColor(TEAL)
    canvas.rect(0, PAGE_H - 6, PAGE_W, 6, stroke=0, fill=1)
    # Footer
    canvas.setFillColor(MID_GREY)
    canvas.setFont('Helvetica', 7)
    footer_text = (
        f"{business_name}  |  Retail DNA Report  |  {report_date}  |  "
        f"Page {doc.page}"
    )
    canvas.drawCentredString(PAGE_W / 2, 14, footer_text)
    canvas.setStrokeColor(LIGHT_GREY)
    canvas.line(MARGIN, 22, PAGE_W - MARGIN, 22)
    canvas.restoreState()


# ─────────────────────────────────────────────
# Scenario planning calculations
# ─────────────────────────────────────────────

def _build_scenario_rows(data: dict) -> list:
    customers  = data.get('customers', 0)
    frequency  = data.get('frequency', 1)
    avg_spend  = data.get('avg_spend', 0)
    np_pct     = data.get('net_profit', 4) / 100
    gm_pct     = data.get('gross_margin', 30) / 100
    mult       = _annualise(data)

    base_rev    = customers * frequency * avg_spend * mult
    base_profit = base_rev * np_pct

    levers = [
        ('Customer Base',     customers * 1.10, frequency,        avg_spend,        np_pct),
        ('Frequency',         customers,        frequency * 1.10, avg_spend,        np_pct),
        ('Transaction Value', customers,        frequency,        avg_spend * 1.10, np_pct),
        ('Margin',            customers,        frequency,        avg_spend,        np_pct * 1.10),
    ]

    rows = []
    for lever, c, f, s, np in levers:
        new_rev    = c * f * s * mult
        new_profit = new_rev * np
        rev_impact    = new_rev    - base_rev
        profit_impact = new_profit - base_profit
        pct_gain      = ((new_profit / base_profit) - 1) * 100 if base_profit else 0
        rows.append({
            'lever':          lever,
            'base_rev':       base_rev,
            'new_rev':        new_rev,
            'rev_impact':     rev_impact,
            'base_profit':    base_profit,
            'new_profit':     new_profit,
            'profit_impact':  profit_impact,
            'pct_gain':       pct_gain,
        })

    # Sort by profit impact descending
    rows.sort(key=lambda r: r['profit_impact'], reverse=True)
    return rows


# ─────────────────────────────────────────────
# Recommendation library
# ─────────────────────────────────────────────

RECOMMENDATIONS = {
    'Customer Base': [
        {
            'action':  'Launch geo-targeted social media ads',
            'impact':  '+5–10% new customer acquisition',
            'effort':  'Medium',
            'timeline': '1 month',
        },
        {
            'action':  'Optimise Google Business Profile (photos, posts, reviews)',
            'impact':  '+3–8% walk-in traffic',
            'effort':  'Low',
            'timeline': '1 month',
        },
        {
            'action':  'Introduce a referral incentive program',
            'impact':  '+0.5–2 new customers per existing customer/month',
            'effort':  'Low',
            'timeline': '1 month',
        },
        {
            'action':  'Partner with complementary local businesses for cross-promotion',
            'impact':  '+5–15% new customer reach',
            'effort':  'Medium',
            'timeline': '3 months',
        },
        {
            'action':  'Expand product range to attract new shopper segments',
            'impact':  '+10–20% addressable market',
            'effort':  'High',
            'timeline': '3 months',
        },
    ],
    'Frequency': [
        {
            'action':  'Implement a digital loyalty / stamp-card program',
            'impact':  '+0.3–0.5 visits/period per member',
            'effort':  'Low',
            'timeline': '1 month',
        },
        {
            'action':  'Create weekly in-store events (tastings, demos, workshops)',
            'impact':  '+0.2–0.4 visits/period',
            'effort':  'Medium',
            'timeline': '1 month',
        },
        {
            'action':  'Send personalised SMS/email when customers haven\'t visited in 14 days',
            'impact':  '+5–12% reactivation rate',
            'effort':  'Low',
            'timeline': '1 month',
        },
        {
            'action':  'Stock everyday essentials (FOP categories) to drive habitual visits',
            'impact':  '+0.3–0.6 visits/period',
            'effort':  'Medium',
            'timeline': '3 months',
        },
        {
            'action':  'Introduce subscription / auto-replenishment for top SKUs',
            'impact':  '+1–2 guaranteed visits/period per subscriber',
            'effort':  'High',
            'timeline': '3 months',
        },
    ],
    'Transaction Value': [
        {
            'action':  'Train staff to suggest one complementary item at POS',
            'impact':  '+$3–8 per transaction',
            'effort':  'Low',
            'timeline': '1 month',
        },
        {
            'action':  'Merchandise complementary products together (cross-sell zones)',
            'impact':  '+$5–12 per transaction',
            'effort':  'Low',
            'timeline': '1 month',
        },
        {
            'action':  'Introduce bundle deals ("Buy 2, save 10%")',
            'impact':  '+$8–15 per transaction',
            'effort':  'Low',
            'timeline': '1 month',
        },
        {
            'action':  'Add a premium / trade-up product range',
            'impact':  '+$10–25 per transaction for upgraders',
            'effort':  'Medium',
            'timeline': '3 months',
        },
        {
            'action':  'Set minimum spend thresholds for perks (free delivery, gift)',
            'impact':  '+$5–10 average basket lift',
            'effort':  'Low',
            'timeline': '1 month',
        },
    ],
    'Margin': [
        {
            'action':  'Renegotiate supplier terms (volume rebates, early-pay discounts)',
            'impact':  '+1–3% gross margin',
            'effort':  'Medium',
            'timeline': '1 month',
        },
        {
            'action':  'Audit and reduce top CODB line items (rent, wages, energy)',
            'impact':  '+0.5–2% net margin',
            'effort':  'Medium',
            'timeline': '1 month',
        },
        {
            'action':  'Rationalise slow-moving SKUs to free up cash and reduce waste',
            'impact':  '+0.5–1.5% gross margin',
            'effort':  'Low',
            'timeline': '1 month',
        },
        {
            'action':  'Shift product mix toward higher-margin own-label / premium lines',
            'impact':  '+2–5% gross margin over time',
            'effort':  'High',
            'timeline': '6 months',
        },
        {
            'action':  'Implement waste / shrinkage tracking and reduction program',
            'impact':  '+0.5–1% gross margin',
            'effort':  'Medium',
            'timeline': '3 months',
        },
    ],
}

EFFORT_ORDER = {'Low': 0, 'Medium': 1, 'High': 2}


def _get_prioritised_recs(bottleneck: str, scores: dict) -> list:
    """
    Return recommendations sorted by: bottleneck lever first, then by effort
    (Low → Medium → High).
    """
    lever_order = [bottleneck] + [l for l in scores if l != bottleneck]
    all_recs = []
    for lever in lever_order:
        for rec in RECOMMENDATIONS.get(lever, []):
            all_recs.append({'lever': lever, **rec})
    # Within each lever group, sort by effort
    all_recs.sort(key=lambda r: (lever_order.index(r['lever']),
                                  EFFORT_ORDER.get(r['effort'], 1)))
    return all_recs


# ─────────────────────────────────────────────
# 90-Day plan builder
# ─────────────────────────────────────────────

def _build_90_day_plan(bottleneck: str, scores: dict) -> dict:
    recs = _get_prioritised_recs(bottleneck, scores)
    low    = [r for r in recs if r['effort'] == 'Low'][:3]
    medium = [r for r in recs if r['effort'] == 'Medium'][:3]
    high   = [r for r in recs if r['effort'] == 'High'][:2]
    return {
        'month1': low,
        'month2': medium,
        'month3': high,
    }


# ─────────────────────────────────────────────
# Financial projections
# ─────────────────────────────────────────────

def _build_projections(data: dict) -> dict:
    customers  = data.get('customers', 0)
    frequency  = data.get('frequency', 1)
    avg_spend  = data.get('avg_spend', 0)
    gm_pct     = data.get('gross_margin', 30) / 100
    cogs_pct   = data.get('cogs', 70) / 100
    np_pct     = data.get('net_profit', 4) / 100
    mult       = _annualise(data)

    def _calc(c, f, s, gm, np):
        rev        = c * f * s * mult
        cogs_val   = rev * (1 - gm)
        gross_p    = rev * gm
        net_p      = rev * np
        return dict(customers=c, frequency=f, avg_spend=s,
                    revenue=rev, cogs=cogs_val,
                    gross_profit=gross_p, net_profit=net_p)

    current = _calc(customers, frequency, avg_spend, gm_pct, np_pct)

    # 90-day: modest improvements across all levers
    target_90 = _calc(
        customers  * 1.05,
        frequency  * 1.05,
        avg_spend  * 1.05,
        min(gm_pct + 0.02, 0.80),
        min(np_pct + 0.01, 0.40),
    )

    # 12-month: compounding effect
    target_12m = _calc(
        customers  * 1.15,
        frequency  * 1.15,
        avg_spend  * 1.10,
        min(gm_pct + 0.05, 0.80),
        min(np_pct + 0.03, 0.40),
    )

    return {'current': current, 'target_90': target_90, 'target_12m': target_12m}


# ─────────────────────────────────────────────
# Data persistence helpers
# ─────────────────────────────────────────────

HISTORY_DIR = 'report_history'


def save_analysis_history(chat_id: int, data: dict, scores: dict,
                           bottleneck: str, business_name: str):
    """Persist analysis data to JSON for progress tracking."""
    os.makedirs(HISTORY_DIR, exist_ok=True)
    history_file = os.path.join(HISTORY_DIR, f'{chat_id}_history.json')

    history = []
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r') as f:
                history = json.load(f)
        except Exception:
            history = []

    entry = {
        'timestamp':     datetime.now().isoformat(),
        'business_name': business_name,
        'timeframe':     data.get('timeframe', 'weekly'),
        'customers':     data.get('customers', 0),
        'frequency':     data.get('frequency', 0),
        'avg_spend':     data.get('avg_spend', 0),
        'gross_margin':  data.get('gross_margin', 0),
        'cogs':          data.get('cogs', 0),
        'net_profit':    data.get('net_profit', 0),
        'annual_revenue': _annual_revenue(data),
        'annual_profit':  _annual_profit(data),
        'scores':        scores,
        'bottleneck':    bottleneck,
    }
    history.append(entry)

    with open(history_file, 'w') as f:
        json.dump(history, f, indent=2)

    return history


def load_analysis_history(chat_id: int) -> list:
    history_file = os.path.join(HISTORY_DIR, f'{chat_id}_history.json')
    if not os.path.exists(history_file):
        return []
    try:
        with open(history_file, 'r') as f:
            return json.load(f)
    except Exception:
        return []


# ─────────────────────────────────────────────
# ─────────────────────────────────────────────
# PAGE BUILDERS
# ─────────────────────────────────────────────
# ─────────────────────────────────────────────

def _page1_cover(story, data, scores, bottleneck, business_name,
                 report_date, styles):
    """Page 1 — Cover & Executive Summary."""
    tf           = data.get('timeframe', 'weekly')
    annual_rev   = _annual_revenue(data)
    annual_prof  = _annual_profit(data)
    net_margin   = data.get('net_profit', 0)
    usable_w     = PAGE_W - 2 * MARGIN

    # ── Full-width navy cover block ──────────────────────────────────────
    cover_data = [[
        Paragraph('RETAIL DNA', styles['cover_title']),
    ]]
    cover_tbl = Table(cover_data, colWidths=[usable_w])
    cover_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), NAVY),
        ('TOPPADDING',    (0, 0), (-1, -1), 28),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING',   (0, 0), (-1, -1), 16),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 16),
        ('ROUNDEDCORNERS', [6]),
    ]))
    story.append(cover_tbl)

    sub_data = [[
        Paragraph('Business Diagnostic Report', styles['cover_sub']),
    ]]
    sub_tbl = Table(sub_data, colWidths=[usable_w])
    sub_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), NAVY),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 20),
        ('LEFTPADDING',   (0, 0), (-1, -1), 16),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 16),
    ]))
    story.append(sub_tbl)
    story.append(Spacer(1, 10))

    # ── Business name / date / timeframe ────────────────────────────────
    meta_rows = [
        [Paragraph(f'<b>Business:</b>  {business_name}', styles['body']),
         Paragraph(f'<b>Date:</b>  {report_date}', styles['body'])],
        [Paragraph(f'<b>Timeframe:</b>  {tf.capitalize()} data', styles['body']),
         Paragraph(f'<b>Bottleneck:</b>  {bottleneck}', styles['body'])],
    ]
    meta_tbl = Table(meta_rows, colWidths=[usable_w / 2, usable_w / 2])
    meta_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), LIGHT_GREY),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
        ('GRID',          (0, 0), (-1, -1), 0.3, MID_GREY),
        ('ROUNDEDCORNERS', [4]),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 14))

    # ── KPI tiles ────────────────────────────────────────────────────────
    story.extend(_section_header('📊  Executive Summary', styles, PAGE_W))

    kpi_col_w = usable_w / 3
    kpi_data = [[
        Paragraph(_fmt_dollar(annual_rev),  styles['kpi_value']),
        Paragraph(_fmt_dollar(annual_prof), styles['kpi_value']),
        Paragraph(_fmt_pct(net_margin),     styles['kpi_value']),
    ], [
        Paragraph('Annual Revenue',  styles['kpi_label']),
        Paragraph('Annual Net Profit', styles['kpi_label']),
        Paragraph('Net Margin',      styles['kpi_label']),
    ]]
    kpi_tbl = Table(kpi_data, colWidths=[kpi_col_w] * 3)
    kpi_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), LIGHT_GREY),
        ('TOPPADDING',    (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
        ('LINEAFTER',     (0, 0), (1, -1),  0.5, MID_GREY),
        ('ROUNDEDCORNERS', [4]),
    ]))
    story.append(kpi_tbl)
    story.append(Spacer(1, 14))

    # ── Bottleneck callout ───────────────────────────────────────────────
    bn_explanations = {
        'Customer Base':
            'You don\'t have enough customers flowing through the door. '
            'Every other lever is limited by this ceiling.',
        'Frequency':
            'Your existing customers aren\'t coming back often enough. '
            'Loyalty and repeat-visit strategies will move the needle fastest.',
        'Transaction Value':
            'Customers are visiting but spending too little per trip. '
            'Basket-building tactics will unlock significant revenue.',
        'Margin':
            'Your cost structure is eroding profit. Even small improvements '
            'to COGS or CODB will have an outsized impact on the bottom line.',
    }
    bn_text = bn_explanations.get(bottleneck, '')
    bn_score = scores.get(bottleneck, 0)
    status_text, status_color = _lever_status(bn_score)

    bn_data = [[
        Paragraph(f'🚨  Bottleneck Lever: <b>{bottleneck}</b>  '
                  f'(Score: {bn_score:.0f}/100)', styles['h2']),
        Paragraph(status_text, ParagraphStyle(
            'status', fontName='Helvetica-Bold', fontSize=10,
            textColor=status_color, alignment=TA_RIGHT)),
    ], [
        Paragraph(bn_text, styles['body']),
        Paragraph('', styles['body']),
    ]]
    bn_tbl = Table(bn_data, colWidths=[usable_w * 0.72, usable_w * 0.28])
    bn_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#FFF3CD')),
        ('TOPPADDING',    (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
        ('SPAN',          (0, 1), (1, 1)),
        ('ROUNDEDCORNERS', [4]),
        ('BOX',           (0, 0), (-1, -1), 1, AMBER),
    ]))
    story.append(bn_tbl)
    story.append(Spacer(1, 14))

    # ── One-sentence recommendation ──────────────────────────────────────
    one_liners = {
        'Customer Base':
            'Priority action: Launch a referral program and geo-targeted ads '
            'this month to grow your customer base by 10%.',
        'Frequency':
            'Priority action: Implement a digital loyalty program this month '
            'to increase visit frequency by 0.3+ visits per period.',
        'Transaction Value':
            'Priority action: Train staff to cross-sell one item at POS and '
            'introduce bundle deals to lift average spend by $5–10.',
        'Margin':
            'Priority action: Renegotiate your top 3 supplier contracts and '
            'audit CODB this month to recover 1–2% net margin.',
    }
    story.append(Paragraph(
        f'<b>Recommended Priority:</b>  {one_liners.get(bottleneck, "")}',
        styles['body']
    ))
    story.append(PageBreak())


def _page2_financial(story, data, styles):
    """Page 2 — Financial Snapshot."""
    tf           = data.get('timeframe', 'weekly')
    mult         = _annualise(data)
    period_rev   = _period_revenue(data)
    annual_rev   = period_rev * mult
    cogs_pct     = data.get('cogs', 70)
    gm_pct       = data.get('gross_margin', 30)
    np_pct       = data.get('net_profit', 4)
    cogs_val     = annual_rev * (cogs_pct / 100)
    gross_profit = annual_rev * (gm_pct / 100)
    net_profit   = annual_rev * (np_pct / 100)
    usable_w     = PAGE_W - 2 * MARGIN

    story.extend(_section_header('💰  Financial Snapshot', styles, PAGE_W))

    # ── Summary table ────────────────────────────────────────────────────
    col_w = [usable_w * 0.45, usable_w * 0.28, usable_w * 0.27]
    hdr = [
        Paragraph('Metric',          styles['table_hdr']),
        Paragraph('Amount ($)',       styles['table_hdr']),
        Paragraph('% of Revenue',     styles['table_hdr']),
    ]
    rows = [
        [Paragraph(f'Period Revenue ({tf.capitalize()})', styles['table_left']),
         Paragraph(_fmt_dollar(period_rev), styles['table_cell']),
         Paragraph('100.0%', styles['table_cell'])],
        [Paragraph('Annual Revenue (Projected)', styles['table_left']),
         Paragraph(_fmt_dollar(annual_rev), styles['table_cell']),
         Paragraph('100.0%', styles['table_cell'])],
        [Paragraph('COGS', styles['table_left']),
         Paragraph(_fmt_dollar(cogs_val), styles['table_cell']),
         Paragraph(_fmt_pct(cogs_pct), styles['table_cell'])],
        [Paragraph('Gross Profit', styles['table_left']),
         Paragraph(_fmt_dollar(gross_profit), styles['table_cell']),
         Paragraph(_fmt_pct(gm_pct), styles['table_cell'])],
        [Paragraph('Net Profit', styles['table_left']),
         Paragraph(_fmt_dollar(net_profit), styles['table_cell']),
         Paragraph(_fmt_pct(np_pct), styles['table_cell'])],
    ]

    fin_tbl = Table([hdr] + rows, colWidths=col_w)
    fin_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0),  NAVY),
        ('BACKGROUND',    (0, 1), (-1, 1),  LIGHT_GREY),
        ('BACKGROUND',    (0, 2), (-1, 2),  WHITE),
        ('BACKGROUND',    (0, 3), (-1, 3),  LIGHT_GREY),
        ('BACKGROUND',    (0, 4), (-1, 4),  WHITE),
        ('BACKGROUND',    (0, 5), (-1, 5),  colors.HexColor('#E8F8F5')),
        ('TEXTCOLOR',     (0, 0), (-1, 0),  WHITE),
        ('FONTNAME',      (0, 5), (-1, 5),  'Helvetica-Bold'),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
        ('GRID',          (0, 0), (-1, -1), 0.3, MID_GREY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHT_GREY, WHITE]),
    ]))
    story.append(fin_tbl)
    story.append(Spacer(1, 14))

    # ── Revenue formula ──────────────────────────────────────────────────
    customers_n = data.get('customers', 0)
    freq        = data.get('frequency', 0)
    spend       = data.get('avg_spend', 0)

    story.append(Paragraph('Revenue Formula', styles['h2']))
    formula_data = [[
        Paragraph(f'{customers_n:,}', styles['kpi_value']),
        Paragraph('×', styles['h2']),
        Paragraph(f'{freq:.1f}', styles['kpi_value']),
        Paragraph('×', styles['h2']),
        Paragraph(f'${spend:.2f}', styles['kpi_value']),
        Paragraph('×', styles['h2']),
        Paragraph(f'{mult}', styles['kpi_value']),
        Paragraph('=', styles['h2']),
        Paragraph(_fmt_dollar(annual_rev), styles['kpi_value']),
    ], [
        Paragraph('Customers', styles['kpi_label']),
        Paragraph('', styles['kpi_label']),
        Paragraph('Frequency', styles['kpi_label']),
        Paragraph('', styles['kpi_label']),
        Paragraph('Avg Spend', styles['kpi_label']),
        Paragraph('', styles['kpi_label']),
        Paragraph('Periods/yr', styles['kpi_label']),
        Paragraph('', styles['kpi_label']),
        Paragraph('Annual Rev', styles['kpi_label']),
    ]]
    col_ws = [usable_w * w for w in
              [0.14, 0.04, 0.10, 0.04, 0.12, 0.04, 0.12, 0.04, 0.36]]
    formula_tbl = Table(formula_data, colWidths=col_ws)
    formula_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), LIGHT_GREY),
        ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('ROUNDEDCORNERS', [4]),
    ]))
    story.append(formula_tbl)
    story.append(PageBreak())


def _page3_lever_analysis(story, data, scores, bottleneck, chart_path, styles):
    """Page 3 — Retail DNA Lever Analysis."""
    usable_w = PAGE_W - 2 * MARGIN

    story.extend(_section_header('🧬  Retail DNA Lever Analysis', styles, PAGE_W))

    benchmarks = {
        'Customer Base':     '500 customers/period',
        'Frequency':         '3.0 visits/period',
        'Transaction Value': '$100.00 avg spend',
        'Margin':            '50% gross margin',
    }
    current_vals = {
        'Customer Base':     f"{data.get('customers', 0):,} customers",
        'Frequency':         f"{data.get('frequency', 0):.1f} visits/period",
        'Transaction Value': f"${data.get('avg_spend', 0):.2f} avg spend",
        'Margin':            f"{data.get('gross_margin', 0):.1f}% gross margin",
    }

    col_w = [usable_w * w for w in [0.22, 0.22, 0.12, 0.22, 0.22]]
    hdr = [
        Paragraph('Lever',         styles['table_hdr']),
        Paragraph('Current Value', styles['table_hdr']),
        Paragraph('Score',         styles['table_hdr']),
        Paragraph('Benchmark',     styles['table_hdr']),
        Paragraph('Status',        styles['table_hdr']),
    ]
    rows = []
    for lever, score in scores.items():
        status_text, status_color = _lever_status(score)
        is_bn = (lever == bottleneck)
        rows.append([
            Paragraph(f'<b>{lever}</b>' if is_bn else lever, styles['table_left']),
            Paragraph(current_vals.get(lever, '—'), styles['table_cell']),
            Paragraph(f'{score:.0f}/100', styles['table_cell']),
            Paragraph(benchmarks.get(lever, '—'), styles['table_cell']),
            Paragraph(status_text, ParagraphStyle(
                'st', fontName='Helvetica-Bold', fontSize=8,
                textColor=status_color, alignment=TA_CENTER)),
        ])

    lever_tbl = Table([hdr] + rows, colWidths=col_w)
    ts = [
        ('BACKGROUND',    (0, 0), (-1, 0),  NAVY),
        ('TEXTCOLOR',     (0, 0), (-1, 0),  WHITE),
        ('TOPPADDING',    (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING',   (0, 0), (-1, -1), 6),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 6),
        ('GRID',          (0, 0), (-1, -1), 0.3, MID_GREY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHT_GREY, WHITE]),
    ]
    # Highlight bottleneck row
    for i, lever in enumerate(scores.keys()):
        if lever == bottleneck:
            ts.append(('BACKGROUND', (0, i + 1), (-1, i + 1),
                        colors.HexColor('#FDECEA')))
    lever_tbl.setStyle(TableStyle(ts))
    story.append(lever_tbl)
    story.append(Spacer(1, 14))

    # ── Bar chart ────────────────────────────────────────────────────────
    story.append(Paragraph('Lever Score Visualisation', styles['h2']))
    story.append(Spacer(1, 4))
    img = Image(chart_path, width=usable_w, height=usable_w * 0.46)
    story.append(img)
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        'Red bar = bottleneck lever (lowest score).  '
        'Dashed line = target score of 70.  '
        'Focus improvement efforts on the red lever first.',
        styles['small']
    ))
    story.append(PageBreak())


def _page4_bottleneck(story, data, scores, bottleneck, styles):
    """Page 4 — Bottleneck Deep-Dive."""
    usable_w = PAGE_W - 2 * MARGIN
    bn_score = scores.get(bottleneck, 0)
    status_text, status_color = _lever_status(bn_score)

    story.extend(_section_header(
        f'🔎  Bottleneck Deep-Dive: {bottleneck}', styles, PAGE_W))

    benchmarks_num = {
        'Customer Base':     500,
        'Frequency':         3.0,
        'Transaction Value': 100.0,
        'Margin':            50.0,
    }
    current_num = {
        'Customer Base':     data.get('customers', 0),
        'Frequency':         data.get('frequency', 0),
        'Transaction Value': data.get('avg_spend', 0),
        'Margin':            data.get('gross_margin', 0),
    }
    units = {
        'Customer Base':     'customers/period',
        'Frequency':         'visits/period',
        'Transaction Value': '$ avg spend',
        'Margin':            '% gross margin',
    }

    cur_val  = current_num.get(bottleneck, 0)
    bench    = benchmarks_num.get(bottleneck, 100)
    unit     = units.get(bottleneck, '')
    gap      = bench - cur_val
    gap_pct  = (gap / bench * 100) if bench else 0

    # ── State vs benchmark ───────────────────────────────────────────────
    state_data = [[
        Paragraph('Current State', styles['table_hdr']),
        Paragraph('Benchmark',     styles['table_hdr']),
        Paragraph('Gap',           styles['table_hdr']),
        Paragraph('Gap %',         styles['table_hdr']),
        Paragraph('Score',         styles['table_hdr']),
    ], [
        Paragraph(f'{cur_val:,.1f} {unit}', styles['table_cell']),
        Paragraph(f'{bench:,.1f} {unit}',   styles['table_cell']),
        Paragraph(f'{gap:,.1f} {unit}',     styles['table_cell']),
        Paragraph(f'{gap_pct:.1f}%',        styles['table_cell']),
        Paragraph(f'{bn_score:.0f}/100',    styles['table_cell']),
    ]]
    col_w = [usable_w / 5] * 5
    state_tbl = Table(state_data, colWidths=col_w)
    state_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0),  NAVY),
        ('BACKGROUND',    (0, 1), (-1, 1),  colors.HexColor('#FDECEA')),
        ('TEXTCOLOR',     (0, 0), (-1, 0),  WHITE),
        ('TOPPADDING',    (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('GRID',          (0, 0), (-1, -1), 0.3, MID_GREY),
        ('ROUNDEDCORNERS', [4]),
    ]))
    story.append(state_tbl)
    story.append(Spacer(1, 12))

    # ── Why it matters ───────────────────────────────────────────────────
    story.append(Paragraph('Why This Lever Matters Most', styles['h2']))
    why_text = {
        'Customer Base':
            'Customer Base is the foundation of your revenue engine. '
            'Every other lever — frequency, spend, and margin — is multiplied '
            'by the number of customers you have. A thin customer base creates '
            'a ceiling that no amount of loyalty or upselling can overcome. '
            'Growing your customer count by even 10% delivers a direct, '
            'proportional lift to every other metric.',
        'Frequency':
            'Frequency is the most cost-effective growth lever because you\'re '
            'selling to people who already know and trust you. Increasing how '
            'often existing customers visit requires no new acquisition spend — '
            'just better loyalty mechanics, in-store reasons to return, and '
            'proactive outreach. A 10% lift in frequency is a 10% lift in '
            'revenue with near-zero incremental cost.',
        'Transaction Value':
            'Transaction Value determines how much revenue you extract from '
            'each customer interaction. If customers are visiting but spending '
            'below benchmark, you\'re leaving money on the table at every '
            'single transaction. Cross-selling, bundling, and premium ranging '
            'are proven, low-cost tactics that compound across every visit.',
        'Margin':
            'Margin is the multiplier on everything else. A business with '
            'strong revenue but thin margins is working hard for little reward. '
            'Even a 1% improvement in gross margin flows directly to the bottom '
            'line. Supplier negotiations, CODB reduction, and mix management '
            'are the fastest paths to meaningful profit improvement.',
    }
    story.append(Paragraph(why_text.get(bottleneck, ''), styles['body']))
    story.append(Spacer(1, 10))

    # ── Diagnostic answers ───────────────────────────────────────────────
    diag = data.get('diagnostic_answers', '')
    if diag:
        story.append(Paragraph('Your Diagnostic Answers', styles['h2']))
        story.append(Paragraph(
            'Based on your responses to the diagnostic questions:', styles['body']))
        story.append(Spacer(1, 4))
        diag_data = [[Paragraph(diag, styles['body'])]]
        diag_tbl = Table(diag_data, colWidths=[usable_w])
        diag_tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), LIGHT_GREY),
            ('TOPPADDING',    (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING',   (0, 0), (-1, -1), 10),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
            ('BOX',           (0, 0), (-1, -1), 0.5, TEAL),
            ('ROUNDEDCORNERS', [4]),
        ]))
        story.append(diag_tbl)
        story.append(Spacer(1, 10))

    # ── Impact on business ───────────────────────────────────────────────
    story.append(Paragraph('Impact on Overall Business', styles['h2']))
    annual_rev   = _annual_revenue(data)
    annual_prof  = _annual_profit(data)
    np_pct       = data.get('net_profit', 4) / 100
    mult         = _annualise(data)
    customers_n  = data.get('customers', 0)
    freq         = data.get('frequency', 1)
    spend        = data.get('avg_spend', 0)

    if bottleneck == 'Customer Base':
        new_rev  = (customers_n * 1.10) * freq * spend * mult
    elif bottleneck == 'Frequency':
        new_rev  = customers_n * (freq * 1.10) * spend * mult
    elif bottleneck == 'Transaction Value':
        new_rev  = customers_n * freq * (spend * 1.10) * mult
    else:
        new_rev  = annual_rev  # margin improvement doesn't change revenue

    new_profit   = new_rev * (np_pct * (1.10 if bottleneck == 'Margin' else 1))
    rev_gain     = new_rev    - annual_rev
    profit_gain  = new_profit - annual_prof

    impact_data = [[
        Paragraph('Metric',          styles['table_hdr']),
        Paragraph('Current',         styles['table_hdr']),
        Paragraph('+10% Improvement', styles['table_hdr']),
        Paragraph('Gain',            styles['table_hdr']),
    ], [
        Paragraph('Annual Revenue',  styles['table_left']),
        Paragraph(_fmt_dollar(annual_rev),  styles['table_cell']),
        Paragraph(_fmt_dollar(new_rev),     styles['table_cell']),
        Paragraph(f'+{_fmt_dollar(rev_gain)}', styles['table_cell']),
    ], [
        Paragraph('Annual Net Profit', styles['table_left']),
        Paragraph(_fmt_dollar(annual_prof),  styles['table_cell']),
        Paragraph(_fmt_dollar(new_profit),   styles['table_cell']),
        Paragraph(f'+{_fmt_dollar(profit_gain)}', styles['table_cell']),
    ]]
    col_w = [usable_w * w for w in [0.30, 0.23, 0.27, 0.20]]
    impact_tbl = Table(impact_data, colWidths=col_w)
    impact_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0),  NAVY),
        ('BACKGROUND',    (0, 1), (-1, 1),  LIGHT_GREY),
        ('BACKGROUND',    (0, 2), (-1, 2),  colors.HexColor('#E8F8F5')),
        ('TEXTCOLOR',     (0, 0), (-1, 0),  WHITE),
        ('FONTNAME',      (3, 1), (3, -1),  'Helvetica-Bold'),
        ('TEXTCOLOR',     (3, 1), (3, -1),  GREEN),
        ('TOPPADDING',    (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
        ('GRID',          (0, 0), (-1, -1), 0.3, MID_GREY),
    ]))
    story.append(impact_tbl)
    story.append(PageBreak())


def _page5_scenario(story, data, scenario_rows, chart_path, styles):
    """Page 5 — Scenario Planning (What-If Analysis)."""
    usable_w = PAGE_W - 2 * MARGIN

    story.extend(_section_header('📐  Scenario Planning — What-If Analysis', styles, PAGE_W))
    story.append(Paragraph(
        'The table below shows the annual revenue and profit impact of a '
        '10% improvement in each lever independently, ranked by profit impact.',
        styles['body']
    ))
    story.append(Spacer(1, 8))

    col_w = [usable_w * w for w in [0.22, 0.18, 0.18, 0.14, 0.14, 0.14]]
    hdr = [
        Paragraph('Lever',           styles['table_hdr']),
        Paragraph('Current Rev',     styles['table_hdr']),
        Paragraph('+10% Rev',        styles['table_hdr']),
        Paragraph('Rev Impact',      styles['table_hdr']),
        Paragraph('Profit Impact',   styles['table_hdr']),
        Paragraph('Profit % Gain',   styles['table_hdr']),
    ]
    rows = []
    for i, r in enumerate(scenario_rows):
        rank_label = '🥇' if i == 0 else ('🥈' if i == 1 else ('🥉' if i == 2 else ''))
        rows.append([
            Paragraph(f'{rank_label} {r["lever"]}', styles['table_left']),
            Paragraph(_fmt_dollar(r['base_rev']),    styles['table_cell']),
            Paragraph(_fmt_dollar(r['new_rev']),     styles['table_cell']),
            Paragraph(f'+{_fmt_dollar(r["rev_impact"])}',    styles['table_cell']),
            Paragraph(f'+{_fmt_dollar(r["profit_impact"])}', styles['table_cell']),
            Paragraph(f'+{r["pct_gain"]:.1f}%',     styles['table_cell']),
        ])

    scen_tbl = Table([hdr] + rows, colWidths=col_w)
    ts = [
        ('BACKGROUND',    (0, 0), (-1, 0),  NAVY),
        ('TEXTCOLOR',     (0, 0), (-1, 0),  WHITE),
        ('TOPPADDING',    (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING',   (0, 0), (-1, -1), 6),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 6),
        ('GRID',          (0, 0), (-1, -1), 0.3, MID_GREY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHT_GREY, WHITE]),
        ('FONTNAME',      (0, 1), (-1, 1),  'Helvetica-Bold'),
        ('BACKGROUND',    (0, 1), (-1, 1),  colors.HexColor('#E8F8F5')),
    ]
    scen_tbl.setStyle(TableStyle(ts))
    story.append(scen_tbl)
    story.append(Spacer(1, 14))

    # ── Chart ────────────────────────────────────────────────────────────
    story.append(Paragraph('Revenue Impact Visualisation', styles['h2']))
    story.append(Spacer(1, 4))
    img = Image(chart_path, width=usable_w, height=usable_w * 0.40)
    story.append(img)
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        'Highlighted bar = highest-ROI lever.  '
        'Focus your first 30 days on the top-ranked lever for maximum return.',
        styles['small']
    ))
    story.append(PageBreak())


def _page6_recommendations(story, data, scores, bottleneck, styles):
    """Page 6 — Actionable Recommendations."""
    usable_w = PAGE_W - 2 * MARGIN
    recs = _get_prioritised_recs(bottleneck, scores)[:12]  # top 12

    story.extend(_section_header('✅  Actionable Recommendations', styles, PAGE_W))
    story.append(Paragraph(
        'Recommendations are prioritised by lever (bottleneck first) and '
        'effort level (Low → Medium → High).  '
        'Fill in the Owner column to assign accountability.',
        styles['body']
    ))
    story.append(Spacer(1, 8))

    col_w = [usable_w * w for w in [0.20, 0.28, 0.18, 0.10, 0.12, 0.12]]
    hdr = [
        Paragraph('Lever',          styles['table_hdr']),
        Paragraph('Action',         styles['table_hdr']),
        Paragraph('Expected Impact', styles['table_hdr']),
        Paragraph('Effort',         styles['table_hdr']),
        Paragraph('Timeline',       styles['table_hdr']),
        Paragraph('Owner',          styles['table_hdr']),
    ]
    rows = []
    for rec in recs:
        effort_color = {'Low': GREEN, 'Medium': ORANGE, 'High': RED}.get(
            rec['effort'], DARK_GREY)
        rows.append([
            Paragraph(rec['lever'],    styles['table_left']),
            Paragraph(rec['action'],   styles['table_left']),
            Paragraph(rec['impact'],   styles['table_left']),
            Paragraph(rec['effort'],   ParagraphStyle(
                'eff', fontName='Helvetica-Bold', fontSize=8,
                textColor=effort_color, alignment=TA_CENTER)),
            Paragraph(rec['timeline'], styles['table_cell']),
            Paragraph('___________',  styles['table_cell']),
        ])

    rec_tbl = Table([hdr] + rows, colWidths=col_w)
    rec_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0),  NAVY),
        ('TEXTCOLOR',     (0, 0), (-1, 0),  WHITE),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING',   (0, 0), (-1, -1), 5),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 5),
        ('GRID',          (0, 0), (-1, -1), 0.3, MID_GREY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHT_GREY, WHITE]),
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(rec_tbl)
    story.append(PageBreak())


def _page7_action_plan(story, data, scores, bottleneck, styles):
    """Page 7 — 90-Day Action Plan."""
    usable_w = PAGE_W - 2 * MARGIN
    plan = _build_90_day_plan(bottleneck, scores)

    story.extend(_section_header('📅  90-Day Action Plan', styles, PAGE_W))
    story.append(Paragraph(
        'A phased plan to implement recommendations over the next 90 days. '
        'Month 1 focuses on quick wins; Month 2 on medium-term initiatives; '
        'Month 3 on strategic moves that compound over time.',
        styles['body']
    ))
    story.append(Spacer(1, 10))

    months = [
        ('Month 1 — Quick Wins', plan['month1'],
         'Complete setup and launch.  Measure baseline metrics.',
         TEAL),
        ('Month 2 — Build Momentum', plan['month2'],
         'Review Month 1 results.  Optimise and scale what\'s working.',
         NAVY),
        ('Month 3 — Strategic Moves', plan['month3'],
         'Assess compounding impact.  Set 12-month targets.',
         AMBER),
    ]

    for month_title, month_recs, success_metric, hdr_color in months:
        # Month header
        hdr_data = [[Paragraph(month_title, styles['section_hdr'])]]
        hdr_tbl = Table(hdr_data, colWidths=[usable_w])
        hdr_tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), hdr_color),
            ('TOPPADDING',    (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING',   (0, 0), (-1, -1), 8),
            ('ROUNDEDCORNERS', [4]),
        ]))
        story.append(hdr_tbl)
        story.append(Spacer(1, 4))

        if month_recs:
            col_w = [usable_w * w for w in [0.22, 0.35, 0.20, 0.10, 0.13]]
            hdr_row = [
                Paragraph('Lever',    styles['table_hdr']),
                Paragraph('Action',   styles['table_hdr']),
                Paragraph('Impact',   styles['table_hdr']),
                Paragraph('Effort',   styles['table_hdr']),
                Paragraph('Timeline', styles['table_hdr']),
            ]
            rows = []
            for rec in month_recs:
                rows.append([
                    Paragraph(rec['lever'],    styles['table_left']),
                    Paragraph(rec['action'],   styles['table_left']),
                    Paragraph(rec['impact'],   styles['table_left']),
                    Paragraph(rec['effort'],   styles['table_cell']),
                    Paragraph(rec['timeline'], styles['table_cell']),
                ])
            m_tbl = Table([hdr_row] + rows, colWidths=col_w)
            m_tbl.setStyle(TableStyle([
                ('BACKGROUND',    (0, 0), (-1, 0),  DARK_GREY),
                ('TEXTCOLOR',     (0, 0), (-1, 0),  WHITE),
                ('TOPPADDING',    (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('LEFTPADDING',   (0, 0), (-1, -1), 5),
                ('RIGHTPADDING',  (0, 0), (-1, -1), 5),
                ('GRID',          (0, 0), (-1, -1), 0.3, MID_GREY),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHT_GREY, WHITE]),
                ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
            ]))
            story.append(m_tbl)
        else:
            story.append(Paragraph(
                'Continue optimising Month 1 & 2 initiatives.',
                styles['body']))

        story.append(Spacer(1, 4))
        story.append(Paragraph(
            f'<b>✓ Success Metric:</b>  {success_metric}', styles['small']))
        story.append(Spacer(1, 10))

    story.append(PageBreak())


def _page8_projections(story, data, styles):
    """Page 8 — Financial Projections."""
    usable_w = PAGE_W - 2 * MARGIN
    proj = _build_projections(data)

    story.extend(_section_header('📈  Financial Projections', styles, PAGE_W))
    story.append(Paragraph(
        'Projections assume modest, compounding improvements across all levers. '
        '90-day target: +5% on each lever.  '
        '12-month target: +10–15% on customers & frequency, +10% on spend, '
        '+5% gross margin improvement.',
        styles['body']
    ))
    story.append(Spacer(1, 10))

    col_w = [usable_w * w for w in [0.22, 0.26, 0.26, 0.26]]
    hdr = [
        Paragraph('Metric',           styles['table_hdr']),
        Paragraph('Current State',    styles['table_hdr']),
        Paragraph('90-Day Target',    styles['table_hdr']),
        Paragraph('12-Month Target',  styles['table_hdr']),
    ]

    def _row(label, key, fmt_fn):
        return [
            Paragraph(label, styles['table_left']),
            Paragraph(fmt_fn(proj['current'][key]),   styles['table_cell']),
            Paragraph(fmt_fn(proj['target_90'][key]), styles['table_cell']),
            Paragraph(fmt_fn(proj['target_12m'][key]), styles['table_cell']),
        ]

    rows = [
        _row('Customers / Period', 'customers',
             lambda v: f'{v:,.0f}'),
        _row('Frequency (visits/period)', 'frequency',
             lambda v: f'{v:.2f}'),
        _row('Avg Spend / Visit', 'avg_spend',
             lambda v: f'${v:.2f}'),
        _row('Annual Revenue', 'revenue',
             _fmt_dollar),
        _row('Annual COGS', 'cogs',
             _fmt_dollar),
        _row('Annual Gross Profit', 'gross_profit',
             _fmt_dollar),
        _row('Annual Net Profit', 'net_profit',
             _fmt_dollar),
    ]

    proj_tbl = Table([hdr] + rows, colWidths=col_w)
    ts = [
        ('BACKGROUND',    (0, 0), (-1, 0),  NAVY),
        ('TEXTCOLOR',     (0, 0), (-1, 0),  WHITE),
        ('TOPPADDING',    (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
        ('GRID',          (0, 0), (-1, -1), 0.3, MID_GREY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHT_GREY, WHITE]),
        ('FONTNAME',      (0, 7), (-1, 7),  'Helvetica-Bold'),
        ('BACKGROUND',    (0, 7), (-1, 7),  colors.HexColor('#E8F8F5')),
        ('TEXTCOLOR',     (1, 7), (-1, 7),  GREEN),
    ]
    proj_tbl.setStyle(TableStyle(ts))
    story.append(proj_tbl)
    story.append(Spacer(1, 14))

    # ── Compounding note ─────────────────────────────────────────────────
    current_np  = proj['current']['net_profit']
    target_12_np = proj['target_12m']['net_profit']
    np_gain     = target_12_np - current_np
    np_pct_gain = ((target_12_np / current_np) - 1) * 100 if current_np else 0

    note_data = [[Paragraph(
        f'<b>Compounding Effect:</b>  Achieving the 12-month targets across all '
        f'levers simultaneously would grow annual net profit from '
        f'<b>{_fmt_dollar(current_np)}</b> to '
        f'<b>{_fmt_dollar(target_12_np)}</b> — '
        f'an increase of <b>{_fmt_dollar(np_gain)} (+{np_pct_gain:.0f}%)</b>.',
        styles['body']
    )]]
    note_tbl = Table(note_data, colWidths=[usable_w])
    note_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#E8F8F5')),
        ('TOPPADDING',    (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING',   (0, 0), (-1, -1), 12),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 12),
        ('BOX',           (0, 0), (-1, -1), 1, TEAL),
        ('ROUNDEDCORNERS', [4]),
    ]))
    story.append(note_tbl)
    story.append(PageBreak())


def _page9_dashboard(story, data, scores, bottleneck, styles):
    """Page 9 — Key Metrics Dashboard & Tracking Sheet."""
    usable_w = PAGE_W - 2 * MARGIN

    story.extend(_section_header('📋  Key Metrics Dashboard', styles, PAGE_W))
    story.append(Paragraph(
        'Use this page to track your KPIs weekly or monthly. '
        'Fill in the blank rows to monitor progress toward your targets.',
        styles['body']
    ))
    story.append(Spacer(1, 8))

    # ── Current KPI summary ──────────────────────────────────────────────
    annual_rev  = _annual_revenue(data)
    annual_prof = _annual_profit(data)
    np_pct      = data.get('net_profit', 0)
    gm_pct      = data.get('gross_margin', 0)

    kpi_items = [
        ('Customers / Period',  f"{data.get('customers', 0):,}"),
        ('Frequency',           f"{data.get('frequency', 0):.2f} visits"),
        ('Avg Spend',           f"${data.get('avg_spend', 0):.2f}"),
        ('Gross Margin',        f"{gm_pct:.1f}%"),
        ('Net Margin',          f"{np_pct:.1f}%"),
        ('Annual Revenue',      _fmt_dollar(annual_rev)),
        ('Annual Net Profit',   _fmt_dollar(annual_prof)),
        ('Bottleneck Lever',    bottleneck),
        ('Bottleneck Score',    f"{scores.get(bottleneck, 0):.0f}/100"),
    ]

    # 3-column KPI grid
    kpi_col_w = usable_w / 3
    kpi_rows = []
    for i in range(0, len(kpi_items), 3):
        chunk = kpi_items[i:i + 3]
        while len(chunk) < 3:
            chunk.append(('', ''))
        row = []
        for label, value in chunk:
            cell = Table([
                [Paragraph(value, styles['kpi_value'])],
                [Paragraph(label, styles['kpi_label'])],
            ], colWidths=[kpi_col_w - 4])
            cell.setStyle(TableStyle([
                ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
                ('TOPPADDING',    (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ]))
            row.append(cell)
        kpi_rows.append(row)

    kpi_grid = Table(kpi_rows, colWidths=[kpi_col_w] * 3)
    kpi_grid.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), LIGHT_GREY),
        ('GRID',          (0, 0), (-1, -1), 0.5, WHITE),
        ('TOPPADDING',    (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('ROUNDEDCORNERS', [4]),
    ]))
    story.append(kpi_grid)
    story.append(Spacer(1, 14))

    # ── Tracking sheet ───────────────────────────────────────────────────
    story.append(Paragraph('Progress Tracking Sheet', styles['h2']))
    story.append(Paragraph(
        'Record your metrics each week or month to track improvement.',
        styles['body']))
    story.append(Spacer(1, 6))

    track_col_w = [usable_w * w for w in [0.14, 0.14, 0.12, 0.12, 0.12, 0.12, 0.12, 0.12]]
    track_hdr = [
        Paragraph('Date',        styles['table_hdr']),
        Paragraph('Customers',   styles['table_hdr']),
        Paragraph('Frequency',   styles['table_hdr']),
        Paragraph('Avg Spend',   styles['table_hdr']),
        Paragraph('Revenue',     styles['table_hdr']),
        Paragraph('Gross Margin', styles['table_hdr']),
        Paragraph('Net Margin',  styles['table_hdr']),
        Paragraph('Notes',       styles['table_hdr']),
    ]

    # Pre-fill first row with current data, rest blank
    blank = Paragraph('', styles['table_cell'])
    current_row = [
        Paragraph(datetime.now().strftime('%d/%m/%y'), styles['table_cell']),
        Paragraph(f"{data.get('customers', 0):,}", styles['table_cell']),
        Paragraph(f"{data.get('frequency', 0):.1f}", styles['table_cell']),
        Paragraph(f"${data.get('avg_spend', 0):.2f}", styles['table_cell']),
        Paragraph(_fmt_dollar(_period_revenue(data)), styles['table_cell']),
        Paragraph(f"{gm_pct:.1f}%", styles['table_cell']),
        Paragraph(f"{np_pct:.1f}%", styles['table_cell']),
        Paragraph('Baseline', styles['table_cell']),
    ]
    blank_rows = [[blank] * 8 for _ in range(7)]

    track_tbl = Table(
        [track_hdr, current_row] + blank_rows,
        colWidths=track_col_w,
        rowHeights=[None] + [None] + [18] * 7
    )
    track_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0),  NAVY),
        ('BACKGROUND',    (0, 1), (-1, 1),  colors.HexColor('#E8F8F5')),
        ('TEXTCOLOR',     (0, 0), (-1, 0),  WHITE),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
        ('GRID',          (0, 0), (-1, -1), 0.3, MID_GREY),
        ('ROWBACKGROUNDS', (0, 2), (-1, -1), [LIGHT_GREY, WHITE]),
    ]))
    story.append(track_tbl)
    story.append(PageBreak())


def _page10_appendix(story, styles):
    """Page 10 — Appendix: Framework, Glossary, Notes."""
    usable_w = PAGE_W - 2 * MARGIN

    story.extend(_section_header('📚  Appendix', styles, PAGE_W))

    # ── Retail DNA Framework ─────────────────────────────────────────────
    story.append(Paragraph('The Retail DNA Framework', styles['h2']))
    story.append(Paragraph(
        'Retail DNA is a diagnostic framework that breaks retail business '
        'performance into four fundamental levers. Every dollar of revenue '
        'is the product of these four variables:',
        styles['appendix']
    ))
    story.append(Spacer(1, 6))

    formula_text = (
        'Revenue  =  Customers  ×  Frequency  ×  Average Spend  ×  Periods per Year'
    )
    formula_data = [[Paragraph(formula_text, ParagraphStyle(
        'formula', fontName='Helvetica-Bold', fontSize=10,
        textColor=NAVY, alignment=TA_CENTER, leading=14))]]
    formula_tbl = Table(formula_data, colWidths=[usable_w])
    formula_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), LIGHT_GREY),
        ('TOPPADDING',    (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('BOX',           (0, 0), (-1, -1), 1, TEAL),
        ('ROUNDEDCORNERS', [4]),
    ]))
    story.append(formula_tbl)
    story.append(Spacer(1, 8))

    levers_desc = [
        ('Customer Base',
         'The total number of unique customers who visit in a given period. '
         'This is the foundation — every other lever is multiplied by it.'),
        ('Frequency',
         'How often each customer visits per period. Loyalty programs, '
         'in-store events, and habitual-purchase categories drive this lever.'),
        ('Transaction Value (Avg Spend)',
         'The average dollar amount spent per visit. Cross-selling, bundling, '
         'premium ranging, and staff training are the primary drivers.'),
        ('Margin',
         'The percentage of revenue retained after costs. Includes both '
         'Gross Margin (revenue minus COGS) and Net Margin (after all CODB).'),
    ]
    for lever, desc in levers_desc:
        story.append(Paragraph(f'<b>{lever}:</b>  {desc}', styles['appendix']))
        story.append(Spacer(1, 3))

    story.append(Spacer(1, 10))

    # ── Six Key Profit Levers ────────────────────────────────────────────
    story.append(Paragraph('Six Key Profit Levers', styles['h2']))
    six_levers = [
        ('1. Customer Acquisition',
         'Grow the number of new customers through marketing, referrals, '
         'and range expansion.'),
        ('2. COGS Reduction',
         'Reduce the cost of goods sold through supplier negotiation, '
         'volume buying, and range rationalisation.'),
        ('3. Expense Reduction (CODB)',
         'Cut the Cost of Doing Business — rent, wages, energy, and '
         'other overheads — through efficiency and renegotiation.'),
        ('4. Frequency Improvement',
         'Increase how often existing customers visit through loyalty '
         'programs, in-store theatre, and personalised outreach.'),
        ('5. Basket Size (Transaction Value)',
         'Grow the average spend per visit through cross-selling, '
         'bundling, and premium product ranging.'),
        ('6. Trade-Up / Premiumisation',
         'Shift the product mix toward higher-margin items and own-label '
         'lines to improve both revenue and margin simultaneously.'),
    ]
    for lever, desc in six_levers:
        story.append(Paragraph(f'<b>{lever}:</b>  {desc}', styles['appendix']))
        story.append(Spacer(1, 3))

    story.append(Spacer(1, 10))

    # ── Glossary ─────────────────────────────────────────────────────────
    story.append(Paragraph('Glossary', styles['h2']))
    glossary = [
        ('COGS', 'Cost of Goods Sold — the direct cost of the products you sell.'),
        ('CODB', 'Cost of Doing Business — all operating expenses excluding COGS '
                 '(rent, wages, utilities, marketing, etc.).'),
        ('Gross Margin',
         'Revenue minus COGS, expressed as a percentage of revenue. '
         'Measures how efficiently you buy and sell product.'),
        ('Net Margin',
         'Revenue minus all costs (COGS + CODB), expressed as a percentage. '
         'The "true" profitability of the business.'),
        ('Bottleneck Lever',
         'The Retail DNA lever with the lowest score relative to benchmark. '
         'Improving the bottleneck delivers the highest marginal return.'),
        ('Benchmark',
         'The target value for each lever, based on healthy retail performance. '
         'Used to calculate the 0–100 score for each lever.'),
        ('FOP Categories',
         'Front of Pack — everyday essential categories that drive habitual '
         'customer visits (e.g. bread, milk, coffee).'),
        ('SKU',
         'Stock Keeping Unit — a unique identifier for each product variant '
         'in your range.'),
    ]
    col_w = [usable_w * 0.22, usable_w * 0.78]
    gloss_rows = [
        [Paragraph(f'<b>{term}</b>', styles['appendix']),
         Paragraph(defn, styles['appendix'])]
        for term, defn in glossary
    ]
    gloss_tbl = Table(gloss_rows, colWidths=col_w)
    gloss_tbl.setStyle(TableStyle([
        ('TOPPADDING',    (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
        ('GRID',          (0, 0), (-1, -1), 0.3, MID_GREY),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [LIGHT_GREY, WHITE]),
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(gloss_tbl)
    story.append(Spacer(1, 14))

    # ── Notes ────────────────────────────────────────────────────────────
    story.append(Paragraph('Notes', styles['h2']))
    story.append(Paragraph(
        'Use this space to record observations, decisions, and follow-up actions.',
        styles['appendix']
    ))
    story.append(Spacer(1, 6))

    note_lines = [[Paragraph('', styles['appendix'])] for _ in range(10)]
    notes_tbl = Table(note_lines, colWidths=[usable_w],
                      rowHeights=[20] * 10)
    notes_tbl.setStyle(TableStyle([
        ('GRID',          (0, 0), (-1, -1), 0.3, MID_GREY),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [WHITE, LIGHT_GREY]),
    ]))
    story.append(notes_tbl)


# ─────────────────────────────────────────────
# Main public function
# ─────────────────────────────────────────────

def generate_pdf_report(data: dict, chat_id: int,
                        business_name: str = 'Your Store') -> str:
    """
    Build a 10-page PDF diagnostic report and return the file path.

    Parameters
    ----------
    data          : user_data dict from the Telegram conversation
    chat_id       : Telegram chat ID (used for unique file naming)
    business_name : Business name to display on the report
    """
    report_date = datetime.now().strftime('%d %B %Y')
    scores      = data.get('lever_scores') or _scores_from_data(data)
    bottleneck  = data.get('bottleneck')   or _bottleneck(scores)
    styles      = _make_styles()

    # ── Generate chart images ────────────────────────────────────────────
    lever_chart_path  = f'rpt_levers_{chat_id}.png'
    profit_chart_path = f'rpt_profit_{chat_id}.png'
    scenario_rows     = _build_scenario_rows(data)
    scenario_chart_path = f'rpt_scenario_{chat_id}.png'

    try:
        _chart_lever_bars(scores, bottleneck, lever_chart_path)
        _chart_profit_waterfall(data, profit_chart_path)
        _chart_scenario(scenario_rows, scenario_chart_path)
    except Exception as e:
        logger.warning(f'Chart generation error: {e}')

    # ── Persist history ──────────────────────────────────────────────────
    try:
        save_analysis_history(chat_id, data, scores, bottleneck, business_name)
    except Exception as e:
        logger.warning(f'History save error: {e}')

    # ── Build PDF ────────────────────────────────────────────────────────
    pdf_path = f'retail_dna_report_{chat_id}.pdf'

    doc = BaseDocTemplate(
        pdf_path,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN + 10,
        bottomMargin=MARGIN + 10,
    )

    frame = Frame(
        MARGIN, MARGIN + 10,
        PAGE_W - 2 * MARGIN,
        PAGE_H - 2 * MARGIN - 20,
        id='main'
    )

    def _page_cb(canvas, doc):
        _on_page(canvas, doc, business_name, report_date)

    doc.addPageTemplates([
        PageTemplate(id='main', frames=[frame], onPage=_page_cb)
    ])

    story = []

    # Page 1 — Cover & Executive Summary
    _page1_cover(story, data, scores, bottleneck, business_name,
                 report_date, styles)

    # Page 2 — Financial Snapshot
    _page2_financial(story, data, styles)

    # Page 3 — Lever Analysis
    _page3_lever_analysis(story, data, scores, bottleneck,
                          lever_chart_path, styles)

    # Page 4 — Bottleneck Deep-Dive
    _page4_bottleneck(story, data, scores, bottleneck, styles)

    # Page 5 — Scenario Planning
    _page5_scenario(story, data, scenario_rows, scenario_chart_path, styles)

    # Page 6 — Recommendations
    _page6_recommendations(story, data, scores, bottleneck, styles)

    # Page 7 — 90-Day Action Plan
    _page7_action_plan(story, data, scores, bottleneck, styles)

    # Page 8 — Financial Projections
    _page8_projections(story, data, styles)

    # Page 9 — Key Metrics Dashboard
    _page9_dashboard(story, data, scores, bottleneck, styles)

    # Page 10 — Appendix
    _page10_appendix(story, styles)

    doc.build(story)

    # ── Clean up temp chart files ────────────────────────────────────────
    for p in [lever_chart_path, profit_chart_path, scenario_chart_path]:
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass

    logger.info(f'PDF report generated: {pdf_path}')
    return pdf_path
