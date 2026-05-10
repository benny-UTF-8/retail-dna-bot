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
# Convenience: format a full P&L row
# ─────────────────────────────────────────────

def fmt_pnl_row(label: str, amount: float, pct_of_rev: float) -> dict:
    """Return a dict suitable for rendering a P&L table row."""
    return {
        'label':  label,
        'amount': fmt_currency(amount),
        'pct':    fmt_pct_from_decimal(pct_of_rev),
    }
