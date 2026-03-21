import asyncio
import logging
import os
from pyrogram import Client
from bot.config import Config
from bot.handlers import callbacks, start
from bot.handlers import queue_handler
from bot.handlers import website as website_handler
from bot.handlers import youtube as youtube_handler
from bot.services.converter import convert_to_mkv, get_video_quality
from bot.services.downloader import download_direct
from bot.services.queue_manager import Task, TaskSource, TaskStatus, queue_manager
from bot.services.uploader import upload_to_telegram
from bot.services.ytdl import download_video as ytdl_download
from bot.utils.cleanup import cleanup_task_files, ensure_download_dir
from bot.utils.progress import (
    ProgressTracker,
    build_progress_message,
    task_control_buttons,
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
# Suppress noisy loggers
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)
def create_app() -> Client:
    app = Client(
        name="anime_bot",
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        bot_token=Config.BOT_TOKEN,
        workdir="./sessions",
    )
    return app
def register_handlers(app: Client):
    """Register all handlers. Order matters for text message routing."""
    start.register(app)
    website_handler.register(app)
    youtube_handler.register(app)
    queue_handler.register(app)
    # callbacks.register must come LAST so it acts as a fallback text router
    callbacks.register(app)
async def process_task(task: Task):
    """Main pipeline: download → convert → rename → upload → cleanup."""
    from bot.main import bot_app
    if task.status == TaskStatus.CANCELLED:
        return
    tracker = ProgressTracker(min_interval=3.0)
    async def _update_message(stage: str, pct: float, speed: str = "", eta: str = ""):
        task.progress = pct
        task.speed = speed
        task.eta = eta
        if not tracker.should_update(pct):
            return
        text = build_progress_message(
            task_id=task.task_id,
            stage=stage,
            percentage=pct,
            speed=speed or None,
            eta=eta or None,
            filename=task.display_name,
        )
        try:
            await bot_app.edit_message_text(
                chat_id=task.chat_id,
                message_id=task.message_id,
                text=text,
                reply_markup=task_control_buttons(task.task_id),
            )
        except Exception:
            pass
    task_dir = ensure_download_dir(Config.DOWNLOAD_DIR, task.task_id)
    # ── STEP 1: Download ──
    task.status = TaskStatus.DOWNLOADING
    await _update_message("Downloading…", 0)
    async def download_progress(pct, speed, eta):
        if task.status == TaskStatus.CANCELLED:
            raise asyncio.CancelledError("Task cancelled")
        await _update_message("Downloading…", pct, speed, eta)
    raw_file = os.path.join(task_dir, "raw_video")
    downloaded_path = None
    try:
        if task.source == TaskSource.YOUTUBE:
            # yt-dlp handles YouTube downloads
            raw_file_template = os.path.join(task_dir, "raw_video.%(ext)s")
            downloaded_path = await ytdl_download(
                task.url, raw_file_template, progress_callback=download_progress
            )
        else:
            # For website sources, try yt-dlp first (handles many sites),
            # then fall back to direct download
            raw_file_template = os.path.join(task_dir, "raw_video.%(ext)s")
            downloaded_path = await ytdl_download(
                task.url, raw_file_template, progress_callback=download_progress
            )
            if not downloaded_path:
                raw_file_direct = os.path.join(task_dir, "raw_video.mp4")
                downloaded_path = await download_direct(
                    task.url, raw_file_direct, progress_callback=download_progress
                )
    except asyncio.CancelledError:
        task.status = TaskStatus.CANCELLED
        cleanup_task_files(task.task_id, Config.DOWNLOAD_DIR)
        return
    if not downloaded_path or task.status == TaskStatus.CANCELLED:
        task.status = TaskStatus.FAILED
        task.error = "Download failed"
        await _fail_message(task)
        cleanup_task_files(task.task_id, Config.DOWNLOAD_DIR)
        return
    # Find the actual downloaded file (yt-dlp may change extension)
    actual_file = _find_downloaded_file(task_dir)
    if actual_file:
        downloaded_path = actual_file
    task.downloaded_file = downloaded_path
    await _update_message("Downloading…", 100)
    # ── STEP 2: Detect quality ──
    task.quality = await get_video_quality(downloaded_path)
    # ── STEP 3: Convert to MKV ──
    task.status = TaskStatus.CONVERTING
    tracker = ProgressTracker(min_interval=3.0)
    await _update_message("Converting to MKV…", 0)
    output_filename = task.output_filename
    output_path = os.path.join(task_dir, output_filename)
    async def convert_progress(pct, speed, eta):
        if task.status == TaskStatus.CANCELLED:
            raise asyncio.CancelledError("Task cancelled")
        await _update_message("Converting to MKV…", pct)
    try:
        converted_path = await convert_to_mkv(
            downloaded_path, output_path, progress_callback=convert_progress
        )
    except asyncio.CancelledError:
        task.status = TaskStatus.CANCELLED
        cleanup_task_files(task.task_id, Config.DOWNLOAD_DIR)
        return
    if not converted_path:
        task.status = TaskStatus.FAILED
        task.error = "Conversion failed"
        await _fail_message(task)
        cleanup_task_files(task.task_id, Config.DOWNLOAD_DIR)
        return
    task.converted_file = converted_path
    await _update_message("Converting to MKV…", 100)
    # ── STEP 4: Upload ──
    task.status = TaskStatus.UPLOADING
    tracker = ProgressTracker(min_interval=5.0)
    await _update_message("Uploading…", 0)
    try:
        progress_msg = await bot_app.get_messages(task.chat_id, task.message_id)
    except Exception:
        progress_msg = None
    caption = (
        f"📺 **{task.display_name}**\n"
        f"🌐 Source: {task.source.value}\n"
        f"📐 Quality: {task.quality}\n"
        f"📁 `{output_filename}`"
    )
    upload_success = await upload_to_telegram(
        bot_app, converted_path, caption, progress_msg
    )
    if not upload_success:
        task.status = TaskStatus.FAILED
        task.error = "Upload failed"
        await _fail_message(task)
        cleanup_task_files(task.task_id, Config.DOWNLOAD_DIR)
        return
    # ── STEP 5: Complete ──
    task.status = TaskStatus.COMPLETED
    task.progress = 100
    try:
        dest = Config.UPLOAD_CHANNEL
        if not dest.startswith("@") and not dest.lstrip("-").isdigit():
            dest = f"@{dest}"
        await bot_app.edit_message_text(
            chat_id=task.chat_id,
            message_id=task.message_id,
            text=(
                f"✅ **Completed!**\n\n"
                f"📺 {task.display_name}\n"
                f"📐 Quality: {task.quality}\n"
                f"📁 `{output_filename}`\n\n"
                f"📤 Uploaded to: {dest}"
            ),
            reply_markup=task_control_buttons(task.task_id),
        )
    except Exception:
        pass
    # ── STEP 6: Cleanup ──
    cleanup_task_files(task.task_id, Config.DOWNLOAD_DIR)
    logger.info(f"Task {task.task_id} completed: {output_filename}")
async def _fail_message(task: Task):
    """Send a failure message to the user."""
    from bot.main import bot_app
    try:
        from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        await bot_app.edit_message_text(
            chat_id=task.chat_id,
            message_id=task.message_id,
            text=(
                f"❌ **Task Failed**\n\n"
                f"📺 {task.display_name}\n"
                f"⚠️ Error: {task.error}\n"
                f"🆔 Task: `{task.task_id}`"
            ),
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔄 Retry", callback_data=f"retry_{task.task_id}"
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "🔙 Main Menu", callback_data="main_menu"
                        ),
                    ],
                ]
            ),
        )
    except Exception:
        pass
def _find_downloaded_file(directory: str) -> str:
    """Find the actual downloaded file in the task directory."""
    for f in os.listdir(directory):
        full = os.path.join(directory, f)
        if os.path.isfile(full) and not f.endswith(".part"):
            return full
    return ""
# Global bot instance
bot_app: Client = None  # type: ignore
async def run():
    global bot_app
    os.makedirs("./sessions", exist_ok=True)
    os.makedirs(Config.DOWNLOAD_DIR, exist_ok=True)
    bot_app = create_app()
    register_handlers(bot_app)
    # Set up queue processor
    queue_manager.set_processor(process_task)
    logger.info("Starting bot...")
    await bot_app.start()
    logger.info("Bot started! Waiting for messages...")
    # Start queue workers
    await queue_manager.start_workers(num_workers=Config.MAX_CONCURRENT_TASKS)
    # Keep running
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await queue_manager.stop_workers()
        await bot_app.stop()
        logger.info("Bot stopped.")
