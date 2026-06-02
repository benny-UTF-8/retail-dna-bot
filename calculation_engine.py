"""
calculation_engine.py
======================
Exact calculation engine for the ieRetail Retail DNA framework (Lessons 1-10).

All formulas are implemented exactly as specified — no approximations.
Every number produced here is auditable and traceable.

Public API
----------
calculate_all(data: dict) -> dict
    Run the full calculation suite and return a results dict.

validate_inputs(data: dict) -> list[str]
    Return a list of validation error strings (empty = valid).
"""

from __future__ import annotations

# ─────────────────────────────────────────────
# Store-type benchmarks (avg spend per visit, GST-exclusive)
# ─────────────────────────────────────────────

STORE_TYPE_BENCHMARKS: dict[str, float] = {
    'grocery':   45.0,
    'cafe':      22.0,
    'pharmacy':  55.0,
    'liquor':    65.0,
    'specialty': 80.0,
    'gift':      70.0,
    'hardware':  90.0,
    'other':     50.0,   # neutral fallback
}

VALID_STORE_TYPES = list(STORE_TYPE_BENCHMARKS.keys())

# Lever score status thresholds
STATUS_HEALTHY  = (90, 100)
STATUS_GOOD     = (70, 89)
STATUS_MONITOR  = (50, 69)
STATUS_CRITICAL = (0,  49)


def get_store_benchmark(store_type: str) -> float:
    """Return the avg-spend benchmark for the given store type."""
    return STORE_TYPE_BENCHMARKS.get(store_type.lower(), STORE_TYPE_BENCHMARKS['other'])


def lever_status(score: float) -> str:
    """Return status label for a lever score."""
    s = round(score)
    if s >= 90:
        return 'HEALTHY'
    if s >= 70:
        return 'GOOD'
    if s >= 50:
        return 'MONITOR'
    return 'CRITICAL'


# ─────────────────────────────────────────────
# Contextual bottleneck detection
# ─────────────────────────────────────────────

# Keywords that signal a contextual event, mapped to the lever they impact.
# Matching is case-insensitive.  The first lever whose keywords match wins;
# if multiple levers match, the one with the most keyword hits wins.
CONTEXTUAL_KEYWORDS: dict[str, list[str]] = {
    'Customer Base': [
        'competitor', 'opened', 'new store', "pak'nsave", 'countdown',
        'foodstuffs', 'rival', 'lost customers', 'foot traffic', 'footfall',
        'relocation', 'relocate', 'move', 'new location', 'lease', 'rent',
        'premises', 'moved',
    ],
    'Frequency': [
        'covid', 'lockdown', 'recovery', 'pandemic', 'restrictions',
        'loyalty', 'repeat', 'come back', 'return', 'visit frequency',
    ],
    'Transaction Value': [
        'staff', 'employee', 'turnover', 'quit', 'left', 'shortage',
        'supply', 'stock', 'delivery', 'supplier', 'spend', 'basket',
        'transaction', 'average', 'ticket', 'buy less',
    ],
    'Margin': [
        'price', 'margin', 'cost', 'expensive', 'cheap', 'supplier cost',
        'cogs', 'profit',
    ],
}


def detect_contextual_bottleneck(
    diagnostic_answers: str,
    scores: dict,
) -> tuple[str, str]:
    """
    Analyse free-text diagnostic answers for contextual events that may
    indicate a different bottleneck than the lowest-scoring lever.

    Parameters
    ----------
    diagnostic_answers : str
        Raw text from the owner's diagnostic responses.
    scores : dict
        Lever scores produced by calculate_all(), e.g.
        {'Customer Base': 76, 'Frequency': 65, ...}.

    Returns
    -------
    (bottleneck_lever, override_reason)
        override_reason is an empty string when no override applies.
    """
    if not diagnostic_answers or not diagnostic_answers.strip():
        return ('', '')

    text_lower = diagnostic_answers.lower()

    # Count keyword hits per lever
    hits: dict[str, int] = {}
    for lever, keywords in CONTEXTUAL_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw.lower() in text_lower)
        if count > 0:
            hits[lever] = count

    if not hits:
        return ('', '')

    # Lever with the most keyword hits is the contextual lever
    contextual_lever = max(hits, key=hits.get)

    # Score-based bottleneck (lowest score)
    score_based_bottleneck = min(scores, key=scores.get)

    # Only override when the contextual lever differs from the score-based one
    if contextual_lever == score_based_bottleneck:
        return (contextual_lever, '')

    # Only override when the score-based bottleneck is GOOD (≥70) or HEALTHY (≥90)
    # — i.e. it is not already critical enough to demand attention on its own.
    score_based_score = scores[score_based_bottleneck]
    if score_based_score < 70:
        # Score-based bottleneck is genuinely critical; do not override
        return (score_based_bottleneck, '')

    # Build a human-readable reason for the override
    contextual_score = scores[contextual_lever]
    override_reason = (
        f"Bottleneck identified from context, not score. "
        f"{contextual_lever} scores {contextual_score:.0f}/100 but is declining "
        f"due to a contextual factor identified in the owner's diagnostic answers. "
        f"Score-based bottleneck ({score_based_bottleneck} at "
        f"{score_based_score:.0f}/100) is not the priority because the contextual "
        f"event is actively constraining {contextual_lever}."
    )
    return (contextual_lever, override_reason)


# ─────────────────────────────────────────────
# Input validation
# ─────────────────────────────────────────────

def validate_inputs(data: dict) -> list[str]:
    """
    Validate all user inputs.  Returns a list of error strings.
    An empty list means all inputs are valid.
    """
    errors: list[str] = []

    # Store type
    store_type = data.get('store_type', '').lower()
    if store_type not in VALID_STORE_TYPES:
        errors.append(
            f"Store type '{store_type}' is not valid. "
            f"Choose from: {', '.join(VALID_STORE_TYPES)}."
        )

    # Customers
    customers = data.get('customers', 0)
    if not isinstance(customers, (int, float)) or customers <= 0:
        errors.append("Customers must be a positive number.")

    # Frequency
    frequency = data.get('frequency', 0)
    if not isinstance(frequency, (int, float)) or frequency <= 0:
        errors.append("Frequency must be a positive number.")

    # Avg spend (GST-exclusive)
    avg_spend = data.get('avg_spend', 0)
    if not isinstance(avg_spend, (int, float)) or avg_spend <= 0:
        errors.append("Average spend must be a positive number (GST-exclusive).")

    # COGS %
    cogs_pct = data.get('cogs_pct', None)
    if cogs_pct is None:
        errors.append("COGS % is required.")
    elif not (0 < cogs_pct < 100):
        errors.append("COGS % must be between 0 and 100 (exclusive).")

    # Labour %
    labour_pct = data.get('labour_pct', None)
    if labour_pct is None:
        errors.append("Labour % is required.")
    elif not (0 <= labour_pct <= 100):
        errors.append("Labour % must be between 0 and 100.")

    # Occupancy %
    occupancy_pct = data.get('occupancy_pct', None)
    if occupancy_pct is None:
        errors.append("Occupancy % is required.")
    elif not (0 <= occupancy_pct <= 100):
        errors.append("Occupancy % must be between 0 and 100.")

    # Marketing %
    marketing_pct = data.get('marketing_pct', None)
    if marketing_pct is None:
        errors.append("Marketing % is required.")
    elif not (0 <= marketing_pct <= 100):
        errors.append("Marketing % must be between 0 and 100.")

    # Other CODB %
    other_codb_pct = data.get('other_codb_pct', None)
    if other_codb_pct is None:
        errors.append("Other CODB % is required.")
    elif not (0 <= other_codb_pct <= 100):
        errors.append("Other CODB % must be between 0 and 100.")

    # Cross-field: COGS must be < 100 so gross margin > 0
    if cogs_pct is not None and cogs_pct >= 100:
        errors.append("COGS % must be less than 100% (gross margin must be positive).")

    # Cross-field: total CODB sanity check (warn if outside 5–60%)
    if all(v is not None for v in [labour_pct, occupancy_pct, marketing_pct, other_codb_pct]):
        total_codb = labour_pct + occupancy_pct + marketing_pct + other_codb_pct
        if total_codb > 100:
            errors.append(
                f"Total CODB ({total_codb:.1f}%) exceeds 100%. "
                "Please check your cost percentages."
            )

    return errors


# ─────────────────────────────────────────────
# Core calculation engine
# ─────────────────────────────────────────────

def calculate_all(data: dict) -> dict:
    """
    Run the complete ieRetail calculation suite.

    Parameters
    ----------
    data : dict
        Must contain: customers, frequency, avg_spend, cogs_pct,
        labour_pct, occupancy_pct, marketing_pct, other_codb_pct,
        store_type, timeframe.

    Returns
    -------
    dict with keys: revenue, pnl, scores, bottleneck, scenarios, projections,
                    scratchpad, store_benchmark.
    """
    # ── Raw inputs ───────────────────────────────────────────────────────
    customers      = float(data.get('customers', 0))
    frequency      = float(data.get('frequency', 1))
    avg_spend_input = float(data.get('avg_spend', 0))   # exact user input — never modified
    avg_spend      = avg_spend_input                     # used in all calculations
    cogs_pct_raw   = float(data.get('cogs_pct', 0))   # e.g. 59.0 → 0.59
    labour_pct_raw = float(data.get('labour_pct', 0))
    occ_pct_raw    = float(data.get('occupancy_pct', 0))
    mkt_pct_raw    = float(data.get('marketing_pct', 0))
    oth_pct_raw    = float(data.get('other_codb_pct', 0))
    store_type     = data.get('store_type', 'other').lower()
    timeframe      = data.get('timeframe', 'weekly')

    # Convert percentages to decimals
    cogs_pct       = cogs_pct_raw   / 100
    labour_pct     = labour_pct_raw / 100
    occupancy_pct  = occ_pct_raw    / 100
    marketing_pct  = mkt_pct_raw    / 100
    other_codb_pct = oth_pct_raw    / 100

    # Annualisation multiplier
    mult = {'weekly': 52, 'monthly': 12, 'yearly': 1}.get(timeframe, 52)

    # ── Avg spend integrity check ────────────────────────────────────────
    # avg_spend must equal avg_spend_input exactly (no rounding, no modification).
    if avg_spend != avg_spend_input:
        raise ValueError(
            f"avg_spend integrity failure: input=${avg_spend_input:.2f}, "
            f"used=${avg_spend:.2f}. Difference=${abs(avg_spend - avg_spend_input):.4f}. "
            "avg_spend must be used exactly as entered — no rounding or modification."
        )

    # ── Revenue calculations ─────────────────────────────────────────────
    weekly_revenue = customers * frequency * avg_spend
    annual_revenue = weekly_revenue * mult          # exact formula

    # ── P&L calculations ─────────────────────────────────────────────────
    annual_cogs         = annual_revenue * cogs_pct
    annual_gross_profit = annual_revenue - annual_cogs
    gross_margin_pct    = annual_gross_profit / annual_revenue if annual_revenue else 0.0

    # Validation: gross_margin_pct + cogs_pct must equal 1.000 exactly
    # (floating-point tolerance: within 0.0001)
    _gm_check = gross_margin_pct + cogs_pct
    assert abs(_gm_check - 1.0) < 0.0001, (
        f"Gross margin check failed: {gross_margin_pct:.6f} + {cogs_pct:.6f} = {_gm_check:.6f}"
    )

    total_codb_pct  = labour_pct + occupancy_pct + marketing_pct + other_codb_pct
    annual_codb     = annual_revenue * total_codb_pct

    # CODB breakdown
    annual_labour    = annual_revenue * labour_pct
    annual_occupancy = annual_revenue * occupancy_pct
    annual_marketing = annual_revenue * marketing_pct
    annual_other     = annual_revenue * other_codb_pct

    annual_net_profit = annual_gross_profit - annual_codb
    net_margin_pct    = annual_net_profit / annual_revenue if annual_revenue else 0.0

    # ── Lever scores (store-type-specific) ───────────────────────────────
    store_benchmark = get_store_benchmark(store_type)

    customer_score = min(100, round((customers  / 500)             * 100, 0))
    frequency_score = min(100, round((frequency  / 3.0)            * 100, 0))
    spend_score     = min(100, round((avg_spend  / store_benchmark) * 100, 0))
    margin_score    = min(100, round((gross_margin_pct / 0.50)      * 100, 0))

    scores = {
        'Customer Base':     customer_score,
        'Frequency':         frequency_score,
        'Transaction Value': spend_score,
        'Margin':            margin_score,
    }

    # ── Score-based bottleneck ───────────────────────────────────────────
    bottleneck_score_based = min(scores, key=scores.get)

    # ── Contextual bottleneck override ───────────────────────────────────
    diagnostic_answers = data.get('diagnostic_answers', '')
    bottleneck_contextual, override_reason = detect_contextual_bottleneck(
        diagnostic_answers, scores
    )

    if override_reason:
        bottleneck    = bottleneck_contextual
        context_override = True
    else:
        bottleneck    = bottleneck_score_based
        context_override = False

    # ── Scenario planning (10% improvement per lever) ────────────────────
    scenarios = _build_scenarios(
        customers, frequency, avg_spend,
        cogs_pct, total_codb_pct,
        annual_revenue, annual_net_profit,
        mult
    )

    # ── Financial projections ─────────────────────────────────────────────
    projections = _build_projections(
        customers, frequency, avg_spend,
        cogs_pct, total_codb_pct,
        labour_pct, occupancy_pct, marketing_pct, other_codb_pct,
        mult
    )

    # ── Scratchpad (for transparency / appendix) ──────────────────────────
    scratchpad = _build_scratchpad(
        customers, frequency, avg_spend, avg_spend_input, mult,
        weekly_revenue, annual_revenue,
        cogs_pct_raw, cogs_pct, annual_cogs,
        annual_gross_profit, gross_margin_pct,
        labour_pct_raw, occ_pct_raw, mkt_pct_raw, oth_pct_raw,
        total_codb_pct, annual_codb,
        annual_labour, annual_occupancy, annual_marketing, annual_other,
        annual_net_profit, net_margin_pct,
        store_type, store_benchmark,
        customer_score, frequency_score, spend_score, margin_score,
        bottleneck_score_based,
        context_override=context_override,
        bottleneck_contextual=bottleneck if context_override else '',
        override_reason=override_reason,
    )

    return {
        'revenue': {
            'weekly_revenue':  weekly_revenue,
            'annual_revenue':  annual_revenue,
            'mult':            mult,
            'timeframe':       timeframe,
        },
        'pnl': {
            'annual_revenue':      annual_revenue,
            'annual_cogs':         annual_cogs,
            'annual_gross_profit': annual_gross_profit,
            'gross_margin_pct':    gross_margin_pct,
            'cogs_pct':            cogs_pct,
            'total_codb_pct':      total_codb_pct,
            'annual_codb':         annual_codb,
            'annual_labour':       annual_labour,
            'annual_occupancy':    annual_occupancy,
            'annual_marketing':    annual_marketing,
            'annual_other':        annual_other,
            'labour_pct':          labour_pct,
            'occupancy_pct':       occupancy_pct,
            'marketing_pct':       marketing_pct,
            'other_codb_pct':      other_codb_pct,
            'annual_net_profit':   annual_net_profit,
            'net_margin_pct':      net_margin_pct,
        },
        'scores':                  scores,
        'bottleneck':              bottleneck,
        'bottleneck_score_based':  bottleneck_score_based,
        'context_override':        context_override,
        'context_override_reason': override_reason,
        'store_type':              store_type,
        'store_benchmark':         store_benchmark,
        'scenarios':               scenarios,
        'projections':             projections,
        'scratchpad':              scratchpad,
        # Raw inputs (for display)
        'inputs': {
            'customers':      customers,
            'frequency':      frequency,
            'avg_spend':      avg_spend,
            'cogs_pct_raw':   cogs_pct_raw,
            'labour_pct_raw': labour_pct_raw,
            'occ_pct_raw':    occ_pct_raw,
            'mkt_pct_raw':    mkt_pct_raw,
            'oth_pct_raw':    oth_pct_raw,
            'store_type':     store_type,
            'timeframe':      timeframe,
        },
    }


# ─────────────────────────────────────────────
# Scenario planning
# ─────────────────────────────────────────────

def _build_scenarios(
    customers: float, frequency: float, avg_spend: float,
    cogs_pct: float, total_codb_pct: float,
    base_annual_revenue: float, base_annual_net_profit: float,
    mult: int
) -> list[dict]:
    """
    Build four scenario rows, each showing the impact of a 10% improvement
    in one lever.  Exact formulas per ieRetail spec.

    Margin scenario: new_cogs_pct = cogs_pct × 0.90 (10% reduction in COGS %).
    Revenue is unchanged for the Margin scenario.
    """
    rows = []

    # ── Scenario 1: Transaction Value +10% ───────────────────────────────
    new_avg_spend   = avg_spend * 1.10
    new_rev_tv      = customers * frequency * new_avg_spend * mult
    new_gp_tv       = new_rev_tv * (1 - cogs_pct)
    new_codb_tv     = new_rev_tv * total_codb_pct
    new_np_tv       = new_gp_tv - new_codb_tv
    rows.append({
        'lever':          'Transaction Value',
        'description':    f'Avg spend ${avg_spend:.2f} → ${new_avg_spend:.2f}',
        'base_revenue':   base_annual_revenue,
        'new_revenue':    new_rev_tv,
        'revenue_impact': new_rev_tv - base_annual_revenue,
        'base_profit':    base_annual_net_profit,
        'new_profit':     new_np_tv,
        'profit_impact':  new_np_tv - base_annual_net_profit,
        'pct_gain':       ((new_np_tv / base_annual_net_profit) - 1) * 100
                          if base_annual_net_profit != 0 else 0.0,
    })

    # ── Scenario 2: Customer Base +10% ───────────────────────────────────
    new_customers   = customers * 1.10
    new_rev_cb      = new_customers * frequency * avg_spend * mult
    new_gp_cb       = new_rev_cb * (1 - cogs_pct)
    new_codb_cb     = new_rev_cb * total_codb_pct
    new_np_cb       = new_gp_cb - new_codb_cb
    rows.append({
        'lever':          'Customer Base',
        'description':    f'{customers:,.0f} → {new_customers:,.0f} customers',
        'base_revenue':   base_annual_revenue,
        'new_revenue':    new_rev_cb,
        'revenue_impact': new_rev_cb - base_annual_revenue,
        'base_profit':    base_annual_net_profit,
        'new_profit':     new_np_cb,
        'profit_impact':  new_np_cb - base_annual_net_profit,
        'pct_gain':       ((new_np_cb / base_annual_net_profit) - 1) * 100
                          if base_annual_net_profit != 0 else 0.0,
    })

    # ── Scenario 3: Frequency +10% ───────────────────────────────────────
    new_frequency   = frequency * 1.10
    new_rev_fr      = customers * new_frequency * avg_spend * mult
    new_gp_fr       = new_rev_fr * (1 - cogs_pct)
    new_codb_fr     = new_rev_fr * total_codb_pct
    new_np_fr       = new_gp_fr - new_codb_fr
    rows.append({
        'lever':          'Frequency',
        'description':    f'Frequency {frequency:.2f} → {new_frequency:.2f} visits/period',
        'base_revenue':   base_annual_revenue,
        'new_revenue':    new_rev_fr,
        'revenue_impact': new_rev_fr - base_annual_revenue,
        'base_profit':    base_annual_net_profit,
        'new_profit':     new_np_fr,
        'profit_impact':  new_np_fr - base_annual_net_profit,
        'pct_gain':       ((new_np_fr / base_annual_net_profit) - 1) * 100
                          if base_annual_net_profit != 0 else 0.0,
    })

    # ── Scenario 4: Margin +10% (COGS % reduced by 10%) ─────────────────
    # Revenue is UNCHANGED.  Only COGS % changes.
    new_cogs_pct    = cogs_pct * 0.90
    new_gp_mg       = base_annual_revenue * (1 - new_cogs_pct)
    new_codb_mg     = base_annual_revenue * total_codb_pct
    new_np_mg       = new_gp_mg - new_codb_mg
    rows.append({
        'lever':          'Margin',
        'description':    f'COGS {cogs_pct*100:.1f}% → {new_cogs_pct*100:.1f}%',
        'base_revenue':   base_annual_revenue,
        'new_revenue':    base_annual_revenue,   # revenue unchanged
        'revenue_impact': 0.0,                   # exactly $0
        'base_profit':    base_annual_net_profit,
        'new_profit':     new_np_mg,
        'profit_impact':  new_np_mg - base_annual_net_profit,
        'pct_gain':       ((new_np_mg / base_annual_net_profit) - 1) * 100
                          if base_annual_net_profit != 0 else 0.0,
    })

    # Sort by profit_impact descending
    rows.sort(key=lambda r: r['profit_impact'], reverse=True)
    return rows


# ─────────────────────────────────────────────
# Financial projections
# ─────────────────────────────────────────────

def _build_projections(
    customers: float, frequency: float, avg_spend: float,
    cogs_pct: float, total_codb_pct: float,
    labour_pct: float, occupancy_pct: float,
    marketing_pct: float, other_codb_pct: float,
    mult: int
) -> dict:
    """
    Build current, 90-day, and 12-month projection snapshots.

    90-day:  +5% customers, +5% frequency, +5% avg_spend, −2.5% COGS improvement
             (new_cogs_pct = cogs_pct × 0.975)
    12-month: +12% customers, +15% frequency, +10% avg_spend,
              −5 percentage point COGS reduction (new_cogs_pct = cogs_pct − 0.05)
    """

    def _snapshot(c, f, s, cp):
        rev   = c * f * s * mult
        cogs  = rev * cp
        gp    = rev - cogs
        codb  = rev * total_codb_pct
        np    = gp - codb
        gm    = gp / rev if rev else 0.0
        nm    = np / rev if rev else 0.0
        return {
            'customers':      c,
            'frequency':      f,
            'avg_spend':      s,
            'revenue':        rev,
            'cogs':           cogs,
            'gross_profit':   gp,
            'gross_margin':   gm,
            'codb':           codb,
            'net_profit':     np,
            'net_margin':     nm,
            'cogs_pct':       cp,
        }

    current = _snapshot(customers, frequency, avg_spend, cogs_pct)

    # 90-day: 5% improvement on customers, frequency, spend; 2.5% COGS improvement
    cogs_90 = cogs_pct * 0.975
    target_90 = _snapshot(
        customers  * 1.05,
        frequency  * 1.05,
        avg_spend  * 1.05,
        cogs_90
    )

    # 12-month: 12% customers, 15% frequency, 10% spend, 5pp COGS reduction
    cogs_12m = max(0.0, cogs_pct - 0.05)   # subtract 5 percentage points
    target_12m = _snapshot(
        customers  * 1.12,
        frequency  * 1.15,
        avg_spend  * 1.10,
        cogs_12m
    )

    return {
        'current':    current,
        'target_90':  target_90,
        'target_12m': target_12m,
    }


# ─────────────────────────────────────────────
# Scratchpad builder
# ─────────────────────────────────────────────

def _build_scratchpad(
    customers, frequency, avg_spend, avg_spend_input, mult,
    weekly_revenue, annual_revenue,
    cogs_pct_raw, cogs_pct, annual_cogs,
    annual_gross_profit, gross_margin_pct,
    labour_pct_raw, occ_pct_raw, mkt_pct_raw, oth_pct_raw,
    total_codb_pct, annual_codb,
    annual_labour, annual_occupancy, annual_marketing, annual_other,
    annual_net_profit, net_margin_pct,
    store_type, store_benchmark,
    customer_score, frequency_score, spend_score, margin_score,
    bottleneck,
    *,
    context_override: bool = False,
    bottleneck_contextual: str = '',
    override_reason: str = '',
) -> list[str]:
    """
    Build a list of human-readable scratchpad lines showing every
    intermediate calculation step.
    """
    avg_spend_match = "✓ MATCH" if avg_spend_input == avg_spend else "✗ MISMATCH — ERROR"
    lines = [
        "=== SCRATCHPAD CALCULATIONS ===",
        "",
        "--- AVG SPEND INTEGRITY ---",
        f"avg_spend input  = ${avg_spend_input:.2f}",
        f"avg_spend used   = ${avg_spend:.2f}",
        f"VALIDATION: avg_spend input = ${avg_spend_input:.2f}, avg_spend used = ${avg_spend:.2f}  {avg_spend_match}",
        "",
        "--- REVENUE ---",
        f"weekly_revenue = {customers:,.0f} × {frequency:.2f} × ${avg_spend:.2f} = ${weekly_revenue:,.2f}",
        f"annual_revenue = ${weekly_revenue:,.2f} × {mult} = ${annual_revenue:,.2f}",
        "",
        "--- P&L ---",
        f"annual_cogs = ${annual_revenue:,.2f} × {cogs_pct_raw:.1f}% = ${annual_cogs:,.2f}",
        f"annual_gross_profit = ${annual_revenue:,.2f} − ${annual_cogs:,.2f} = ${annual_gross_profit:,.2f}",
        f"gross_margin_pct = ${annual_gross_profit:,.2f} ÷ ${annual_revenue:,.2f} = {gross_margin_pct*100:.4f}%",
        f"VALIDATION: gross_margin_pct + cogs_pct = {gross_margin_pct*100:.4f}% + {cogs_pct_raw:.4f}% ≈ 100%",
        "",
        "--- CODB BREAKDOWN ---",
        f"labour    = ${annual_revenue:,.2f} × {labour_pct_raw:.1f}% = ${annual_labour:,.2f}",
        f"occupancy = ${annual_revenue:,.2f} × {occ_pct_raw:.1f}% = ${annual_occupancy:,.2f}",
        f"marketing = ${annual_revenue:,.2f} × {mkt_pct_raw:.1f}% = ${annual_marketing:,.2f}",
        f"other     = ${annual_revenue:,.2f} × {oth_pct_raw:.1f}% = ${annual_other:,.2f}",
        f"total_codb_pct = {labour_pct_raw:.1f}% + {occ_pct_raw:.1f}% + {mkt_pct_raw:.1f}% + {oth_pct_raw:.1f}% = {total_codb_pct*100:.1f}%",
        f"annual_codb = ${annual_revenue:,.2f} × {total_codb_pct*100:.1f}% = ${annual_codb:,.2f}",
        "",
        "--- NET PROFIT ---",
        f"annual_net_profit = ${annual_gross_profit:,.2f} − ${annual_codb:,.2f} = ${annual_net_profit:,.2f}",
        f"net_margin_pct = ${annual_net_profit:,.2f} ÷ ${annual_revenue:,.2f} = {net_margin_pct*100:.4f}%",
        "",
        "--- LEVER SCORES ---",
        f"store_type = {store_type}  |  spend_benchmark = ${store_benchmark:.2f}",
        f"customer_score = MIN(100, ROUND(({customers:,.0f} ÷ 500) × 100, 0)) = {customer_score:.0f}",
        f"frequency_score = MIN(100, ROUND(({frequency:.2f} ÷ 3.0) × 100, 0)) = {frequency_score:.0f}",
        f"spend_score = MIN(100, ROUND((${avg_spend:.2f} ÷ ${store_benchmark:.2f}) × 100, 0)) = {spend_score:.0f}",
        f"margin_score = MIN(100, ROUND(({gross_margin_pct*100:.2f}% ÷ 50%) × 100, 0)) = {margin_score:.0f}",
        f"bottleneck (score-based) = {bottleneck} (lowest score)",
    ]

    if context_override and bottleneck_contextual:
        lines += [
            "",
            "--- CONTEXTUAL BOTTLENECK OVERRIDE ---",
            "context_override = True",
            f"bottleneck_contextual = {bottleneck_contextual}",
            f"override_reason = {override_reason}",
        ]
    else:
        lines += [
            "",
            "--- CONTEXTUAL BOTTLENECK OVERRIDE ---",
            "context_override = False  (score-based bottleneck retained)",
        ]

    return lines
