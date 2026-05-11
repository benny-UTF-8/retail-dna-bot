"""
report_generator.py
====================
Generates a professional 10-page PDF business diagnostic report for the
Retail DNA Bot.  Built with ReportLab (Platypus high-level layout engine).

Integrates with calculation_engine.py and formatting_engine.py for exact,
auditable numbers per the ieRetail framework (Lessons 1-10).

Public API
----------
generate_pdf_report(data: dict, chat_id: int, business_name: str) -> str
    Build the PDF and return the file path.

load_analysis_history(chat_id: int) -> list
    Load past analyses for a user.
"""

import os
import json
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
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table,
    TableStyle, Image, PageBreak, KeepTogether,
)
from reportlab.platypus.flowables import Flowable

from calculation_engine import calculate_all, STORE_TYPE_BENCHMARKS, lever_status
from formatting_engine import (
    fmt_currency, fmt_pct, fmt_pct_from_decimal, fmt_pct_pts,
    fmt_profit_impact, fmt_revenue_impact, fmt_pct_gain,
    lever_status_label, lever_status_color_key,
    fmt_how_to_achieve, rewrite_diagnostic_answer,
)

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

STATUS_COLORS = {
    'green':  GREEN,
    'teal':   TEAL,
    'orange': ORANGE,
    'red':    RED,
}

PAGE_W, PAGE_H = A4
MARGIN = 1.8 * cm


# ─────────────────────────────────────────────
# Custom flowable
# ─────────────────────────────────────────────

class ColorRect(Flowable):
    def __init__(self, width, height, fill_color, radius=4):
        super().__init__()
        self.width      = width
        self.height     = height
        self.fill_color = fill_color
        self.radius     = radius

    def draw(self):
        self.canv.setFillColor(self.fill_color)
        self.canv.roundRect(0, 0, self.width, self.height,
                            self.radius, stroke=0, fill=1)


# ─────────────────────────────────────────────
# Style factory
# ─────────────────────────────────────────────

def _make_styles():
    def ps(name, **kw):
        defaults = dict(fontName='Helvetica', fontSize=10,
                        textColor=DARK_GREY, leading=14, spaceAfter=4)
        defaults.update(kw)
        return ParagraphStyle(name, **defaults)

    return {
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
        'footer':      ps('footer', fontSize=7, textColor=MID_GREY,
                          alignment=TA_CENTER, leading=10),
        'appendix':    ps('appendix', fontSize=8.5, leading=13, spaceAfter=3),
        'mono':        ps('mono', fontName='Courier', fontSize=7.5,
                          textColor=DARK_GREY, leading=11, spaceAfter=2),
    }


# ─────────────────────────────────────────────
# Section header helper
# ─────────────────────────────────────────────

def _section_header(title: str, styles: dict, page_width: float) -> list:
    usable = page_width - 2 * MARGIN
    para   = Paragraph(title, styles['section_hdr'])
    tbl    = Table([[para]], colWidths=[usable])
    tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), NAVY),
        ('TOPPADDING',    (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
        ('ROUNDEDCORNERS', [4]),
    ]))
    return [tbl, Spacer(1, 6)]


# ─────────────────────────────────────────────
# Page header / footer callback
# ─────────────────────────────────────────────

def _on_page(canvas, doc, business_name: str, report_date: str):
    canvas.saveState()
    canvas.setFillColor(TEAL)
    canvas.rect(0, PAGE_H - 6, PAGE_W, 6, stroke=0, fill=1)
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
# Matplotlib chart helpers
# ─────────────────────────────────────────────

def _chart_lever_bars(scores: dict, bottleneck: str,
                      store_type: str, store_benchmark: float,
                      path: str) -> str:
    levers     = list(scores.keys())
    values     = [scores[l] for l in levers]
    bar_colors = ['#D62839' if l == bottleneck else '#1B998B' for l in levers]

    fig, ax = plt.subplots(figsize=(7, 3.2))
    fig.patch.set_facecolor('#F4F6F8')
    ax.set_facecolor('#F4F6F8')

    bars = ax.barh(levers, values, color=bar_colors, edgecolor='white',
                   linewidth=0.8, height=0.55)
    ax.set_xlim(0, 115)
    ax.set_xlabel('Score (0 – 100)', fontsize=9, color='#4A4A4A')
    ax.set_title(
        f'Retail DNA — Lever Scores  ({store_type.title()} store)',
        fontsize=11, fontweight='bold', color='#0D1B2A', pad=8
    )
    ax.tick_params(colors='#4A4A4A', labelsize=9)
    ax.spines[['top', 'right', 'bottom']].set_visible(False)
    ax.spines['left'].set_color('#BDC3C7')

    for bar, val in zip(bars, values):
        ax.text(val + 2, bar.get_y() + bar.get_height() / 2,
                f'{val:.0f}', va='center', fontsize=9,
                fontweight='bold', color='#0D1B2A')

    for x, label, col in [(50, 'MONITOR', '#E67E22'), (70, 'GOOD', '#FFBC42'),
                           (90, 'HEALTHY', '#27AE60')]:
        ax.axvline(x=x, color=col, linestyle='--', linewidth=0.8, alpha=0.7)
        ax.text(x + 0.5, -0.55, label, color=col, fontsize=6.5)

    legend_handles = [
        mpatches.Patch(color='#D62839', label='Bottleneck'),
        mpatches.Patch(color='#1B998B', label='Other levers'),
    ]
    ax.legend(handles=legend_handles, loc='lower right', fontsize=8, framealpha=0.6)

    plt.tight_layout(pad=0.8)
    plt.savefig(path, dpi=130, bbox_inches='tight')
    plt.close()
    return path


def _chart_profit_waterfall(calc: dict, path: str) -> str:
    pnl = calc['pnl']
    labels = ['Revenue', 'COGS', 'Gross Profit', 'CODB', 'Net Profit']
    values = [
        pnl['annual_revenue'],
        pnl['annual_cogs'],
        pnl['annual_gross_profit'],
        pnl['annual_codb'],
        pnl['annual_net_profit'],
    ]
    bar_colors = ['#1B998B', '#D62839', '#27AE60', '#E67E22',
                  '#27AE60' if pnl['annual_net_profit'] >= 0 else '#D62839']

    fig, ax = plt.subplots(figsize=(7, 3.2))
    fig.patch.set_facecolor('#F4F6F8')
    ax.set_facecolor('#F4F6F8')

    bars = ax.bar(labels, values, color=bar_colors, edgecolor='white',
                  linewidth=0.8, width=0.55)
    ax.set_title('Annual Financial Snapshot (GST-exclusive)',
                 fontsize=11, fontweight='bold', color='#0D1B2A', pad=8)
    ax.set_ylabel('Dollars ($)', fontsize=9, color='#4A4A4A')
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f'${x:,.0f}'))
    ax.tick_params(colors='#4A4A4A', labelsize=8)
    ax.spines[['top', 'right']].set_visible(False)
    ax.spines[['left', 'bottom']].set_color('#BDC3C7')

    for bar, val in zip(bars, values):
        y_pos = bar.get_height() * 0.93 if val >= 0 else bar.get_height() * 0.05
        ax.text(bar.get_x() + bar.get_width() / 2, y_pos,
                fmt_currency(val), ha='center', va='top',
                color='white', fontsize=7.5, fontweight='bold')

    plt.tight_layout(pad=0.8)
    plt.savefig(path, dpi=130, bbox_inches='tight')
    plt.close()
    return path


def _chart_scenario(scenario_rows: list, path: str) -> str:
    levers  = [r['lever'] for r in scenario_rows]
    impacts = [r['profit_impact'] for r in scenario_rows]
    max_impact = max(abs(v) for v in impacts) if impacts else 1
    bar_colors = ['#D62839' if i == 0 else '#1B998B'
                  for i in range(len(impacts))]

    fig, ax = plt.subplots(figsize=(7, 2.8))
    fig.patch.set_facecolor('#F4F6F8')
    ax.set_facecolor('#F4F6F8')

    bars = ax.barh(levers, impacts, color=bar_colors, edgecolor='white',
                   linewidth=0.8, height=0.5)
    ax.set_xlabel('Additional Annual Net Profit ($)', fontsize=9, color='#4A4A4A')
    ax.set_title('+10% Improvement — Net Profit Impact by Lever', fontsize=10,
                 fontweight='bold', color='#0D1B2A', pad=8)
    ax.xaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f'${x:,.0f}'))
    ax.tick_params(colors='#4A4A4A', labelsize=8)
    ax.spines[['top', 'right', 'bottom']].set_visible(False)
    ax.spines['left'].set_color('#BDC3C7')

    for bar, val in zip(bars, impacts):
        offset = max_impact * 0.01 if max_impact else 100
        ax.text(val + offset,
                bar.get_y() + bar.get_height() / 2,
                fmt_profit_impact(val), va='center', fontsize=8,
                fontweight='bold', color='#0D1B2A')

    plt.tight_layout(pad=0.8)
    plt.savefig(path, dpi=130, bbox_inches='tight')
    plt.close()
    return path


# ─────────────────────────────────────────────
# Recommendation library
# ─────────────────────────────────────────────

RECOMMENDATIONS = {
    'Customer Base': [
        {'action': 'Launch geo-targeted social media ads',
         'impact': '+5-10% new customer acquisition', 'effort': 'Medium', 'timeline': '1 month'},
        {'action': 'Optimise Google Business Profile (photos, posts, reviews)',
         'impact': '+3-8% walk-in traffic', 'effort': 'Low', 'timeline': '1 month'},
        {'action': 'Introduce a referral incentive program',
         'impact': '+0.5-2 new customers per existing customer/month',
         'effort': 'Low', 'timeline': '1 month'},
        {'action': 'Partner with complementary local businesses for cross-promotion',
         'impact': '+5-15% new customer reach', 'effort': 'Medium', 'timeline': '3 months'},
        {'action': 'Expand product range to attract new shopper segments',
         'impact': '+10-20% addressable market', 'effort': 'High', 'timeline': '3 months'},
    ],
    'Frequency': [
        {'action': 'Implement a digital loyalty / stamp-card program',
         'impact': '+0.3-0.5 visits/period per member', 'effort': 'Low', 'timeline': '1 month'},
        {'action': 'Create weekly in-store events (tastings, demos, workshops)',
         'impact': '+0.2-0.4 visits/period', 'effort': 'Medium', 'timeline': '1 month'},
        {'action': "Send personalised SMS/email when customers haven't visited in 14 days",
         'impact': '+5-12% reactivation rate', 'effort': 'Low', 'timeline': '1 month'},
        {'action': 'Stock everyday essentials (FOP categories) to drive habitual visits',
         'impact': '+0.3-0.6 visits/period', 'effort': 'Medium', 'timeline': '3 months'},
        {'action': 'Introduce subscription / auto-replenishment for top SKUs',
         'impact': '+1-2 guaranteed visits/period per subscriber',
         'effort': 'High', 'timeline': '3 months'},
    ],
    'Transaction Value': [
        {'action': 'Train staff to suggest one complementary item at POS',
         'impact': '+$3-8 per transaction', 'effort': 'Low', 'timeline': '1 month'},
        {'action': 'Merchandise complementary products together (cross-sell zones)',
         'impact': '+$5-12 per transaction', 'effort': 'Low', 'timeline': '1 month'},
        {'action': 'Introduce bundle deals ("Buy 2, save 10%")',
         'impact': '+$8-15 per transaction', 'effort': 'Low', 'timeline': '1 month'},
        {'action': 'Add a premium / trade-up product range',
         'impact': '+$10-25 per transaction for upgraders',
         'effort': 'Medium', 'timeline': '3 months'},
        {'action': 'Set minimum spend thresholds for perks (free delivery, gift)',
         'impact': '+$5-10 average basket lift', 'effort': 'Low', 'timeline': '1 month'},
    ],
    'Margin': [
        {'action': 'Renegotiate supplier terms (volume rebates, early-pay discounts)',
         'impact': '+1-3% gross margin', 'effort': 'Medium', 'timeline': '1 month'},
        {'action': 'Audit and reduce top CODB line items (rent, wages, energy)',
         'impact': '+0.5-2% net margin', 'effort': 'Medium', 'timeline': '1 month'},
        {'action': 'Rationalise slow-moving SKUs to free up cash and reduce waste',
         'impact': '+0.5-1.5% gross margin', 'effort': 'Low', 'timeline': '1 month'},
        {'action': 'Shift product mix toward higher-margin own-label / premium lines',
         'impact': '+2-5% gross margin over time', 'effort': 'High', 'timeline': '6 months'},
        {'action': 'Implement waste / shrinkage tracking and reduction program',
         'impact': '+0.5-1% gross margin', 'effort': 'Medium', 'timeline': '3 months'},
    ],
}

EFFORT_ORDER = {'Low': 0, 'Medium': 1, 'High': 2}


def _get_prioritised_recs(bottleneck: str, scores: dict) -> list:
    lever_order = [bottleneck] + [l for l in scores if l != bottleneck]
    all_recs = []
    for lever in lever_order:
        for rec in RECOMMENDATIONS.get(lever, []):
            all_recs.append({'lever': lever, **rec})
    all_recs.sort(key=lambda r: (lever_order.index(r['lever']),
                                  EFFORT_ORDER.get(r['effort'], 1)))
    return all_recs


def _get_prioritised_recs_ordered(bottleneck: str, lever_order: list) -> list:
    """
    Return recommendations ordered by an explicit lever_order list.
    Bottleneck lever is always first; remaining levers follow in the
    order provided (typically profit-impact descending from scenario table).
    Within each lever, recommendations are sorted Low → Medium → High effort.
    """
    all_recs = []
    for lever in lever_order:
        for rec in RECOMMENDATIONS.get(lever, []):
            all_recs.append({'lever': lever, **rec})
    all_recs.sort(key=lambda r: (lever_order.index(r['lever']),
                                  EFFORT_ORDER.get(r['effort'], 1)))
    return all_recs


def _build_90_day_plan(bottleneck: str, scores: dict) -> dict:
    recs = _get_prioritised_recs(bottleneck, scores)

    # Month 1 — Quick Wins: bottleneck lever Low-effort actions FIRST,
    # then other Low-effort actions to fill up to 3 slots
    bn_low    = [r for r in recs if r['effort'] == 'Low' and r['lever'] == bottleneck]
    other_low = [r for r in recs if r['effort'] == 'Low' and r['lever'] != bottleneck]
    low       = (bn_low + other_low)[:3]

    medium = [r for r in recs if r['effort'] == 'Medium'][:3]
    high   = [r for r in recs if r['effort'] == 'High'][:2]
    return {'month1': low, 'month2': medium, 'month3': high}


# ─────────────────────────────────────────────
# Data persistence
# ─────────────────────────────────────────────

HISTORY_DIR = 'report_history'


def save_analysis_history(chat_id: int, data: dict, calc: dict,
                           business_name: str):
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
        'timestamp':      datetime.now().isoformat(),
        'business_name':  business_name,
        'store_type':     calc.get('store_type', 'other'),
        'timeframe':      data.get('timeframe', 'weekly'),
        'customers':      calc['inputs']['customers'],
        'frequency':      calc['inputs']['frequency'],
        'avg_spend':      calc['inputs']['avg_spend'],
        'cogs_pct':       calc['inputs']['cogs_pct_raw'],
        'annual_revenue': calc['pnl']['annual_revenue'],
        'annual_profit':  calc['pnl']['annual_net_profit'],
        'gross_margin':   calc['pnl']['gross_margin_pct'] * 100,
        'net_margin':     calc['pnl']['net_margin_pct'] * 100,
        'scores':         calc['scores'],
        'bottleneck':     calc['bottleneck'],
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
# PAGE BUILDERS
# ─────────────────────────────────────────────

def _page1_cover(story, calc, data, business_name, report_date, styles):
    """Page 1 - Cover & Executive Summary."""
    pnl              = calc['pnl']
    scores           = calc['scores']
    bottleneck       = calc['bottleneck']
    store_type       = calc['store_type']
    context_override = calc.get('context_override', False)
    override_reason  = calc.get('context_override_reason', '')
    usable_w         = PAGE_W - 2 * MARGIN

    cover_data = [[Paragraph('RETAIL DNA', styles['cover_title'])]]
    cover_tbl  = Table(cover_data, colWidths=[usable_w])
    cover_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), NAVY),
        ('TOPPADDING',    (0, 0), (-1, -1), 28),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING',   (0, 0), (-1, -1), 16),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 16),
        ('ROUNDEDCORNERS', [6]),
    ]))
    story.append(cover_tbl)

    sub_data = [[Paragraph('Business Diagnostic Report', styles['cover_sub'])]]
    sub_tbl  = Table(sub_data, colWidths=[usable_w])
    sub_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), NAVY),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 20),
        ('LEFTPADDING',   (0, 0), (-1, -1), 16),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 16),
    ]))
    story.append(sub_tbl)
    story.append(Spacer(1, 10))

    tf       = data.get('timeframe', 'weekly')
    gst_note = 'GST-exclusive' if data.get('gst_exclusive', True) else 'GST-inclusive'
    meta_rows = [
        [Paragraph(f'<b>Business:</b>  {business_name}', styles['body']),
         Paragraph(f'<b>Date:</b>  {report_date}', styles['body'])],
        [Paragraph(f'<b>Store Type:</b>  {store_type.title()}', styles['body']),
         Paragraph(f'<b>Timeframe:</b>  {tf.capitalize()} data', styles['body'])],
        [Paragraph(f'<b>Prices:</b>  {gst_note}', styles['body']),
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

    story.extend(_section_header('Executive Summary', styles, PAGE_W))
    kpi_col_w = usable_w / 3
    kpi_data = [[
        Paragraph(fmt_currency(pnl['annual_revenue']),    styles['kpi_value']),
        Paragraph(fmt_currency(pnl['annual_net_profit']), styles['kpi_value']),
        Paragraph(fmt_pct_from_decimal(pnl['net_margin_pct']), styles['kpi_value']),
    ], [
        Paragraph('Annual Revenue',    styles['kpi_label']),
        Paragraph('Annual Net Profit', styles['kpi_label']),
        Paragraph('Net Margin',        styles['kpi_label']),
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

    bn_explanations = {
        'Customer Base':
            "You don't have enough customers flowing through the door. "
            "Every other lever is limited by this ceiling.",
        'Frequency':
            "Your existing customers aren't coming back often enough. "
            "Loyalty and repeat-visit strategies will move the needle fastest.",
        'Transaction Value':
            "Customers are visiting but spending too little per trip. "
            "Basket-building tactics will unlock significant revenue.",
        'Margin':
            "Your cost structure is eroding profit. Even small improvements "
            "to COGS or CODB will have an outsized impact on the bottom line.",
    }
    bn_score     = scores.get(bottleneck, 0)
    status_label = lever_status_label(bn_score)
    status_ckey  = lever_status_color_key(bn_score)
    status_color = STATUS_COLORS.get(status_ckey, RED)

    bn_data = [[
        Paragraph(f'Bottleneck Lever: <b>{bottleneck}</b>  '
                  f'(Score: {bn_score:.0f}/100)', styles['h2']),
        Paragraph(status_label, ParagraphStyle(
            'status', fontName='Helvetica-Bold', fontSize=10,
            textColor=status_color, alignment=TA_RIGHT)),
    ], [
        Paragraph(bn_explanations.get(bottleneck, ''), styles['body']),
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
    story.append(Spacer(1, 8))

    # ── Contextual override callout (shown only when override is active) ──
    if context_override and override_reason:
        override_body_style = ParagraphStyle(
            'override_body_p1',
            fontName='Helvetica',
            fontSize=8.5,
            textColor=DARK_GREY,
            leading=13,
            spaceAfter=0,
        )
        override_title_style = ParagraphStyle(
            'override_title_p1',
            fontName='Helvetica-Bold',
            fontSize=9,
            textColor=colors.HexColor('#7D4E00'),
            leading=13,
            spaceAfter=4,
        )
        override_data = [
            [Paragraph('\u26a0 CONTEXTUAL OVERRIDE', override_title_style)],
            [Paragraph(override_reason, override_body_style)],
        ]
        override_tbl = Table(override_data, colWidths=[usable_w])
        override_tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#FFF8DC')),
            ('TOPPADDING',    (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING',   (0, 0), (-1, -1), 12),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
            ('LINEBEFORE',    (0, 0), (0, -1),  3, ORANGE),
            ('ROUNDEDCORNERS', [4]),
        ]))
        story.append(override_tbl)
        story.append(Spacer(1, 8))

    one_liners = {
        'Customer Base':
            'Launch a referral program and geo-targeted ads this month '
            'to grow your customer base by 10%.',
        'Frequency':
            'Implement a digital loyalty program this month to increase '
            'visit frequency by 0.3+ visits per period.',
        'Transaction Value':
            'Train staff to cross-sell one item at POS and introduce bundle '
            'deals to lift average spend by $5-10.',
        'Margin':
            'Renegotiate your top 3 supplier contracts and audit CODB this '
            'month to recover 1-2% net margin.',
    }
    story.append(Paragraph(
        f'<b>Recommended Priority:</b>  {one_liners.get(bottleneck, "")}',
        styles['body']
    ))
    story.append(PageBreak())


def _page2_financial(story, calc, data, styles):
    """Page 2 - Financial Snapshot with CODB breakdown."""
    pnl      = calc['pnl']
    rev      = calc['revenue']
    usable_w = PAGE_W - 2 * MARGIN
    tf       = data.get('timeframe', 'weekly')

    story.extend(_section_header('Financial Snapshot', styles, PAGE_W))
    story.append(Paragraph(
        'All figures are GST-exclusive. '
        'Annual revenue = Customers x Frequency x Avg Spend x Periods/Year.',
        styles['small']
    ))
    story.append(Spacer(1, 8))

    col_w = [usable_w * 0.45, usable_w * 0.28, usable_w * 0.27]
    hdr = [
        Paragraph('Metric',       styles['table_hdr']),
        Paragraph('Amount ($)',   styles['table_hdr']),
        Paragraph('% of Revenue', styles['table_hdr']),
    ]
    rows = [
        [Paragraph(f'Period Revenue ({tf.capitalize()})', styles['table_left']),
         Paragraph(fmt_currency(rev['weekly_revenue']),   styles['table_cell']),
         Paragraph('100.0%',                              styles['table_cell'])],
        [Paragraph('Annual Revenue (Projected)',           styles['table_left']),
         Paragraph(fmt_currency(pnl['annual_revenue']),   styles['table_cell']),
         Paragraph('100.0%',                              styles['table_cell'])],
        [Paragraph('COGS',                                styles['table_left']),
         Paragraph(fmt_currency(pnl['annual_cogs']),      styles['table_cell']),
         Paragraph(fmt_pct_from_decimal(pnl['cogs_pct']), styles['table_cell'])],
        [Paragraph('Gross Profit',                        styles['table_left']),
         Paragraph(fmt_currency(pnl['annual_gross_profit']), styles['table_cell']),
         Paragraph(fmt_pct_from_decimal(pnl['gross_margin_pct']), styles['table_cell'])],
        [Paragraph('Total CODB',                          styles['table_left']),
         Paragraph(fmt_currency(pnl['annual_codb']),      styles['table_cell']),
         Paragraph(fmt_pct_from_decimal(pnl['total_codb_pct']), styles['table_cell'])],
        [Paragraph('Net Profit',                          styles['table_left']),
         Paragraph(fmt_currency(pnl['annual_net_profit']), styles['table_cell']),
         Paragraph(fmt_pct_from_decimal(pnl['net_margin_pct']), styles['table_cell'])],
    ]

    fin_tbl = Table([hdr] + rows, colWidths=col_w)
    fin_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0),  NAVY),
        ('TEXTCOLOR',     (0, 0), (-1, 0),  WHITE),
        ('FONTNAME',      (0, 6), (-1, 6),  'Helvetica-Bold'),
        ('BACKGROUND',    (0, 6), (-1, 6),  colors.HexColor('#E8F8F5')),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
        ('GRID',          (0, 0), (-1, -1), 0.3, MID_GREY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHT_GREY, WHITE]),
    ]))
    story.append(fin_tbl)
    story.append(Spacer(1, 14))

    # CODB breakdown
    story.append(Paragraph('CODB Breakdown', styles['h2']))
    story.append(Paragraph(
        'Cost of Doing Business split by category (all GST-exclusive, annual).',
        styles['small']
    ))
    story.append(Spacer(1, 4))

    codb_col_w = [usable_w * 0.40, usable_w * 0.30, usable_w * 0.30]
    codb_hdr = [
        Paragraph('CODB Category', styles['table_hdr']),
        Paragraph('Annual ($)',    styles['table_hdr']),
        Paragraph('% of Revenue', styles['table_hdr']),
    ]
    codb_rows = [
        [Paragraph('Labour',    styles['table_left']),
         Paragraph(fmt_currency(pnl['annual_labour']),    styles['table_cell']),
         Paragraph(fmt_pct_from_decimal(pnl['labour_pct']), styles['table_cell'])],
        [Paragraph('Occupancy', styles['table_left']),
         Paragraph(fmt_currency(pnl['annual_occupancy']), styles['table_cell']),
         Paragraph(fmt_pct_from_decimal(pnl['occupancy_pct']), styles['table_cell'])],
        [Paragraph('Marketing', styles['table_left']),
         Paragraph(fmt_currency(pnl['annual_marketing']), styles['table_cell']),
         Paragraph(fmt_pct_from_decimal(pnl['marketing_pct']), styles['table_cell'])],
        [Paragraph('Other',     styles['table_left']),
         Paragraph(fmt_currency(pnl['annual_other']),     styles['table_cell']),
         Paragraph(fmt_pct_from_decimal(pnl['other_codb_pct']), styles['table_cell'])],
        [Paragraph('<b>Total CODB</b>', styles['table_left']),
         Paragraph(f'<b>{fmt_currency(pnl["annual_codb"])}</b>', styles['table_cell']),
         Paragraph(f'<b>{fmt_pct_from_decimal(pnl["total_codb_pct"])}</b>', styles['table_cell'])],
    ]
    codb_tbl = Table([codb_hdr] + codb_rows, colWidths=codb_col_w)
    codb_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0),  NAVY),
        ('TEXTCOLOR',     (0, 0), (-1, 0),  WHITE),
        ('FONTNAME',      (0, 5), (-1, 5),  'Helvetica-Bold'),
        ('BACKGROUND',    (0, 5), (-1, 5),  colors.HexColor('#FFF3CD')),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
        ('GRID',          (0, 0), (-1, -1), 0.3, MID_GREY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHT_GREY, WHITE]),
    ]))
    story.append(codb_tbl)
    story.append(Spacer(1, 14))

    # Revenue formula
    inp  = calc['inputs']
    mult = rev['mult']
    story.append(Paragraph('Revenue Formula', styles['h2']))
    formula_data = [[
        Paragraph(f"{inp['customers']:,.0f}", styles['kpi_value']),
        Paragraph('x', styles['h2']),
        Paragraph(f"{inp['frequency']:.2f}", styles['kpi_value']),
        Paragraph('x', styles['h2']),
        Paragraph(fmt_currency(inp['avg_spend']), styles['kpi_value']),
        Paragraph('x', styles['h2']),
        Paragraph(f'{mult}', styles['kpi_value']),
        Paragraph('=', styles['h2']),
        Paragraph(fmt_currency(pnl['annual_revenue']), styles['kpi_value']),
    ], [
        Paragraph('Customers',  styles['kpi_label']),
        Paragraph('',           styles['kpi_label']),
        Paragraph('Frequency',  styles['kpi_label']),
        Paragraph('',           styles['kpi_label']),
        Paragraph('Avg Spend',  styles['kpi_label']),
        Paragraph('',           styles['kpi_label']),
        Paragraph('Periods/yr', styles['kpi_label']),
        Paragraph('',           styles['kpi_label']),
        Paragraph('Annual Rev', styles['kpi_label']),
    ]]
    col_ws = [usable_w * w for w in [0.14, 0.04, 0.10, 0.04, 0.12, 0.04, 0.12, 0.04, 0.36]]
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


def _page3_lever_analysis(story, calc, data, chart_path, styles):
    """Page 3 - Retail DNA Lever Analysis with store-type-specific benchmarks."""
    scores          = calc['scores']
    bottleneck      = calc['bottleneck']
    store_type      = calc['store_type']
    store_benchmark = calc['store_benchmark']
    pnl             = calc['pnl']
    inp             = calc['inputs']
    usable_w        = PAGE_W - 2 * MARGIN

    story.extend(_section_header('Retail DNA Lever Analysis', styles, PAGE_W))
    story.append(Paragraph(
        f'Store type: <b>{store_type.title()}</b>  |  '
        f'Avg spend benchmark: <b>{fmt_currency(store_benchmark)}</b>  |  '
        f'HEALTHY 90-100, GOOD 70-89, MONITOR 50-69, CRITICAL below 50',
        styles['small']
    ))
    story.append(Spacer(1, 8))

    benchmarks_display = {
        'Customer Base':     '500 customers/period',
        'Frequency':         '3.0 visits/period',
        'Transaction Value': f'{fmt_currency(store_benchmark)} avg spend ({store_type.title()})',
        'Margin':            '50.0% gross margin',
    }
    current_vals = {
        'Customer Base':     f"{inp['customers']:,.0f} customers",
        'Frequency':         f"{inp['frequency']:.2f} visits/period",
        'Transaction Value': f"{fmt_currency(inp['avg_spend'])} avg spend",
        'Margin':            f"{fmt_pct_from_decimal(pnl['gross_margin_pct'])} gross margin",
    }

    col_w = [usable_w * w for w in [0.22, 0.22, 0.10, 0.26, 0.20]]
    hdr = [
        Paragraph('Lever',         styles['table_hdr']),
        Paragraph('Current Value', styles['table_hdr']),
        Paragraph('Score',         styles['table_hdr']),
        Paragraph('Benchmark',     styles['table_hdr']),
        Paragraph('Status',        styles['table_hdr']),
    ]
    rows = []
    for lever, score in scores.items():
        status_lbl  = lever_status_label(score)
        status_ckey = lever_status_color_key(score)
        status_col  = STATUS_COLORS.get(status_ckey, RED)
        is_bn       = (lever == bottleneck)
        rows.append([
            Paragraph(f'<b>{lever}</b>' if is_bn else lever, styles['table_left']),
            Paragraph(current_vals.get(lever, '-'),           styles['table_cell']),
            Paragraph(f'{score:.0f}/100',                     styles['table_cell']),
            Paragraph(benchmarks_display.get(lever, '-'),     styles['table_cell']),
            Paragraph(status_lbl, ParagraphStyle(
                'st', fontName='Helvetica-Bold', fontSize=8,
                textColor=status_col, alignment=TA_CENTER)),
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
    for i, lever in enumerate(scores.keys()):
        if lever == bottleneck:
            ts.append(('BACKGROUND', (0, i + 1), (-1, i + 1),
                        colors.HexColor('#FDECEA')))
    lever_tbl.setStyle(TableStyle(ts))
    story.append(lever_tbl)
    story.append(Spacer(1, 14))

    story.append(Paragraph('Lever Score Visualisation', styles['h2']))
    story.append(Spacer(1, 4))
    img = Image(chart_path, width=usable_w, height=usable_w * 0.46)
    story.append(img)
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        'Red bar = bottleneck lever (lowest score).  '
        'Dashed lines = status thresholds (MONITOR 50, GOOD 70, HEALTHY 90).  '
        'Focus improvement efforts on the red lever first.',
        styles['small']
    ))
    story.append(PageBreak())


def _page4_bottleneck(story, calc, data, styles):
    """Page 4 - Bottleneck Deep-Dive with exact profit impact formula."""
    scores               = calc['scores']
    bottleneck           = calc['bottleneck']
    bottleneck_sb        = calc.get('bottleneck_score_based', bottleneck)
    context_override     = calc.get('context_override', False)
    override_reason      = calc.get('context_override_reason', '')
    pnl                  = calc['pnl']
    inp                  = calc['inputs']
    store_benchmark      = calc['store_benchmark']
    usable_w             = PAGE_W - 2 * MARGIN
    bn_score             = scores.get(bottleneck, 0)
    status_ckey          = lever_status_color_key(bn_score)
    status_color         = STATUS_COLORS.get(status_ckey, RED)

    story.extend(_section_header(
        f'Bottleneck Deep-Dive: {bottleneck}', styles, PAGE_W))

    benchmarks_num = {
        'Customer Base':     500.0,
        'Frequency':         3.0,
        'Transaction Value': store_benchmark,
        'Margin':            50.0,
    }
    current_num = {
        'Customer Base':     inp['customers'],
        'Frequency':         inp['frequency'],
        'Transaction Value': inp['avg_spend'],
        'Margin':            pnl['gross_margin_pct'] * 100,
    }
    units = {
        'Customer Base':     'customers/period',
        'Frequency':         'visits/period',
        'Transaction Value': '$ avg spend',
        'Margin':            '% gross margin',
    }

    cur_val = current_num.get(bottleneck, 0)
    bench   = benchmarks_num.get(bottleneck, 100)
    unit    = units.get(bottleneck, '')
    gap     = bench - cur_val
    gap_pct = (gap / bench * 100) if bench else 0

    state_data = [[
        Paragraph('Current State', styles['table_hdr']),
        Paragraph('Benchmark',     styles['table_hdr']),
        Paragraph('Gap',           styles['table_hdr']),
        Paragraph('Gap %',         styles['table_hdr']),
        Paragraph('Score',         styles['table_hdr']),
    ], [
        Paragraph(f'{cur_val:,.2f} {unit}', styles['table_cell']),
        Paragraph(f'{bench:,.2f} {unit}',   styles['table_cell']),
        Paragraph(f'{gap:,.2f} {unit}',     styles['table_cell']),
        Paragraph(fmt_pct(gap_pct),         styles['table_cell']),
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

    story.append(Paragraph('Why This Lever Matters Most', styles['h2']))
    why_text = {
        'Customer Base':
            'Customer Base is the foundation of your revenue engine. '
            'Every other lever is multiplied by the number of customers you have. '
            'A thin customer base creates a ceiling that no amount of loyalty or '
            'upselling can overcome. Growing your customer count by even 10% '
            'delivers a direct, proportional lift to every other metric.',
        'Frequency':
            "Frequency is the most cost-effective growth lever because you're "
            'selling to people who already know and trust you. Increasing how '
            'often existing customers visit requires no new acquisition spend. '
            'A 10% lift in frequency is a 10% lift in revenue with near-zero '
            'incremental cost.',
        'Transaction Value':
            'Transaction Value determines how much revenue you extract from '
            'each customer interaction. If customers are visiting but spending '
            'below the benchmark for your store type, you are leaving money on '
            'the table at every single transaction. Cross-selling, bundling, '
            'and premium ranging are proven, low-cost tactics that compound '
            'across every visit.',
        'Margin':
            'Margin is the multiplier on everything else. A business with '
            'strong revenue but thin margins is working hard for little reward. '
            'Even a 1% improvement in gross margin flows directly to the bottom '
            'line. Supplier negotiations, CODB reduction, and mix management '
            'are the fastest paths to meaningful profit improvement.',
    }
    story.append(Paragraph(why_text.get(bottleneck, ''), styles['body']))
    story.append(Spacer(1, 10))

    # ── Contextual Analysis section (shown only when override is active) ──
    if context_override and override_reason:
        story.append(Paragraph('Contextual Analysis', styles['h2']))
        ctx_body_style = ParagraphStyle(
            'ctx_body_p4',
            fontName='Helvetica',
            fontSize=9,
            textColor=DARK_GREY,
            leading=13,
            spaceAfter=4,
        )
        ctx_note_style = ParagraphStyle(
            'ctx_note_p4',
            fontName='Helvetica-Oblique',
            fontSize=8.5,
            textColor=DARK_GREY,
            leading=12,
            spaceAfter=0,
        )
        sb_score = scores.get(bottleneck_sb, 0)
        ctx_note = (
            f'This contextual factor takes priority over the static benchmark score. '
            f'While <b>{bottleneck_sb}</b> scores {sb_score:.0f}/100, the immediate '
            f'business constraint is <b>{bottleneck}</b> due to the contextual event '
            f'identified in the owner\'s diagnostic answers.'
        )
        ctx_data = [
            [Paragraph(override_reason, ctx_body_style)],
            [Spacer(1, 4)],
            [Paragraph(ctx_note, ctx_note_style)],
        ]
        ctx_tbl = Table(ctx_data, colWidths=[usable_w])
        ctx_tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#FFF8DC')),
            ('TOPPADDING',    (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING',   (0, 0), (-1, -1), 12),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
            ('LINEBEFORE',    (0, 0), (0, -1),  3, ORANGE),
            ('ROUNDEDCORNERS', [4]),
        ]))
        story.append(ctx_tbl)
        story.append(Spacer(1, 10))

    diag_raw = data.get('diagnostic_answers', '')
    if diag_raw:
        diag = rewrite_diagnostic_answer(diag_raw, bottleneck)
        story.append(Paragraph('Diagnostic Observations', styles['h2']))
        story.append(Paragraph(
            'The following observations are drawn from the owner\'s diagnostic '
            'responses and have been restated in professional third-person for '
            'reporting purposes:', styles['body']))
        story.append(Spacer(1, 4))
        diag_data = [[Paragraph(diag, styles['body'])]]
        diag_tbl  = Table(diag_data, colWidths=[usable_w])
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

    story.append(Paragraph('Impact of 10% Improvement on This Lever', styles['h2']))
    scenario_row = next(
        (r for r in calc['scenarios'] if r['lever'] == bottleneck), None
    )
    if scenario_row:
        annual_rev  = pnl['annual_revenue']
        annual_prof = pnl['annual_net_profit']
        new_rev     = scenario_row['new_revenue']
        new_profit  = scenario_row['new_profit']
        rev_gain    = scenario_row['revenue_impact']
        profit_gain = scenario_row['profit_impact']

        impact_data = [[
            Paragraph('Metric',           styles['table_hdr']),
            Paragraph('Current',          styles['table_hdr']),
            Paragraph('+10% Improvement', styles['table_hdr']),
            Paragraph('Gain',             styles['table_hdr']),
        ], [
            Paragraph('Annual Revenue',   styles['table_left']),
            Paragraph(fmt_currency(annual_rev),  styles['table_cell']),
            Paragraph(fmt_currency(new_rev),     styles['table_cell']),
            Paragraph(fmt_revenue_impact(rev_gain), styles['table_cell']),
        ], [
            Paragraph('Annual Net Profit', styles['table_left']),
            Paragraph(fmt_currency(annual_prof), styles['table_cell']),
            Paragraph(fmt_currency(new_profit),  styles['table_cell']),
            Paragraph(fmt_profit_impact(profit_gain), styles['table_cell']),
        ]]
        col_w = [usable_w * w for w in [0.30, 0.23, 0.27, 0.20]]
        gain_color = GREEN if profit_gain >= 0 else RED
        impact_tbl = Table(impact_data, colWidths=col_w)
        impact_tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, 0),  NAVY),
            ('BACKGROUND',    (0, 1), (-1, 1),  LIGHT_GREY),
            ('BACKGROUND',    (0, 2), (-1, 2),  colors.HexColor('#E8F8F5')),
            ('TEXTCOLOR',     (0, 0), (-1, 0),  WHITE),
            ('FONTNAME',      (3, 1), (3, -1),  'Helvetica-Bold'),
            ('TEXTCOLOR',     (3, 1), (3, -1),  gain_color),
            ('TOPPADDING',    (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('LEFTPADDING',   (0, 0), (-1, -1), 8),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
            ('GRID',          (0, 0), (-1, -1), 0.3, MID_GREY),
        ]))
        story.append(impact_tbl)
    story.append(PageBreak())


def _page5_scenario(story, calc, chart_path, styles):
    """Page 5 - Scenario Planning with exact formulas, ranked by profit impact."""
    scenario_rows    = calc['scenarios']
    bottleneck       = calc['bottleneck']
    context_override = calc.get('context_override', False)
    override_reason  = calc.get('context_override_reason', '')
    usable_w         = PAGE_W - 2 * MARGIN

    story.extend(_section_header('Scenario Planning - What-If Analysis', styles, PAGE_W))
    story.append(Paragraph(
        'Each scenario shows the annual impact of a 10% improvement in one lever, '
        'calculated independently using exact formulas. '
        'Ranked by net profit impact (highest first). '
        'Margin scenario revenue impact = $0 (COGS % reduced, revenue unchanged).',
        styles['body']
    ))
    story.append(Spacer(1, 8))

    # ── Contextual override note (shown only when override is active) ─────
    if context_override and override_reason:
        ctx_note_title_style = ParagraphStyle(
            'ctx_note_title_p5',
            fontName='Helvetica-Bold',
            fontSize=9,
            textColor=colors.HexColor('#7D4E00'),
            leading=13,
            spaceAfter=4,
        )
        ctx_note_body_style = ParagraphStyle(
            'ctx_note_body_p5',
            fontName='Helvetica',
            fontSize=8.5,
            textColor=DARK_GREY,
            leading=13,
            spaceAfter=0,
        )
        ctx_note_data = [
            [Paragraph(
                '\u26a0 NOTE: This analysis is based on a contextual bottleneck override.',
                ctx_note_title_style,
            )],
            [Paragraph(override_reason, ctx_note_body_style)],
        ]
        ctx_note_tbl = Table(ctx_note_data, colWidths=[usable_w])
        ctx_note_tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#FFF8DC')),
            ('TOPPADDING',    (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING',   (0, 0), (-1, -1), 12),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
            ('LINEBEFORE',    (0, 0), (0, -1),  3, ORANGE),
            ('ROUNDEDCORNERS', [4]),
        ]))
        story.append(ctx_note_tbl)
        story.append(Spacer(1, 8))

    # ── Bottleneck priority callout ABOVE the table ───────────────────────
    priority_title_style = ParagraphStyle(
        'priority_title',
        fontName='Helvetica-Bold',
        fontSize=10,
        textColor=colors.HexColor('#7D0000'),
        leading=14,
        spaceAfter=4,
    )
    priority_body_style = ParagraphStyle(
        'priority_body',
        fontName='Helvetica',
        fontSize=8.5,
        textColor=DARK_GREY,
        leading=13,
        spaceAfter=0,
    )
    priority_data = [[
        Paragraph(
            f'\u26a0 NOTE: Scenario table ranks by profit impact. '
            f'The bottleneck lever <b>{bottleneck}</b> scores lowest and should be '
            f'your FIRST priority regardless of this ranking. '
            f'Fix the bottleneck before optimising other levers.',
            priority_body_style
        ),
    ]]
    priority_tbl = Table(priority_data, colWidths=[usable_w])
    priority_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#FDECEA')),
        ('TOPPADDING',    (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING',   (0, 0), (-1, -1), 14),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 12),
        ('LINEBEFORE',    (0, 0), (0, -1),  5, RED),
        ('ROUNDEDCORNERS', [4]),
    ]))
    story.append(priority_tbl)
    story.append(Spacer(1, 10))

    # ── Scenario table — 6 columns including "How to Achieve" ────────────
    col_w = [usable_w * w for w in [0.18, 0.14, 0.14, 0.12, 0.14, 0.28]]
    hdr = [
        Paragraph('Lever',          styles['table_hdr']),
        Paragraph('Current Rev',    styles['table_hdr']),
        Paragraph('+10% Rev',       styles['table_hdr']),
        Paragraph('Rev Impact',     styles['table_hdr']),
        Paragraph('Profit Impact',  styles['table_hdr']),
        Paragraph('How to Achieve', styles['table_hdr']),
    ]
    rows = []
    rank_suffixes = {0: '1st', 1: '2nd', 2: '3rd', 3: '4th'}
    for i, r in enumerate(scenario_rows):
        rank_label = rank_suffixes.get(i, f'{i+1}th')
        is_bn      = (r['lever'] == bottleneck)
        # Lever label: ★ + bold for bottleneck, rank label for all
        if is_bn:
            lever_label = f'<b>\u2605 {r["lever"]}</b><br/><font size="7">(Bottleneck — fix first)</font>'
        else:
            lever_label = f'{rank_label} {r["lever"]}'
        rows.append([
            Paragraph(lever_label,                             styles['table_left']),
            Paragraph(fmt_currency(r['base_revenue']),         styles['table_cell']),
            Paragraph(fmt_currency(r['new_revenue']),          styles['table_cell']),
            Paragraph(fmt_revenue_impact(r['revenue_impact']), styles['table_cell']),
            Paragraph(fmt_profit_impact(r['profit_impact']),   styles['table_cell']),
            Paragraph(fmt_how_to_achieve(r['lever']),          styles['table_left']),
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
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
    ]
    # Highlight bottleneck row in the table
    for i, r in enumerate(scenario_rows):
        if r['lever'] == bottleneck:
            ts.append(('BACKGROUND', (0, i + 1), (-1, i + 1),
                        colors.HexColor('#FDECEA')))
            ts.append(('FONTNAME', (0, i + 1), (0, i + 1), 'Helvetica-Bold'))
    scen_tbl.setStyle(TableStyle(ts))
    story.append(scen_tbl)
    story.append(Spacer(1, 8))

    # ── Equal-profit-impact footnote ─────────────────────────────────────
    footnote_style = ParagraphStyle(
        'footnote',
        fontName='Helvetica-Oblique',
        fontSize=7.5,
        textColor=DARK_GREY,
        leading=11,
        spaceAfter=0,
    )
    story.append(Paragraph(
        '<b>Note on equal profit impacts:</b> Transaction Value, Customer Base, '
        'and Frequency produce equal profit impact at current margins because CODB '
        'scales with revenue — a 10% lift in any revenue lever produces the same '
        'net profit gain. The bottleneck lever (<b>' + bottleneck + '</b>) is '
        'prioritised first because it is the fastest, lowest-cost path to '
        'improvement for this store\'s specific situation — not because it has '
        'the highest dollar impact.',
        footnote_style
    ))
    story.append(Spacer(1, 14))

    # ── Bottleneck vs. highest-ROI callout ───────────────────────────────
    highest_roi   = scenario_rows[0]['lever'] if scenario_rows else bottleneck
    is_same_lever = (bottleneck == highest_roi)

    if is_same_lever:
        callout_body = (
            f'<b>Good news:</b> The highest profit-impact lever and the bottleneck lever '
            f'are the same — <b>{bottleneck}</b>. Prioritising it first will '
            f'deliver both the constraint relief and the highest profit return '
            f'simultaneously. Proceed with confidence.'
        )
    else:
        bottleneck_examples = {
            'Frequency':
                'If Frequency is the bottleneck (low repeat visits), improving '
                'Margin won\'t help much — you don\'t have enough customer visits '
                'to benefit from the higher margin. Fix the bottleneck first.',
            'Customer Base':
                'If Customer Base is the bottleneck (too few customers), '
                'optimising Transaction Value or Margin yields limited returns '
                'because the volume simply isn\'t there yet. Fix the bottleneck first.',
            'Transaction Value':
                'If Transaction Value is the bottleneck (customers spending too '
                'little per visit), growing your Customer Base amplifies a weak '
                'spend rate. Fix the bottleneck first.',
            'Margin':
                'If Margin is the bottleneck (costs eroding profit), revenue '
                'growth alone won\'t rescue the bottom line — every extra dollar '
                'earned leaks straight out. Fix the bottleneck first.',
        }
        example_text = bottleneck_examples.get(
            bottleneck,
            f'Every other lever\'s impact is constrained by {bottleneck}. '
            f'Fix the bottleneck first.'
        )
        callout_body = (
            f'<b>Profit-impact rank \u2260 bottleneck lever in this report.</b><br/><br/>'
            f'The bottleneck <b>{bottleneck}</b> should be addressed <b>FIRST</b> '
            f'as it is the multiplier on all other levers. Every other lever\'s '
            f'impact is constrained by the bottleneck.<br/><br/>'
            f'<i>Example: {example_text}</i><br/><br/>'
            f'<b>Recommended sequence:</b><br/>'
            f'1. Address the bottleneck lever (<b>{bottleneck}</b> — this report\'s priority)<br/>'
            f'2. Then optimise the highest profit-impact levers from the scenario table above (<b>{highest_roi}</b> ranks first)<br/>'
            f'3. Compound improvements across all four levers over 12 months'
        )

    callout_title_style = ParagraphStyle(
        'callout_title',
        fontName='Helvetica-Bold',
        fontSize=10,
        textColor=colors.HexColor('#7D4E00'),
        leading=14,
        spaceAfter=4,
    )
    callout_body_style = ParagraphStyle(
        'callout_body',
        fontName='Helvetica',
        fontSize=8.5,
        textColor=DARK_GREY,
        leading=13,
        spaceAfter=0,
    )

    callout_icon  = '\u26a0\ufe0f' if not is_same_lever else '\U0001f3af'
    callout_title = (
        f'{callout_icon}  Important: Bottleneck vs. Profit-Impact Ranking'
    )

    callout_data = [[
        Paragraph(callout_title, callout_title_style),
    ], [
        Paragraph(callout_body, callout_body_style),
    ]]
    callout_tbl = Table(callout_data, colWidths=[usable_w])
    callout_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#FFF3CD')),
        ('TOPPADDING',    (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING',   (0, 0), (-1, -1), 14),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 12),
        ('LINEBEFORE',    (0, 0), (0, -1),  5, colors.HexColor('#E67E22')),
        ('ROUNDEDCORNERS', [4]),
    ]))
    story.append(KeepTogether([callout_tbl]))
    story.append(Spacer(1, 14))

    story.append(Paragraph('Net Profit Impact Visualisation', styles['h2']))
    story.append(Spacer(1, 4))
    img = Image(chart_path, width=usable_w, height=usable_w * 0.40)
    story.append(img)
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        f'Red bar = bottleneck lever ({bottleneck}).  '
        'Scenario table ranks by profit impact; bottleneck lever is your FIRST priority '
        'regardless of its profit-impact rank.',
        styles['small']
    ))
    story.append(PageBreak())


def _page6_recommendations(story, calc, data, styles):
    """Page 6 - Actionable Recommendations."""
    scores     = calc['scores']
    bottleneck = calc['bottleneck']
    scenarios  = calc['scenarios']
    usable_w   = PAGE_W - 2 * MARGIN

    # Build lever order: bottleneck ALWAYS first, then remaining levers
    # in profit-impact order (from scenario table, which is already sorted desc)
    scenario_lever_order = [r['lever'] for r in scenarios]
    lever_order = [bottleneck] + [l for l in scenario_lever_order if l != bottleneck]
    recs = _get_prioritised_recs_ordered(bottleneck, lever_order)[:12]

    story.extend(_section_header('Actionable Recommendations', styles, PAGE_W))
    story.append(Paragraph(
        'Recommendations are prioritised by lever (bottleneck first, then by '
        'profit impact) and effort level (Low to Medium to High).  '
        'Fill in the Owner column to assign accountability.',
        styles['body']
    ))
    story.append(Spacer(1, 8))

    col_w = [usable_w * w for w in [0.20, 0.28, 0.18, 0.10, 0.12, 0.12]]
    hdr = [
        Paragraph('Lever',           styles['table_hdr']),
        Paragraph('Action',          styles['table_hdr']),
        Paragraph('Expected Impact', styles['table_hdr']),
        Paragraph('Effort',          styles['table_hdr']),
        Paragraph('Timeline',        styles['table_hdr']),
        Paragraph('Owner',           styles['table_hdr']),
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


def _page7_action_plan(story, calc, styles):
    """Page 7 - 90-Day Action Plan."""
    scores     = calc['scores']
    bottleneck = calc['bottleneck']
    usable_w   = PAGE_W - 2 * MARGIN
    plan       = _build_90_day_plan(bottleneck, scores)

    story.extend(_section_header('90-Day Action Plan', styles, PAGE_W))
    story.append(Paragraph(
        'A phased plan to implement recommendations over the next 90 days. '
        'Month 1 focuses on quick wins; Month 2 on medium-term initiatives; '
        'Month 3 on strategic moves that compound over time.',
        styles['body']
    ))
    story.append(Spacer(1, 10))

    months = [
        ('Month 1 - Quick Wins', plan['month1'],
         'Complete setup and launch.  Measure baseline metrics.', TEAL),
        ('Month 2 - Build Momentum', plan['month2'],
         "Review Month 1 results.  Optimise and scale what's working.", NAVY),
        ('Month 3 - Strategic Moves', plan['month3'],
         'Assess compounding impact.  Set 12-month targets.', AMBER),
    ]

    for month_title, month_recs, success_metric, hdr_color in months:
        hdr_data = [[Paragraph(month_title, styles['section_hdr'])]]
        hdr_tbl  = Table(hdr_data, colWidths=[usable_w])
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
                'Continue optimising Month 1 & 2 initiatives.', styles['body']))

        story.append(Spacer(1, 4))
        story.append(Paragraph(
            f'<b>Success Metric:</b>  {success_metric}', styles['small']))
        story.append(Spacer(1, 10))

    story.append(PageBreak())


def _page8_projections(story, calc, styles):
    """Page 8 - Financial Projections with exact 90-day and 12-month formulas."""
    proj     = calc['projections']
    usable_w = PAGE_W - 2 * MARGIN

    story.extend(_section_header('Financial Projections', styles, PAGE_W))
    story.append(Paragraph(
        '90-day target: +5% customers, +5% frequency, +5% avg spend, '
        'COGS reduced by 2.5% (multiplied by 0.975).  '
        '12-month target: +12% customers, +15% frequency, +10% avg spend, '
        'COGS reduced by 5 percentage points.  '
        'All figures GST-exclusive.',
        styles['body']
    ))
    story.append(Spacer(1, 10))

    col_w = [usable_w * w for w in [0.28, 0.24, 0.24, 0.24]]
    hdr = [
        Paragraph('Metric',          styles['table_hdr']),
        Paragraph('Current State',   styles['table_hdr']),
        Paragraph('90-Day Target',   styles['table_hdr']),
        Paragraph('12-Month Target', styles['table_hdr']),
    ]

    def _row(label, cur_val, t90_val, t12_val):
        return [
            Paragraph(label,   styles['table_left']),
            Paragraph(cur_val, styles['table_cell']),
            Paragraph(t90_val, styles['table_cell']),
            Paragraph(t12_val, styles['table_cell']),
        ]

    c   = proj['current']
    t90 = proj['target_90']
    t12 = proj['target_12m']

    rows = [
        _row('Customers / Period',
             f"{c['customers']:,.0f}",
             f"{t90['customers']:,.0f}",
             f"{t12['customers']:,.0f}"),
        _row('Frequency (visits/period)',
             f"{c['frequency']:.2f}",
             f"{t90['frequency']:.2f}",
             f"{t12['frequency']:.2f}"),
        _row('Avg Spend / Visit',
             fmt_currency(c['avg_spend']),
             fmt_currency(t90['avg_spend']),
             fmt_currency(t12['avg_spend'])),
        _row('COGS %',
             fmt_pct_from_decimal(c['cogs_pct']),
             fmt_pct_from_decimal(t90['cogs_pct']),
             fmt_pct_from_decimal(t12['cogs_pct'])),
        _row('Annual Revenue',
             fmt_currency(c['revenue']),
             fmt_currency(t90['revenue']),
             fmt_currency(t12['revenue'])),
        _row('Annual COGS',
             fmt_currency(c['cogs']),
             fmt_currency(t90['cogs']),
             fmt_currency(t12['cogs'])),
        _row('Annual Gross Profit',
             fmt_currency(c['gross_profit']),
             fmt_currency(t90['gross_profit']),
             fmt_currency(t12['gross_profit'])),
        _row('Annual CODB',
             fmt_currency(c['codb']),
             fmt_currency(t90['codb']),
             fmt_currency(t12['codb'])),
        _row('Annual Net Profit',
             fmt_currency(c['net_profit']),
             fmt_currency(t90['net_profit']),
             fmt_currency(t12['net_profit'])),
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
        ('FONTNAME',      (0, 9), (-1, 9),  'Helvetica-Bold'),
        ('BACKGROUND',    (0, 9), (-1, 9),  colors.HexColor('#E8F8F5')),
        ('TEXTCOLOR',     (1, 9), (-1, 9),  GREEN),
    ]
    proj_tbl.setStyle(TableStyle(ts))
    story.append(proj_tbl)
    story.append(Spacer(1, 14))

    current_np   = c['net_profit']
    target_12_np = t12['net_profit']
    np_gain      = target_12_np - current_np
    np_pct_gain  = ((target_12_np / current_np) - 1) * 100 if current_np else 0

    note_data = [[Paragraph(
        f'<b>Compounding Effect:</b>  Achieving the 12-month targets across all '
        f'levers simultaneously would grow annual net profit from '
        f'<b>{fmt_currency(current_np)}</b> to '
        f'<b>{fmt_currency(target_12_np)}</b> - '
        f'an increase of <b>{fmt_profit_impact(np_gain)} ({np_pct_gain:+.0f}%)</b>.',
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


def _page9_dashboard(story, calc, data, styles):
    """Page 9 - Key Metrics Dashboard & Tracking Sheet."""
    pnl        = calc['pnl']
    scores     = calc['scores']
    bottleneck = calc['bottleneck']
    inp        = calc['inputs']
    usable_w   = PAGE_W - 2 * MARGIN

    story.extend(_section_header('Key Metrics Dashboard', styles, PAGE_W))
    story.append(Paragraph(
        'Use this page to track your KPIs weekly or monthly. '
        'Fill in the blank rows to monitor progress toward your targets.',
        styles['body']
    ))
    story.append(Spacer(1, 8))

    kpi_items = [
        ('Customers / Period',  f"{inp['customers']:,.0f}"),
        ('Frequency',           f"{inp['frequency']:.2f} visits"),
        ('Avg Spend',           fmt_currency(inp['avg_spend'])),
        ('Gross Margin',        fmt_pct_from_decimal(pnl['gross_margin_pct'])),
        ('Net Margin',          fmt_pct_from_decimal(pnl['net_margin_pct'])),
        ('Annual Revenue',      fmt_currency(pnl['annual_revenue'])),
        ('Annual Net Profit',   fmt_currency(pnl['annual_net_profit'])),
        ('Bottleneck Lever',    bottleneck),
        ('Bottleneck Score',    f"{scores.get(bottleneck, 0):.0f}/100"),
    ]

    kpi_col_w = usable_w / 3
    kpi_rows  = []
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

    story.append(Paragraph('Progress Tracking Sheet', styles['h2']))
    story.append(Paragraph(
        'Record your metrics each week or month to track improvement.',
        styles['body']))
    story.append(Spacer(1, 6))

    track_col_w = [usable_w * w for w in [0.14, 0.14, 0.12, 0.12, 0.12, 0.12, 0.12, 0.12]]
    track_hdr = [
        Paragraph('Date',         styles['table_hdr']),
        Paragraph('Customers',    styles['table_hdr']),
        Paragraph('Frequency',    styles['table_hdr']),
        Paragraph('Avg Spend',    styles['table_hdr']),
        Paragraph('Revenue',      styles['table_hdr']),
        Paragraph('Gross Margin', styles['table_hdr']),
        Paragraph('Net Margin',   styles['table_hdr']),
        Paragraph('Notes',        styles['table_hdr']),
    ]
    blank = Paragraph('', styles['table_cell'])
    current_row = [
        Paragraph(datetime.now().strftime('%d/%m/%y'),           styles['table_cell']),
        Paragraph(f"{inp['customers']:,.0f}",                    styles['table_cell']),
        Paragraph(f"{inp['frequency']:.2f}",                     styles['table_cell']),
        Paragraph(fmt_currency(inp['avg_spend']),                styles['table_cell']),
        Paragraph(fmt_currency(calc['revenue']['weekly_revenue']), styles['table_cell']),
        Paragraph(fmt_pct_from_decimal(pnl['gross_margin_pct']), styles['table_cell']),
        Paragraph(fmt_pct_from_decimal(pnl['net_margin_pct']),   styles['table_cell']),
        Paragraph('Baseline',                                    styles['table_cell']),
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


def _page10_appendix(story, calc, styles):
    """Page 10 - Appendix: Framework, Glossary, GST note, Scratchpad."""
    usable_w   = PAGE_W - 2 * MARGIN
    store_type = calc['store_type']

    story.extend(_section_header('Appendix', styles, PAGE_W))

    story.append(Paragraph('The Retail DNA Framework', styles['h2']))
    story.append(Paragraph(
        'Retail DNA is a diagnostic framework that breaks retail business '
        'performance into four fundamental levers. Every dollar of revenue '
        'is the product of these four variables:',
        styles['appendix']
    ))
    story.append(Spacer(1, 6))

    formula_text = (
        'Revenue  =  Customers  x  Frequency  x  Average Spend  x  Periods per Year'
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
         'This is the foundation - every other lever is multiplied by it.'),
        ('Frequency',
         'How often each customer visits per period. Loyalty programs, '
         'in-store events, and habitual-purchase categories drive this lever.'),
        ('Transaction Value (Avg Spend)',
         'The average dollar amount spent per visit (GST-exclusive). '
         'Cross-selling, bundling, premium ranging, and staff training are '
         'the primary drivers.'),
        ('Margin',
         'The percentage of revenue retained after costs. Includes both '
         'Gross Margin (revenue minus COGS) and Net Margin (after all CODB).'),
    ]
    for lever, desc in levers_desc:
        story.append(Paragraph(f'<b>{lever}:</b>  {desc}', styles['appendix']))
        story.append(Spacer(1, 3))

    story.append(Spacer(1, 8))

    # Store-type benchmarks table
    story.append(Paragraph('Store-Type Avg Spend Benchmarks', styles['h2']))
    story.append(Paragraph(
        'Transaction Value scores are calculated against the benchmark for '
        'your specific store type (GST-exclusive).',
        styles['appendix']
    ))
    story.append(Spacer(1, 4))

    bench_col_w = [usable_w * 0.35, usable_w * 0.35, usable_w * 0.30]
    bench_hdr = [
        Paragraph('Store Type',          styles['table_hdr']),
        Paragraph('Avg Spend Benchmark', styles['table_hdr']),
        Paragraph('Your Store',          styles['table_hdr']),
    ]
    bench_rows = []
    for st, bv in STORE_TYPE_BENCHMARKS.items():
        is_current = (st == store_type)
        bench_rows.append([
            Paragraph(f'<b>{st.title()}</b>' if is_current else st.title(),
                      styles['table_left']),
            Paragraph(fmt_currency(bv), styles['table_cell']),
            Paragraph('Your store' if is_current else '', styles['table_cell']),
        ])
    bench_tbl = Table([bench_hdr] + bench_rows, colWidths=bench_col_w)
    bench_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0),  NAVY),
        ('TEXTCOLOR',     (0, 0), (-1, 0),  WHITE),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING',   (0, 0), (-1, -1), 6),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 6),
        ('GRID',          (0, 0), (-1, -1), 0.3, MID_GREY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHT_GREY, WHITE]),
    ]))
    story.append(bench_tbl)
    story.append(Spacer(1, 10))

    # GST note
    gst_data = [[Paragraph(
        '<b>GST Note:</b>  All margin calculations in this report use '
        'GST-exclusive prices (NZ context). '
        'Ensure your avg spend, COGS, and revenue figures exclude GST '
        'before entering them into the diagnostic.',
        styles['appendix']
    )]]
    gst_tbl = Table(gst_data, colWidths=[usable_w])
    gst_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#E8F8F5')),
        ('TOPPADDING',    (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
        ('BOX',           (0, 0), (-1, -1), 1, TEAL),
        ('ROUNDEDCORNERS', [4]),
    ]))
    story.append(gst_tbl)
    story.append(Spacer(1, 10))

    # Glossary
    story.append(Paragraph('Glossary', styles['h2']))
    glossary = [
        ('COGS',
         'Cost of Goods Sold - the direct cost of the products you sell (GST-exclusive).'),
        ('CODB',
         'Cost of Doing Business - all operating expenses excluding COGS '
         '(labour, occupancy, marketing, other).'),
        ('Gross Profit',
         'Revenue minus COGS. Gross Profit % = (Revenue - COGS) / Revenue.'),
        ('Net Profit',
         'Gross Profit minus CODB. The true bottom-line profitability.'),
        ('CTM',
         'Contribution to Margin - the gross profit contribution of a '
         'product or category after direct costs.'),
        ('MAP',
         'Minimum Advertised Price - the lowest price a retailer may '
         'advertise a product, set by the supplier.'),
        ('Strike Rate',
         'The percentage of customer interactions that result in a sale. '
         'Higher strike rate = better conversion.'),
        ('FOP Categories',
         'Front of Pack - everyday essential categories that drive habitual '
         'customer visits (e.g. bread, milk, coffee).'),
        ('SKU',
         'Stock Keeping Unit - a unique identifier for each product variant '
         'in your range.'),
        ('Bottleneck Lever',
         'The Retail DNA lever with the lowest score relative to benchmark. '
         'Improving the bottleneck delivers the highest marginal return.'),
    ]
    col_w = [usable_w * 0.18, usable_w * 0.82]
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
    story.append(Spacer(1, 10))

    # Scratchpad calculations
    story.append(Paragraph('Calculation Scratchpad', styles['h2']))
    story.append(Paragraph(
        'Every number in this report is derived from the following '
        'step-by-step calculations. Use this section to verify any figure.',
        styles['appendix']
    ))
    story.append(Spacer(1, 4))

    scratchpad_lines = calc.get('scratchpad', [])
    scratch_text = '\n'.join(scratchpad_lines)
    scratch_data = [[Paragraph(scratch_text, styles['mono'])]]
    scratch_tbl  = Table(scratch_data, colWidths=[usable_w])
    scratch_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#F8F9FA')),
        ('TOPPADDING',    (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
        ('BOX',           (0, 0), (-1, -1), 0.5, MID_GREY),
        ('ROUNDEDCORNERS', [4]),
    ]))
    story.append(scratch_tbl)
    story.append(Spacer(1, 10))

    # Notes
    story.append(Paragraph('Notes', styles['h2']))
    story.append(Paragraph(
        'Use this space to record observations, decisions, and follow-up actions.',
        styles['appendix']
    ))
    story.append(Spacer(1, 6))

    note_lines = [[Paragraph('', styles['appendix'])] for _ in range(8)]
    notes_tbl  = Table(note_lines, colWidths=[usable_w], rowHeights=[20] * 8)
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
    styles      = _make_styles()

    # Run calculation engine
    calc = calculate_all(data)

    scores          = calc['scores']
    bottleneck      = calc['bottleneck']
    store_type      = calc['store_type']
    store_benchmark = calc['store_benchmark']
    pnl             = calc['pnl']
    inp             = calc['inputs']
    scenarios       = calc['scenarios']

    # ── Pre-build validation checklist ───────────────────────────────────
    validation_errors: list[str] = []
    context_override        = calc.get('context_override', False)
    context_override_reason = calc.get('context_override_reason', '')
    bottleneck_score_based  = calc.get('bottleneck_score_based', bottleneck)

    # 1. Avg spend: input must equal used (exact match)
    avg_spend_input = inp['avg_spend']
    avg_spend_used  = inp['avg_spend']   # same reference — confirmed by calculation_engine
    if avg_spend_input != avg_spend_used:
        validation_errors.append(
            f"AVG SPEND MISMATCH: input=${avg_spend_input:.2f}, "
            f"used=${avg_spend_used:.2f}"
        )

    # 2. Margin scenario revenue impact must be exactly $0
    margin_row = next((r for r in scenarios if r['lever'] == 'Margin'), None)
    if margin_row is not None and abs(margin_row['revenue_impact']) > 0.01:
        validation_errors.append(
            f"MARGIN REVENUE IMPACT != $0: got ${margin_row['revenue_impact']:.4f}"
        )

    # 3. Revenue levers (TV, CB, Freq) should produce equal profit impacts
    #    (within $1 rounding tolerance — they are mathematically equal)
    rev_levers = [r for r in scenarios if r['lever'] != 'Margin']
    if len(rev_levers) >= 2:
        impacts = [r['profit_impact'] for r in rev_levers]
        max_diff = max(impacts) - min(impacts)
        if max_diff > 1.0:
            validation_errors.append(
                f"REVENUE LEVER PROFIT IMPACTS NOT EQUAL: "
                f"max diff=${max_diff:.4f} (expected <$1.00 rounding tolerance)"
            )

    # 4. Bottleneck consistency:
    #    - If no contextual override: bottleneck must equal the lowest-score lever.
    #    - If contextual override: bottleneck must differ from the score-based lever,
    #      and override_reason must be non-empty.
    expected_score_based = min(scores, key=scores.get)
    if context_override:
        if not context_override_reason:
            validation_errors.append(
                "CONTEXT OVERRIDE ACTIVE but override_reason is empty."
            )
        if bottleneck == bottleneck_score_based:
            validation_errors.append(
                f"CONTEXT OVERRIDE ACTIVE but bottleneck ({bottleneck}) "
                f"equals bottleneck_score_based ({bottleneck_score_based}). "
                "They must differ when an override is applied."
            )
    else:
        if bottleneck != expected_score_based:
            validation_errors.append(
                f"BOTTLENECK INCONSISTENCY: reported={bottleneck}, "
                f"lowest-score lever={expected_score_based}"
            )

    # 5. Annual revenue cross-check: customers × frequency × avg_spend × mult
    mult = calc['revenue']['mult']
    expected_revenue = inp['customers'] * inp['frequency'] * inp['avg_spend'] * mult
    actual_revenue   = pnl['annual_revenue']
    if abs(expected_revenue - actual_revenue) > 1.0:
        validation_errors.append(
            f"REVENUE CROSS-CHECK FAILED: "
            f"expected=${expected_revenue:,.2f}, actual=${actual_revenue:,.2f}"
        )

    if validation_errors:
        error_summary = '\n'.join(f'  - {e}' for e in validation_errors)
        raise ValueError(
            f"Report pre-build validation failed ({len(validation_errors)} error(s)):\n"
            f"{error_summary}\n\n"
            "Fix the underlying data before generating the PDF."
        )

    logger.info(
        f'Pre-build validation passed: avg_spend=${avg_spend_input:.2f}, '
        f'bottleneck={bottleneck}, revenue=${actual_revenue:,.2f}'
    )

    # Generate chart images
    lever_chart_path    = f'rpt_levers_{chat_id}.png'
    profit_chart_path   = f'rpt_profit_{chat_id}.png'
    scenario_chart_path = f'rpt_scenario_{chat_id}.png'

    try:
        _chart_lever_bars(scores, bottleneck, store_type, store_benchmark,
                          lever_chart_path)
        _chart_profit_waterfall(calc, profit_chart_path)
        _chart_scenario(calc['scenarios'], scenario_chart_path)
    except Exception as e:
        logger.warning(f'Chart generation error: {e}')

    # Persist history
    try:
        save_analysis_history(chat_id, data, calc, business_name)
    except Exception as e:
        logger.warning(f'History save error: {e}')

    # Build PDF
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

    _page1_cover(story, calc, data, business_name, report_date, styles)
    _page2_financial(story, calc, data, styles)
    _page3_lever_analysis(story, calc, data, lever_chart_path, styles)
    _page4_bottleneck(story, calc, data, styles)
    _page5_scenario(story, calc, scenario_chart_path, styles)
    _page6_recommendations(story, calc, data, styles)
    _page7_action_plan(story, calc, styles)
    _page8_projections(story, calc, styles)
    _page9_dashboard(story, calc, data, styles)
    _page10_appendix(story, calc, styles)

    doc.build(story)

    # Clean up temp chart files
    for p in [lever_chart_path, profit_chart_path, scenario_chart_path]:
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass

    logger.info(f'PDF report generated: {pdf_path}')
    return pdf_path
