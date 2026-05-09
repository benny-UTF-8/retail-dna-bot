import os
import logging
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# States
TIMEFRAME, CUSTOMERS, FREQUENCY, AVG_SPEND, GROSS_MARGIN, COGS, NET_PROFIT, CHALLENGES, UPLOAD = range(9)

# ====================== TIMEFRAME COMMANDS ======================
async def set_weekly(update: Update, context: ContextTypes.DEFAULT_TYPE):
 context.user_data['timeframe'] = 'weekly'
 await update.message.reply_text("⏱️ Timeframe set to **Weekly**.\n\nStarting fresh diagnostic...")
 return await start_diagnostic(update, context)

async def set_monthly(update: Update, context: ContextTypes.DEFAULT_TYPE):
 context.user_data['timeframe'] = 'monthly'
 await update.message.reply_text("⏱️ Timeframe set to **Monthly**.\n\nStarting fresh diagnostic...")
 return await start_diagnostic(update, context)

async def set_yearly(update: Update, context: ContextTypes.DEFAULT_TYPE):
 context.user_data['timeframe'] = 'yearly'
 await update.message.reply_text("⏱️ Timeframe set to **Yearly**.\n\nStarting fresh diagnostic...")
 return await start_diagnostic(update, context)

# ====================== MAIN DIAGNOSTIC ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
 context.user_data.clear()
 await update.message.reply_text(
 "👋 Welcome to **Retail DNA Bot**!\n\n"
 "Use /week, /month, or /year to set timeframe anytime.\n\n"
 "What is the **timeframe** of your data? (weekly / monthly / yearly)"
 )
 return TIMEFRAME

async def start_diagnostic(update: Update, context: ContextTypes.DEFAULT_TYPE):
 """Helper to restart diagnostic with preset timeframe"""
 tf = context.user_data.get('timeframe', 'weekly')
 await update.message.reply_text(f"Starting **{tf.capitalize()}** diagnostic.\n\n"
 f"How many **unique customers** in that period?")
 return CUSTOMERS

async def timeframe(update: Update, context: ContextTypes.DEFAULT_TYPE):
 tf = update.message.text.lower()
 if tf in ['weekly', 'month', 'monthly', 'year', 'yearly']:
 if tf.startswith('month'): context.user_data['timeframe'] = 'monthly'
 elif tf.startswith('year'): context.user_data['timeframe'] = 'yearly'
 else: context.user_data['timeframe'] = 'weekly'
 else:
 await update.message.reply_text("Please use: weekly, monthly, or yearly")
 return TIMEFRAME
 
 return await start_diagnostic(update, context)

async def customers(update: Update, context: ContextTypes.DEFAULT_TYPE):
 context.user_data['customers'] = int(update.message.text)
 await update.message.reply_text("Average **visits per customer** in that period?")
 return FREQUENCY

async def frequency(update: Update, context: ContextTypes.DEFAULT_TYPE):
 context.user_data['frequency'] = float(update.message.text)
 await update.message.reply_text("Average **spend per visit** ($)?")
 return AVG_SPEND

async def avg_spend(update: Update, context: ContextTypes.DEFAULT_TYPE):
 context.user_data['avg_spend'] = float(update.message.text)
 await update.message.reply_text("Current **Gross Margin %**?")
 return GROSS_MARGIN

async def gross_margin(update: Update, context: ContextTypes.DEFAULT_TYPE):
 context.user_data['gross_margin'] = float(update.message.text)
 await update.message.reply_text("**COGS %**?")
 return COGS

async def cogs(update: Update, context: ContextTypes.DEFAULT_TYPE):
 context.user_data['cogs'] = float(update.message.text)
 await update.message.reply_text("Approximate **Net Profit %**?")
 return NET_PROFIT

async def net_profit(update: Update, context: ContextTypes.DEFAULT_TYPE):
 context.user_data['net_profit'] = float(update.message.text)
 await update.message.reply_text("Biggest challenge right now?")
 return CHALLENGES

async def challenges(update: Update, context: ContextTypes.DEFAULT_TYPE):
 context.user_data['challenges'] = update.message.text
 await update.message.reply_text(
 "✅ Basic DNA collected!\n\n"
 "Upload your sales data / P&L (Excel or CSV) for deeper analysis + charts, or type `skip`"
 )
 return UPLOAD

# File handling and analysis
async def handle_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
 if update.message.document:
 file = await update.message.document.get_file()
 file_path = f"data_{update.message.chat_id}.xlsx"
 await file.download_to_drive(file_path)
 try:
 if file_path.endswith('.xlsx'):
 df = pd.read_excel(file_path)
 else:
 df = pd.read_csv(file_path)
 context.user_data['df'] = df
 await update.message.reply_text(f"✅ File loaded! ({len(df)} rows)")
 except Exception as e:
 await update.message.reply_text(f"❌ Error: {str(e)}")
 await generate_analysis(update, context)
 return ConversationHandler.END

async def skip_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
 if update.message.text.lower() == 'skip':
 await generate_analysis(update, context)
 return ConversationHandler.END
 return UPLOAD

async def generate_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
 data = context.user_data
 tf = data.get('timeframe', 'weekly')
 multiplier = {'weekly': 52, 'monthly': 12, 'yearly': 1}[tf]
 weekly_sales = data.get('customers', 0) * data.get('frequency', 0) * data.get('avg_spend', 0)
 annual_sales = weekly_sales * 52 # Always show annual for consistency
 
 # Generate Chart
 try:
 fig, ax = plt.subplots(figsize=(8, 5))
 categories = ['Sales', 'COGS', 'Gross Profit', 'Net Profit']
 values = [
 annual_sales,
 annual_sales * (data.get('cogs', 70) / 100),
 annual_sales * (data.get('gross_margin', 30) / 100),
 annual_sales * (data.get('net_profit', 4) / 100)
 ]
 ax.bar(categories, values, color=['#1f77b4', '#d62728', '#2ca02c', '#ff7f0e'])
 ax.set_title(f'Annual Profit Breakdown ({tf.capitalize()} data)')
 ax.set_ylabel('Dollars ($)')
 for bar in ax.patches:
 height = bar.get_height()
 ax.text(bar.get_x() + bar.get_width()/2., height * 0.9, f'${height:,.0f}', ha='center')
 plt.tight_layout()
 chart_path = f"chart_{update.message.chat_id}.png"
 plt.savefig(chart_path)
 plt.close()
 await update.message.reply_photo(open(chart_path, 'rb'), caption="📊 Annual Profit Breakdown")
 except:
 pass
 
 # Text Analysis
 analysis = f"""
🔍 **Retail DNA Analysis — {tf.capitalize()} View**
**Sales**: ${weekly_sales:,.0f} /week → **${annual_sales:,.0f}** /year
**Gross Margin**: {data.get('gross_margin')}% 
**COGS**: {data.get('cogs')}% 
**Net Profit**: {data.get('net_profit')}% 
**Top Priority**: {'Increase Frequency' if data.get('frequency', 2) < 2 else 'Improve Gross Margin' if data.get('gross_margin', 30) < 28 else 'Grow Basket Size'}
Use /week, /month, or /year to run a new analysis with different timeframe.
"""
 await update.message.reply_text(analysis)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
 await update.message.reply_text("❌ Cancelled.")
 return ConversationHandler.END

def main():
 TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
 app = Application.builder().token(TOKEN).build()
 conv_handler = ConversationHandler(
 entry_points=[CommandHandler('start', start)],
 states={
 TIMEFRAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, timeframe)],
 CUSTOMERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, customers)],
 FREQUENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, frequency)],
 AVG_SPEND: [MessageHandler(filters.TEXT & ~filters.COMMAND, avg_spend)],
 GROSS_MARGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, gross_margin)],
 COGS: [MessageHandler(filters.TEXT & ~filters.COMMAND, cogs)],
 NET_PROFIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, net_profit)],
 CHALLENGES: [MessageHandler(filters.TEXT & ~filters.COMMAND, challenges)],
 UPLOAD: [
 MessageHandler(filters.Document.ALL, handle_upload),
 MessageHandler(filters.TEXT & ~filters.COMMAND, skip_upload)
 ],
 },
 fallbacks=[CommandHandler('cancel', cancel)],
 )
 
 # Register timeframe shortcut commands
 app.add_handler(CommandHandler('week', set_weekly))
 app.add_handler(CommandHandler('month', set_monthly))
 app.add_handler(CommandHandler('year', set_yearly))
 app.add_handler(conv_handler)
 app.add_handler(CommandHandler('help', lambda u,c: u.message.reply_text("Commands: /start /week /month /year /cancel")))
 
 print("🤖 Retail DNA Bot with /week /month /year commands is running...")
 app.run_polling()

if __name__ == '__main__':
 main()
