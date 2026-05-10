import os
import logging
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler,
)
from report_generator import generate_pdf_report, load_analysis_history
from calculation_engine import (
    calculate_all, validate_inputs, VALID_STORE_TYPES,
    get_store_benchmark, lever_status,
)
from formatting_engine import (
    fmt_currency, fmt_pct_from_decimal, fmt_profit_impact,
    lever_status_label,
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
)

# ====================== CONVERSATION STATES ======================
(
    TIMEFRAME,
    STORE_TYPE,
    CUSTOMERS,
    FREQUENCY,
    AVG_SPEND,
    GST_CONFIRM,
    COGS_PCT,
    LABOUR_PCT,
    OCCUPANCY_PCT,
    MARKETING_PCT,
    OTHER_CODB_PCT,
    CHALLENGES,
    DIAGNOSTIC,
    UPLOAD,
    BUSINESS_NAME,
    PDF_CONFIRM,
) = range(16)

# ====================== STORE TYPE KEYBOARD ======================

STORE_TYPE_KEYBOARD = [
    ['grocery', 'cafe', 'pharmacy'],
    ['liquor', 'specialty', 'gift'],
    ['hardware', 'other'],
]

# ====================== DIAGNOSTIC QUESTIONS ======================

def get_diagnostic_questions(bottleneck: str) -> str:
    questions = {
        'Customer Base': (
            "*Diagnosing: Customer Base*\n\n"
            "To understand your acquisition challenge, please answer:\n\n"
            "1. What is your *point of difference* vs competitors?\n"
            "2. How do you currently *acquire new customers*? "
            "(e.g. word of mouth, social media, flyers, none)\n\n"
            "Type your answers and press Send."
        ),
        'Frequency': (
            "*Diagnosing: Customer Frequency*\n\n"
            "To understand your loyalty challenge, please answer:\n\n"
            "1. Which *categories* drive the most repeat visits?\n"
            "2. Do you have a *loyalty or rewards program*? "
            "(yes / no - if yes, what type?)\n\n"
            "Type your answers and press Send."
        ),
        'Transaction Value': (
            "*Diagnosing: Transaction Value*\n\n"
            "To understand your basket-size challenge, please answer:\n\n"
            "1. How many *items* does the average customer buy per visit?\n"
            "2. Do your staff actively *cross-sell or upsell*? "
            "(yes / no - if yes, how?)\n\n"
            "Type your answers and press Send."
        ),
        'Margin': (
            "*Diagnosing: Margins (COGS & CODB)*\n\n"
            "To understand your margin challenge, please answer:\n\n"
            "1. Have you *negotiated with suppliers* in the last 12 months?\n"
            "2. What is your biggest *Cost of Doing Business (CODB)* line item? "
            "(e.g. rent, wages, utilities)\n\n"
            "Type your answers and press Send."
        ),
    }
    return questions.get(bottleneck, "Tell me more about your biggest challenge.")


def get_lever_recommendations(bottleneck: str) -> str:
    recs = {
        'Customer Base': (
            "*Strategies to Grow Your Customer Base*\n\n"
            "- *Expand your range* - stock products that attract new shopper segments\n"
            "- *Sharpen your point of difference* - be known for something specific\n"
            "- *Run targeted marketing* - geo-targeted social ads, Google Business profile\n"
            "- *Referral incentives* - reward existing customers for bringing friends\n"
            "- *Community presence* - sponsor local events, partner with complementary businesses"
        ),
        'Frequency': (
            "*Strategies to Improve Customer Frequency*\n\n"
            "- *Implement a loyalty program* - even a simple stamp card lifts repeat visits\n"
            "- *Create in-store theatre* - seasonal displays, tastings, demos\n"
            "- *Focus on FOP categories* - stock everyday essentials that drive habitual visits\n"
            "- *Subscription or auto-replenishment* - lock in regular purchases\n"
            "- *Personalised outreach* - SMS/email reminders when customers haven't visited"
        ),
        'Transaction Value': (
            "*Strategies to Grow Transaction Value*\n\n"
            "- *Improve merchandising* - place complementary products together\n"
            "- *Train staff to cross-sell* - suggest one related item at point of sale\n"
            "- *Add a premium range* - trade customers up with a higher-margin option\n"
            "- *Bundle deals* - 'buy 2 get 10% off' increases items per basket\n"
            "- *Minimum spend thresholds* - 'spend $50, get free delivery' lifts average ticket"
        ),
        'Margin': (
            "*Strategies to Improve Margins*\n\n"
            "- *Negotiate supplier deals* - volume commitments, early payment discounts\n"
            "- *Reduce CODB* - audit rent, wages scheduling, energy costs\n"
            "- *Improve operational efficiency* - reduce waste, shrinkage, and overordering\n"
            "- *Rationalise the range* - cut slow-moving SKUs that tie up cash and space\n"
            "- *Premiumise* - shift mix toward higher-margin products and own-label lines"
        ),
    }
    return recs.get(bottleneck, "Focus on the lever with the most room for improvement.")


def build_lever_score_bar(scores: dict) -> str:
    lines = []
    for lever, score in scores.items():
        filled = int(score / 10)
        empty  = 10 - filled
        bar    = "█" * filled + "░" * empty
        status = lever_status_label(score)
        lines.append(f"{lever:<18} [{bar}] {score:.0f}/100  {status}")
    return "\n".join(lines)


# ====================== CHART GENERATORS ======================

def _save_lever_chart(scores: dict, bottleneck: str,
                      store_type: str, chat_id: int) -> str:
    levers = list(scores.keys())
    values = [scores[l] for l in levers]
    colors = ['#D62839' if l == bottleneck else '#1B998B' for l in levers]

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.barh(levers, values, color=colors, edgecolor='white', linewidth=0.8)
    ax.set_xlim(0, 110)
    ax.set_xlabel('Score (0 - 100)', fontsize=11)
    ax.set_title(f'Retail DNA - Lever Scores ({store_type.title()} store)',
                 fontsize=13, fontweight='bold')

    for bar, val in zip(bars, values):
        ax.text(val + 1.5, bar.get_y() + bar.get_height() / 2,
                f'{val:.0f}', va='center', fontsize=10, fontweight='bold')

    for x, label, col in [(50, 'MONITOR', '#E67E22'), (70, 'GOOD', '#FFBC42'),
                           (90, 'HEALTHY', '#27AE60')]:
        ax.axvline(x=x, color=col, linestyle='--', linewidth=1)
        ax.text(x + 0.5, -0.5, label, color=col, fontsize=8)

    legend_handles = [
        mpatches.Patch(color='#D62839', label='Bottleneck lever'),
        mpatches.Patch(color='#1B998B', label='Other levers'),
    ]
    ax.legend(handles=legend_handles, loc='lower right', fontsize=9)

    plt.tight_layout()
    path = f"chart_levers_{chat_id}.png"
    plt.savefig(path, dpi=120)
    plt.close()
    return path


# ====================== TIMEFRAME COMMANDS ======================

async def set_weekly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['timeframe'] = 'weekly'
    await update.message.reply_text(
        "Timeframe set to *Weekly*.\n\nStarting fresh diagnostic...",
        parse_mode='Markdown')
    return await ask_store_type(update, context)

async def set_monthly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['timeframe'] = 'monthly'
    await update.message.reply_text(
        "Timeframe set to *Monthly*.\n\nStarting fresh diagnostic...",
        parse_mode='Markdown')
    return await ask_store_type(update, context)

async def set_yearly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['timeframe'] = 'yearly'
    await update.message.reply_text(
        "Timeframe set to *Yearly*.\n\nStarting fresh diagnostic...",
        parse_mode='Markdown')
    return await ask_store_type(update, context)


# ====================== MAIN DIAGNOSTIC FLOW ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "*Welcome to Retail DNA Bot!*\n\n"
        "I'll run a precise, auditable diagnostic of your retail business "
        "using the ieRetail framework.\n\n"
        "All calculations use exact formulas - no approximations.\n"
        "All prices should be *GST-exclusive* (NZ context).\n\n"
        "What is the *timeframe* of your data?\n"
        "Reply: *weekly*, *monthly*, or *yearly*",
        parse_mode='Markdown'
    )
    return TIMEFRAME


async def timeframe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tf = update.message.text.lower().strip()
    if tf.startswith('month'):
        context.user_data['timeframe'] = 'monthly'
    elif tf.startswith('year'):
        context.user_data['timeframe'] = 'yearly'
    elif tf.startswith('week'):
        context.user_data['timeframe'] = 'weekly'
    else:
        await update.message.reply_text(
            "Please reply with: *weekly*, *monthly*, or *yearly*",
            parse_mode='Markdown')
        return TIMEFRAME
    return await ask_store_type(update, context)


async def ask_store_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "What *type of store* do you operate?\n\n"
        "This determines the avg spend benchmark used to score your "
        "Transaction Value lever.\n\n"
        "Benchmarks (GST-exclusive avg spend):\n"
        "- grocery: $45\n"
        "- cafe: $22\n"
        "- pharmacy: $55\n"
        "- liquor: $65\n"
        "- specialty: $80\n"
        "- gift: $70\n"
        "- hardware: $90\n"
        "- other: $50\n\n"
        "Select your store type:",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardMarkup(
            STORE_TYPE_KEYBOARD, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return STORE_TYPE


async def store_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    st = update.message.text.lower().strip()
    if st not in VALID_STORE_TYPES:
        await update.message.reply_text(
            f"Please choose one of: {', '.join(VALID_STORE_TYPES)}",
            reply_markup=ReplyKeyboardMarkup(
                STORE_TYPE_KEYBOARD, one_time_keyboard=True, resize_keyboard=True
            ),
        )
        return STORE_TYPE
    context.user_data['store_type'] = st
    tf = context.user_data.get('timeframe', 'weekly')
    await update.message.reply_text(
        f"Store type: *{st.title()}*  |  Timeframe: *{tf.capitalize()}*\n\n"
        f"How many *unique customers* visited in that {tf} period?",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardRemove(),
    )
    return CUSTOMERS


async def customers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = int(float(update.message.text.replace(',', '')))
        if val <= 0:
            raise ValueError
        context.user_data['customers'] = val
    except ValueError:
        await update.message.reply_text("Please enter a positive whole number (e.g. 350).")
        return CUSTOMERS
    await update.message.reply_text(
        "Average *visits per customer* in that period?\n"
        "_(e.g. 1.5 for weekly, 4 for monthly)_",
        parse_mode='Markdown'
    )
    return FREQUENCY


async def frequency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text)
        if val <= 0:
            raise ValueError
        context.user_data['frequency'] = val
    except ValueError:
        await update.message.reply_text("Please enter a positive number (e.g. 2.5).")
        return FREQUENCY
    await update.message.reply_text(
        "Average *spend per visit* ($)?\n"
        "_(Enter GST-exclusive price, e.g. 43.50)_",
        parse_mode='Markdown'
    )
    return AVG_SPEND


async def avg_spend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.replace('$', '').replace(',', ''))
        if val <= 0:
            raise ValueError
        context.user_data['avg_spend'] = val
    except ValueError:
        await update.message.reply_text(
            "Please enter a positive dollar amount (e.g. 43.50).")
        return AVG_SPEND
    await update.message.reply_text(
        "Are your prices *GST-exclusive*?\n\n"
        "_(All calculations use GST-exclusive prices. "
        "If your avg spend includes GST, divide by 1.15 first.)_\n\n"
        "Reply: *yes* or *no*",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardMarkup(
            [['yes', 'no']], one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return GST_CONFIRM


async def gst_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower().strip()
    if text in ('yes', 'y'):
        context.user_data['gst_exclusive'] = True
    elif text in ('no', 'n'):
        context.user_data['gst_exclusive'] = False
        # Auto-adjust avg_spend to GST-exclusive
        gst_inclusive = context.user_data.get('avg_spend', 0)
        context.user_data['avg_spend'] = round(gst_inclusive / 1.15, 2)
        await update.message.reply_text(
            f"Noted. Avg spend adjusted to GST-exclusive: "
            f"*${context.user_data['avg_spend']:.2f}*\n"
            f"_(${gst_inclusive:.2f} / 1.15)_",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove(),
        )
    else:
        await update.message.reply_text(
            "Please reply *yes* or *no*.",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardMarkup(
                [['yes', 'no']], one_time_keyboard=True, resize_keyboard=True
            ),
        )
        return GST_CONFIRM

    await update.message.reply_text(
        "*COGS %* (Cost of Goods Sold as a % of revenue)?\n"
        "_(e.g. 59 for 59%. Typical range: 40-80%)_",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardRemove(),
    )
    return COGS_PCT


async def cogs_pct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.replace('%', ''))
        if not (0 < val < 100):
            raise ValueError
        context.user_data['cogs_pct'] = val
    except ValueError:
        await update.message.reply_text(
            "Please enter a percentage between 0 and 100 (e.g. 59).")
        return COGS_PCT
    gm = 100 - val
    await update.message.reply_text(
        f"COGS: *{val:.1f}%*  |  Gross Margin: *{gm:.1f}%*\n\n"
        "Now let's break down your *Cost of Doing Business (CODB)*.\n\n"
        "*Labour cost %* (wages as a % of revenue)?\n"
        "_(e.g. 15 for 15%. Typical range: 10-25%)_",
        parse_mode='Markdown'
    )
    return LABOUR_PCT


async def labour_pct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.replace('%', ''))
        if not (0 <= val <= 100):
            raise ValueError
        context.user_data['labour_pct'] = val
    except ValueError:
        await update.message.reply_text(
            "Please enter a percentage between 0 and 100 (e.g. 15).")
        return LABOUR_PCT
    await update.message.reply_text(
        f"Labour: *{val:.1f}%*\n\n"
        "*Occupancy cost %* (rent, rates, utilities as a % of revenue)?\n"
        "_(e.g. 8 for 8%. Typical range: 5-15%)_",
        parse_mode='Markdown'
    )
    return OCCUPANCY_PCT


async def occupancy_pct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.replace('%', ''))
        if not (0 <= val <= 100):
            raise ValueError
        context.user_data['occupancy_pct'] = val
    except ValueError:
        await update.message.reply_text(
            "Please enter a percentage between 0 and 100 (e.g. 8).")
        return OCCUPANCY_PCT
    await update.message.reply_text(
        f"Occupancy: *{val:.1f}%*\n\n"
        "*Marketing cost %* (advertising, promotions as a % of revenue)?\n"
        "_(e.g. 2 for 2%. Typical range: 1-5%)_",
        parse_mode='Markdown'
    )
    return MARKETING_PCT


async def marketing_pct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.replace('%', ''))
        if not (0 <= val <= 100):
            raise ValueError
        context.user_data['marketing_pct'] = val
    except ValueError:
        await update.message.reply_text(
            "Please enter a percentage between 0 and 100 (e.g. 2).")
        return MARKETING_PCT
    await update.message.reply_text(
        f"Marketing: *{val:.1f}%*\n\n"
        "*Other CODB %* (all other operating costs as a % of revenue)?\n"
        "_(e.g. 3 for 3%. Includes admin, insurance, depreciation, etc.)_",
        parse_mode='Markdown'
    )
    return OTHER_CODB_PCT


async def other_codb_pct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.replace('%', ''))
        if not (0 <= val <= 100):
            raise ValueError
        context.user_data['other_codb_pct'] = val
    except ValueError:
        await update.message.reply_text(
            "Please enter a percentage between 0 and 100 (e.g. 3).")
        return OTHER_CODB_PCT

    # Show CODB summary
    labour    = context.user_data.get('labour_pct', 0)
    occupancy = context.user_data.get('occupancy_pct', 0)
    marketing = context.user_data.get('marketing_pct', 0)
    other     = val
    total     = labour + occupancy + marketing + other
    cogs      = context.user_data.get('cogs_pct', 0)
    gm        = 100 - cogs
    net_est   = gm - total

    await update.message.reply_text(
        f"*CODB Summary:*\n"
        f"Labour:    {labour:.1f}%\n"
        f"Occupancy: {occupancy:.1f}%\n"
        f"Marketing: {marketing:.1f}%\n"
        f"Other:     {other:.1f}%\n"
        f"Total CODB: *{total:.1f}%*\n\n"
        f"Gross Margin: {gm:.1f}%\n"
        f"Est. Net Margin: *{net_est:.1f}%*\n\n"
        "What is your *biggest challenge* right now?\n"
        "_(e.g. not enough customers, low repeat visits, thin margins...)_",
        parse_mode='Markdown'
    )
    return CHALLENGES


async def challenges(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['challenges'] = update.message.text

    # Validate inputs before calculating
    errors = validate_inputs(context.user_data)
    if errors:
        error_text = "\n".join(f"- {e}" for e in errors)
        await update.message.reply_text(
            f"There are some issues with your inputs:\n\n{error_text}\n\n"
            "Please use /start to begin again.",
            parse_mode='Markdown'
        )
        return ConversationHandler.END

    # Run calculation engine
    try:
        calc = calculate_all(context.user_data)
    except Exception as e:
        logging.error(f"Calculation error: {e}")
        await update.message.reply_text(
            f"Calculation error: {str(e)}\n\nPlease use /start to begin again."
        )
        return ConversationHandler.END

    scores     = calc['scores']
    bottleneck = calc['bottleneck']
    context.user_data['_calc'] = calc

    diag_q = get_diagnostic_questions(bottleneck)
    await update.message.reply_text(
        f"*Basic DNA collected!*\n\n"
        f"Your weakest lever appears to be *{bottleneck}* "
        f"(score: {scores[bottleneck]:.0f}/100) - let's dig deeper.\n\n"
        + diag_q,
        parse_mode='Markdown'
    )
    return DIAGNOSTIC


async def diagnostic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['diagnostic_answers'] = update.message.text
    await update.message.reply_text(
        "Upload your sales data / P&L (Excel or CSV) for deeper analysis + charts, "
        "or type `skip` to proceed with the data you've entered.",
        parse_mode='Markdown'
    )
    return UPLOAD


async def handle_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.document:
        file      = await update.message.document.get_file()
        file_path = f"data_{update.message.chat_id}.xlsx"
        await file.download_to_drive(file_path)
        try:
            df = pd.read_excel(file_path) if file_path.endswith('.xlsx') else pd.read_csv(file_path)
            context.user_data['df'] = df
            await update.message.reply_text(f"File loaded! ({len(df)} rows)")
        except Exception as e:
            await update.message.reply_text(f"Error reading file: {str(e)}")
    return await generate_analysis(update, context)


async def skip_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.lower().strip() == 'skip':
        return await generate_analysis(update, context)
    await update.message.reply_text(
        "Type `skip` to continue without a file, or attach an Excel/CSV.",
        parse_mode='Markdown')
    return UPLOAD


# ====================== ANALYSIS OUTPUT ======================

async def generate_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data

    # Use cached calc or recompute
    calc = data.get('_calc')
    if calc is None:
        errors = validate_inputs(data)
        if errors:
            error_text = "\n".join(f"- {e}" for e in errors)
            await update.message.reply_text(
                f"Validation errors:\n\n{error_text}\n\nUse /start to begin again.")
            return ConversationHandler.END
        try:
            calc = calculate_all(data)
        except Exception as e:
            await update.message.reply_text(f"Calculation error: {str(e)}")
            return ConversationHandler.END

    pnl        = calc['pnl']
    scores     = calc['scores']
    bottleneck = calc['bottleneck']
    store_type = calc['store_type']
    inp        = calc['inputs']
    chat_id    = update.message.chat_id

    # Chart: Lever Scores
    try:
        lever_chart = _save_lever_chart(scores, bottleneck, store_type, chat_id)
        await update.message.reply_photo(
            open(lever_chart, 'rb'),
            caption=f"Retail DNA Lever Scores ({store_type.title()} store) - red = bottleneck"
        )
        try:
            os.remove(lever_chart)
        except Exception:
            pass
    except Exception as e:
        logging.warning(f"Lever chart failed: {e}")

    # Lever score text bars
    score_bars = build_lever_score_bar(scores)

    # Bottleneck explanations
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

    # Top scenario (highest profit impact)
    top_scenario = calc['scenarios'][0] if calc['scenarios'] else None
    scenario_text = ''
    if top_scenario:
        scenario_text = (
            f"\n*Top Opportunity: {top_scenario['lever']} +10%*\n"
            f"{top_scenario['description']}\n"
            f"Profit impact: *{fmt_profit_impact(top_scenario['profit_impact'])}*"
        )

    # Net profit display (handle negative)
    net_profit_val = pnl['annual_net_profit']
    net_profit_display = fmt_currency(net_profit_val)
    if net_profit_val < 0:
        net_profit_display = f"({fmt_currency(abs(net_profit_val))}) LOSS"

    # Main analysis message
    tf = data.get('timeframe', 'weekly')
    analysis = (
        f"*Retail DNA Analysis - {tf.capitalize()} View*\n"
        f"{'─' * 32}\n\n"
        f"*Financial Snapshot (GST-exclusive)*\n"
        f"Store type:      {store_type.title()}\n"
        f"Period revenue:  {fmt_currency(calc['revenue']['weekly_revenue'])}\n"
        f"Annual revenue:  {fmt_currency(pnl['annual_revenue'])}\n"
        f"Gross Margin:    {fmt_pct_from_decimal(pnl['gross_margin_pct'])}\n"
        f"COGS:            {fmt_pct_from_decimal(pnl['cogs_pct'])}\n"
        f"Total CODB:      {fmt_pct_from_decimal(pnl['total_codb_pct'])}\n"
        f"  Labour:        {fmt_pct_from_decimal(pnl['labour_pct'])}\n"
        f"  Occupancy:     {fmt_pct_from_decimal(pnl['occupancy_pct'])}\n"
        f"  Marketing:     {fmt_pct_from_decimal(pnl['marketing_pct'])}\n"
        f"  Other:         {fmt_pct_from_decimal(pnl['other_codb_pct'])}\n"
        f"Net Profit:      {fmt_pct_from_decimal(pnl['net_margin_pct'])}  "
        f"({net_profit_display}/yr)\n\n"
        f"*Lever Scores*\n"
        f"```\n{score_bars}\n```\n\n"
        f"*Bottleneck: {bottleneck}* (score: {scores[bottleneck]:.0f}/100)\n"
        f"{bn_explanations.get(bottleneck, '')}"
        f"{scenario_text}\n\n"
        f"{get_lever_recommendations(bottleneck)}\n\n"
        f"{'─' * 32}\n"
        f"_Use /week, /month, or /year to run a new analysis._"
    )
    await update.message.reply_text(analysis, parse_mode='Markdown')

    # Prompt for business name / PDF
    await update.message.reply_text(
        "*Would you like a professional PDF report?*\n\n"
        "First, what is your *business name*?\n"
        "_(Type your store name, or type `skip` to use \"Your Store\")_",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardRemove(),
    )
    return BUSINESS_NAME


async def collect_business_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() == 'skip':
        context.user_data['business_name'] = 'Your Store'
    else:
        context.user_data['business_name'] = text

    reply_keyboard = [['Yes, generate PDF', 'No thanks']]
    await update.message.reply_text(
        f"Great!  Generating a report for *{context.user_data['business_name']}*.\n\n"
        "Shall I create your *10-page PDF diagnostic report* now?\n"
        "_(Includes financial snapshot with CODB breakdown, lever analysis, "
        "scenario planning, recommendations, 90-day action plan, projections, "
        "and a full calculation scratchpad for auditability.)_",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return PDF_CONFIRM


async def handle_pdf_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if 'no' in text.lower() or text.lower() in ('no thanks', 'nope', 'n'):
        await update.message.reply_text(
            "No problem! Your inline analysis is above.\n\n"
            "_Use /start to run a new diagnostic, or /history to view past analyses._",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END

    business_name = context.user_data.get('business_name', 'Your Store')
    chat_id       = update.message.chat_id

    await update.message.reply_text(
        "*Building your PDF report...*\n"
        "This takes a few seconds - please wait.",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardRemove(),
    )

    try:
        pdf_path = generate_pdf_report(
            data=context.user_data,
            chat_id=chat_id,
            business_name=business_name,
        )
        with open(pdf_path, 'rb') as pdf_file:
            await update.message.reply_document(
                document=pdf_file,
                filename=f"RetailDNA_Report_{business_name.replace(' ', '_')}.pdf",
                caption=(
                    f"*Retail DNA Report - {business_name}*\n\n"
                    "Your 10-page diagnostic report includes:\n"
                    "- Executive summary & key metrics\n"
                    "- Financial snapshot with CODB breakdown\n"
                    "- Lever analysis (store-type benchmarks)\n"
                    "- Bottleneck deep-dive\n"
                    "- Scenario planning (exact formulas)\n"
                    "- Prioritised recommendations\n"
                    "- 90-day action plan\n"
                    "- Financial projections (90-day & 12-month)\n"
                    "- KPI tracking dashboard\n"
                    "- Appendix with GST note, glossary & calculation scratchpad\n\n"
                    "_All numbers are calculated using exact formulas - fully auditable._"
                ),
                parse_mode='Markdown',
            )
        try:
            os.remove(pdf_path)
        except Exception:
            pass

        await update.message.reply_text(
            "*Report sent!*\n\n"
            "Use /start to run a new diagnostic, or /history to compare past analyses.",
            parse_mode='Markdown',
        )

    except Exception as e:
        logging.error(f"PDF generation failed: {e}")
        await update.message.reply_text(
            "Sorry, there was an error generating your PDF report. "
            "Your inline analysis above contains all the key insights.\n\n"
            f"_Error: {str(e)}_",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove(),
        )

    return ConversationHandler.END


# ====================== HISTORY COMMAND ======================

async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    history = load_analysis_history(chat_id)

    if not history:
        await update.message.reply_text(
            "No previous analyses found.\n\n"
            "Run /start to begin your first diagnostic.",
            parse_mode='Markdown',
        )
        return

    lines = ["*Your Analysis History*\n"]
    for i, entry in enumerate(history[-5:], 1):
        ts   = entry.get('timestamp', '')[:10]
        name = entry.get('business_name', 'Your Store')
        st   = entry.get('store_type', '-')
        rev  = entry.get('annual_revenue', 0)
        bn   = entry.get('bottleneck', '-')
        np_v = entry.get('annual_profit', 0)
        gm   = entry.get('gross_margin', 0)
        lines.append(
            f"*{i}. {name}* ({ts})\n"
            f"   Store: {st.title()}  |  Revenue: {fmt_currency(rev)}\n"
            f"   Gross Margin: {gm:.1f}%  |  Net Profit: {fmt_currency(np_v)}\n"
            f"   Bottleneck: {bn}\n"
        )

    lines.append("_Run /start to add a new analysis._")
    await update.message.reply_text('\n'.join(lines), parse_mode='Markdown')


# ====================== CANCEL ======================

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Diagnostic cancelled. Type /start to begin again.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


# ====================== BOT SETUP ======================

def main():
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    app   = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            TIMEFRAME:      [MessageHandler(filters.TEXT & ~filters.COMMAND, timeframe)],
            STORE_TYPE:     [MessageHandler(filters.TEXT & ~filters.COMMAND, store_type)],
            CUSTOMERS:      [MessageHandler(filters.TEXT & ~filters.COMMAND, customers)],
            FREQUENCY:      [MessageHandler(filters.TEXT & ~filters.COMMAND, frequency)],
            AVG_SPEND:      [MessageHandler(filters.TEXT & ~filters.COMMAND, avg_spend)],
            GST_CONFIRM:    [MessageHandler(filters.TEXT & ~filters.COMMAND, gst_confirm)],
            COGS_PCT:       [MessageHandler(filters.TEXT & ~filters.COMMAND, cogs_pct)],
            LABOUR_PCT:     [MessageHandler(filters.TEXT & ~filters.COMMAND, labour_pct)],
            OCCUPANCY_PCT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, occupancy_pct)],
            MARKETING_PCT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, marketing_pct)],
            OTHER_CODB_PCT: [MessageHandler(filters.TEXT & ~filters.COMMAND, other_codb_pct)],
            CHALLENGES:     [MessageHandler(filters.TEXT & ~filters.COMMAND, challenges)],
            DIAGNOSTIC:     [MessageHandler(filters.TEXT & ~filters.COMMAND, diagnostic)],
            UPLOAD: [
                MessageHandler(filters.Document.ALL, handle_upload),
                MessageHandler(filters.TEXT & ~filters.COMMAND, skip_upload),
            ],
            BUSINESS_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, collect_business_name),
            ],
            PDF_CONFIRM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_pdf_confirm),
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    app.add_handler(CommandHandler('week',    set_weekly))
    app.add_handler(CommandHandler('month',   set_monthly))
    app.add_handler(CommandHandler('year',    set_yearly))
    app.add_handler(CommandHandler('history', show_history))
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler(
        'help',
        lambda u, c: u.message.reply_text(
            "*Retail DNA Bot - Commands*\n\n"
            "/start   - begin a new diagnostic\n"
            "/week    - set timeframe to weekly\n"
            "/month   - set timeframe to monthly\n"
            "/year    - set timeframe to yearly\n"
            "/history - view past analyses\n"
            "/cancel  - cancel current session\n\n"
            "*Data collected:*\n"
            "Store type, customers, frequency, avg spend (GST-exclusive),\n"
            "COGS %, labour %, occupancy %, marketing %, other CODB %\n\n"
            "*Report includes:*\n"
            "Store-type benchmarks, exact P&L, CODB breakdown,\n"
            "scenario planning, 90-day & 12-month projections,\n"
            "calculation scratchpad for full auditability.",
            parse_mode='Markdown'
        )
    ))

    print("Retail DNA Bot is running...")
    app.run_polling()


if __name__ == '__main__':
    main()
