from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
MAIN_MENU_MARKUP = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("🌐 Anime from Website", callback_data="menu_website")],
        [InlineKeyboardButton("🎬 Anime from YouTube", callback_data="menu_youtube")],
        [InlineKeyboardButton("📋 My Queue / Status", callback_data="menu_queue")],
    ]
)
WELCOME_TEXT = (
    "🎌 **Anime Download Bot**\n\n"
    "Choose an option below to get started:\n\n"
    "🌐 **Website** — Search & download from rareanimes.app\n"
    "🎬 **YouTube** — Search & download from YouTube\n"
    "📋 **Queue** — Check your active downloads"
)
def register(app: Client):
    @app.on_message(filters.command("start") & filters.private)
    async def start_command(client: Client, message: Message):
        await message.reply_text(
            WELCOME_TEXT,
            reply_markup=MAIN_MENU_MARKUP,
        )
    @app.on_callback_query(filters.regex(r"^main_menu$"))
    async def back_to_main_menu(client: Client, callback: CallbackQuery):
        await callback.message.edit_text(
            WELCOME_TEXT,
            reply_markup=MAIN_MENU_MARKUP,
        )
        await callback.answer()
