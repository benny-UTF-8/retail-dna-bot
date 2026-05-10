"""
formatting_engine.py
=====================
Strict formatting rules for the ieRetail Retail DNA framework.

All currency, percentage, and profit-impact formatting follows the
exact rules specified in the ieRetail system prompt.

Public API
----------
fmt_currency(v: float) -> str
    Format a dollar value per ieRetail rules.

fmt_pct(v: float) -> str
    Format a percentage to exactly one decimal place.

fmt_pct_pts(v: float) -> str
    Format a percentage-point change using "pts" suffix.

fmt_profit_impact(v: float) -> str
    Format a profit impact: positive → +$X,XXX, negative → ($X,XXX).

fmt_revenue_impact(v: float) -> str
    Format a revenue impact (same sign rules as profit impact).

lever_status_label(score: float) -> str
    Return the status label with emoji for a lever score.
"""

from __future__ import annotations


# ─────────────────────────────────────────────
# Currency formatting
# ─────────────────────────────────────────────

def fmt_currency(v: float) -> str:
    """
    Format a dollar value per ieRetail rules:
      < $1,000        → $XXX   (no decimals)
      $1,000–$999,999 → $X,XXX (comma, no decimals)
      ≥ $1,000,000    → $X.XM  (one decimal)

    Negative values use the same magnitude rules with a leading minus.
    """
    neg = v < 0
    av  = abs(v)

    if av >= 1_000_000:
        formatted = f"${av / 1_000_000:.1f}M"
    elif av >= 1_000:
        formatted = f"${av:,.0f}"
    else:
        formatted = f"${av:.0f}"

    return f"-{formatted}" if neg else formatted


def fmt_pct(v: float) -> str:
    """
    Format a percentage to exactly one decimal place.
    Input is already a percentage (e.g. 41.0, not 0.41).
    """
    return f"{v:.1f}%"


def fmt_pct_from_decimal(v: float) -> str:
    """
    Format a decimal fraction as a percentage to one decimal place.
    Input is a decimal (e.g. 0.41 → '41.0%').
    """
    return f"{v * 100:.1f}%"


def fmt_pct_pts(v: float) -> str:
    """
    Format a percentage-point change.
    Uses 'pts' suffix, not '%'.
    e.g. 7.0 → '+7.0pts', -3.5 → '-3.5pts'
    """
    sign = '+' if v >= 0 else ''
    return f"{sign}{v:.1f}pts"


def fmt_profit_impact(v: float) -> str:
    """
    Format a profit impact value:
      Positive → +$X,XXX
      Negative → ($X,XXX)  [parentheses, no minus sign]
      Zero     → $0

    NEVER produces '+$-X,XXX'.
    """
    if v == 0:
        return "$0"
    if v > 0:
        return f"+{fmt_currency(v)}"
    # Negative: use parentheses, no minus sign
    av = abs(v)
    if av >= 1_000_000:
        return f"(${av / 1_000_000:.1f}M)"
    if av >= 1_000:
        return f"(${av:,.0f})"
    return f"(${av:.0f})"


def fmt_revenue_impact(v: float) -> str:
    """
    Format a revenue impact value (same rules as profit impact).
    Margin scenario always passes 0.0 → returns '$0'.
    """
    return fmt_profit_impact(v)


def fmt_pct_gain(v: float) -> str:
    """
    Format a percentage gain for scenario table.
    e.g. 10.0 → '+10.0%', -5.0 → '(-5.0%)'
    """
    if v >= 0:
        return f"+{v:.1f}%"
    return f"({abs(v):.1f}%)"


# ─────────────────────────────────────────────
# Lever status labels
# ─────────────────────────────────────────────

def lever_status_label(score: float) -> str:
    """
    Return a status label with colour indicator for a lever score.
    HEALTHY (90-100), GOOD (70-89), MONITOR (50-69), CRITICAL (<50)
    """
    s = round(score)
    if s >= 90:
        return "● HEALTHY"
    if s >= 70:
        return "● GOOD"
    if s >= 50:
        return "● MONITOR"
    return "● CRITICAL"


def lever_status_color_key(score: float) -> str:
    """Return a string key for the status colour ('green', 'teal', 'orange', 'red')."""
    s = round(score)
    if s >= 90:
        return 'green'
    if s >= 70:
        return 'teal'
    if s >= 50:
        return 'orange'
    return 'red'


# ─────────────────────────────────────────────
# How to Achieve helper
# ─────────────────────────────────────────────

def fmt_how_to_achieve(lever: str) -> str:
    """
    Return a concise, actionable tactics string for the given lever.
    Used in the scenario table 'How to Achieve' column.
    """
    tactics = {
        'Frequency':         'Loyalty programme, FOP stocking, in-store events',
        'Customer Base':     'Marketing, referrals, range expansion',
        'Transaction Value': 'Cross-sell training, upsell, merchandising',
        'Margin':            'COGS reduction, supplier negotiation',
    }
    return tactics.get(lever, 'Review lever-specific strategies')


# ─────────────────────────────────────────────
# Diagnostic answer rewriter
# ─────────────────────────────────────────────

def rewrite_diagnostic_answer(raw_text: str, bottleneck: str) -> str:
    """
    Rewrite raw user diagnostic text into professional third-person prose.

    Strips first-person pronouns, conversational filler, and incomplete
    sentences.  Returns a polished observation suitable for a business report.
    """
    if not raw_text or not raw_text.strip():
        return ''

    import re

    text = raw_text.strip()

    # ── Normalise whitespace ─────────────────────────────────────────────
    text = re.sub(r'\s+', ' ', text)

    # ── Strip first-person pronouns (case-insensitive) ───────────────────
    # Replace "I have", "I've", "I do", "I don't", "I am", "I'm" etc.
    text = re.sub(r"\bI've\b", 'The store has', text, flags=re.IGNORECASE)
    text = re.sub(r"\bI'm\b",  'The store is',  text, flags=re.IGNORECASE)
    text = re.sub(r"\bI am\b", 'The store is',  text, flags=re.IGNORECASE)
    text = re.sub(r"\bI do\b", 'The store does', text, flags=re.IGNORECASE)
    text = re.sub(r"\bI don't\b", 'The store does not', text, flags=re.IGNORECASE)
    text = re.sub(r"\bI have\b", 'The store has', text, flags=re.IGNORECASE)
    text = re.sub(r"\bI\b", 'The store', text, flags=re.IGNORECASE)
    text = re.sub(r"\bwe've\b", 'the business has', text, flags=re.IGNORECASE)
    text = re.sub(r"\bwe're\b", 'the business is',  text, flags=re.IGNORECASE)
    text = re.sub(r"\bwe are\b", 'the business is', text, flags=re.IGNORECASE)
    text = re.sub(r"\bwe have\b", 'the business has', text, flags=re.IGNORECASE)
    text = re.sub(r"\bwe\b", 'the business', text, flags=re.IGNORECASE)
    text = re.sub(r"\bmy\b",  'the store\'s', text, flags=re.IGNORECASE)
    text = re.sub(r"\bour\b", 'the store\'s', text, flags=re.IGNORECASE)

    # ── Remove conversational filler ─────────────────────────────────────
    filler_patterns = [
        r'\bum\b', r'\buh\b', r'\byeah\b', r'\byep\b', r'\bnope\b',
        r'\bkinda\b', r'\bsorta\b', r'\bbasically\b', r'\blike\b(?=\s)',
        r'\bpretty much\b', r'\bto be honest\b', r'\bhonestly\b',
        r'\bI guess\b', r'\bI think\b', r'\bI reckon\b',
    ]
    for pat in filler_patterns:
        text = re.sub(pat, '', text, flags=re.IGNORECASE)

    # ── Clean up double spaces left by removals ──────────────────────────
    text = re.sub(r'\s{2,}', ' ', text).strip()

    # ── Capitalise first letter of each sentence ─────────────────────────
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s[0].upper() + s[1:] if s else s for s in sentences]
    text = ' '.join(sentences)

    # ── Ensure text ends with a period ───────────────────────────────────
    if text and text[-1] not in '.!?':
        text += '.'

    return text


# ─────────────────────────────────────────────
# Convenience: format a full P&L row
# ─────────────────────────────────────────────

def fmt_pnl_row(label: str, amount: float, pct_of_rev: float) -> dict:
    """Return a dict suitable for rendering a P&L table row."""
    return {
        'label':  label,
        'amount': fmt_currency(amount),
        'pct':    fmt_pct_from_decimal(pct_of_rev),
    }
