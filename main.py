import os
import logging
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ====================== CONVERSATION STATES ======================
(
    TIMEFRAME,
    CUSTOMERS,
    FREQUENCY,
    AVG_SPEND,
    GROSS_MARGIN,
    COGS,
    NET_PROFIT,
    CHALLENGES,
    DIAGNOSTIC,
    UPLOAD,
) = range(10)

# ====================== LEVER ANALYSIS ENGINE ======================

def calculate_lever_scores(data: dict) -> dict:
    """
    Normalise each of the four Retail DNA levers to a 0-100 score.

    Benchmarks (weekly):
      Customer Base  – 500 customers = 100
      Frequency      – 3+ visits/period = 100
      Transaction    – $100 avg spend = 100
      Margin         – 50% gross margin = 100
    """
    customers   = data.get('customers', 0)
    frequency   = data.get('frequency', 0)
    avg_spend   = data.get('avg_spend', 0)
    gross_margin = data.get('gross_margin', 0)

    scores = {
        'Customer Base':      min(100, round((customers   / 500)  * 100, 1)),
        'Frequency':          min(100, round((frequency   / 3)    * 100, 1)),
        'Transaction Value':  min(100, round((avg_spend   / 100)  * 100, 1)),
        'Margin':             min(100, round((gross_margin / 50)  * 100, 1)),
    }
    return scores


def identify_bottleneck(scores: dict) -> str:
    """Return the lever name with the lowest score."""
    return min(scores, key=scores.get)


def get_diagnostic_questions(bottleneck: str) -> str:
    """Return targeted diagnostic questions for the weakest lever."""
    questions = {
        'Customer Base': (
            "🔎 *Diagnosing: Customer Base*\n\n"
            "To understand your acquisition challenge, please answer:\n\n"
            "1️⃣ What is your *point of difference* vs competitors?\n"
            "2️⃣ How do you currently *acquire new customers*? "
            "(e.g. word of mouth, social media, flyers, none)\n\n"
            "Type your answers and press Send."
        ),
        'Frequency': (
            "🔎 *Diagnosing: Customer Frequency*\n\n"
            "To understand your loyalty challenge, please answer:\n\n"
            "1️⃣ Which *categories* drive the most repeat visits?\n"
            "2️⃣ Do you have a *loyalty or rewards program*? "
            "(yes / no — if yes, what type?)\n\n"
            "Type your answers and press Send."
        ),
        'Transaction Value': (
            "🔎 *Diagnosing: Transaction Value*\n\n"
            "To understand your basket-size challenge, please answer:\n\n"
            "1️⃣ How many *items* does the average customer buy per visit?\n"
            "2️⃣ Do your staff actively *cross-sell or upsell*? "
            "(yes / no — if yes, how?)\n\n"
            "Type your answers and press Send."
        ),
        'Margin': (
            "🔎 *Diagnosing: Margins (COGS & CODB)*\n\n"
            "To understand your margin challenge, please answer:\n\n"
            "1️⃣ Have you *negotiated with suppliers* in the last 12 months?\n"
            "2️⃣ What is your biggest *Cost of Doing Business (CODB)* line item? "
            "(e.g. rent, wages, utilities)\n\n"
            "Type your answers and press Send."
        ),
    }
    return questions.get(bottleneck, "Tell me more about your biggest challenge.")


def get_lever_recommendations(bottleneck: str, data: dict) -> str:
    """Return actionable strategies mapped to the weakest lever."""
    recs = {
        'Customer Base': (
            "📌 *Strategies to Grow Your Customer Base*\n\n"
            "• *Expand your range* — stock products that attract new shopper segments\n"
            "• *Sharpen your point of difference* — be known for something specific "
            "(price, range, service, convenience)\n"
            "• *Run targeted marketing* — geo-targeted social ads, letterbox drops, "
            "Google Business profile optimisation\n"
            "• *Referral incentives* — reward existing customers for bringing friends\n"
            "• *Community presence* — sponsor local events, partner with complementary businesses"
        ),
        'Frequency': (
            "📌 *Strategies to Improve Customer Frequency*\n\n"
            "• *Implement a loyalty program* — even a simple stamp card lifts repeat visits\n"
            "• *Create in-store theatre* — seasonal displays, tastings, demos that give "
            "customers a reason to return\n"
            "• *Focus on FOP (Front of Pack) categories* — stock the everyday essentials "
            "that drive habitual visits\n"
            "• *Subscription or auto-replenishment* — lock in regular purchases\n"
            "• *Personalised outreach* — SMS/email reminders when customers haven't visited"
        ),
        'Transaction Value': (
            "📌 *Strategies to Grow Transaction Value*\n\n"
            "• *Improve merchandising* — place complementary products together to trigger "
            "add-on purchases\n"
            "• *Train staff to cross-sell* — suggest one related item at point of sale\n"
            "• *Add a premium range* — trade customers up with a higher-margin option\n"
            "• *Bundle deals* — 'buy 2 get 10% off' increases items per basket\n"
            "• *Minimum spend thresholds* — 'spend $50, get free delivery' lifts average ticket"
        ),
        'Margin': (
            "📌 *Strategies to Improve Margins*\n\n"
            "• *Negotiate supplier deals* — volume commitments, early payment discounts, "
            "rebate structures\n"
            "• *Reduce CODB* — audit rent, wages scheduling, energy costs; small cuts "
            "compound quickly\n"
            "• *Improve operational efficiency* — reduce waste, shrinkage, and overordering\n"
            "• *Rationalise the range* — cut slow-moving SKUs that tie up cash and space\n"
            "• *Premiumise* — shift mix toward higher-margin products and own-label lines"
        ),
    }
    return recs.get(bottleneck, "Focus on the lever with the most room for improvement.")


def calculate_profit_impact(data: dict, scores: dict, bottleneck: str) -> str:
    """
    Show the dollar impact of a 10 % improvement in the bottleneck lever.
    Profit = customers × frequency × avg_spend × net_profit_margin
    """
    customers    = data.get('customers', 0)
    frequency    = data.get('frequency', 1)
    avg_spend    = data.get('avg_spend', 0)
    net_margin   = data.get('net_profit', 4) / 100
    tf           = data.get('timeframe', 'weekly')

    # Annualise
    multiplier = {'weekly': 52, 'monthly': 12, 'yearly': 1}.get(tf, 52)
    base_profit = customers * frequency * avg_spend * net_margin * multiplier

    improvement = 0.10  # 10 % lift

    if bottleneck == 'Customer Base':
        new_profit = (customers * 1.10) * frequency * avg_spend * net_margin * multiplier
        lever_detail = (
            f"Adding {customers * improvement:,.0f} customers "
            f"({customers:,.0f} → {customers * 1.10:,.0f})"
        )
    elif bottleneck == 'Frequency':
        new_profit = customers * (frequency * 1.10) * avg_spend * net_margin * multiplier
        lever_detail = (
            f"Frequency {frequency:.1f} → {frequency * 1.10:.2f} visits/period"
        )
    elif bottleneck == 'Transaction Value':
        new_profit = customers * frequency * (avg_spend * 1.10) * net_margin * multiplier
        lever_detail = (
            f"Avg spend ${avg_spend:.2f} → ${avg_spend * 1.10:.2f}/visit"
        )
    else:  # Margin
        new_margin = (data.get('net_profit', 4) * 1.10) / 100
        new_profit = customers * frequency * avg_spend * new_margin * multiplier
        lever_detail = (
            f"Net margin {data.get('net_profit', 4):.1f}% → "
            f"{data.get('net_profit', 4) * 1.10:.2f}%"
        )

    profit_gain = new_profit - base_profit
    pct_gain    = ((new_profit / base_profit) - 1) * 100 if base_profit else 0

    return (
        f"💡 *Impact of a 10% improvement in {bottleneck}*\n"
        f"{lever_detail}\n"
        f"Annual profit: ${base_profit:,.0f} → ${new_profit:,.0f} "
        f"(+${profit_gain:,.0f} / +{pct_gain:.1f}%)"
    )


def build_lever_score_bar(scores: dict) -> str:
    """Build a simple text progress-bar representation of lever scores."""
    lines = []
    for lever, score in scores.items():
        filled = int(score / 10)          # 0-10 blocks
        empty  = 10 - filled
        bar    = "█" * filled + "░" * empty
        lines.append(f"{lever:<18} [{bar}] {score:.0f}/100")
    return "\n".join(lines)


# ====================== CHART GENERATORS ======================

def _save_profit_chart(data: dict, chat_id: int) -> str:
    tf           = data.get('timeframe', 'weekly')
    multiplier   = {'weekly': 52, 'monthly': 12, 'yearly': 1}.get(tf, 52)
    weekly_sales = data.get('customers', 0) * data.get('frequency', 0) * data.get('avg_spend', 0)
    annual_sales = weekly_sales * multiplier

    fig, ax = plt.subplots(figsize=(8, 5))
    categories = ['Revenue', 'COGS', 'Gross Profit', 'Net Profit']
    values = [
        annual_sales,
        annual_sales * (data.get('cogs', 70) / 100),
        annual_sales * (data.get('gross_margin', 30) / 100),
        annual_sales * (data.get('net_profit', 4) / 100),
    ]
    colors = ['#1f77b4', '#d62728', '#2ca02c', '#ff7f0e']
    bars = ax.bar(categories, values, color=colors, edgecolor='white', linewidth=0.8)
    ax.set_title(f'Annual Profit Breakdown  ({tf.capitalize()} data extrapolated)', fontsize=13, fontweight='bold')
    ax.set_ylabel('Dollars ($)', fontsize=11)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x:,.0f}'))
    for bar, val in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() * 0.92,
            f'${val:,.0f}',
            ha='center', va='top', color='white', fontsize=9, fontweight='bold'
        )
    plt.tight_layout()
    path = f"chart_profit_{chat_id}.png"
    plt.savefig(path, dpi=120)
    plt.close()
    return path


def _save_lever_chart(scores: dict, bottleneck: str, chat_id: int) -> str:
    levers = list(scores.keys())
    values = [scores[l] for l in levers]
    colors = ['#d62728' if l == bottleneck else '#2ca02c' for l in levers]

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.barh(levers, values, color=colors, edgecolor='white', linewidth=0.8)
    ax.set_xlim(0, 110)
    ax.set_xlabel('Score (0 – 100)', fontsize=11)
    ax.set_title('Retail DNA — Lever Scores', fontsize=13, fontweight='bold')

    for bar, val in zip(bars, values):
        ax.text(
            val + 1.5,
            bar.get_y() + bar.get_height() / 2,
            f'{val:.0f}',
            va='center', fontsize=10, fontweight='bold'
        )

    # Legend
    legend_handles = [
        mpatches.Patch(color='#d62728', label='Bottleneck lever'),
        mpatches.Patch(color='#2ca02c', label='Other levers'),
    ]
    ax.legend(handles=legend_handles, loc='lower right', fontsize=9)
    ax.axvline(x=70, color='#ff7f0e', linestyle='--', linewidth=1, label='Target (70)')
    ax.text(71, -0.5, 'Target', color='#ff7f0e', fontsize=8)

    plt.tight_layout()
    path = f"chart_levers_{chat_id}.png"
    plt.savefig(path, dpi=120)
    plt.close()
    return path


# ====================== TIMEFRAME COMMANDS ======================

async def set_weekly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['timeframe'] = 'weekly'
    await update.message.reply_text("⏱️ Timeframe set to *Weekly*.\n\nStarting fresh diagnostic…", parse_mode='Markdown')
    return await start_diagnostic(update, context)

async def set_monthly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['timeframe'] = 'monthly'
    await update.message.reply_text("⏱️ Timeframe set to *Monthly*.\n\nStarting fresh diagnostic…", parse_mode='Markdown')
    return await start_diagnostic(update, context)

async def set_yearly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['timeframe'] = 'yearly'
    await update.message.reply_text("⏱️ Timeframe set to *Yearly*.\n\nStarting fresh diagnostic…", parse_mode='Markdown')
    return await start_diagnostic(update, context)

# ====================== MAIN DIAGNOSTIC FLOW ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Welcome to *Retail DNA Bot*!\n\n"
        "I'll help you identify which profit lever to pull for maximum impact.\n\n"
        "Use /week, /month, or /year to set your timeframe, or just tell me now:\n"
        "What is the *timeframe* of your data? (weekly / monthly / yearly)",
        parse_mode='Markdown'
    )
    return TIMEFRAME

async def start_diagnostic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tf = context.user_data.get('timeframe', 'weekly')
    await update.message.reply_text(
        f"Starting *{tf.capitalize()}* diagnostic.\n\n"
        f"How many *unique customers* visited in that period?",
        parse_mode='Markdown'
    )
    return CUSTOMERS

async def timeframe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tf = update.message.text.lower().strip()
    if tf.startswith('month'):
        context.user_data['timeframe'] = 'monthly'
    elif tf.startswith('year'):
        context.user_data['timeframe'] = 'yearly'
    elif tf.startswith('week'):
        context.user_data['timeframe'] = 'weekly'
    else:
        await update.message.reply_text("Please reply with: *weekly*, *monthly*, or *yearly*", parse_mode='Markdown')
        return TIMEFRAME
    return await start_diagnostic(update, context)

async def customers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['customers'] = int(float(update.message.text.replace(',', '')))
    except ValueError:
        await update.message.reply_text("Please enter a whole number (e.g. 350).")
        return CUSTOMERS
    await update.message.reply_text(
        "Average *visits per customer* in that period?\n_(e.g. 1.5 for weekly, 4 for monthly)_",
        parse_mode='Markdown'
    )
    return FREQUENCY

async def frequency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['frequency'] = float(update.message.text)
    except ValueError:
        await update.message.reply_text("Please enter a number (e.g. 2.5).")
        return FREQUENCY
    await update.message.reply_text("Average *spend per visit* ($)?", parse_mode='Markdown')
    return AVG_SPEND

async def avg_spend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['avg_spend'] = float(update.message.text.replace('$', '').replace(',', ''))
    except ValueError:
        await update.message.reply_text("Please enter a dollar amount (e.g. 45.50).")
        return AVG_SPEND
    await update.message.reply_text("Current *Gross Margin %*?\n_(Revenue minus COGS, as a percentage)_", parse_mode='Markdown')
    return GROSS_MARGIN

async def gross_margin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['gross_margin'] = float(update.message.text.replace('%', ''))
    except ValueError:
        await update.message.reply_text("Please enter a percentage (e.g. 32).")
        return GROSS_MARGIN
    await update.message.reply_text("*COGS %*?\n_(Cost of Goods Sold as a % of revenue)_", parse_mode='Markdown')
    return COGS

async def cogs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['cogs'] = float(update.message.text.replace('%', ''))
    except ValueError:
        await update.message.reply_text("Please enter a percentage (e.g. 68).")
        return COGS
    await update.message.reply_text("Approximate *Net Profit %*?\n_(After all costs)_", parse_mode='Markdown')
    return NET_PROFIT

async def net_profit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['net_profit'] = float(update.message.text.replace('%', ''))
    except ValueError:
        await update.message.reply_text("Please enter a percentage (e.g. 5).")
        return NET_PROFIT
    await update.message.reply_text(
        "What is your *biggest challenge* right now?\n"
        "_(e.g. not enough customers, low repeat visits, thin margins…)_",
        parse_mode='Markdown'
    )
    return CHALLENGES

async def challenges(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['challenges'] = update.message.text

    # --- Calculate lever scores and identify bottleneck ---
    scores      = calculate_lever_scores(context.user_data)
    bottleneck  = identify_bottleneck(scores)
    context.user_data['lever_scores'] = scores
    context.user_data['bottleneck']   = bottleneck

    # --- Ask targeted diagnostic questions for the weakest lever ---
    diag_q = get_diagnostic_questions(bottleneck)
    await update.message.reply_text(
        f"✅ *Basic DNA collected!*\n\n"
        f"Your weakest lever appears to be *{bottleneck}* — let's dig deeper.\n\n"
        + diag_q,
        parse_mode='Markdown'
    )
    return DIAGNOSTIC

async def diagnostic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['diagnostic_answers'] = update.message.text
    await update.message.reply_text(
        "📁 Upload your sales data / P&L (Excel or CSV) for deeper analysis + charts, "
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
            await update.message.reply_text(f"✅ File loaded! ({len(df)} rows)")
        except Exception as e:
            await update.message.reply_text(f"❌ Error reading file: {str(e)}")
    await generate_analysis(update, context)
    return ConversationHandler.END

async def skip_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.lower().strip() == 'skip':
        await generate_analysis(update, context)
        return ConversationHandler.END
    await update.message.reply_text("Type `skip` to continue without a file, or attach an Excel/CSV.", parse_mode='Markdown')
    return UPLOAD

# ====================== ANALYSIS OUTPUT ======================

async def generate_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data        = context.user_data
    tf          = data.get('timeframe', 'weekly')
    multiplier  = {'weekly': 52, 'monthly': 12, 'yearly': 1}.get(tf, 52)

    customers_n = data.get('customers', 0)
    freq        = data.get('frequency', 0)
    spend       = data.get('avg_spend', 0)
    gm          = data.get('gross_margin', 0)
    cogs_pct    = data.get('cogs', 0)
    np_pct      = data.get('net_profit', 0)

    period_sales = customers_n * freq * spend
    annual_sales = period_sales * multiplier
    annual_profit = annual_sales * (np_pct / 100)

    scores     = data.get('lever_scores') or calculate_lever_scores(data)
    bottleneck = data.get('bottleneck')   or identify_bottleneck(scores)

    chat_id = update.message.chat_id

    # --- Chart 1: Profit Breakdown ---
    try:
        profit_chart = _save_profit_chart(data, chat_id)
        await update.message.reply_photo(
            open(profit_chart, 'rb'),
            caption="📊 Chart 1 of 2 — Annual Profit Breakdown"
        )
    except Exception as e:
        logging.warning(f"Profit chart failed: {e}")

    # --- Chart 2: Lever Scores ---
    try:
        lever_chart = _save_lever_chart(scores, bottleneck, chat_id)
        await update.message.reply_photo(
            open(lever_chart, 'rb'),
            caption="📊 Chart 2 of 2 — Retail DNA Lever Scores (red = bottleneck)"
        )
    except Exception as e:
        logging.warning(f"Lever chart failed: {e}")

    # --- Lever score text bars ---
    score_bars = build_lever_score_bar(scores)

    # --- Bottleneck explanation ---
    bottleneck_explanations = {
        'Customer Base':     "You don't have enough customers flowing through the door. Every other lever is limited by this ceiling.",
        'Frequency':         "Your existing customers aren't coming back often enough. Loyalty and repeat-visit strategies will move the needle fastest.",
        'Transaction Value': "Customers are visiting but spending too little per trip. Basket-building tactics will unlock significant revenue.",
        'Margin':            "Your cost structure is eroding profit. Even small improvements to COGS or CODB will have an outsized impact on the bottom line.",
    }
    bottleneck_explanation = bottleneck_explanations.get(bottleneck, "")

    # --- Recommendations ---
    recommendations = get_lever_recommendations(bottleneck, data)

    # --- Impact calculation ---
    impact = calculate_profit_impact(data, scores, bottleneck)

    # --- Six key profit levers summary ---
    six_levers = (
        "🔑 *Six Key Profit Levers*\n"
        "1. Customer Acquisition — grow the base\n"
        "2. COGS Reduction — negotiate & rationalise\n"
        "3. Expense Reduction — cut CODB\n"
        "4. Frequency Improvement — loyalty & theatre\n"
        "5. Basket Size — cross-sell & upsell\n"
        "6. Trade-Up / Premiumisation — shift the mix"
    )

    # --- Main analysis message ---
    analysis = (
        f"🔍 *Retail DNA Analysis — {tf.capitalize()} View*\n"
        f"{'─' * 32}\n\n"
        f"*📈 Financial Snapshot*\n"
        f"Period revenue:  ${period_sales:,.0f}\n"
        f"Annual revenue:  ${annual_sales:,.0f}\n"
        f"Gross Margin:    {gm:.1f}%\n"
        f"COGS:            {cogs_pct:.1f}%\n"
        f"Net Profit:      {np_pct:.1f}%  (${annual_profit:,.0f}/yr)\n\n"
        f"*🧬 Lever Scores*\n"
        f"```\n{score_bars}\n```\n\n"
        f"*🚨 Bottleneck: {bottleneck}* (score: {scores[bottleneck]:.0f}/100)\n"
        f"{bottleneck_explanation}\n\n"
        f"{impact}\n\n"
        f"{recommendations}\n\n"
        f"{'─' * 32}\n"
        f"{six_levers}\n\n"
        f"_Use /week, /month, or /year to run a new analysis._"
    )
    await update.message.reply_text(analysis, parse_mode='Markdown')

# ====================== CANCEL ======================

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Diagnostic cancelled. Type /start to begin again.")
    return ConversationHandler.END

# ====================== BOT SETUP ======================

def main():
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    app   = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            TIMEFRAME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, timeframe)],
            CUSTOMERS:  [MessageHandler(filters.TEXT & ~filters.COMMAND, customers)],
            FREQUENCY:  [MessageHandler(filters.TEXT & ~filters.COMMAND, frequency)],
            AVG_SPEND:  [MessageHandler(filters.TEXT & ~filters.COMMAND, avg_spend)],
            GROSS_MARGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, gross_margin)],
            COGS:       [MessageHandler(filters.TEXT & ~filters.COMMAND, cogs)],
            NET_PROFIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, net_profit)],
            CHALLENGES: [MessageHandler(filters.TEXT & ~filters.COMMAND, challenges)],
            DIAGNOSTIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, diagnostic)],
            UPLOAD: [
                MessageHandler(filters.Document.ALL, handle_upload),
                MessageHandler(filters.TEXT & ~filters.COMMAND, skip_upload),
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    app.add_handler(CommandHandler('week',  set_weekly))
    app.add_handler(CommandHandler('month', set_monthly))
    app.add_handler(CommandHandler('year',  set_yearly))
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler(
        'help',
        lambda u, c: u.message.reply_text(
            "📖 *Retail DNA Bot — Commands*\n\n"
            "/start — begin a new diagnostic\n"
            "/week  — set timeframe to weekly\n"
            "/month — set timeframe to monthly\n"
            "/year  — set timeframe to yearly\n"
            "/cancel — cancel current session",
            parse_mode='Markdown'
        )
    ))

    print("🤖 Retail DNA Bot is running…")
    app.run_polling()

if __name__ == '__main__':
    main()

