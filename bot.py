from telegram import Update
from telegram.ext import Updater, CommandHandler
from config import API_TOKEN
from handlers.start_handler import start

def main():
    # Initialize the Updater and Dispatcher
    updater = Updater(API_TOKEN)
    dispatcher = updater.dispatcher

    # Register the start command handler
    dispatcher.add_handler(CommandHandler("start", start))

    # Start the bot
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
