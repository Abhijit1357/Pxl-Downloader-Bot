from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from config import BOT_TOKEN  # <-- config se token le rahe hain

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Bot Online\n\nCommands:\n/start\n/help"
    )

# /help command
async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚡ Commands:\n/start\n/help"
    )

# Build app
app = ApplicationBuilder().token(BOT_TOKEN).build()

# Add handlers
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help))

print("Bot Running...")

app.run_polling()
