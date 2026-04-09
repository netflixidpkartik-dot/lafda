import asyncio
import random
import string
import re
import json
from datetime import datetime, timedelta
from telethon import TelegramClient, functions, types
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError,
    FloodWaitError,
    UpdateAppToLoginError,
    PhoneNumberInvalidError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    SessionExpiredError,
    PasswordHashInvalidError
)
from pyrogram import Client as PyroClient, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from pyrogram.errors import UserNotParticipant, PeerIdInvalid, ChatWriteForbidden, FloodWait, MessageNotModified
from pyrogram.enums import ParseMode, ChatType
import config
from database import EnhancedDatabaseManager
from utils import validate_phone_number, generate_progress_bar, format_duration
import os
import logging
from cryptography.fernet import Fernet

# Logging setup
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/TecxoAds.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

print("Tecxo Bot Free Version Started. 🚀")

# Initialize encryption key with persistence
ENCRYPTION_KEY = getattr(config, 'ENCRYPTION_KEY', None)
KEY_FILE = 'encryption.key'
if not ENCRYPTION_KEY:
    logger.warning("No ENCRYPTION_KEY in config. Loading or generating from file.")
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, 'r') as f:
            ENCRYPTION_KEY = f.read().strip()
    else:
        ENCRYPTION_KEY = Fernet.generate_key().decode()
        with open(KEY_FILE, 'w') as f:
            f.write(ENCRYPTION_KEY)
        logger.info("Generated and saved new encryption key to encryption.key")
else:
    with open(KEY_FILE, 'w') as f:
        f.write(ENCRYPTION_KEY)
    logger.info("Using ENCRYPTION_KEY from config and saved to file.")

cipher_suite = Fernet(ENCRYPTION_KEY.encode())

# Initialize database
try:
    db = EnhancedDatabaseManager()
except Exception as e:
    logger.error(f"Failed to initialize database: {e}. Exiting.")
    print("Bot failed to start due to database error. Check logs/TecxoAds.log for details.")
    exit(1)

# Admin check
ADMIN_IDS = [config.ADMIN_ID]
ALLOWED_BD_IDS = ADMIN_IDS

def is_owner(uid):
    return uid in ALLOWED_BD_IDS

# Inline keyboard helper
def kb(rows):
    if not isinstance(rows, list) or not all(isinstance(row, list) for row in rows):
        logger.error("Invalid rows format for InlineKeyboardMarkup")
        raise ValueError("Rows must be a list of lists")
    return InlineKeyboardMarkup(rows)

# Initialize Pyrogram clients
pyro = PyroClient("TecxoAds", api_id=config.API_ID, api_hash=config.API_HASH, bot_token=config.BOT_TOKEN)
logger_client = PyroClient("logger_bot", api_id=config.API_ID, api_hash=config.API_HASH, bot_token=config.LOGGER_BOT_TOKEN)

# In-memory storage for broadcast tasks
user_tasks = {}

async def send_dm_log(user_id, log_message):
    if not db.get_logger_status(user_id):
        logger.info(f"User {user_id} has not started logger bot. Skipping DM log.")
        return
    try:
        await logger_client.resolve_peer(user_id)
        await logger_client.send_message(user_id, log_message, parse_mode=ParseMode.HTML)
        logger.info(f"DM log sent to {user_id}: {log_message[:50]}...")
    except PeerIdInvalid:
        logger.error(f"DM log failed for {user_id}: Peer not found. User must start logger bot.")
        db.log_logger_failure(user_id, "PeerIdInvalid: User must start logger bot")
        try:
            await pyro.send_message(
                user_id,
                "<b>⚠️ Logger bot not started!</b>\n\n"
                f"Please start @{config.LOGGER_BOT_USERNAME} to receive broadcast logs. 🌟",
                parse_mode=ParseMode.HTML,
                reply_markup=kb([[InlineKeyboardButton("Start Logger Bot 📩", url=f"https://t.me/{config.LOGGER_BOT_USERNAME.lstrip('@')}")]])
            )
        except Exception as e:
            logger.error(f"Failed to notify user {user_id} to start logger bot: {e}")
    except Exception as e:
        logger.error(f"DM log failed for {user_id}: {e} - Message: {log_message[:50]}...")
        db.log_logger_failure(user_id, str(e))

@logger_client.on_message(filters.command(["start"]))
async def logger_start(client, m):
    uid = m.from_user.id
    username = m.from_user.username or "Unknown"
    first_name = m.from_user.first_name or "User"
    
    db.create_user(uid, username, first_name)
    if is_owner(uid):
        db.db.users.update_one({"user_id": uid}, {"$set": {"accounts_limit": "unlimited"}})
    db.set_logger_status(uid, is_active=True)
    await m.reply(
        f"<b>╰_╯Welcome to Tecxo Logger Bot! </b>\n\n"
        f"Logs for your ad broadcasts will be sent here.\n"
        f"Start the main bot (@{config.BOT_USERNAME.lstrip('@')}) to begin broadcasting! 🌟",
        parse_mode=ParseMode.HTML
    )
    logger.info(f"Logger bot started by user {uid}")

async def is_joined(client, uid, chat_id):
    max_retries = 3
    retry_delay = 2
    for attempt in range(max_retries):
        try:
            logger.info(f"Checking membership for user {uid} in chat_id {chat_id} (Attempt {attempt + 1})")
            await client.get_chat_member(chat_id, uid)
            logger.info(f"User {uid} is a member of chat_id {chat_id}")
            return True
        except UserNotParticipant:
            logger.info(f"User {uid} is not a member of chat_id {chat_id}")
            return False
        except Exception as e:
            logger.error(f"Attempt {attempt + 1}: Failed to check join status for {uid} in chat_id {chat_id}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
                continue
            logger.error(f"All retries failed for user {uid} in chat_id {chat_id}: {e}")
            return False
    return False

async def is_joined_all(client, uid):
    channel_joined = await is_joined(client, uid, config.MUST_JOIN_CHANNEL_ID)
    await asyncio.sleep(0.5)
    group_joined = await is_joined(client, uid, config.MUSTJOIN_GROUP_ID)
    logger.info(f"User {uid} - Channel ({config.MUST_JOIN_CHANNEL_ID}) joined: {channel_joined}, Group ({config.MUSTJOIN_GROUP_ID}) joined: {group_joined}")
    if not channel_joined:
        logger.info(f"User {uid} has not joined channel {config.MUST_JOIN_CHANNEL_ID}")
    if not group_joined:
        logger.info(f"User {uid} has not joined group {config.MUSTJOIN_GROUP_ID}")
    return channel_joined and group_joined

async def validate_session(session_str):
    try:
        tg_client = TelegramClient(StringSession(session_str), config.API_ID, config.API_HASH)
        await tg_client.connect()
        is_valid = await tg_client.is_user_authorized()
        await tg_client.disconnect()
        return is_valid
    except Exception as e:
        logger.error(f"Session validation failed: {e}")
        return False

async def stop_broadcast_task(uid):
    state = db.get_broadcast_state(uid)
    running = state.get("running", False)
    if not running:
        logger.info(f"No broadcast running for user {uid}")
        return False

    if uid in user_tasks:
        task = user_tasks[uid]
        try:
            task.cancel()
            await task
            logger.info(f"Cancelled broadcast task for {uid}")
        except asyncio.CancelledError:
            logger.info(f"Broadcast task for {uid} was cancelled successfully")
        except Exception as e:
            logger.error(f"Failed to cancel broadcast task for {uid}: {e}")
        finally:
            del user_tasks[uid]
    
    db.set_broadcast_state(uid, running=False)
    return True

async def run_broadcast(client, uid):
    try:
        sent_count = 0
        failed_count = 0
        cycle_count = 0
        msg = db.get_user_ad_messages(uid)
        msg = msg[0]["message"] if msg else None
        if not msg:
            await client.send_message(uid, "╰_╯Baka! No ad message set! ", parse_mode=ParseMode.HTML)
            return
        delay = db.get_user_ad_delay(uid)
        accounts = db.get_user_accounts(uid)
        target_groups = db.get_target_groups(uid)
        group_ids = [g['group_id'] for g in target_groups] if target_groups else None
        group_cache = {}
        clients = {}
        error_summary = []

        skip_group_ids = [config.MUSTJOIN_GROUP_ID]

        for acc in accounts:
            try:
                session_str = cipher_suite.decrypt(acc['session_string'].encode()).decode()
                if not await validate_session(session_str):
                    db.deactivate_account(acc['_id'])
                    logger.warning(f"Deactivated invalid session for {acc['phone_number']}")
                    continue
                tg_client = TelegramClient(StringSession(session_str), config.API_ID, config.API_HASH)
                await tg_client.start()
                
                cached_groups = []
                async for dialog in tg_client.iter_dialogs(limit=None):
                    if dialog.is_group and (not group_ids or dialog.id in group_ids):
                        if dialog.id in skip_group_ids:
                            logger.info(f"Skipping protected group {dialog.name} ({dialog.id}) for account {acc['phone_number']}")
                            continue
                        cached_groups.append((dialog.id, dialog.name))
                group_cache[acc['_id']] = cached_groups
                
                clients[acc['_id']] = tg_client
            except Exception as e:
                logger.error(f"Failed to start client for {acc['phone_number']}: {e}")
                failed_count += 1
                db.increment_broadcast_stats(uid, False)
                error_summary.append(f"Account {acc['phone_number']}: {str(e)}")
                await send_dm_log(uid, f"<b>╰_╯Failed to start account {acc['phone_number']}:</b> {str(e)}❌")
        
        if not clients:
            await client.send_message(uid, "╰_╯No valid accounts found!", parse_mode=ParseMode.HTML)
            return

        db.set_broadcast_state(uid, running=True)

        try:
            while db.get_broadcast_state(uid).get("running", False):
                for acc in accounts:
                    tg_client = clients.get(acc['_id'])
                    if not tg_client:
                        continue
                    cached_groups = group_cache.get(acc['_id'], [])
                    for gid, group_name in cached_groups:
                        if not db.get_broadcast_state(uid).get("running", False):
                            raise asyncio.CancelledError("Broadcast stopped by user")
                        try:
                            await tg_client.send_message(gid, msg)
                            sent_count += 1
                            db.increment_broadcast_stats(uid, True)
                            await send_dm_log(uid, f"<b>✅ Sent to {group_name} ({gid})</b> using account {acc['phone_number']}")
                        except FloodWaitError as e:
                            logger.warning(f"Flood wait in group {gid}: Wait {e.seconds} seconds")
                            if e.seconds > 300:
                                failed_count += 1
                                db.increment_broadcast_stats(uid, False)
                                error_summary.append(f"Group {gid}: FloodWaitError (capped at {e.seconds}s)")
                                await send_dm_log(uid, f"<b>⚠️ Flood wait in {group_name} ({gid}):</b> Skipped due to long wait ({e.seconds}s)")
                                continue
                            await asyncio.sleep(e.seconds)
                            await tg_client.send_message(gid, msg)
                            sent_count += 1
                            db.increment_broadcast_stats(uid, True)
                            await send_dm_log(uid, f"<b>✅ Sent to {group_name} ({gid}) after wait</b> using account {acc['phone_number']}")
                        except Exception as e:
                            logger.error(f"Failed to send message to group {gid}: {e}")
                            failed_count += 1
                            db.increment_broadcast_stats(uid, False)
                            error_summary.append(f"Group {gid}: {str(e)}")
                            await send_dm_log(uid, f"<b>❌ Failed to send to {group_name} ({gid}):</b> {str(e)}")
                        await asyncio.sleep(random.uniform(5, 6))
                        if not db.get_broadcast_state(uid).get("running", False):
                            raise asyncio.CancelledError("Broadcast stopped by user")
                cycle_count += 1
                db.increment_broadcast_cycle(uid)
                if error_summary:
                    logger.warning(f"Broadcast errors for user {uid}: {len(error_summary)} failures - {', '.join(error_summary[:5])}")
                    await send_dm_log(uid, f"<b>⚠️ Cycle {cycle_count} Errors:</b> {len(error_summary)} issues encountered")
                    error_summary = []
                await asyncio.sleep(delay)
                if not db.get_broadcast_state(uid).get("running", False):
                    raise asyncio.CancelledError("Broadcast stopped by user")
        except asyncio.CancelledError:
            logger.info(f"Broadcast task cancelled for {uid}")
            raise
        finally:
            for tg_client in clients.values():
                try:
                    await tg_client.disconnect()
                except Exception as e:
                    logger.error(f"Failed to disconnect client: {e}")
            db.set_broadcast_state(uid, running=False)
            if uid in user_tasks:
                del user_tasks[uid]
    except asyncio.CancelledError:
        logger.info(f"Broadcast task cancelled for {uid}")
    except Exception as e:
        logger.error(f"Broadcast task failed for {uid}: {e}")
        db.increment_broadcast_stats(uid, False)
        db.set_broadcast_state(uid, running=False)
        if uid in user_tasks:
            del user_tasks[uid]
        await send_dm_log(uid, f"<b>❌ Broadcast task failed:</b> {str(e)}")
        for admin_id in ALLOWED_BD_IDS:
            try:
                await client.resolve_peer(admin_id)
                await client.send_message(
                    admin_id,
                    f"Broadcast task failed for user {uid}: {e}"
                )
                break
            except Exception as admin_e:
                logger.error(f"Failed to notify admin {admin_id}: {admin_e}")

def get_otp_keyboard():
    rows = [
        [InlineKeyboardButton("1", callback_data="otp_1"), InlineKeyboardButton("2", callback_data="otp_2"), InlineKeyboardButton("3", callback_data="otp_3")],
        [InlineKeyboardButton("4", callback_data="otp_4"), InlineKeyboardButton("5", callback_data="otp_5"), InlineKeyboardButton("6", callback_data="otp_6")],
        [InlineKeyboardButton("7", callback_data="otp_7"), InlineKeyboardButton("8", callback_data="otp_8"), InlineKeyboardButton("9", callback_data="otp_9")],
        [InlineKeyboardButton("⌫", callback_data="otp_back"), InlineKeyboardButton("0", callback_data="otp_0"), InlineKeyboardButton("❌", callback_data="otp_cancel")],
        [InlineKeyboardButton("Show Code", url="tg://openmessage?user_id=777000")]
    ]
    return kb(rows)

@pyro.on_callback_query(filters.regex("^otp_"))
async def otp_callback(client, cb):
    uid = cb.from_user.id
    state = db.get_user_state(uid)
    if state != "telethon_wait_otp":
        await cb.answer("╰_╯Invalid state! Please restart with /start.", show_alert=True)
        return

    temp_encrypted = db.get_temp_data(uid)
    if not temp_encrypted:
        await cb.answer("╰_╯Session expired! Please restart.", show_alert=True)
        db.set_user_state(uid, "")
        return

    try:
        temp_json = cipher_suite.decrypt(temp_encrypted.encode()).decode()
        temp_dict = json.loads(temp_json)
        phone = temp_dict["phone"]
        session_str = temp_dict["session_str"]
        phone_code_hash = temp_dict["phone_code_hash"]
        otp = temp_dict.get("otp", "")
    except (json.JSONDecodeError, Fernet.InvalidToken) as e:
        logger.error(f"Invalid temp data for user {uid}: {e}")
        await cb.answer("╰_╯Error: Corrupted session data. Please restart.", show_alert=True)
        db.set_user_state(uid, "")
        db.set_temp_data(uid, None)
        return

    try:
        StringSession(session_str)
    except Exception as e:
        logger.error(f"Invalid session string for user {uid}: {e}")
        await cb.answer("╰_╯Error: Invalid session. Please restart.", show_alert=True)
        db.set_user_state(uid, "")
        db.set_temp_data(uid, None)
        return

    action = cb.data.replace("otp_", "")
    if action.isdigit():
        if len(otp) < 5:
            otp += action
    elif action == "back":
        otp = otp[:-1] if otp else ""
    elif action == "cancel":
        db.set_user_state(uid, "")
        db.set_temp_data(uid, None)
        await cb.message.edit_caption("OTP entry cancelled.", reply_markup=None)
        return

    temp_dict["otp"] = otp
    temp_json = json.dumps(temp_dict)
    temp_encrypted = cipher_suite.encrypt(temp_json.encode()).decode()
    db.set_temp_data(uid, temp_encrypted)

    masked = " ".join("*" for _ in otp) if otp else "_____"
    base_caption = (
        f"Phone: {phone}\n\n"
        f"<blockquote><b>OTP sent!✅</b></blockquote>\n\n"
        f"Enter the OTP using the keypad below\n"
        f"<b>Current:</b> <code>{masked}</code>\n"
        f"<b>Format:</b> <code>12345</code> (no spaces needed)\n"
        f"<i>Valid for:</i>{config.OTP_EXPIRY // 60} minutes"
    )

    await cb.message.edit_caption(
        caption=base_caption,
        parse_mode=ParseMode.HTML,
        reply_markup=get_otp_keyboard()
    )

    if len(otp) == 5:
        await cb.message.edit_caption(base_caption + "\n\n<b>Verifying OTP...</b>", parse_mode=ParseMode.HTML, reply_markup=None)
        max_retries = 3
        retry_delay = 2

        for attempt in range(max_retries):
            tg = TelegramClient(StringSession(session_str), config.API_ID, config.API_HASH)
            try:
                await tg.connect()
                await tg.sign_in(phone, code=otp, phone_code_hash=phone_code_hash)

                session_encrypted = cipher_suite.encrypt(session_str.encode()).decode()
                db.add_user_account(uid, phone, session_encrypted)

                await cb.message.edit_caption(
                    f"<blockquote><b>Account Successfully added!✅</b></blockquote>\n\n"
                    f"Phone: <code>{phone}</code>\n"
                    "╰_╯Your account is ready for broadcasting!",
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb([[InlineKeyboardButton("Dashboard 🚪", callback_data="menu_main")]])
                )
                await send_dm_log(uid, f"<b> Account added successfully:</b> <code>{phone}</code>✅")
                db.set_user_state(uid, "")
                db.set_temp_data(uid, None)
                break
            except SessionPasswordNeededError:
                temp_dict_2fa = {
                    "phone": phone,
                    "session_str": session_str
                }
                temp_json_2fa = json.dumps(temp_dict_2fa)
                temp_encrypted_2fa = cipher_suite.encrypt(temp_json_2fa.encode()).decode()
                db.set_user_state(uid, "telethon_wait_password")
                db.set_temp_data(uid, temp_encrypted_2fa)
                await cb.message.edit_caption(
                    base_caption + "\n\n<blockquote><b>🔐 2FA Detected!</b></blockquote>\n\n"
                    "Please send your Telegram cloud password:",
                    parse_mode=ParseMode.HTML,
                    reply_markup=None
                )
                break
            except PhoneCodeInvalidError:
                if attempt < max_retries - 1:
                    logger.warning(f"Invalid OTP attempt {attempt + 1} for {uid}, retrying...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                await cb.message.edit_caption(
                    base_caption + "\n\n<b>❌ Invalid OTP! Try again.</b>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_otp_keyboard()
                )
                temp_dict["otp"] = ""
                temp_json = json.dumps(temp_dict)
                temp_encrypted = cipher_suite.encrypt(temp_json.encode()).decode()
                db.set_temp_data(uid, temp_encrypted)
            except PhoneCodeExpiredError:
                await cb.message.edit_caption(
                    base_caption + "\n\n<b>❌ OTP expired! Please restart.</b>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=None
                )
                db.set_user_state(uid, "")
                db.set_temp_data(uid, None)
                break
            except FloodWaitError as e:
                logger.warning(f"Flood wait during OTP verification for {uid}: Wait {e.seconds} seconds")
                await asyncio.sleep(e.seconds)
                if attempt < max_retries - 1:
                    continue
                await cb.message.edit_caption(
                    base_caption + f"\n\n<b>❌ Flood wait limit reached: Please wait {e.seconds}s and try again.</b>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=None
                )
                db.set_user_state(uid, "")
                db.set_temp_data(uid, None)
                break
            except Exception as e:
                logger.error(f"Error signing in for {uid} (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                await cb.message.edit_caption(
                    base_caption + f"\n\n<blockquote><b>❌ Login failed:</b>{str(e)}</blockquote>\n\n"
                    f"<b>Contact support:</b> @{config.ADMIN_USERNAME}",
                    parse_mode=ParseMode.HTML,
                    reply_markup=None
                )
                await send_dm_log(uid, f"<b>❌ Account login failed:</b> {str(e)}")
                db.set_user_state(uid, "")
                db.set_temp_data(uid, None)
                break
            finally:
                await tg.disconnect()

@pyro.on_callback_query(filters.regex("joined_check"))
async def joined_check(client, cb):
    uid = cb.from_user.id
    if not await is_joined_all(client, uid):
        await cb.answer("Please join both the channel and group first!", show_alert=True)
        logger.info(f"User {uid} failed join check: not in both {config.MUST_JOIN_CHANNEL_ID} and {config.MUSTJOIN_GROUP_ID}")
        return
    await cb.message.delete()
    await start(client, cb.message)
    logger.info(f"User {uid} passed join check and proceeded to dashboard")

@pyro.on_callback_query(filters.regex("back_to_start"))
async def back_to_start(client, cb):
    await cb.message.delete()
    await start(client, cb.message)

@pyro.on_callback_query(filters.regex("menu_main"))
async def menu_main(client, cb):
    try:
        uid = cb.from_user.id
        db.update_user_last_interaction(uid)
        user = db.get_user(uid)
        
        if not user:
            await cb.answer("Please restart with /start ", show_alert=True)
            return
        
        accounts_count = db.get_user_accounts_count(uid)
        saved_msgs = db.get_user_ad_messages(uid)
        ad_msg_status = "Set ✅" if saved_msgs else "Not Set ⭕"
        current_delay = db.get_user_ad_delay(uid)
        broadcast_state = db.get_broadcast_state(uid)
        running = broadcast_state.get("running", False)
        broadcast_status = "Running 🚀" if running else "Paused ⏸️"
        
        dashboard_caption = (
            f"<blockquote><b>╰_╯ ADS DASHBOARD</b></blockquote>\n\n"
            f"•Hosted Accounts: <code>{accounts_count}</code>\n"
            f"•Ad Message: {ad_msg_status}\n"
            f"•Cycle Interval: {current_delay}s\n"
            f"•Advertising Status: <b>{broadcast_status}</b>\n\n"
            "<blockquote>╰_╯Choose an action below to continue </blockquote>"
        )
        
        menu = [
            [InlineKeyboardButton("Add Accounts", callback_data="host_account"),
             InlineKeyboardButton("My Accounts", callback_data="view_accounts")],
            [InlineKeyboardButton("Set Ad Message", callback_data="set_msg"),
             InlineKeyboardButton("Set Time Interval", callback_data="set_delay")],
            [InlineKeyboardButton("Start Ads▶️", callback_data="start_broadcast"),
             InlineKeyboardButton("Stop Ads⏸️", callback_data="stop_broadcast")],
            [InlineKeyboardButton("Delete Accounts", callback_data="delete_accounts"),
             InlineKeyboardButton("Analytics", callback_data="analytics")],
            [InlineKeyboardButton("Auto Reply", callback_data="auto_reply")]
        ]
        
        try:
            await cb.message.edit_text(
                text=dashboard_caption,
                reply_markup=kb(menu),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Error editing message in menu_main: {e}")
            await cb.answer("Error loading dashboard. Try /start.", show_alert=True)
        logger.info(f"Menu main accessed by user {uid}, callback_data: {cb.data}")
    except Exception as e:
        logger.error(f"Error in menu_main for user {uid}: {e}")
        await cb.answer("Error loading dashboard. Try /start.", show_alert=True)

@pyro.on_callback_query(filters.regex("host_account"))
async def host_account(client, cb):
    uid = cb.from_user.id
    user = db.get_user(uid)
    
    if not user:
        await cb.answer("Please restart with /start", show_alert=True)
        return
    
    accounts_count = db.get_user_accounts_count(uid)
    
    try:
        db.set_user_state(uid, "telethon_wait_phone")
        db.set_temp_data(uid, None)
    except Exception as e:
        logger.error(f"Failed to set user state for {uid}: {e}")
        await cb.answer("Error initiating account hosting. Try again.", show_alert=True)
        return
    
    await cb.message.edit_media(
        media=InputMediaPhoto(
            media=config.FORCE_JOIN_IMAGE,
            caption="""<blockquote><b>╰_╯HOST NEW ACCOUNT</b></blockquote>\n\n"""
                    """Secure Account Hosting\n\n"""
                    """Enter your phone number with country code:\n\n"""
                    """<blockquote>Example: <code>+1234567890</code></blockquote>\n\n"""
                    """Your data is encrypted and secure""",
            parse_mode=ParseMode.HTML
        ),
        reply_markup=kb([[InlineKeyboardButton("Back 🔙", callback_data="menu_main")]])
    )

@pyro.on_callback_query(filters.regex("view_accounts"))
async def view_accounts(client, cb):
    uid = cb.from_user.id
    accounts = db.get_user_accounts(uid)
    if not accounts:
        await cb.message.edit_caption(
            caption="""<blockquote><b>╰_╯NO ACCOUNTS HOSTED</b></blockquote>\n\n"""
                    """Add an account to start broadcasting!""",
            reply_markup=kb([[InlineKeyboardButton("Add Account 📱", callback_data="host_account"),
                            InlineKeyboardButton("Back 🔙", callback_data="menu_main")]]),
            parse_mode=ParseMode.HTML
        )
        return
    
    caption = "<blockquote><b>╰_╯HOSTED ACCOUNTS</b></blockquote>\n\n"
    buttons = []
    for i, acc in enumerate(accounts, 1):
        status = "Active ✅" if acc['is_active'] else "Inactive ❌"
        caption += f"{i}. <code>{acc['phone_number']}</code> - <i>{status}</i>\n"
        buttons.append([
            InlineKeyboardButton(f"{acc['phone_number']} ({status})", callback_data=f"view_acc_{acc['_id']}"),
            InlineKeyboardButton("Delete", callback_data=f"delete_acc_{acc['_id']}")
        ])
    
    caption += "\n<blockquote>╰_╯Choose an action:</blockquote>"
    buttons.append([InlineKeyboardButton("Add Account", callback_data="host_account")])
    buttons.append([InlineKeyboardButton("Back", callback_data="menu_main")])
    
    await cb.message.edit_caption(
        caption=caption,
        reply_markup=kb(buttons),
        parse_mode=ParseMode.HTML
    )

@pyro.on_callback_query(filters.regex("delete_accounts"))
async def delete_accounts(client, cb):
    uid = cb.from_user.id
    accounts = db.get_user_accounts(uid)
    if not accounts:
        await cb.message.edit_caption(
            caption="""<blockquote><b>╰_╯NO ACCOUNTS TO DELETE</b></blockquote>\n\n"""
                    """Add an account to start Advertising!""",
            reply_markup=kb([[InlineKeyboardButton("Add Account", callback_data="host_account"),
                            InlineKeyboardButton("Back", callback_data="menu_main")]]),
            parse_mode=ParseMode.HTML
        )
        return
    
    caption = "<blockquote><b>╰_╯ DELETE ACCOUNTS</b></blockquote>\n\n"
    buttons = []
    for i, acc in enumerate(accounts, 1):
        status = "Active ✅" if acc['is_active'] else "Inactive ❌"
        caption += f"{i}. <code>{acc['phone_number']}</code> - <i>{status}</i>\n"
        buttons.append([
            InlineKeyboardButton(f"{acc['phone_number']} ({status})", callback_data=f"view_acc_{acc['_id']}"),
            InlineKeyboardButton("Delete", callback_data=f"delete_acc_{acc['_id']}")
        ])
    
    caption += "\n<blockquote>Choose an account to delete:</blockquote>"
    buttons.append([InlineKeyboardButton("Back", callback_data="menu_main")])
    
    await cb.message.edit_caption(
        caption=caption,
        reply_markup=kb(buttons),
        parse_mode=ParseMode.HTML
    )

@pyro.on_callback_query(filters.regex("delete_acc_"))
async def delete_account(client, cb):
    uid = cb.from_user.id
    acc_id = cb.data.replace("delete_acc_", "")
    try:
        db.delete_user_account(uid, acc_id)
        await cb.message.edit_caption(
            caption="""<blockquote><b> Account deleted!</b></blockquote>\n\n"""
                    """Account removed successfully.✅""",
            reply_markup=kb([[InlineKeyboardButton("Back 🔙", callback_data="delete_accounts")]]),
            parse_mode=ParseMode.HTML
        )
        await send_dm_log(uid, f"<b>Account deleted:</b> ID {acc_id}")
        logger.info(f"Account {acc_id} deleted by user {uid}")
    except Exception as e:
        logger.error(f"Failed to delete account {acc_id} for user {uid}: {e}")
        await cb.answer("Error deleting account. Try again.", show_alert=True)
        await send_dm_log(uid, f"<b>❌ Failed to delete account:</b> {str(e)}")

@pyro.on_callback_query(filters.regex("view_acc_"))
async def view_account(client, cb):
    uid = cb.from_user.id
    acc_id = cb.data.replace("view_acc_", "")
    accounts = db.get_user_accounts(uid)
    account = next((acc for acc in accounts if acc['_id'] == acc_id), None)
    if not account:
        await cb.answer("╰_╯Custom settings for Accounts is not available in this version, Update will come soon.", show_alert=True)
        return
    
    status = "Active ✅" if account['is_active'] else "Inactive ⭕"
    caption = (
        f"<blockquote><b>╰_╯ACCOUNT DETAILS</b></blockquote>\n\n"
        f"Phone: <code>{account['phone_number']}</code>\n"
        f"<b>Status:</b>{status}\n\n"
        f"<blockquote>Choose an action:</blockquote>"
    )
    
    await cb.message.edit_caption(
        caption=caption,
        reply_markup=kb([
            [InlineKeyboardButton("Delete Account", callback_data=f"delete_acc_{acc_id}")],
            [InlineKeyboardButton("Back", callback_data="delete_accounts")]
        ]),
        parse_mode=ParseMode.HTML
    )

@pyro.on_callback_query(filters.regex("set_msg"))
async def set_msg(client, cb):
    uid = cb.from_user.id
    db.set_user_state(uid, "waiting_broadcast_msg")
    saved_msgs = db.get_user_ad_messages(uid)
    current_msg = saved_msgs[0]["message"] if saved_msgs else "None set"
    
    current_msg_section = f"\n\n<blockquote><b>Current Ad Message:</b>\n{current_msg}</blockquote>" if current_msg != "None set" else "\n\n<blockquote><b>Current Ad Message:</b>\nNo message set yet.</blockquote>"
    
    await cb.message.edit_media(
        media=InputMediaPhoto(
            media=config.START_IMAGE,
            caption=f"""<blockquote>╰_╯ <b>SET YOUR AD MESSAGE</b></blockquote>{current_msg_section}

Tips for effective ads:
•Keep it concise and engaging
•Use premium emojis for flair
•Include clear call-to-action
•Avoid excessive caps or spam words

<blockquote>Send your ad message now:</blockquote>""",
            parse_mode=ParseMode.HTML
        ),
        reply_markup=kb([[InlineKeyboardButton("Back", callback_data="menu_main")]])
    )

@pyro.on_callback_query(filters.regex("set_delay"))
async def set_delay(client, cb):
    uid = cb.from_user.id
    current_delay = db.get_user_ad_delay(uid)
    
    await cb.message.edit_media(
        media=InputMediaPhoto(
            media=config.START_IMAGE,
            caption=f"""<blockquote><b>╰_╯SET BROADCAST CYCLE INTERVAL</b></blockquote>\n\n"""
                    f"<u>Current Interval:</u> <code>{current_delay} seconds</code>\n\n"
                    f"<b>Recommended Intervals:</b>\n"
                    f"•300s - Aggressive (5 min) 🔴\n"
                    f"•600s - Safe & Balanced (10 min) 🟡\n"
                    f"•1200s - Conservative (20 min) 🟢\n\n"
                    f"<blockquote>To set custom time interval Send a number (in seconds):\n\n(Note: using short time interval for broadcasting can get your Account on high risk.)</blockquote>",
            parse_mode=ParseMode.HTML
        ),
        reply_markup=kb([
            [InlineKeyboardButton("20min 🟢", callback_data="quick_delay_1200"),
             InlineKeyboardButton("5min 🔴", callback_data="quick_delay_300"),
             InlineKeyboardButton("10min 🟡", callback_data="quick_delay_600")],
            [InlineKeyboardButton("Back 🔙", callback_data="menu_main")]
        ])
    )
    db.set_user_state(uid, "waiting_broadcast_delay")

@pyro.on_callback_query(filters.regex("quick_delay_"))
async def quick_delay(client, cb):
    uid = cb.from_user.id
    delay = int(cb.data.split("_")[-1])
    
    try:
        db.set_user_ad_delay(uid, delay)
    except Exception as e:
        logger.error(f"Failed to set ad delay for user {uid}: {e}")
        await cb.answer("Error setting delay. Try again.", show_alert=True)
        return
    
    mode = "Aggressive" if delay >= 300 else "Balanced" if delay >= 600 else "Conservative" if delay >= 1200 else "Custom"
    
    await cb.message.edit_caption(
        caption=f"""<blockquote><b>╰_╯CYCLE INTERVAL UPDATED!</b></blockquote>\n\n"""
                f"<u>New Interval:</u> <code>{delay} seconds</code> \n"
                f"<b>Mode:</b> <i>{mode}</i>\n\n"
                f"<blockquote>Ready for broadcasting!</blockquote>",
        reply_markup=kb([[InlineKeyboardButton("Back", callback_data="menu_main")]]),
        parse_mode=ParseMode.HTML
    )
    await send_dm_log(uid, f"<b> Broadcast interval updated:</b> {delay} seconds ({mode})")
    db.set_user_state(uid, "")

@pyro.on_callback_query(filters.regex("start_broadcast"))
async def start_broadcast(client, cb):
    uid = cb.from_user.id
    try:
        if db.get_broadcast_state(uid).get("running"):
            await cb.answer("╰_╯Broadcast already running!", show_alert=True)
            return
        
        if not db.get_user_ad_messages(uid):
            await cb.answer("╰_╯Baka! set an ad message first!", show_alert=True)
            return
        
        accounts = db.get_user_accounts(uid)
        if not accounts:
            await cb.answer("╰_╯Baka! No accounts hosted yet!", show_alert=True)
            return
        
        if not db.get_logger_status(uid):
            try:
                await cb.message.edit_caption(
                    caption="<b>⚠️ Logger bot not started yet!</b>\n\n"
                            f"Please start @{config.LOGGER_BOT_USERNAME.lstrip('@')} to receive Advertising logs.\n"
                            "<i>After starting, return here to begin Advertising.</i>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb([
                        [InlineKeyboardButton("Start Logger Bot 📩", url=f"https://t.me/{config.LOGGER_BOT_USERNAME.lstrip('@')}")],
                        [InlineKeyboardButton("Back", callback_data="menu_main")]
                    ])
                )
            except Exception as e:
                logger.error(f"Failed to edit logger bot message for {uid}: {e}")
                await cb.answer("╰_╯Error: Please try again.", show_alert=True)
            return
        
        current_task = user_tasks.get(uid)
        if current_task:
            try:
                current_task.cancel()
                await current_task
                logger.info(f"Cancelled previous broadcast for {uid}")
            except Exception as e:
                logger.error(f"Failed to cancel previous broadcast task for {uid}: {e}")
            finally:
                if uid in user_tasks:
                    del user_tasks[uid]
        
        task = asyncio.create_task(run_broadcast(client, uid))
        user_tasks[uid] = task
        db.set_broadcast_state(uid, running=True)
        
        try:
            await cb.message.edit_caption(
                caption="""<blockquote> <b>╰_╯BROADCAST ON!</b></blockquote>\n\n"""
                        """Your ads are now being sent to the groups your account is joined in.\n"""
                        f"""Logs will be sent to your DM via @{config.LOGGER_BOT_USERNAME.lstrip('@')}.</i>""",
                parse_mode=ParseMode.HTML,
                reply_markup=kb([[InlineKeyboardButton("Back", callback_data="menu_main")]])
            )
            await cb.answer("Broadcast started! ▶️", show_alert=True)
            await send_dm_log(uid, "<b>🚀 Broadcast started! Logs will come here</b>")
            logger.info(f"Broadcast started via callback for user {uid}")
        except Exception as e:
            logger.error(f"Failed to edit BROADCAST ON message for {uid}: {e}")
            try:
                await client.send_photo(
                    chat_id=uid,
                    photo=config.START_IMAGE,
                    caption="""<blockquote><b>╰_╯BROADCAST ON! </b></blockquote>\n\n"""
                            """Your ads are now being sent to the groups your account is joined in.\n"""
                            f"""Logs will be sent to your DM via @{config.LOGGER_BOT_USERNAME.lstrip('@')}.""",
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb([[InlineKeyboardButton("Back 🔙", callback_data="menu_main")]])
                )
                await cb.answer("Broadcast started! 🚀", show_alert=True)
                await send_dm_log(uid, "<b>Broadcast started! Logs will come here</b>")
                logger.info(f"Broadcast started via callback for user {uid} (fallback send)")
            except Exception as e2:
                logger.error(f"Failed to send fallback BROADCAST ON message for {uid}: {e2}")
                await cb.answer("Error starting broadcast. Please try again. 😔", show_alert=True)
                await send_dm_log(uid, f"<b>❌ Failed to start broadcast:</b> {str(e2)} 😔")
    except Exception as e:
        logger.error(f"Error in start_broadcast for {uid}: {e}")
        await cb.answer("Error starting broadcast. Contact support. 😔", show_alert=True)
        await send_dm_log(uid, f"<b>❌ Failed to start broadcast:</b> {str(e)} 😔")

@pyro.on_callback_query(filters.regex("stop_broadcast"))
async def stop_broadcast(client, cb):
    uid = cb.from_user.id
    stopped = await stop_broadcast_task(uid)
    if not stopped:
        await cb.answer("╰_╯No broadcast running!", show_alert=True)
        return
    
    await cb.answer("Broadcast stopped! ⏸️", show_alert=True)
    try:
        await cb.message.edit_caption(
            caption="""<blockquote><b>╰_╯BROADCAST STOPPED! ✨</b></blockquote>\n\n"""
                    """Your broadcast has been stopped.\n"""
                    """Check analytics for final stats.""",
            reply_markup=kb([[InlineKeyboardButton("Back", callback_data="menu_main")]]),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Failed to edit BROADCAST STOPPED message for {uid}: {e}")
        await client.send_photo(
            chat_id=uid,
            photo=config.START_IMAGE,
            caption="""<blockquote><b>╰_╯BROADCAST STOPPED!</b></blockquote>\n\n"""
                    """Your broadcast has been stopped.\n"""
                    """Check analytics for final stats.""",
            parse_mode=ParseMode.HTML,
            reply_markup=kb([[InlineKeyboardButton("Back", callback_data="menu_main")]])
        )
    await send_dm_log(uid, f"<b>╰_╯ Broadcast stopped!</b>")
    logger.info(f"Broadcast stopped via callback for user {uid}")

@pyro.on_callback_query(filters.regex("auto_reply"))
async def auto_reply(client, cb):
    uid = cb.from_user.id
    await cb.message.edit_caption(
        caption="""<blockquote> <b>╰_╯AUTO REPLY FEATURE</b></blockquote>\n\n"""
                """This feature is coming soon!\n"""
                """Stay tuned for automated reply capabilities to enhance your campaigns. This feature is right now available in our @AdsReachbot""",
        reply_markup=kb([[InlineKeyboardButton("Back", callback_data="menu_main")]]),
        parse_mode=ParseMode.HTML
    )

@pyro.on_callback_query(filters.regex("analytics"))
async def analytics(client, cb):
    uid = cb.from_user.id
    user_stats = db.get_user_analytics(uid)
    accounts = db.get_user_accounts(uid)
    logger_failures = len(db.get_logger_failures(uid))
    
    analytics_text = (
        f"<blockquote><b>╰_╯@Tecxo ANALYTICS</b></blockquote>\n\n"
        f"<u>Broadcast Cycles Completed:</u> <code>{user_stats.get('total_cycles', 0)}</code>\n"
        f"<b>Messages Sent:</b> <i>{user_stats.get('total_sent', 0)}</i>\n"
        f"<u>Failed Sends:</u> <code>{user_stats.get('total_failed', 0)}</code>\n"
        f"<b>Logger Failures:</b> <i>{logger_failures}</i>\n"
        f"<b>Active Accounts:</b> <i>{len([a for a in accounts if a['is_active']])}</i>\n"
        f"<u>Avg Delay:</u> <code>{db.get_user_ad_delay(uid)}s</code>\n\n"
        f"<blockquote>Success Rate: {generate_progress_bar(user_stats.get('total_sent', 0), user_stats.get('total_sent', 0) + user_stats.get('total_failed', 0))}</blockquote>"
    )
    
    await cb.message.edit_caption(
        caption=analytics_text,
        reply_markup=kb([
            [InlineKeyboardButton("Detailed Report", callback_data="detailed_report")],
            [InlineKeyboardButton("Back", callback_data="menu_main")]
        ]),
        parse_mode=ParseMode.HTML
    )

@pyro.on_callback_query(filters.regex("detailed_report"))
async def detailed_report(client, cb):
    uid = cb.from_user.id
    user_stats = db.get_user_analytics(uid)
    accounts = db.get_user_accounts(uid)
    logger_failures = db.get_logger_failures(uid)
    
    detailed_text = (
        f"<blockquote><b>╰_╯ DETAILED ANALYTICS REPORT:</b></blockquote>\n\n"
        f"<u>Date:</u> <i>{datetime.now().strftime('%d/%m/%y')}</i>\n"
        f"<b>User ID:</b> <code>{uid}</code>\n\n"
        "<b>Broadcast Stats:</b>\n"
        f"- <u>Total Sent:</u> <code>{user_stats.get('total_sent', 0)}</code>\n"
        f"- <i>Total Failed:</i> <b>{user_stats.get('total_failed', 0)}</b>\n"
        f"- <u>Total Broadcasts:</u> <code>{user_stats.get('total_broadcasts', 0)}</code>\n\n"
        "<b>Logger Stats:</b>\n"
        f"- <u>Logger Failures:</u> <code>{len(logger_failures)}</code>\n"
        f"- <i>Last Failure:</i> <b>{logger_failures[-1]['error'] if logger_failures else 'None'}</b>\n\n"
        "<b>Account Stats:</b>\n"
        f"- <i>Total Accounts:</i> <u>{len(accounts)}</u>\n"
        f"- <b>Active Accounts:</b> <code>{len([a for a in accounts if a['is_active']])}</code> 🟢\n"
        f"- <u>Inactive Accounts:</u> <i>{len([a for a in accounts if not a['is_active']])}</i> 🔴\n\n"
        f"<blockquote><b>Current Delay:</b> <code>{db.get_user_ad_delay(uid)}s</code></blockquote>"
    )
    
    await cb.message.edit_caption(
        caption=detailed_text,
        reply_markup=kb([
            [InlineKeyboardButton("Back", callback_data="analytics")]
        ]),
        parse_mode=ParseMode.HTML
    )

@pyro.on_message(filters.command("stats") & filters.user(ALLOWED_BD_IDS))
async def admin_stats(client, m):
    try:
        stats = db.get_admin_stats()
        
        stats_text = (
            f"<blockquote><b>╰_╯ Tecxo Ads ADMIN DASHBOARD </b></blockquote>\n\n"
            f"<u>Report Date:</u> <i>{datetime.now().strftime('%d/%m/%y • %I:%M %p')}</i>\n\n"
            "<b>USER STATISTICS</b>\n"
            f"• <u>Total Users:</u> <code>{stats.get('total_users', 0)}</code>\n"
            f"• <b>Hosted Accounts:</b> <code>{stats.get('total_accounts', 0)}</code>\n"
            f"• <u>Total Forwards:</u> <i>{stats.get('total_forwards', 0)}</i>\n"
            f"• <b>Active Logger Users:</b> <code>{stats.get('active_logger_users', 0)}</code>\n"
        )
        
        await m.reply_photo(
            photo=config.START_IMAGE,
            caption=stats_text,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        await m.reply(f"╰_╯Error generating stats: {str(e)}", parse_mode=ParseMode.HTML)

@pyro.on_message(filters.command("stats") & ~filters.user(ALLOWED_BD_IDS))
async def non_admin_stats(client, m):
    await m.reply("╰_╯Baka! This is an admin command you are not allowed to do this.")

@pyro.on_message(filters.command("bd") & filters.user(ALLOWED_BD_IDS))
async def admin_broadcast(client, m):
    uid = m.from_user.id
    if not is_owner(uid):
        await m.reply("╰_╯Baka! This is an Admin only command.", parse_mode=ParseMode.HTML)
        return
    
    if not m.reply_to_message:
        await m.reply("╰_╯Reply to a message to broadcast it.", parse_mode=ParseMode.HTML)
        return
    
    all_users = db.get_all_users(limit=0)  # Fetch all users without limit
    if not all_users:
        await m.reply("╰_╯No users found.", parse_mode=ParseMode.HTML)
        return
    
    total_users = len(all_users)
    status_msg = await m.reply(
        """<blockquote><b>📢 Tecxo ADMIN BROADCAST</b></blockquote>\n\n"""
        "<u>Status: Initializing...</u>",
        parse_mode=ParseMode.HTML
    )
    
    sent_count = 0
    failed_count = 0
    
    reply_msg = m.reply_to_message
    media = None
    caption = reply_msg.caption or reply_msg.text or ""
    
    if reply_msg.photo:
        media = reply_msg.photo.file_id
    elif reply_msg.document:
        media = reply_msg.document.file_id
    elif reply_msg.video:
        media = reply_msg.video.file_id
    
    for user in all_users:
        user_id = user['user_id']
        try:
            await client.resolve_peer(user_id)
            if media:
                await client.send_photo(
                    chat_id=user_id,
                    photo=media,
                    caption=caption,
                    parse_mode=ParseMode.HTML
                )
            else:
                await client.send_message(
                    chat_id=user_id,
                    text=caption,
                    parse_mode=ParseMode.HTML
                )
            sent_count += 1
        except PeerIdInvalid:
            logger.error(f"Failed to send broadcast to user {user_id}: PeerIdInvalid")
            failed_count += 1
            await send_dm_log(user_id, f"<b>⚠️ Admin broadcast failed:</b> PeerIdInvalid")
        except FloodWait as e:
            logger.warning(f"Flood wait for user {user_id}: Wait {e.seconds} seconds")
            await asyncio.sleep(e.seconds)
            try:
                if media:
                    await client.send_photo(chat_id=user_id, photo=media, caption=caption, parse_mode=ParseMode.HTML)
                else:
                    await client.send_message(chat_id=user_id, text=caption, parse_mode=ParseMode.HTML)
                sent_count += 1
            except Exception:
                failed_count += 1
                await send_dm_log(user_id, f"<b>⚠️ Admin broadcast failed after wait:</b> {str(e)} ")
        except Exception as e:
            logger.error(f"Failed to send broadcast to user {user_id}: {e}")
            failed_count += 1
            await send_dm_log(user_id, f"<b>⚠️ Admin broadcast failed:</b> {str(e)} ")
        if (sent_count + failed_count) % 10 == 0 or (sent_count + failed_count) == total_users:
            try:
                await status_msg.edit_text(
                    f"""<blockquote><b>📢 Tecxo ADMIN BROADCAST</b></blockquote>\n\n"""
                    f"<u>Status: In Progress...</u> \n"
                    f"<b>Sent:</b> <code>{sent_count}/{total_users}</code>\n"
                    f"<i>Failed:</i> <u>{failed_count}</u>\n"
                    f"<blockquote>Progress: {generate_progress_bar(sent_count + failed_count, total_users)} </blockquote>",
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.error(f"Failed to update broadcast status: {e}")
        await asyncio.sleep(0.5)
    
    await status_msg.edit_text(
        f"""<blockquote><b>✅ Tecxo ADMIN BROADCAST COMPLETED </b></blockquote>\n\n"""
        f"<u>Sent:</u> <code>{sent_count}/{total_users}</code>\n"
        f"<b>Failed:</b> <i>{failed_count}</i> ⚠️\n"
        f"<blockquote>Success Rate: {generate_progress_bar(sent_count, total_users)} 💹</blockquote>",
        parse_mode=ParseMode.HTML
    )
    await send_dm_log(uid, f"<b>🏁 Admin broadcast completed:</b> Sent {sent_count}/{total_users}, Failed {failed_count} ✨")

@pyro.on_message(filters.command("bd") & ~filters.user(ALLOWED_BD_IDS))
async def non_admin_bd(client, m):
    await m.reply("╰_╯Baka! command is for admins only, you are not allowed to use it.")

@pyro.on_message(filters.command("stop"))
async def stop_command(client, m):
    uid = m.from_user.id
    stopped = await stop_broadcast_task(uid)
    if stopped:
        await m.reply("<blockquote><b>⏹️ Broadcast stopped! </b></blockquote>", parse_mode=ParseMode.HTML)
        await send_dm_log(uid, "<b>⏹️ Broadcast stopped! </b>")
    else:
        await m.reply("╰_╯No broadcast running!", parse_mode=ParseMode.HTML)

@pyro.on_message(filters.command("me"))
async def user_info(client, m):
    uid = m.from_user.id
    user = db.get_user(uid)
    
    if not user:
        await m.reply("╰_╯You're not registered. Please /start first.", parse_mode=ParseMode.HTML)
        return
    
    accounts_count = db.get_user_accounts_count(uid)
    
    status_text = (
        f"<blockquote><b>╰_╯ Tecxo FREE Ads bot</b></blockquote>\n\n"
        f"<u>User ID:</u> <code>{uid}</code>\n"
        f"<b>Username:</b> <i>@{user.get('username', 'N/A')}</i>\n"
        "<blockquote><b>Status: FREE USER </b></blockquote>\n"
        f"Hosted Accounts: <u>{accounts_count}/5 \n"
        f"<b>Logger Active:</b>{'Yes ✅' if db.get_logger_status(uid) else 'No ❌'}\n"
        "<b>Features:</b>\n"
        "•Up to 5 account hosting\n"
        "•Automated broadcasting\n"
        "•Group targeting\n"
        "•Real-time analytics\n"
        "•DM logging via logger bot\n"
    )
    
    status_buttons = [
        [InlineKeyboardButton("Dashboard", callback_data="menu_main")],
        [InlineKeyboardButton("Support 💬", url=config.SUPPORT_GROUP_URL)]
    ]
    
    await m.reply_photo(
        photo=config.START_IMAGE,
        caption=status_text,
        reply_markup=InlineKeyboardMarkup(status_buttons),
        parse_mode=ParseMode.HTML
    )

@pyro.on_message(filters.command(["start"]))
async def start(client, m):
    uid = m.from_user.id
    username = m.from_user.username or "Unknown"
    first_name = m.from_user.first_name or "User"
    
    db.create_user(uid, username, first_name)
    if is_owner(uid):
        db.db.users.update_one({"user_id": uid}, {"$set": {"accounts_limit": "unlimited"}})
    db.update_user_last_interaction(uid)
    
    if config.ENABLE_FORCE_JOIN:
        if not await is_joined_all(client, uid):
            try:
                await m.reply_photo(
                    photo=config.FORCE_JOIN_IMAGE,
                    caption="""<blockquote><b>╰_╯WELCOME TO @TECXO FREE ADS BOT</b></blockquote>\n\n"""
                            """To unlock the full <b>Theodron</b> experience, please join our official channel and group first!\n\n"""
                            """<i>Tip: Click the buttons below to join both. After joining, click 'Try Again' to proceed.</i>\n\n"""
                            """Your <i>Free premium automation journey</i> starts here""",
                    reply_markup=kb([
                        [InlineKeyboardButton("Join Channel", url=config.MUST_JOIN_CHANNEL_URL)],
                        [InlineKeyboardButton("Join Group", url=config.MUSTJOIN_GROUP_URL)],
                        [InlineKeyboardButton("Try again", callback_data="joined_check")]
                    ]),
                    parse_mode=ParseMode.HTML
                )
                logger.info(f"Sent force join message to user {uid}")
            except Exception as e:
                logger.error(f"Failed to send force join message to {uid}: {e}")
                await m.reply("╰_╯Please join my channel and group to proceed. Contact support you are having any issues...")
            return
    
    try:
        await m.reply(
            "<blockquote><b>╰_╯ Welcome! Your Ads Bot is ready.</b></blockquote>",
            reply_markup=kb([
                [InlineKeyboardButton("Dashboard", callback_data="menu_main")]
            ]),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"╰_╯Failed to send start message to {uid}: {e}")
        await m.reply("╰_╯Error starting bot. Please try again or contact support.")

@pyro.on_message(filters.text & filters.regex(r"https?://t\.me/.*") & filters.private & ~filters.command(["start", "bd", "me", "stats", "stop"]))
async def handle_group_link(client, m):
    uid = m.from_user.id
    state = db.get_user_state(uid)
    if state != "waiting_group_link":
        return
    link = m.text.strip()
    try:
        tg_client = TelegramClient(StringSession(), config.API_ID, config.API_HASH)
        await tg_client.connect()
        chat = await tg_client.get_entity(link)
        db.add_target_group(uid, chat.id, chat.title)
        await m.reply(f"<blockquote><b>✅ Group <i>{chat.title}</i> added! ✨</b></blockquote>", parse_mode=ParseMode.HTML)
        await send_dm_log(uid, f"<b>🎯 Group added:</b> <i>{chat.title}</i> ✨")
        db.set_user_state(uid, "")
        await tg_client.disconnect()
    except Exception as e:
        await m.reply(f"<blockquote><b>❌ Failed to add group:</b> <i>{str(e)}</i> 😔</blockquote>", parse_mode=ParseMode.HTML)
        await send_dm_log(uid, f"<b>❌ Failed to add group:</b> {str(e)} 😔")
        logger.error(f"Failed to add group for {uid}: {e}")

@pyro.on_message(filters.text & filters.private & ~filters.command(["start", "bd", "me", "stats", "stop"]))
async def handle_text_message(client, m):
    uid = m.from_user.id
    state = db.get_user_state(uid)
    text = m.text.strip()
    
    if state == "waiting_broadcast_msg":
        try:
            db.add_user_ad_message(uid, text, datetime.now())
            db.set_user_state(uid, "")
            await m.reply(
                f"<blockquote><b>╰_╯ AD MESSAGE SET!✅</b></blockquote>\n\n"
                f"<u>Message Preview:</u>\n<code>{text}</code>\n\n"
                f"<b>Ready to broadcast!</b>\n"
                f"<i>Start your campaign from the dashboard.</i>",
                parse_mode=ParseMode.HTML,
                reply_markup=kb([[InlineKeyboardButton("Dashboard 🚪", callback_data="menu_main")]])
            )
            await send_dm_log(uid, f"<b>📝 Ad message updated:</b> <code>{text[:50]}{'...' if len(text) > 50 else ''}</code>")
            logger.info(f"Ad message set for user {uid}: {text[:50]}...")
        except Exception as e:
            logger.error(f"Failed to add ad message for user {uid}: {e}")
            db.set_user_state(uid, "")
            await m.reply(
                f"<blockquote><b>❌ Failed to save ad message!</b></blockquote>\n\n"
                f"<u>Error:</u> <i>{str(e)}</i>\n"
                f"<b>Contact Support:</b> @{config.ADMIN_USERNAME}",
                parse_mode=ParseMode.HTML,
                reply_markup=kb([[InlineKeyboardButton("Dashboard 🚪", callback_data="menu_main")]])
            )
            await send_dm_log(uid, f"<b>❌ Failed to set ad message:</b> {str(e)}")
    elif state == "waiting_broadcast_delay":
        try:
            delay = int(text)
            if delay < 120:
                await m.reply(
                    f"<blockquote><b>❌ Invalid interval!</b></blockquote>\n\n"
                    f"Minimum interval is 120 seconds.\n"
                    f"Please enter a valid number",
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb([[InlineKeyboardButton("Back", callback_data="menu_main")]])
                )
                return
            if delay > 86400:
                await m.reply(
                    f"<blockquote><b>❌ Invalid interval!</b></blockquote>\n\n"
                    f"Maximum interval is 86400 seconds (24 hours).\n"
                    f"Please enter a valid number",
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb([[InlineKeyboardButton("Back", callback_data="menu_main")]])
                )
                return
            db.set_user_ad_delay(uid, delay)
            db.set_user_state(uid, "")
            mode = "Aggressive" if delay >= 300 else "Balanced" if delay >= 600 else "Conservative" if delay >= 1200 else "Custom"
            await m.reply(
                f"<blockquote><b>╰_╯CYCLE INTERVAL UPDATED! ✅</b></blockquote>\n\n"
                f"<u>New Interval:</u> <code>{delay} seconds</code>\n"
                f"<b>Mode:</b> <i>{mode}</i>\n\n"
                f"<blockquote>Ready for broadcasting!</blockquote>",
                parse_mode=ParseMode.HTML,
                reply_markup=kb([[InlineKeyboardButton("Dashboard 🚪", callback_data="menu_main")]])
            )
            await send_dm_log(uid, f"<b>⏱️ Broadcast interval updated:</b> {delay} seconds ({mode})")
            logger.info(f"Broadcast delay set for user {uid}: {delay}s")
        except ValueError:
            await m.reply(
                f"<blockquote><b>❌ Invalid input!</b></blockquote>\n\n"
                f"<u>Please enter a number (in seconds).</u>\n"
                f"<i>Example: <code>300</code> for 5 minutes.</i>",
                parse_mode=ParseMode.HTML,
                reply_markup=kb([[InlineKeyboardButton("Back", callback_data="menu_main")]])
            )
        except Exception as e:
            logger.error(f"Failed to set broadcast delay for user {uid}: {e}")
            db.set_user_state(uid, "")
            await m.reply(
                f"<blockquote><b>❌ Failed to set interval!</b></blockquote>\n\n"
                f"<u>Error:</u> <i>{str(e)}</i>\n"
                f"<b>Contact support:</b> @{config.ADMIN_USERNAME}",
                parse_mode=ParseMode.HTML,
                reply_markup=kb([[InlineKeyboardButton("Dashboard", callback_data="menu_main")]])
            )
            await send_dm_log(uid, f"<b>❌ Failed to set broadcast interval:</b> {str(e)}")
    elif state == "telethon_wait_phone":
        if not validate_phone_number(text):
            await m.reply(
                f"<blockquote><b>❌ Invalid phone number!</b></blockquote>\n\n"
                f"<u>Please use international format.</u>\n"
                f"<i>Example: <code>+1234567890</code></i>",
                parse_mode=ParseMode.HTML,
                reply_markup=kb([[InlineKeyboardButton("Back", callback_data="menu_main")]])
            )
            return
        status_msg = await m.reply(
            f"<blockquote><b>⏳ Hold! We’re trying to OTP...</b></blockquote>\n\n"
            f"<u>Phone:</u> <code>{text}</code> \n"
            f"<i>Please wait a moment.</i> ",
            parse_mode=ParseMode.HTML
        )
        try:
            tg = TelegramClient(StringSession(), config.API_ID, config.API_HASH)
            await tg.connect()
            sent_code = await tg.send_code_request(text)
            session_str = tg.session.save()

            temp_dict = {
                "phone": text,
                "session_str": session_str,
                "phone_code_hash": sent_code.phone_code_hash,
                "otp": ""
            }

            temp_json = json.dumps(temp_dict)
            temp_encrypted = cipher_suite.encrypt(temp_json.encode()).decode()
            db.set_temp_data(uid, temp_encrypted)
            db.set_user_state(uid, "telethon_wait_otp")

            base_caption = (
                f"<blockquote><b>╰_╯ OTP sent to <code>{text}</code>! ✅</b></blockquote>\n\n"
                f"Enter the OTP using the keypad below\n"
                f"<b>Current:</b> <code>_____</code>\n"
                f"<b>Format:</b> <code>12345</code> (no spaces needed)\n"
                f"<i>Valid for:</i> <u>{config.OTP_EXPIRY // 60} minutes</u>"
            )

            await status_msg.edit_caption(
                base_caption,
                parse_mode=ParseMode.HTML,
                reply_markup=get_otp_keyboard()
            )
            await send_dm_log(uid, f"<b>╰_╯ OTP requested for phone number:</b> <code>{text}</code>")
        except PhoneNumberInvalidError:
            await status_msg.edit_caption(
                f"<blockquote><b>❌ Invalid phone number! </b></blockquote>\n\n"
                f"<u>Please check the number and try again.</u>",
                parse_mode=ParseMode.HTML,
                reply_markup=kb([[InlineKeyboardButton("Back", callback_data="menu_main")]])
            )
        except Exception as e:
            logger.error(f"Failed to send OTP for {uid}: {e}")
            db.set_user_state(uid, "")
            await status_msg.edit_caption(
                f"<blockquote><b>❌ Failed to send OTP!</b></blockquote>\n\n"
                f"<u>Error:</u> <i>{str(e)}</i>\n"
                f"<b>Contact support:</b> @{config.ADMIN_USERNAME}",
                parse_mode=ParseMode.HTML,
                reply_markup=kb([[InlineKeyboardButton("Back", callback_data="menu_main")]])
            )
            await send_dm_log(uid, f"<b>❌ Failed to send OTP for phone:</b> {str(e)}")
        finally:
            await tg.disconnect()
    elif state == "telethon_wait_password":
        temp_encrypted = db.get_temp_data(uid)
        if not temp_encrypted:
            await m.reply(
                f"<blockquote><b>❌ Session expired!</b></blockquote>\n\n"
                f"<u>Please restart the process.</u>",
                parse_mode=ParseMode.HTML,
                reply_markup=kb([[InlineKeyboardButton("Back", callback_data="menu_main")]])
            )
            db.set_user_state(uid, "")
            return

        try:
            temp_json = cipher_suite.decrypt(temp_encrypted.encode()).decode()
            temp_dict = json.loads(temp_json)
            phone = temp_dict["phone"]
            session_str = temp_dict["session_str"]
        except (json.JSONDecodeError, Fernet.InvalidToken) as e:
            logger.error(f"Invalid temp data for user {uid} in 2FA: {e}")
            await m.reply(
                f"<blockquote><b>❌ Corrupted session data!</b></blockquote>\n\n"
                f"<b>Please restart the process.</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=kb([[InlineKeyboardButton("Back", callback_data="menu_main")]])
            )
            db.set_user_state(uid, "")
            db.set_temp_data(uid, None)
            return

        tg = TelegramClient(StringSession(session_str), config.API_ID, config.API_HASH)
        try:
            await tg.connect()
            await tg.sign_in(password=text)
            session_encrypted = cipher_suite.encrypt(session_str.encode()).decode()
            db.add_user_account(uid, phone, session_encrypted)
            await m.reply(
                f"<blockquote><b>╰_╯Account added!✅ </b></blockquote>\n\n"
                f"<u>Phone:</u> <code>{phone}</code>\n"
                "•Account is ready for broadcasting!",
                parse_mode=ParseMode.HTML,
                reply_markup=kb([[InlineKeyboardButton("Dashboard", callback_data="menu_main")]])
            )
            await send_dm_log(uid, f"<b>╰_╯Account added successfully ✅:</b> <code>{phone}</code> ✨")
            db.set_user_state(uid, "")
            db.set_temp_data(uid, None)
        except PasswordHashInvalidError:
            await m.reply(
                f"<blockquote><b>⚠️ Invalid password!</b></blockquote>\n\n"
                f"<u>Please try again.</u>",
                parse_mode=ParseMode.HTML,
                reply_markup=kb([[InlineKeyboardButton("Back 🔙", callback_data="menu_main")]])
            )
        except Exception as e:
            logger.error(f"Failed to sign in with password for {uid}: {e}")
            db.set_user_state(uid, "")
            db.set_temp_data(uid, None)
            await m.reply(
                f"<blockquote><b>❌ Login failed!</b></blockquote>\n\n"
                f"<u>Error:</u> <i>{str(e)}</i>\n"
                f"<b>Contact support:</b> @{config.ADMIN_USERNAME}",
                parse_mode=ParseMode.HTML,
                reply_markup=kb([[InlineKeyboardButton("Dashboard 🚪", callback_data="menu_main")]])
            )
            await send_dm_log(uid, f"<b>╰_╯Account login failed:❌</b> {str(e)}")
        finally:
            await tg.disconnect()

async def main():
    await pyro.start()
    await logger_client.start()
    try:
        await idle()
    except KeyboardInterrupt:
        for uid, task in list(user_tasks.items()):
            task.cancel()
        db.close()
        logger.info("Bot stopped gracefully")

if __name__ == "__main__":
    pyro.run(main())
