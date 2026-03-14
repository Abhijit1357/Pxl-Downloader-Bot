from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from config import BOT_TOKEN

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    start_text = """
🎬 *Welcome to Pxl Downloader Bot!* 🎬

I can help you download your favourite Anime (and soon Movies!)  
directly to your Telegram channel.  

⚡ *Commands:*
• /start - Show this welcome message
• /help  - Show command list
• /anime <link> - Download Anime episode (multi-quality, MKV)

💡 _Tip: Send me the link from RareAnimes and relax!_
"""
    await update.message.reply_markdown(start_text)

# /help command
async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
⚡ *Available Commands:*
• /start - Welcome message
• /help  - This help message
• /anime <link> - Download Anime in MKV format
"""
    await update.message.reply_markdown(help_text)

# Build app
app = ApplicationBuilder().token(BOT_TOKEN).build()

# Add handlers
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help))

print("Bot Running...")

app.run_polling()
