#!/usr/bin/env python3
# Telegram service bot starter for Termux
# Python 3.10+ | python-telegram-bot v21+
# Configure BOT_TOKEN and ADMIN_IDS (comma-separated Telegram IDs) before running.

import os
import html
import sqlite3
import logging
import shutil
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "").strip()
if not TOKEN or not ADMIN_IDS_RAW:
    raise SystemExit('Set BOT_TOKEN and ADMIN_IDS, e.g. ADMIN_IDS="111,222,333"')
try:
    ADMIN_IDS = {int(x.strip()) for x in ADMIN_IDS_RAW.split(",") if x.strip()}
except ValueError:
    raise SystemExit("ADMIN_IDS must contain Telegram numeric IDs separated by commas.")
if not ADMIN_IDS:
    raise SystemExit("Set at least one Telegram ID in ADMIN_IDS.")
DB_PATH = os.getenv("BOT_DB", "service_bot.db")

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger(__name__)

# Default button labels. Admins can rename these from the Admin menu.
BUTTON_DEFAULTS = {
    "account": "👤 គណនី",
    "deposit": "💳 បញ្ចូលលុយ",
    "order": "🛒 បញ្ជាទិញសេវា",
    "history": "📜 ប្រវត្តិការបញ្ជាទិញ",
    "track": "🔎 តាមដានការបញ្ជាទិញ",
    "help": "💬 ជំនួយ Admin",
    "guide": "💡 របៀបប្រើប្រាស់",
    "buy_robux": "🛍️ ទិញ Robux",
    "top_robux": "🏆 Top 10 Robux",
    "ai_help": "🤖 ជំនួយស្វ័យប្រវត្តិ",
}
BTN_ADMIN = "⚙️ Admin"
BTN_EDIT_BUTTONS = "📝 កែឈ្មោះប៊ូតុង"
BTN_MANAGE_BUTTONS = "➕➖ ដាក់/លុបប៊ូតុង"
BTN_SET_CONTACT = "💬 កំណត់ទំនាក់ទំនង Admin"
BTN_SET_WELCOME = "🖼️ កំណត់រូប និងសារស្វាគមន៍"
BTN_BUY_ROBUX = "🛍️ ទិញ Robux"
BTN_AI_HELP = "🤖 ជំនួយស្វ័យប្រវត្តិ"
BTN_SET_ROBUX_QR = "🖼️ កំណត់ QR និងសារទិញ Robux"
BTN_COPY_BOT = "📋 Copy BOT"
BTN_PREMIUM_EMOJI = "💎 កំណត់ Premium Emoji"
BTN_SAVED_EMOJIS = "💎 Emoji ដែលបានរក្សាទុក"
BTN_BUTTON_EMOJI = "💎 កំណត់ Premium Emoji លើប៊ូតុង"
BTN_ADD_ADMIN = "👥 Add Admin តាម ID"
BTN_EDIT_GUIDE = "📝 កែរបៀបប្រើប្រាស់"
COPY_BOT_ROOT = Path(os.getenv("COPY_BOT_ROOT", str(Path.home() / "copied_bots"))).expanduser()
DEFAULT_ROBUX_QR_CAPTION = (
    "💎 ការទិញ Robux\n"
    "សូមស្កេន QR ដើម្បីទូទាត់ចំនួនខាងលើ។\n"
    "បន្ទាប់ពីបង់ប្រាក់ សូមផ្ញើរូប Screenshot បញ្ជាក់ការទូទាត់មកទីនេះ។\n"
    "⚠️ សូមកុំផ្ញើ Password ឬលេខកូដសម្ងាត់ Roblox។ Admin នឹងពិនិត្យមុនបំពេញការបញ្ជាទិញ។"
)
DEFAULT_WELCOME_TEXT = "សូមស្វាគមន៍មកកាន់ Bot សេវាកម្ម!\nជ្រើសរើសមុខងារខាងក្រោម។"
DEFAULT_CONTACT_MESSAGE = "💬 សូមផ្ញើសារទៅ Admin៖ @PISETHTOPUPROBUXBOT"

# Keep these constants as fallback labels for old code or help text.
BTN_ACCOUNT = BUTTON_DEFAULTS["account"]
BTN_DEPOSIT = BUTTON_DEFAULTS["deposit"]
BTN_ORDER = BUTTON_DEFAULTS["order"]
BTN_HISTORY = BUTTON_DEFAULTS["history"]
BTN_TRACK = BUTTON_DEFAULTS["track"]
BTN_HELP = BUTTON_DEFAULTS["help"]
BTN_GUIDE = BUTTON_DEFAULTS["guide"]

def get_button_labels():
    labels = BUTTON_DEFAULTS.copy()
    try:
        with db() as c:
            rows = c.execute("SELECT key, value FROM settings WHERE key LIKE 'button_%'").fetchall()
        for row in rows:
            key = row["key"][7:]
            if key in labels and row["value"].strip():
                labels[key] = row["value"]
    except sqlite3.OperationalError:
        pass
    return labels

def keyboard_button(button_key: str, label: str):
    """Build a colored Telegram reply-keyboard button with an optional custom emoji icon.

    Requires python-telegram-bot 22.7+ and Telegram Bot API 9.4+.
    """
    styles = {
        "account": "success",       # green
        "deposit": "primary",      # blue
        "order": "success",        # green
        "buy_robux": "success",    # green
        "ai_help": "success",      # green
        "history": "success",      # green
        "track": "success",        # green
        "help": "success",         # green
        "guide": "primary",        # blue
    }
    kwargs = {"text": label, "style": styles.get(button_key, "success")}
    emoji_id = get_button_custom_emoji_id(button_key)
    if emoji_id.isdigit():
        kwargs["icon_custom_emoji_id"] = emoji_id
    try:
        return KeyboardButton(**kwargs)
    except TypeError:
        log.error("python-telegram-bot is too old for styled/custom-emoji buttons; upgrade to 22.7+")
        return KeyboardButton(label)


def main_keyboard():
    labels = get_button_labels()
    # Admin can hide/show each built-in user button; hidden buttons are not shown on keyboard.
    keys = ["account", "deposit", "order", "buy_robux", "ai_help", "history", "track", "help", "guide", "top_robux"]
    defaults = {}
    visible = {}
    for key in keys:
        visible[key] = get_setting(f"button_visible_{key}", "1") != "0"
    label_for = {**labels, **defaults}
    rows = []
    pair = [keyboard_button(k, label_for[k]) for k in ("account", "deposit") if visible[k]]
    if pair: rows.append(pair)
    for key in ("order",):
        if visible[key]: rows.append([keyboard_button(key, label_for[key])])
    pair = [keyboard_button(k, label_for[k]) for k in ("buy_robux", "ai_help") if visible[k]]
    if pair: rows.append(pair)
    pair = [keyboard_button(k, label_for[k]) for k in ("history", "track") if visible[k]]
    if pair: rows.append(pair)
    pair = [keyboard_button(k, label_for[k]) for k in ("help", "guide") if visible[k]]
    if pair: rows.append(pair)
    if visible["top_robux"]: rows.append([keyboard_button("top_robux", label_for["top_robux"])])
    return ReplyKeyboardMarkup(rows or [[KeyboardButton(BTN_ADMIN)]], resize_keyboard=True)

ADMIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("➕ បន្ថែមសមតុល្យ"), KeyboardButton("📢 ផ្ញើសារទៅអ្នកប្រើទាំងអស់")],
        [KeyboardButton("➕ បន្ថែមសេវា"), KeyboardButton("🗑️ លុបសេវាកម្ម")],
        [KeyboardButton("📋 គ្រប់គ្រងការបញ្ជាទិញ")],
        [KeyboardButton("🖼️ កំណត់ QR ដាក់ប្រាក់")],
        [KeyboardButton(BTN_SET_ROBUX_QR)],
        [KeyboardButton(BTN_COPY_BOT)],
        [KeyboardButton("🛠️ គ្រប់គ្រង Copy Bot")],
        [KeyboardButton(BTN_PREMIUM_EMOJI)],
        [KeyboardButton(BTN_SAVED_EMOJIS)],
        [KeyboardButton(BTN_BUTTON_EMOJI)],
        [KeyboardButton(BTN_ADD_ADMIN)],
        [KeyboardButton(BTN_EDIT_BUTTONS)],
        [KeyboardButton(BTN_MANAGE_BUTTONS)],
        [KeyboardButton(BTN_SET_CONTACT)],
        [KeyboardButton(BTN_EDIT_GUIDE)],
        [KeyboardButton(BTN_SET_WELCOME)],
        [KeyboardButton("⬅️ ត្រឡប់ទៅម៉ឺនុយ")],
    ],
    resize_keyboard=True
)

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS extra_admins(user_id INTEGER PRIMARY KEY, added_by INTEGER NOT NULL, added_at TEXT NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS saved_custom_emojis(emoji_id TEXT PRIMARY KEY, added_by INTEGER NOT NULL, added_at TEXT NOT NULL)")
        c.execute("""CREATE TABLE IF NOT EXISTS robux_orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, username TEXT NOT NULL,
            roblox_username TEXT NOT NULL, amount INTEGER NOT NULL, price REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL, completed_at TEXT DEFAULT '')""")
        c.execute("""CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY, username TEXT, balance REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS deposits(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            amount REAL NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS services(
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            price REAL NOT NULL, description TEXT DEFAULT '', active INTEGER NOT NULL DEFAULT 1)""")
        c.execute("""CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            service_id INTEGER NOT NULL, service_name TEXT NOT NULL,
            target TEXT NOT NULL, price REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL)""")
        count = c.execute("SELECT COUNT(*) n FROM services").fetchone()["n"]
        if count == 0:
            c.executemany(
                "INSERT INTO services(name, price, description) VALUES(?,?,?)",
                [
                    ("សេវាគំរូ 1", 1.00, "កែឈ្មោះ និងតម្លៃក្នុង Admin"),
                    ("សេវាគំរូ 2", 2.00, "កែឈ្មោះ និងតម្លៃក្នុង Admin"),
                ],
            )

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def get_setting(key: str, default: str = "") -> str:
    with db() as c:
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default

def save_setting(key: str, value: str):
    with db() as c:
        c.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value)
        )


def get_button_custom_emoji_id(button_key: str) -> str:
    return get_setting(f"button_custom_emoji_{button_key}", "").strip()

async def send_button_custom_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE, button_key: str):
    """Keyboard button text cannot contain custom-emoji entities; show assigned emoji in chat after button press."""
    emoji_id = get_button_custom_emoji_id(button_key)
    if emoji_id.isdigit() and update.effective_message:
        try:
            await update.effective_message.reply_text(
                f'<tg-emoji emoji-id="{html.escape(emoji_id)}">💎</tg-emoji>',
                parse_mode="HTML"
            )
        except Exception as exc:
            log.warning("Could not render custom emoji for button %s: %s", button_key, exc)

async def send_deposit_qr(chat_id: int, amount: float, deposit_id: int, context: ContextTypes.DEFAULT_TYPE):
    qr_file_id = get_setting("deposit_qr_file_id")
    caption = (
        f"💳 សំណើបញ្ចូលប្រាក់ #{deposit_id}\n"
        f"💵 ចំនួន៖ ${amount:.2f}\n\n"
        "សូមស្កេន QR ដើម្បីទូទាត់ ហើយផ្ញើរូប/វិក្កយបត្របញ្ជាក់ការទូទាត់មកទីនេះ។\n"
        "⚠️ សមតុល្យនឹងកើនឡើងក្រោយ Admin ពិនិត្យ និងអនុម័តប៉ុណ្ណោះ។"
    )
    if qr_file_id:
        await context.bot.send_photo(chat_id=chat_id, photo=qr_file_id, caption=caption)
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"{caption}\nមិនទាន់មាន QR ទេ។ សូមទាក់ទង Admin។"
        )

def ensure_user(user):
    with db() as c:
        c.execute(
            "INSERT INTO users(user_id, username, created_at) VALUES(?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET username=excluded.username",
            (user.id, user.username or "", now())
        )

def is_admin(update: Update) -> bool:
    if not update.effective_user:
        return False
    uid = update.effective_user.id
    if uid in ADMIN_IDS:
        return True
    try:
        with db() as c:
            return c.execute("SELECT 1 FROM extra_admins WHERE user_id=?", (uid,)).fetchone() is not None
    except sqlite3.OperationalError:
        return False


def is_owner(update: Update) -> bool:
    # Only IDs configured in ADMIN_IDS can add/remove other admins.
    return bool(update.effective_user and update.effective_user.id in ADMIN_IDS)

async def notify_admins(context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None):
    """Send an admin notification to every configured admin account."""
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, text, reply_markup=reply_markup)
        except Exception as exc:
            log.warning("Could not notify admin %s: %s", admin_id, exc)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.effective_user)
    welcome_text = get_setting("welcome_text", DEFAULT_WELCOME_TEXT)
    welcome_photo = get_setting("welcome_photo_file_id", "")
    premium_id = get_setting("premium_emoji_id", "").strip()
    # Render every 5+ digit custom_emoji_id anywhere in the welcome text as a Premium emoji.
    # Supports IDs at the start of a line, ID|text, and IDs embedded anywhere in the message.
    import re
    rendered_parts = []
    for line in welcome_text.splitlines():
        lead = re.match(r"^(\d{5,})(?:\s*\|\s*|\s+)(.*)$", line.strip())
        if lead:
            emoji_id, body = lead.group(1), lead.group(2)
            rendered_parts.append(f'<tg-emoji emoji-id="{emoji_id}">💎</tg-emoji> {html.escape(body)}')
            continue
        pieces = []
        last = 0
        for match in re.finditer(r"(?<!\d)(\d{5,})(?!\d)", line):
            pieces.append(html.escape(line[last:match.start()]))
            emoji_id = match.group(1)
            pieces.append(f'<tg-emoji emoji-id="{emoji_id}">💎</tg-emoji>')
            last = match.end()
        pieces.append(html.escape(line[last:]))
        rendered_parts.append("".join(pieces))
    safe_text = "\n".join(rendered_parts)
    # Preserve the legacy single welcome emoji setting when configured.
    if premium_id.isdigit():
        safe_text = f'<tg-emoji emoji-id="{premium_id}">💎</tg-emoji> ' + safe_text
    if welcome_photo:
        await update.message.reply_photo(
            photo=welcome_photo,
            caption=safe_text,
            parse_mode="HTML",
            reply_markup=main_keyboard()
        )
    else:
        await update.message.reply_text(safe_text, parse_mode="HTML", reply_markup=main_keyboard())

async def stars_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Public /stars command; explains Telegram Stars support for this service bot."""
    await update.message.reply_text(
        "⭐ Telegram Stars\n\n"
        "បើបងចង់បង់ប្រាក់ដោយ Telegram Stars សូមទាក់ទង Admin ដើម្បីពិនិត្យសេវាកម្មដែលគាំទ្រ។\n"
        "សូមកុំផ្ញើ Password ឬលេខកូដសម្ងាត់។",
        reply_markup=main_keyboard()
    )


async def setup_bot_commands(app: Application):
    # Telegram command names must be lowercase; /admin is displayed in the menu.
    await app.bot.set_my_commands([
        BotCommand("start", "ចាប់ផ្តើម Bot"),
        BotCommand("stars", "Telegram Stars"),
        BotCommand("admin", "Admin panel (សម្រាប់ Admin)"),
        BotCommand("cancel", "បោះបង់សកម្មភាព"),
    ])


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("បានបោះបង់ជំហានបច្ចុប្បន្ន។", reply_markup=main_keyboard())

async def premium_buttons_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Open the per-button custom emoji settings directly with /premium_buttons."""
    if not is_admin(update):
        await update.message.reply_text("⛔ មុខងារនេះសម្រាប់ Admin ប៉ុណ្ណោះ។")
        return
    labels = get_button_labels()
    choices = {labels[key]: key for key in BUTTON_DEFAULTS}
    choices["💎 Robux តម្លៃ / កញ្ចប់ទាំងអស់"] = "robux_package"
    context.user_data["premium_button_choices"] = choices
    context.user_data["state"] = "admin_choose_premium_button"
    rows = [[KeyboardButton(label)] for label in choices]
    rows.append([KeyboardButton("⬅️ ត្រឡប់ទៅ Admin")])
    await update.message.reply_text(
        "💎 កំណត់ Premium Emoji តាមប៊ូតុង\n"
        "ជ្រើសឈ្មោះប៊ូតុង រួចផ្ញើ custom_emoji_id។\n"
        "ត្រូវការ python-telegram-bot 22.7+ និង Telegram Bot API 9.4+។\n"
        "បើប៊ូតុងមិនបង្ហាញ icon សូមពិនិត្យថាគណនីម្ចាស់ Bot មាន Telegram Premium និងធ្វើ /start ម្ដងទៀត។",
        reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
    )

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ មុខងារនេះសម្រាប់ Admin ប៉ុណ្ណោះ។")
        return
    context.user_data.clear()
    await update.message.reply_text("⚙️ ម៉ឺនុយ Admin", reply_markup=ADMIN_KEYBOARD)

async def show_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    with db() as c:
        row = c.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
        order_count = c.execute("SELECT COUNT(*) n FROM orders WHERE user_id=?", (uid,)).fetchone()["n"]
    balance = row["balance"] if row else 0
    await update.message.reply_text(
        f"👤 គណនីរបស់អ្នក\n━━━━━━━━━━━━\n🆔 ID: `{uid}`\n💰 សមតុល្យ: ${balance:.2f}\n📦 ការបញ្ជាទិញ: {order_count}",
        parse_mode="Markdown", reply_markup=main_keyboard()
    )

async def deposit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("$1", callback_data="deposit:1"),
         InlineKeyboardButton("$2", callback_data="deposit:2"),
         InlineKeyboardButton("$5", callback_data="deposit:5")],
        [InlineKeyboardButton("$10", callback_data="deposit:10"),
         InlineKeyboardButton("$20", callback_data="deposit:20"),
         InlineKeyboardButton("$50", callback_data="deposit:50")],
        [InlineKeyboardButton("បញ្ចូលចំនួនផ្សេង", callback_data="deposit:custom")]
    ])
    await update.message.reply_text(
        "💳 ជ្រើសរើសចំនួនទឹកប្រាក់ដែលចង់បញ្ចូល។\n"
        "នេះជាការស្នើសុំបញ្ចូលលុយប៉ុណ្ណោះ—Admin ត្រូវពិនិត្យការទូទាត់ និងអនុម័តដោយដៃ។",
        reply_markup=kb
    )

async def top_robux_text():
    """Persistent Top 10 based only on Robux orders an admin marked completed."""
    with db() as c:
        rows = c.execute("""SELECT user_id, MAX(username) AS username, SUM(amount) AS total_robux, COUNT(*) AS orders_count
            FROM robux_orders WHERE status='completed'
            GROUP BY user_id ORDER BY total_robux DESC, orders_count DESC, user_id ASC LIMIT 10""").fetchall()
    if not rows:
        return "🏆 TOP 10 អ្នកទិញ Robux ច្រើនជាងគេ\n\nមិនទាន់មានការបញ្ជាទិញ Robux ដែល Admin បានបញ្ជាក់ថារួចរាល់ទេ។"
    top_emoji_id = get_setting("button_custom_emoji_top_robux", "").strip()
    heading = (f'<tg-emoji emoji-id="{top_emoji_id}">🏆</tg-emoji> TOP 10 អ្នកទិញ Robux ច្រើនជាងគេ'
               if top_emoji_id.isdigit() else "🏆 TOP 10 អ្នកទិញ Robux ច្រើនជាងគេ")
    lines = [heading, "📊 គិតតែ Robux ដែល Admin បានចុចថា រួចរាល់", ""]
    medals = ["🥇", "🥈", "🥉"]
    for i, row in enumerate(rows, 1):
        medal = medals[i-1] if i <= 3 else f"{i}."
        name = ("@" + row["username"]) if row["username"] else f"User {row['user_id']}"
        lines.append(f"{medal} {name} — {row['total_robux']:,} Robux")
    return "\n".join(lines)


async def show_top_robux(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = await top_robux_text()
    if update.callback_query:
        await update.callback_query.message.reply_text(text, parse_mode="HTML", reply_markup=main_keyboard())
    elif update.message:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=main_keyboard())


async def robux_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show Robux packages from 10 through 1000, priced at $0.01 per Robux."""
    rows = []
    amounts = list(range(10, 101, 10)) + list(range(200, 1001, 100))
    for i in range(0, len(amounts), 3):
        row = []
        for amount in amounts[i:i+3]:
            price = amount / 100
            kwargs = {"text": f"{amount} Robux — ${price:.2f}", "callback_data": f"robux:{amount}"}
            package_emoji_id = get_setting("button_custom_emoji_robux_package", "").strip()
            if package_emoji_id.isdigit():
                kwargs["icon_custom_emoji_id"] = package_emoji_id
            try:
                row.append(InlineKeyboardButton(**kwargs))
            except TypeError:
                kwargs.pop("icon_custom_emoji_id", None)
                row.append(InlineKeyboardButton(**kwargs))
        rows.append(row)
    await update.message.reply_text(
        "🛍️ ជ្រើសរើសចំនួន Robux ដែលចង់ទិញ៖\nតម្លៃ៖ 100 Robux = $1.00",
        reply_markup=InlineKeyboardMarkup(rows)
    )

def _sync_copybots_to_latest():
    """Push the master bot's latest code and appearance settings to every copied bot.
    Copied instances never run this sync themselves, preventing version ping-pong.
    """
    source = Path(__file__).resolve()
    root = COPY_BOT_ROOT.resolve()
    # A copied bot must never overwrite the master version with its own code.
    if root == source.parent or root in source.parents:
        return
    try:
        source_bytes = source.read_bytes()
    except OSError:
        log.exception("Cannot read master bot script for Copy BOT sync")
        return

    # Appearance/config settings and saved custom emoji IDs are shared from master.
    master_settings = []
    master_emojis = []
    try:
        with sqlite3.connect(DB_PATH) as conn:
            master_settings = conn.execute("SELECT key, value FROM settings").fetchall()
            master_emojis = conn.execute(
                "SELECT emoji_id, added_by, added_at FROM saved_custom_emojis"
            ).fetchall()
    except sqlite3.Error:
        log.exception("Cannot read master settings for Copy BOT sync")

    for bot_dir in _copybot_dirs():
        script_path = bot_dir / "bot.py"
        try:
            old_bytes = script_path.read_bytes() if script_path.exists() else b""
            changed = old_bytes != source_bytes
            running = _copybot_pid(bot_dir)
            if changed and running:
                try:
                    os.kill(running, 15)
                except OSError:
                    pass
                # Wait briefly so the old process releases Telegram polling.
                import time
                for _ in range(20):
                    try:
                        os.kill(running, 0)
                    except OSError:
                        break
                    time.sleep(0.1)
                try:
                    os.kill(running, 9)
                except OSError:
                    pass

            if changed:
                temp_path = bot_dir / "bot.py.new"
                temp_path.write_bytes(source_bytes)
                os.chmod(temp_path, 0o600)
                temp_path.replace(script_path)
                log.info("Updated Copy BOT code: %s", bot_dir.name)

            # Preserve each copied bot's users/orders/balances while refreshing
            # appearance settings and premium custom emoji IDs from the master.
            db_path = bot_dir / "service_bot.db"
            if db_path.exists() and (master_settings or master_emojis):
                with sqlite3.connect(db_path) as conn:
                    conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                    conn.execute("""CREATE TABLE IF NOT EXISTS saved_custom_emojis (
                        emoji_id TEXT PRIMARY KEY, added_by INTEGER NOT NULL, added_at TEXT NOT NULL
                    )""")
                    # Seed only settings that are missing in the copied bot.
                    # Never overwrite per-copy customizations (QR, welcome text,
                    # guide, labels, captions, etc.) during master sync/restart.
                    conn.executemany(
                        "INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",
                        master_settings
                    )
                    # Merge master emoji IDs without deleting emojis saved in a copy.
                    conn.executemany(
                        "INSERT OR IGNORE INTO saved_custom_emojis(emoji_id,added_by,added_at) VALUES(?,?,?)",
                        master_emojis
                    )

            if changed and running:
                try:
                    _copybot_start(bot_dir)
                except Exception:
                    log.exception("Failed to restart updated Copy BOT: %s", bot_dir.name)
        except Exception:
            log.exception("Could not sync Copy BOT: %s", bot_dir.name)


def _copybot_dirs():
    COPY_BOT_ROOT.mkdir(parents=True, exist_ok=True)
    return sorted([p for p in COPY_BOT_ROOT.iterdir() if p.is_dir() and (p / "run.sh").exists()], key=lambda p: p.name.lower())

def _copybot_pid(bot_dir: Path):
    try:
        pid = int((bot_dir / "pid").read_text(encoding="utf-8").strip())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError, FileNotFoundError):
        return None

def _copybot_start(bot_dir: Path):
    log_path = bot_dir / "bot.log"
    with log_path.open("ab") as log_file:
        proc = subprocess.Popen(["bash", str(bot_dir / "run.sh")], cwd=str(bot_dir), stdin=subprocess.DEVNULL,
                                stdout=log_file, stderr=subprocess.STDOUT, start_new_session=True)
    (bot_dir / "pid").write_text(str(proc.pid), encoding="utf-8")
    return proc.pid

def _copybot_stop(bot_dir: Path):
    pid = _copybot_pid(bot_dir)
    if not pid:
        return False
    try:
        os.kill(pid, 15)
        return True
    except OSError:
        return False

async def show_copybots(message, edit=False):
    dirs = _copybot_dirs()
    rows = []
    for i, d in enumerate(dirs[:40]):
        pid = _copybot_pid(d)
        status = "🟢 ដំណើរការ" if pid else "🔴 បិទ"
        label = d.name[:35]
        rows.append([InlineKeyboardButton(f"{status} · {label}", callback_data=f"copybot:detail:{i}")])
    if not dirs:
        text = "📋 មិនទាន់មាន Copy Bot ទេ។ ចុច 📋 Copy BOT ដើម្បីបង្កើត Bot ថ្មី។"
    else:
        text = "📋 គ្រប់គ្រង Copy Bot\nចុច Bot មួយ ដើម្បីបើក/បិទ ឬមើល Log។"
    markup = InlineKeyboardMarkup(rows) if rows else None
    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.reply_text(text, reply_markup=markup)

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    if data == "toprobux:show":
        await show_top_robux(update, context)
        return
    if data.startswith("robux:complete:"):
        if not is_admin(update):
            await q.answer("មុខងារនេះសម្រាប់ Admin ប៉ុណ្ណោះ។", show_alert=True)
            return
        try:
            order_id = int(data.rsplit(":", 1)[1])
        except ValueError:
            await q.answer("លេខបញ្ជាទិញមិនត្រឹមត្រូវ។", show_alert=True)
            return
        with db() as c:
            order = c.execute("SELECT * FROM robux_orders WHERE id=?", (order_id,)).fetchone()
            if not order:
                await q.answer("រកមិនឃើញសំណើ Robux នេះទេ។", show_alert=True)
                return
            if order["status"] == "completed":
                await q.answer("សំណើនេះបានបញ្ជាក់រួចហើយ។", show_alert=True)
                return
            c.execute("UPDATE robux_orders SET status='completed', completed_at=? WHERE id=?", (now(), order_id))
        try:
            await context.bot.send_message(
                chat_id=order["user_id"],
                text=(f"✅ ការបញ្ជាទិញ Robux របស់អ្នករួចរាល់ហើយ!\n"
                      f"💎 ចំនួន៖ {order['amount']:,} Robux\n💵 តម្លៃ៖ ${order['price']:.2f}\n"
                      f"🎮 Roblox Username៖ {order['roblox_username']}\n\nអរគុណសម្រាប់ការគាំទ្រ ❤️"),
                reply_markup=main_keyboard())
        except Exception:
            log.exception("Could not notify user about completed Robux order %s", order_id)
        await q.edit_message_reply_markup(reply_markup=None)
        await q.message.reply_text(f"✅ បានសម្គាល់សំណើ #{order_id} ជារួចរាល់។ អ្នកប្រើត្រូវបានជូនដំណឹង។")
        return
    if data == "copybot:list":
        if not is_admin(update):
            await q.message.reply_text("⛔ មុខងារនេះសម្រាប់ Admin ប៉ុណ្ណោះ។")
            return
        await show_copybots(q.message)
        return
    if data.startswith("copybot:detail:"):
        if not is_admin(update):
            await q.message.reply_text("⛔ មុខងារនេះសម្រាប់ Admin ប៉ុណ្ណោះ។")
            return
        try:
            idx = int(data.rsplit(":", 1)[1])
            dirs = _copybot_dirs()
            bot_dir = dirs[idx]
        except (ValueError, IndexError):
            await q.message.reply_text("មិនអាចរក Copy Bot នេះបានទេ។ សូមបើកបញ្ជីឡើងវិញ។")
            return
        pid = _copybot_pid(bot_dir)
        status = f"🟢 ដំណើរការ (PID {pid})" if pid else "🔴 បិទ"
        rows = [[InlineKeyboardButton("⏹ បិទ Bot", callback_data=f"copybot:stop:{idx}") if pid else InlineKeyboardButton("▶️ បើក Bot", callback_data=f"copybot:start:{idx}")],
                [InlineKeyboardButton("📄 មើល Log", callback_data=f"copybot:log:{idx}")],
                [InlineKeyboardButton("↩️ ត្រឡប់", callback_data="copybot:list")]]
        await q.message.reply_text(f"🤖 Copy Bot: {bot_dir.name}\nស្ថានភាព: {status}\nថត: {bot_dir}", reply_markup=InlineKeyboardMarkup(rows))
        return
    if data.startswith(("copybot:start:", "copybot:stop:", "copybot:log:")):
        if not is_admin(update):
            await q.message.reply_text("⛔ មុខងារនេះសម្រាប់ Admin ប៉ុណ្ណោះ។")
            return
        action, idx_text = data.split(":", 2)[1:]
        try:
            idx = int(idx_text)
            bot_dir = _copybot_dirs()[idx]
        except (ValueError, IndexError):
            await q.message.reply_text("មិនអាចរក Copy Bot នេះបានទេ។")
            return
        if action == "start":
            if _copybot_pid(bot_dir):
                result = "Bot នេះកំពុងដំណើរការរួចហើយ។"
            else:
                try:
                    pid = _copybot_start(bot_dir)
                    result = f"✅ បានបើក Bot វិញ (PID {pid})។"
                except Exception as exc:
                    log.exception("Could not start copied bot")
                    result = f"❌ បើកមិនបាន៖ {type(exc).__name__}។ ពិនិត្យ bot.log។"
            await q.message.reply_text(result)
        elif action == "stop":
            result = "⏹ បានបញ្ជាឱ្យបិទ Bot។" if _copybot_stop(bot_dir) else "Bot នេះមិនដំណើរការទេ។"
            await q.message.reply_text(result)
        else:
            try:
                lines = (bot_dir / "bot.log").read_text(encoding="utf-8", errors="replace").splitlines()[-18:]
                log_text = "\n".join(lines) or "Log ទទេ។"
                await q.message.reply_text("📄 Log ចុងក្រោយ:\n<pre>" + html.escape(log_text[-3500:]) + "</pre>", parse_mode="HTML")
            except Exception:
                await q.message.reply_text("មិនអាចអាន Log បានទេ។")
        return
    if data == "emoji:collect":
        if not is_admin(update):
            await q.message.reply_text("⛔ មុខងារនេះសម្រាប់ Admin ប៉ុណ្ណោះ។")
            return
        context.user_data["state"] = "admin_collect_custom_emojis"
        await q.message.reply_text(
            "💎 សូមផ្ញើសារដែលមាន Premium Custom Emoji មកទីនេះ។\n"
            "ខ្ញុំនឹងរក្សាទុក Emoji ID ដោយស្វ័យប្រវត្តិ។ អ្នកអាចផ្ញើច្រើនសារបាន។\n"
            "ពេលរួចរាល់ សូមផ្ញើ /cancel។"
        )
        return
    if data.startswith("emoji:use:"):
        emoji_id = data.split(":", 2)[2]
        await q.message.reply_text(f'<tg-emoji emoji-id="{html.escape(emoji_id)}">💎</tg-emoji>', parse_mode="HTML")
        return
    if data == "emoji:list":
        if not is_admin(update):
            await q.message.reply_text("⛔ មុខងារនេះសម្រាប់ Admin ប៉ុណ្ណោះ។")
            return
        with db() as c:
            emoji_rows = c.execute("SELECT emoji_id FROM saved_custom_emojis ORDER BY added_at DESC LIMIT 50").fetchall()
        keyboard = [[InlineKeyboardButton(f"💎 Emoji {i+1}", callback_data=f"emoji:use:{row['emoji_id']}")] for i, row in enumerate(emoji_rows)]
        keyboard.append([InlineKeyboardButton("➕ បន្ថែម Emoji", callback_data="emoji:collect")])
        if not emoji_rows:
            await q.message.reply_text("មិនទាន់មាន Emoji ដែលបានរក្សាទុកទេ។ ចុច ➕ បន្ថែម Emoji ដើម្បីផ្ញើ Custom Emoji មករក្សាទុក។", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await q.message.reply_text("💎 Emoji ដែលបានរក្សាទុក (ចុចមួយដើម្បីបង្ហាញវា):", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    if data.startswith("deposit:"):
        value = data.split(":", 1)[1]
        if value == "custom":
            context.user_data["state"] = "deposit_custom"
            await q.message.reply_text("សូមវាយចំនួនទឹកប្រាក់ជា USD (ឧ. 7.5):")
            return
        amount = float(value)
        with db() as c:
            cur = c.execute(
                "INSERT INTO deposits(user_id, amount, created_at) VALUES(?,?,?)",
                (q.from_user.id, amount, now())
            )
            deposit_id = cur.lastrowid
        await send_deposit_qr(q.from_user.id, amount, deposit_id, context)
        try:
            await notify_admins(
                context,
                f"💳 សំណើបញ្ចូលលុយ #{deposit_id}\nUser ID: {q.from_user.id}\nចំនួន: ${amount:.2f}\n"
                f"អនុម័ត៖ /approve_deposit {deposit_id}\nបដិសេធ៖ /reject_deposit {deposit_id}"
            )
        except Exception:
            log.exception("Could not notify admin")
    elif data.startswith("robux:"):
        try:
            amount = int(data.split(":", 1)[1])
        except ValueError:
            await q.message.reply_text("ចំនួន Robux មិនត្រឹមត្រូវទេ។")
            return
        valid_amounts = set(list(range(10, 101, 10)) + list(range(200, 1001, 100)))
        if amount not in valid_amounts:
            await q.message.reply_text("សូមជ្រើសចំនួន Robux ពីបញ្ជី។")
            return
        context.user_data["robux_amount"] = amount
        context.user_data["robux_price"] = amount / 100
        context.user_data["state"] = "robux_waiting_username"
        await q.message.reply_text(
            f"✅ អ្នកបានជ្រើស {amount} Robux — ${amount/100:.2f}\n"
            "សូមផ្ញើ Roblox Username របស់អ្នក (កុំផ្ញើ Password)។\n"
            "វាយ /cancel ដើម្បីបោះបង់។"
        )
    elif data.startswith("service:"):
        sid = int(data.split(":", 1)[1])
        with db() as c:
            s = c.execute("SELECT * FROM services WHERE id=? AND active=1", (sid,)).fetchone()
        if not s:
            await q.message.reply_text("សេវានេះមិនមានទៀតទេ។")
            return
        context.user_data["state"] = "order_target"
        context.user_data["service_id"] = sid
        await q.message.reply_text(
            f"សេវា៖ {s['name']}\nតម្លៃ៖ ${s['price']:.2f}\n"
            "សូមផ្ញើ Link ឬព័ត៌មានគោលដៅដែលត្រូវការសេវា៖"
        )
    elif data.startswith("svcdelete:"):
        if not is_admin(update):
            await q.answer("មុខងារនេះសម្រាប់ Admin ប៉ុណ្ណោះ។", show_alert=True)
            return
        action = data.split(":", 1)[1]
        if action == "cancel":
            context.user_data.pop("services_to_delete", None)
            await q.edit_message_text("បានបោះបង់ការលុបសេវាកម្ម។")
            return
        if action == "confirm":
            selected = context.user_data.get("services_to_delete", set())
            if not selected:
                await q.answer("សូមជ្រើសរើសសេវាកម្មយ៉ាងហោចណាស់ 1។", show_alert=True)
                return
            ids = [int(x) for x in selected]
            with db() as c:
                placeholders = ",".join("?" for _ in ids)
                c.execute(f"UPDATE services SET active=0 WHERE id IN ({placeholders})", ids)
            context.user_data.pop("services_to_delete", None)
            await q.edit_message_text(f"✅ បានលុប/លាក់សេវាកម្មចំនួន {len(ids)} មុខពីបញ្ជីអ្នកប្រើ។ ប្រវត្តិការបញ្ជាទិញចាស់នៅរក្សាទុកដដែល។")
            return
        if action.startswith("toggle:"):
            try:
                sid = int(action.split(":", 1)[1])
            except ValueError:
                await q.answer("លេខសេវាកម្មមិនត្រឹមត្រូវ។", show_alert=True)
                return
            selected = set(context.user_data.get("services_to_delete", set()))
            sid_text = str(sid)
            if sid_text in selected:
                selected.remove(sid_text)
            else:
                selected.add(sid_text)
            context.user_data["services_to_delete"] = selected
            with db() as c:
                services = c.execute("SELECT id,name,price FROM services WHERE active=1 ORDER BY id").fetchall()
            rows = []
            for service in services:
                mark = "☑️" if str(service["id"]) in selected else "⬜"
                rows.append([InlineKeyboardButton(f"{mark} {service['name']} — ${service['price']:.2f}", callback_data=f"svcdelete:toggle:{service['id']}")])
            rows.append([InlineKeyboardButton("✅ លុបសេវាដែលបានជ្រើស", callback_data="svcdelete:confirm")])
            rows.append([InlineKeyboardButton("❌ បោះបង់", callback_data="svcdelete:cancel")])
            await q.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(rows))
            await q.answer()
            return
    elif data.startswith("status:"):
        if not is_admin(update):
            return
        _, order_id, status = data.split(":")
        with db() as c:
            c.execute("UPDATE orders SET status=? WHERE id=?", (status, int(order_id)))
            order = c.execute("SELECT user_id FROM orders WHERE id=?", (int(order_id),)).fetchone()
        await q.message.reply_text(f"បានកែស្ថានភាពការបញ្ជាទិញ #{order_id} ទៅជា {status}")
        if order:
            try:
                await context.bot.send_message(order["user_id"], f"📦 ការបញ្ជាទិញ #{order_id}៖ {status}")
            except Exception:
                pass

async def order_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with db() as c:
        services = c.execute("SELECT * FROM services WHERE active=1 ORDER BY id").fetchall()
    if not services:
        await update.message.reply_text("បច្ចុប្បន្នមិនមានសេវាកម្មទេ។")
        return
    buttons = [
        [InlineKeyboardButton(f"{s['name']} — ${s['price']:.2f}", callback_data=f"service:{s['id']}")]
        for s in services
    ]
    await update.message.reply_text("🛒 ជ្រើសរើសសេវាកម្ម៖", reply_markup=InlineKeyboardMarkup(buttons))

async def order_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with db() as c:
        rows = c.execute(
            "SELECT id, service_name, price, status, created_at FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 10",
            (update.effective_user.id,)
        ).fetchall()
    if not rows:
        await update.message.reply_text("អ្នកមិនទាន់មានប្រវត្តិបញ្ជាទិញទេ។")
        return
    lines = ["📜 ប្រវត្តិការបញ្ជាទិញ (10 ចុងក្រោយ)"]
    for r in rows:
        lines.append(f"#{r['id']} | {r['service_name']} | ${r['price']:.2f} | {r['status']}")
    await update.message.reply_text("\n".join(lines))

async def track_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = "track_order"
    await update.message.reply_text("សូមវាយលេខ Order ID ដែលចង់តាមដាន៖")

async def help_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Contact message is configurable by an Admin from /admin.
    contact_message = get_setting("contact_admin_message", DEFAULT_CONTACT_MESSAGE)
    await update.message.reply_text(contact_message)

async def guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin-configurable usage guide with optional custom emoji per line."""
    saved = get_setting("custom_guide_lines", "").strip()
    if not saved:
        saved = (
            "💡 របៀបប្រើប្រាស់\n"
            "1. ចុច គណនី ដើម្បីមើលសមតុល្យ។\n"
            "2. ចុច ទិញ Robux ដើម្បីជ្រើសចំនួន Robux និងតម្លៃ។\n"
            "3. បង់ប្រាក់តាមការណែនាំ រួចផ្ញើ Screenshot បញ្ជាក់ការទូទាត់។\n"
            "4. ប្រើ ប្រវត្តិការបញ្ជាទិញ ឬ តាមដានការបញ្ជាទិញ ដើម្បីពិនិត្យស្ថានភាព។\n"
            "5. បើមានចម្ងល់ សូមទាក់ទង Admin។"
        )
    rendered = []
    import re
    # Any numeric custom_emoji_id (wherever it appears in a line) is rendered
    # as a Telegram Premium custom emoji, rather than shown as raw digits.
    for line in saved.splitlines():
        line = line.strip()
        if not line:
            rendered.append("")
            continue
        # Accept both "ID text" and "ID|text" formats, rendering the leading ID as emoji.
        lead = re.match(r"^(\d{5,})(?:\s*\|\s*|\s+)(.*)$", line)
        if lead:
            emoji_id, body = lead.group(1), lead.group(2)
            rendered.append(f'<tg-emoji emoji-id="{emoji_id}">✨</tg-emoji> {html.escape(body)}')
            continue
        pieces = []
        last = 0
        for match in re.finditer(r"(?<!\d)(\d{5,})(?!\d)", line):
            pieces.append(html.escape(line[last:match.start()]))
            emoji_id = match.group(1)
            pieces.append(f'<tg-emoji emoji-id="{emoji_id}">✨</tg-emoji>')
            last = match.end()
        pieces.append(html.escape(line[last:]))
        rendered.append("".join(pieces))
    await update.message.reply_text("\n".join(rendered), parse_mode="HTML", reply_markup=main_keyboard())

async def smart_help_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, question: str) -> bool:
    """Rule-based Khmer/English helper for common service and Robux questions."""
    q = question.lower().strip()
    contact = get_setting("contact_admin_message", DEFAULT_CONTACT_MESSAGE)
    price_words = ("robux", "រ៉ូបុក", "តម្លៃ", "price", "ប៉ុន្មាន", "how much", "ប៉ុន្មានលុយ")
    if any(w in q for w in price_words) and any(w in q for w in ("robux", "រ៉ូបុក", "តម្លៃ", "price", "ប៉ុន្មាន", "how much")):
        await update.message.reply_text(
            "💎 តម្លៃ Robux របស់យើង៖\n"
            "• 10 Robux = $0.10\n• 20 Robux = $0.20\n• 50 Robux = $0.50\n"
            "• 100 Robux = $1.00\n• 200 Robux = $2.00\n• 300 Robux = $3.00\n"
            "• 500 Robux = $5.00\n• 1,000 Robux = $10.00\n\n"
            "តម្លៃគឺ $0.01 ក្នុងមួយ Robux។ ចុច 🛍️ ទិញ Robux ដើម្បីជ្រើសចំនួន។"
        )
        return True
    if any(w in q for w in ("ទិញ robux", "buy robux", "របៀបទិញ", "how to buy", "ទិញរ៉ូបុក")):
        await update.message.reply_text(
            "បានចាស 😊 ដើម្បីទិញ Robux សូមចុច 🛍️ ទិញ Robux → ជ្រើសចំនួន → បញ្ចូល Roblox Username → "
            "ស្កេន QR ហើយផ្ញើ Screenshot បង់ប្រាក់។ Admin នឹងពិនិត្យការទូទាត់ដោយដៃ មុនបំពេញការបញ្ជាទិញ។\n"
            "⚠️ កុំផ្ញើ Password ឬលេខកូដសម្ងាត់ Roblox។"
        )
        return True
    if any(w in q for w in ("បង់ប្រាក់", "qr", "ស្កេន", "payment", "pay", "ទូទាត់", "បង់លុយ")):
        await update.message.reply_text(
            "💳 សម្រាប់ការទិញ Robux សូមជ្រើសកញ្ចប់ជាមុន ដើម្បីឱ្យ Bot បង្ហាញ QR។ "
            "បន្ទាប់ពីបង់ប្រាក់ សូមផ្ញើ Screenshot បញ្ជាក់ការទូទាត់។ Screenshot មិនមានន័យថាបានផ្ទៀងផ្ទាត់រួចទេ—Admin នឹងពិនិត្យជាមុន។"
        )
        return True
    if any(w in q for w in ("រង់ចាំ", "យូរ", "status", "order", "ការបញ្ជាទិញ", "មិនទាន់បាន", "where is")):
        await update.message.reply_text(
            "ខ្ញុំជួយពិនិត្យជំហានបាន 😊 សូមចុច 📜 ប្រវត្តិការបញ្ជាទិញ ឬ 🔎 តាមដានការបញ្ជាទិញ។ "
            "បើមិនទាន់មានព័ត៌មាន សូមទាក់ទង Admin ដោយប្រើប៊ូតុងជំនួយ។"
        )
        return True
    if any(w in q for w in ("hello", "hi", "សួស្តី", "ជំរាបសួរ", "ជំរាបសួរ", "hey")):
        await update.message.reply_text(
            "សួស្តី 😊 ស្វាគមន៍មកកាន់ហាងយើង! ខ្ញុំអាចជួយប្រាប់តម្លៃ Robux របៀបទិញ ការទូទាត់ និងការតាមដាន Order បាន។ តើអ្នកចង់សួរអំពីអ្វី?"
        )
        return True
    if any(w in q for w in ("admin", "ទាក់ទង", "ជំនួយ", "help", "contact", "មនុស្ស", "support")):
        await update.message.reply_text(contact)
        return True
    if any(w in q for w in ("សមតុល្យ", "balance", "ដាក់ប្រាក់", "deposit", "បញ្ចូលលុយ")):
        await update.message.reply_text(
            "💰 ចុច 👤 គណនី ដើម្បីមើលសមតុល្យ និងចុច 💳 បញ្ចូលលុយ ដើម្បីចាប់ផ្តើមសំណើបញ្ចូលប្រាក់។ "
            "បើមានបញ្ហា សូមទាក់ទង Admin។"
        )
        return True
    if any(w in q for w in ("សេវា", "service", "services", "បញ្ជាទិញ")):
        await update.message.reply_text(
            "🛒 ចុច 🛒 បញ្ជាទិញសេវា ដើម្បីមើលសេវាដែលមាន។ ជ្រើសសេវា ហើយធ្វើតាមការណែនាំក្នុង Bot។"
        )
        return True
    await update.message.reply_text(
        "ខ្ញុំជាជំនួយការស្វ័យប្រវត្តិ 😊 ខ្ញុំអាចឆ្លើយសំណួរទូទៅអំពី Robux តម្លៃ ការទិញ ការទូទាត់ និង Order។ "
        "សូមសាកសួរ “តម្លៃ Robux ប៉ុន្មាន?” ឬចុចប៊ូតុងជំនួយ ដើម្បីទាក់ទង Admin។"
    )
    return True


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return
    text = msg.text.strip()
    state = context.user_data.get("state")

    if state == "admin_edit_guide":
        if not is_admin(update):
            context.user_data.pop("state", None)
            await msg.reply_text("⛔ មុខងារនេះសម្រាប់ Admin ប៉ុណ្ណោះ។")
            return
        if text == "/cancel":
            context.user_data.pop("state", None)
            await msg.reply_text("បានបោះបង់ការកែរបៀបប្រើប្រាស់។", reply_markup=ADMIN_KEYBOARD)
            return
        if text in {"🔄 ប្រើអត្ថបទដើម", "⬅️ ត្រឡប់ទៅ Admin"}:
            if text == "🔄 ប្រើអត្ថបទដើម":
                save_setting("custom_guide_lines", "")
                context.user_data.pop("state", None)
                await msg.reply_text("✅ បានត្រឡប់ទៅរបៀបប្រើប្រាស់លំនាំដើម។", reply_markup=ADMIN_KEYBOARD)
            else:
                context.user_data.pop("state", None)
                await msg.reply_text("បានបោះបង់ការកែ។", reply_markup=ADMIN_KEYBOARD)
            return
        save_setting("custom_guide_lines", text)
        context.user_data.pop("state", None)
        await msg.reply_text(
            "✅ បានរក្សាទុករបៀបប្រើប្រាស់ថ្មីហើយ។\n"
            "ទម្រង់បន្ទាត់៖ custom_emoji_id បន្ទាប់មកអត្ថបទ។ អាចប្រើ ID|អត្ថបទ ផងដែរ។\n"
            "ឧ. 6192842262393656514 របៀបដាក់ Robux ចុចទិញ Robux\n"
            "សូមចុចប៊ូតុង ‘💡 របៀបប្រើប្រាស់’ ដើម្បីសាកល្បង។",
            reply_markup=ADMIN_KEYBOARD
        )
        return

    if state == "admin_choose_premium_button":
        if not is_admin(update):
            context.user_data.pop("state", None)
            await msg.reply_text("⛔ មុខងារនេះសម្រាប់ Admin ប៉ុណ្ណោះ។")
            return
        if text in {"/cancel", "⬅️ ត្រឡប់ទៅ Admin"}:
            context.user_data.pop("state", None)
            context.user_data.pop("premium_button_choices", None)
            await msg.reply_text("បានបោះបង់។", reply_markup=ADMIN_KEYBOARD)
            return
        choices = context.user_data.get("premium_button_choices", {})
        if text not in choices:
            await msg.reply_text("សូមចុចឈ្មោះប៊ូតុងមួយក្នុងបញ្ជី ឬ /cancel។")
            return
        key = choices[text]
        context.user_data["premium_button_key"] = key
        context.user_data["state"] = "admin_set_button_emoji_id"
        current_id = get_button_custom_emoji_id(key)
        await msg.reply_text(
            f"💎 ប៊ូតុងដែលបានជ្រើស៖ {text}\n"
            "សូមផ្ញើ custom_emoji_id ជាលេខ។\n"
            f"ID បច្ចុប្បន្ន៖ {current_id or 'មិនទាន់កំណត់'}\n"
            "ផ្ញើ /off ដើម្បីលុប Emoji របស់ប៊ូតុងនេះ ឬ /cancel ដើម្បីបោះបង់។"
        )
        return

    if state == "admin_set_button_emoji_id":
        if not is_admin(update):
            context.user_data.pop("state", None)
            await msg.reply_text("⛔ មុខងារនេះសម្រាប់ Admin ប៉ុណ្ណោះ។")
            return
        if text == "/cancel":
            context.user_data.pop("state", None)
            context.user_data.pop("premium_button_key", None)
            await msg.reply_text("បានបោះបង់។", reply_markup=ADMIN_KEYBOARD)
            return
        key = context.user_data.get("premium_button_key")
        if not key:
            context.user_data.pop("state", None)
            await msg.reply_text("សូមចាប់ផ្ដើមកំណត់ម្ដងទៀត។", reply_markup=ADMIN_KEYBOARD)
            return
        if text == "/off":
            save_setting(f"button_custom_emoji_{key}", "")
            context.user_data.pop("state", None)
            context.user_data.pop("premium_button_key", None)
            await msg.reply_text("✅ បានលុប Premium Emoji icon ពីប៊ូតុងនេះ។ សូមផ្ញើ /start ដើម្បីឱ្យម៉ឺនុយថ្មីបង្ហាញ។", reply_markup=ADMIN_KEYBOARD)
            return
        if not text.isdigit():
            await msg.reply_text("ID មិនត្រឹមត្រូវទេ។ សូមផ្ញើ custom_emoji_id ជាលេខ ឬ /off ឬ /cancel។")
            return
        save_setting(f"button_custom_emoji_{key}", text)
        context.user_data.pop("state", None)
        context.user_data.pop("premium_button_key", None)
        await msg.reply_text("✅ បានរក្សាទុក Premium Custom Emoji icon សម្រាប់ប៊ូតុងនេះ។ សូមផ្ញើ /start ដើម្បីឱ្យម៉ឺនុយថ្មីបង្ហាញ icon លើប៊ូតុង។", reply_markup=ADMIN_KEYBOARD)
        return

    if state == "admin_collect_custom_emojis":
        if not is_admin(update):
            context.user_data.pop("state", None)
            await msg.reply_text("⛔ មុខងារនេះសម្រាប់ Admin ប៉ុណ្ណោះ។")
            return
        if text == "/cancel":
            context.user_data.pop("state", None)
            await msg.reply_text("បានបញ្ចប់ការបន្ថែម Emoji។", reply_markup=ADMIN_KEYBOARD)
            return
        entities = msg.entities or []
        ids = [e.custom_emoji_id for e in entities if e.type == "custom_emoji" and getattr(e, "custom_emoji_id", None)]
        if not ids:
            await msg.reply_text("រកមិនឃើញ Premium Custom Emoji ក្នុងសារនេះទេ។ សូមផ្ញើ Emoji ដែលបានជ្រើសពីផ្ទាំង Custom Emoji របស់ Telegram។ ឬ /cancel។")
            return
        with db() as c:
            for emoji_id in ids:
                c.execute("INSERT OR IGNORE INTO saved_custom_emojis(emoji_id, added_by, added_at) VALUES(?,?,?)", (emoji_id, update.effective_user.id, now()))
        await msg.reply_text(f"✅ បានរក្សាទុក Emoji ចំនួន {len(set(ids))} ក្នុងសារនេះ។ អ្នកអាចផ្ញើ Emoji បន្ថែមទៀត ឬ /cancel។")
        return

    if state in {"admin_add_admin_id", "admin_remove_admin_id"}:
        if not is_owner(update):
            context.user_data.pop("state", None)
            await msg.reply_text("⛔ មានតែ Admin ដើមដែលបានកំណត់ក្នុង ADMIN_IDS ប៉ុណ្ណោះអាចគ្រប់គ្រង Admin ផ្សេងបាន។")
            return
        if text in {"/cancel", "⬅️ ត្រឡប់ទៅ Admin"}:
            context.user_data.pop("state", None)
            await msg.reply_text("បានបោះបង់។", reply_markup=ADMIN_KEYBOARD)
            return
        if not text.isdigit() or int(text) <= 0:
            await msg.reply_text("សូមបញ្ចូល Telegram User ID ជាលេខត្រឹមត្រូវ ឬ /cancel។")
            return
        target_id = int(text)
        if target_id in ADMIN_IDS:
            context.user_data.pop("state", None)
            await msg.reply_text("ID នេះជាអ្នកគ្រប់គ្រងដើមរួចហើយ។", reply_markup=ADMIN_KEYBOARD)
            return
        with db() as c:
            if state == "admin_add_admin_id":
                c.execute("INSERT OR IGNORE INTO extra_admins(user_id, added_by, added_at) VALUES(?,?,?)", (target_id, update.effective_user.id, now()))
                response = f"✅ បានបន្ថែម Admin ID: {target_id}\nអ្នកនោះអាចប្រើ /admin បាន។"
            else:
                c.execute("DELETE FROM extra_admins WHERE user_id=?", (target_id,))
                response = f"✅ បានលុបសិទ្ធិ Admin សម្រាប់ ID: {target_id} (បើមាន)។"
        context.user_data.pop("state", None)
        await msg.reply_text(response, reply_markup=ADMIN_KEYBOARD)
        return

    if state == "admin_set_premium_emoji":
        if not is_admin(update):
            context.user_data.pop("state", None)
            await msg.reply_text("⛔ មុខងារនេះសម្រាប់ Admin ប៉ុណ្ណោះ។")
            return
        if text == "/cancel":
            context.user_data.pop("state", None)
            await msg.reply_text("បានបោះបង់។", reply_markup=ADMIN_KEYBOARD)
            return
        if text == "/off":
            save_setting("premium_emoji_id", "")
            context.user_data.pop("state", None)
            await msg.reply_text("បានបិទ Premium Emoji ក្នុងសារស្វាគមន៍។", reply_markup=ADMIN_KEYBOARD)
            return
        emoji_id = text.strip()
        if not emoji_id.isdigit():
            await msg.reply_text("ID មិនត្រឹមត្រូវទេ។ សូមផ្ញើ custom_emoji_id ជាលេខ ឬ /cancel។")
            return
        save_setting("premium_emoji_id", emoji_id)
        context.user_data.pop("state", None)
        await msg.reply_text("✅ បានរក្សាទុក Premium Emoji ID។ សាកល្បងចុច /start ដើម្បីមើល។", reply_markup=ADMIN_KEYBOARD)
        return

    if state in {"copy_bot_token", "copy_bot_admin"}:
        if not is_admin(update):
            context.user_data.clear()
            await msg.reply_text("⛔ មុខងារនេះសម្រាប់ Admin ប៉ុណ្ណោះ។")
            return
        if text == "/cancel":
            context.user_data.pop("state", None)
            context.user_data.pop("copy_bot_token", None)
            await msg.reply_text("បានបោះបង់ Copy BOT។", reply_markup=ADMIN_KEYBOARD)
            return
        if state == "copy_bot_token":
            token = text.strip()
            # Validate token format without logging or echoing it.
            import re
            if not re.fullmatch(r"\d{5,15}:[A-Za-z0-9_-]{20,}", token):
                await msg.reply_text("Token មិនត្រឹមត្រូវទេ។ សូមពិនិត្យ Token ពី BotFather ឬវាយ /cancel ដើម្បីបោះបង់។")
                return
            try:
                from telegram import Bot
                test_bot = Bot(token=token)
                me = await test_bot.get_me()
                await test_bot.shutdown()
            except Exception:
                await msg.reply_text("មិនអាចផ្ទៀងផ្ទាត់ Token បានទេ។ សូមពិនិត្យ Token ហើយសាកម្ដងទៀត។")
                return
            context.user_data["copy_bot_token"] = token
            context.user_data["copy_bot_username"] = me.username or "bot"
            context.user_data["state"] = "copy_bot_admin"
            await msg.reply_text("✅ Token ត្រឹមត្រូវ។ សូមបញ្ចូល Telegram Admin ID ជាលេខ (ឧ. 123456789)。\nវាយ /cancel ដើម្បីបោះបង់។")
            return
        if state == "copy_bot_admin":
            if not text.isdigit() or len(text) > 20:
                await msg.reply_text("Admin ID ត្រូវតែជាលេខ Telegram ID។ សូមវាយម្ដងទៀត ឬ /cancel។")
                return
            admin_id = int(text)
            token = context.user_data.get("copy_bot_token", "")
            username = context.user_data.get("copy_bot_username", "bot")
            try:
                # One isolated folder, script, config and SQLite database per copied bot.
                safe_name = "".join(ch for ch in username.lower() if ch.isalnum() or ch == "_") or "bot"
                bot_dir = COPY_BOT_ROOT / f"{safe_name}_{admin_id}"
                if bot_dir.exists():
                    await msg.reply_text("ថត Bot នេះមានរួចហើយ។ ប្រើ Bot username ឬ Admin ID ផ្សេង។", reply_markup=ADMIN_KEYBOARD)
                    context.user_data.clear()
                    return
                bot_dir.mkdir(parents=True, exist_ok=False)
                source_script = Path(__file__).resolve()
                copied_script = bot_dir / "bot.py"
                shutil.copy2(source_script, copied_script)
                runner = bot_dir / "run.sh"
                runner.write_text(
                    '#!/data/data/com.termux/files/usr/bin/bash\n'
                    'cd "$(dirname "$0")"\n'
                    f'export BOT_TOKEN={__import__("shlex").quote(token)}\n'
                    f'export ADMIN_IDS={__import__("shlex").quote(str(admin_id))}\n'
                    'export BOT_DB="$(pwd)/service_bot.db"\n'
                    'exec python bot.py\n', encoding="utf-8")
                runner.chmod(0o700)
                # Restrict token-bearing launcher permissions to the Android app user.
                os.chmod(copied_script, 0o600)
                log_path = bot_dir / "bot.log"
                with log_path.open("ab") as log_file:
                    proc = subprocess.Popen(["bash", str(runner)], cwd=str(bot_dir), stdin=subprocess.DEVNULL,
                                            stdout=log_file, stderr=subprocess.STDOUT, start_new_session=True)
                (bot_dir / "pid").write_text(str(proc.pid), encoding="utf-8")
                (bot_dir / "bot_token.txt").write_text(token, encoding="utf-8")
                os.chmod(bot_dir / "bot_token.txt", 0o600)
            except Exception as exc:
                log.exception("Copy BOT creation failed")
                await msg.reply_text(f"❌ បង្កើត Bot មិនបានទេ: {type(exc).__name__}. ពិនិត្យសិទ្ធិថត/Termux។", reply_markup=ADMIN_KEYBOARD)
                context.user_data.clear()
                return
            context.user_data.clear()
            await msg.reply_text(
                f"✅ បង្កើត Bot @{username} រួចហើយ។\nAdmin ID: {admin_id}\nPID: {proc.pid}\n"
                f"Database ដាច់ដោយឡែក: {bot_dir / 'service_bot.db'}\nLog: {log_path}\n"
                "⚠️ Bot ថ្មីចាប់ផ្តើមជាដំណើរការផ្សេង។ អាចបើក/បិទវាពី 🛠️ គ្រប់គ្រង Copy Bot។\n"
                "ចំណាំ៖ វាអាចបន្តរត់ពេលបិទផ្ទាំង Termux ប៉ុន្តែបើ Android បង្ខំបិទ/បញ្ឈប់ Termux វាអាចឈប់ដែរ។",
                reply_markup=ADMIN_KEYBOARD)
            return

    if state == "robux_waiting_username":
        username = text.strip().lstrip("@")
        if text == "/cancel":
            context.user_data.pop("state", None)
            context.user_data.pop("robux_amount", None)
            context.user_data.pop("robux_price", None)
            await msg.reply_text("បានបោះបង់ការទិញ Robux។", reply_markup=main_keyboard())
            return
        if len(username) < 3 or len(username) > 20 or any(ch.isspace() for ch in username):
            await msg.reply_text("Roblox Username មិនត្រឹមត្រូវទេ។ សូមវាយ Username ដោយមិនដាក់ចន្លោះ ហើយកុំផ្ញើ Password។")
            return
        context.user_data["robux_username"] = username
        amount = int(context.user_data.get("robux_amount", 0))
        price = float(context.user_data.get("robux_price", 0))
        qr_file_id = get_setting("robux_qr_file_id", "")
        qr_caption = get_setting("robux_qr_caption", DEFAULT_ROBUX_QR_CAPTION)
        final_caption = f"💎 ទិញ {amount} Robux\n💵 តម្លៃ៖ ${price:.2f}\n👤 Roblox Username៖ {username}\n\n{qr_caption}"
        context.user_data["state"] = "robux_waiting_proof"
        if qr_file_id:
            await context.bot.send_photo(chat_id=msg.chat_id, photo=qr_file_id, caption=final_caption[:1024])
        else:
            await msg.reply_text(final_caption + "\n\n⚠️ Admin មិនទាន់ដាក់ QR ទេ។ សូមទាក់ទង Admin។")
        await msg.reply_text("បន្ទាប់ពីទូទាត់ សូមផ្ញើរូប Screenshot/វិក្កយបត្របញ្ជាក់ការទូទាត់ជារូបភាពនៅទីនេះ។")
        return

    if state == "admin_manage_buttons":
        if not is_admin(update):
            context.user_data.pop("state", None)
            await msg.reply_text("⛔ មុខងារនេះសម្រាប់ Admin ប៉ុណ្ណោះ។")
            return
        if text == "⬅️ ត្រឡប់ទៅ Admin":
            context.user_data.pop("state", None)
            await msg.reply_text("⚙️ ម៉ឺនុយ Admin", reply_markup=ADMIN_KEYBOARD)
            return
        labels = get_button_labels()
        choices = {labels[k]: k for k in labels}
        chosen = None
        action = None
        for label, key in choices.items():
            if text == f"➖ លុប {label}": chosen, action = key, "0"; break
            if text == f"➕ ដាក់ {label}": chosen, action = key, "1"; break
        if not chosen:
            await msg.reply_text("សូមជ្រើសប៊ូតុងពីបញ្ជី។")
            return
        save_setting(f"button_visible_{chosen}", action)
        await msg.reply_text(("✅ បានដាក់ប៊ូតុងវិញ៖ " if action == "1" else "✅ បានលាក់ប៊ូតុង៖ ") + labels.get(chosen, chosen), reply_markup=main_keyboard())
        rows = []
        for label, key in choices.items():
            visible = get_setting(f"button_visible_{key}", "1") != "0"
            rows.append([KeyboardButton(("➖ លុប " if visible else "➕ ដាក់ ") + label)])
        rows.append([KeyboardButton("⬅️ ត្រឡប់ទៅ Admin")])
        await msg.reply_text("➕➖ គ្រប់គ្រងប៊ូតុង៖ ជ្រើសប៊ូតុងដើម្បីលាក់ ឬដាក់បង្ហាញវិញ។", reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True))
        return

    if state == "admin_choose_button":
        if text == "⬅️ ត្រឡប់ទៅ Admin" and is_admin(update):
            context.user_data.clear()
            await msg.reply_text("⚙️ ម៉ឺនុយ Admin", reply_markup=ADMIN_KEYBOARD)
            return
        if not is_admin(update):
            context.user_data.pop("state", None)
            await msg.reply_text("⛔ មុខងារនេះសម្រាប់ Admin ប៉ុណ្ណោះ។")
            return
        labels = get_button_labels()
        chosen_key = None
        for key, label in labels.items():
            if text == f"✏️ {label}":
                chosen_key = key
                break
        if not chosen_key:
            await msg.reply_text("សូមជ្រើសប៊ូតុងពីបញ្ជីដែលបានបង្ហាញ។")
            return
        context.user_data["state"] = "admin_rename_button"
        context.user_data["rename_button_key"] = chosen_key
        await msg.reply_text(f"សូមវាយឈ្មោះថ្មីសម្រាប់ប៊ូតុង៖ {labels[chosen_key]}\nឧ. គណនីអាខោន")
        return

    if state == "admin_rename_button":
        if not is_admin(update):
            context.user_data.clear()
            await msg.reply_text("⛔ មុខងារនេះសម្រាប់ Admin ប៉ុណ្ណោះ។")
            return
        new_label = text.strip()
        key = context.user_data.get("rename_button_key")
        if not key or key not in BUTTON_DEFAULTS:
            context.user_data.clear()
            await msg.reply_text("មានបញ្ហា។ សូមចូល Admin ហើយសាកម្ដងទៀត។")
            return
        if len(new_label) < 2 or len(new_label) > 50:
            await msg.reply_text("ឈ្មោះប៊ូតុងត្រូវមាន 2 ដល់ 50 តួអក្សរ។ សូមវាយម្ដងទៀត។")
            return
        with db() as c:
            c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                      (f"button_{key}", new_label))
        context.user_data.pop("state", None)
        context.user_data.pop("rename_button_key", None)
        await msg.reply_text(f"✅ បានប្ដូរឈ្មោះប៊ូតុងទៅជា៖ {new_label}\nម៉ឺនុយថ្មីត្រូវបានបង្ហាញខាងក្រោម។", reply_markup=main_keyboard())
        return

    if state == "deposit_custom":
        try:
            amount = float(text)
            if amount <= 0 or amount > 100000:
                raise ValueError
        except ValueError:
            await msg.reply_text("ចំនួនមិនត្រឹមត្រូវទេ។ សូមបញ្ចូលចំនួន USD វិជ្ជមាន។")
            return
        with db() as c:
            cur = c.execute("INSERT INTO deposits(user_id, amount, created_at) VALUES(?,?,?)",
                            (msg.from_user.id, amount, now()))
            did = cur.lastrowid
        context.user_data.pop("state", None)
        await send_deposit_qr(msg.from_user.id, amount, did, context)
        await notify_admins(context, f"💳 សំណើបញ្ចូលលុយ #{did}\nUser ID: {msg.from_user.id}\nចំនួន: ${amount:.2f}\n/approve_deposit {did} | /reject_deposit {did}")
        return

    if state == "order_target":
        sid = context.user_data.get("service_id")
        with db() as c:
            s = c.execute("SELECT * FROM services WHERE id=? AND active=1", (sid,)).fetchone()
            u = c.execute("SELECT balance FROM users WHERE user_id=?", (msg.from_user.id,)).fetchone()
            if not s:
                context.user_data.clear()
                await msg.reply_text("សេវានេះមិនមានទៀតទេ។")
                return
            balance = u["balance"] if u else 0
            if balance < s["price"]:
                context.user_data.clear()
                await msg.reply_text(f"សមតុល្យមិនគ្រប់ទេ។ ត្រូវការ ${s['price']:.2f}; អ្នកមាន ${balance:.2f}។ សូមបញ្ចូលលុយជាមុន។")
                return
            c.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (s["price"], msg.from_user.id))
            cur = c.execute(
                "INSERT INTO orders(user_id,service_id,service_name,target,price,created_at) VALUES(?,?,?,?,?,?)",
                (msg.from_user.id, sid, s["name"], text, s["price"], now())
            )
            oid = cur.lastrowid
        context.user_data.clear()
        await msg.reply_text(f"✅ បានទទួលការបញ្ជាទិញ #{oid}។ ស្ថានភាព៖ pending")
        await notify_admins(context, f"🛒 Order #{oid}\nUser: {msg.from_user.id}\nសេវា: {s['name']}\nតម្លៃ: ${s['price']:.2f}\nគោលដៅ: {text}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("កំពុងដំណើរការ", callback_data=f"status:{oid}:processing"),
                InlineKeyboardButton("បានបញ្ចប់", callback_data=f"status:{oid}:completed"),
                InlineKeyboardButton("បរាជ័យ", callback_data=f"status:{oid}:failed")
            ]]))
        return

    if state == "track_order":
        context.user_data.pop("state", None)
        try:
            oid = int(text)
        except ValueError:
            await msg.reply_text("Order ID មិនត្រឹមត្រូវទេ។")
            return
        with db() as c:
            r = c.execute("SELECT * FROM orders WHERE id=? AND user_id=?", (oid, msg.from_user.id)).fetchone()
        if r:
            await msg.reply_text(f"Order #{r['id']}\nសេវា: {r['service_name']}\nតម្លៃ: ${r['price']:.2f}\nស្ថានភាព: {r['status']}")
        else:
            await msg.reply_text("រកមិនឃើញ Order នេះក្នុងគណនីរបស់អ្នកទេ។")
        return

    if state == "admin_set_welcome_photo" and text == "/cancel":
        if not is_admin(update):
            context.user_data.pop("state", None)
            await msg.reply_text("⛔ មុខងារនេះសម្រាប់ Admin ប៉ុណ្ណោះ។")
            return
        context.user_data.pop("state", None)
        await msg.reply_text("បានបោះបង់ការកំណត់ស្វាគមន៍។", reply_markup=ADMIN_KEYBOARD)
        return

    if is_admin(update):
        if text == BTN_ADD_ADMIN:
            if not is_owner(update):
                await msg.reply_text("⛔ មានតែ Admin ដើមប៉ុណ្ណោះអាចបន្ថែម ឬលុប Admin។", reply_markup=ADMIN_KEYBOARD)
                return
            context.user_data["state"] = "admin_add_admin_id"
            await msg.reply_text("👥 Add Admin តាម ID\nសូមផ្ញើ Telegram User ID ដែលចង់បន្ថែម។\nវាយ /cancel ដើម្បីបោះបង់។", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("➖ លុប Admin តាម ID")],[KeyboardButton("⬅️ ត្រឡប់ទៅ Admin")]], resize_keyboard=True))
            return
        if text == "➖ លុប Admin តាម ID":
            if not is_owner(update):
                await msg.reply_text("⛔ មានតែ Admin ដើមប៉ុណ្ណោះអាចលុប Admin។", reply_markup=ADMIN_KEYBOARD)
                return
            context.user_data["state"] = "admin_remove_admin_id"
            await msg.reply_text("➖ សូមផ្ញើ Telegram User ID ដែលចង់លុបសិទ្ធិ Admin។\nវាយ /cancel ដើម្បីបោះបង់។", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("⬅️ ត្រឡប់ទៅ Admin")]], resize_keyboard=True))
            return
        if text == "⬅️ ត្រឡប់ទៅម៉ឺនុយ":
            context.user_data.clear()
            await msg.reply_text("ម៉ឺនុយអ្នកប្រើ", reply_markup=main_keyboard())
            return
        if text == BTN_MANAGE_BUTTONS:
            context.user_data["state"] = "admin_manage_buttons"
            labels = get_button_labels()
            choices = labels
            rows = []
            for key, label in choices.items():
                visible = get_setting(f"button_visible_{key}", "1") != "0"
                rows.append([KeyboardButton(("➖ លុប " if visible else "➕ ដាក់ ") + label)])
            rows.append([KeyboardButton("⬅️ ត្រឡប់ទៅ Admin")])
            await msg.reply_text("➕➖ គ្រប់គ្រងប៊ូតុង\nចុច ‘លុប’ ដើម្បីលាក់ប៊ូតុងពីម៉ឺនុយអ្នកប្រើ ឬ ‘ដាក់’ ដើម្បីបង្ហាញវិញ។", reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True))
            return
        if text == BTN_EDIT_BUTTONS:
            labels = get_button_labels()
            rows = [[KeyboardButton(f"✏️ {label}")] for label in labels.values()]
            rows.append([KeyboardButton("⬅️ ត្រឡប់ទៅ Admin")])
            context.user_data["state"] = "admin_choose_button"
            await msg.reply_text(
                "📝 ជ្រើសរើសប៊ូតុងដែលចង់ប្ដូរឈ្មោះ។\nមុខងារនេះមានតែ Admin ប៉ុណ្ណោះអាចប្រើបាន។",
                reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
            )
            return
        if text == "⬅️ ត្រឡប់ទៅ Admin":
            context.user_data.clear()
            await msg.reply_text("⚙️ ម៉ឺនុយ Admin", reply_markup=ADMIN_KEYBOARD)
            return
        if text == "🖼️ កំណត់ QR ដាក់ប្រាក់":
            context.user_data["state"] = "admin_set_deposit_qr"
            await msg.reply_text(
                "សូមផ្ញើរូបភាព QR ដាក់ប្រាក់ជារូប Photo នៅទីនេះ។\n"
                "QR ថ្មីនឹងជំនួស QR ចាស់ ហើយបង្ហាញដល់អ្នកប្រើពេលជ្រើសចំនួនប្រាក់។"
            )
            return
        if text == BTN_SET_ROBUX_QR:
            context.user_data["state"] = "admin_set_robux_qr"
            await msg.reply_text(
                "🖼️ កំណត់ QR និងសារទិញ Robux\n"
                "សូមផ្ញើរូប QR ជា Photo ហើយសរសេរអត្ថបទណែនាំខាងក្រោម QR ក្នុង Caption ជាមួយរូប។\n"
                "រូប និង Caption នេះប្រើសម្រាប់កញ្ចប់ Robux ទាំងអស់ 10–1000។\n"
                "ផ្ញើ /cancel ដើម្បីបោះបង់។"
            )
            return
        if text == BTN_SET_WELCOME:
            context.user_data["state"] = "admin_set_welcome_photo"
            await msg.reply_text(
                "🖼️ កំណត់រូប និងសារស្វាគមន៍\n"
                "សូមផ្ញើរូបភាពជា Photo ហើយសរសេរអត្ថបទស្វាគមន៍ក្នុង Caption ជាមួយរូបនោះ។\n"
                "ឧ. សូមស្វាគមន៍មកកាន់ BOT របស់យើង!\n\n"
                "រូប និងអត្ថបទនេះនឹងបង្ហាញពេលអ្នកប្រើចុច /start។\n"
                "វាយ /cancel ដើម្បីបោះបង់។"
            )
            return
        if text == BTN_EDIT_GUIDE:
            context.user_data["state"] = "admin_edit_guide"
            current_guide = get_setting("custom_guide_lines", "")
            await msg.reply_text(
                "📝 កែរបៀបប្រើប្រាស់ / ជំនួយការទិញ Robux\n\n"
                "សរសេរអត្ថបទថ្មី ដោយដាក់មួយបន្ទាត់ក្នុងមួយជំហាន។\n"
                "ដាក់ custom_emoji_id នៅខាងមុខអត្ថបទ ដើម្បីឱ្យ Emoji Premium បង្ហាញនៅបន្ទាត់នោះ។\n\n"
                "ឧទាហរណ៍៖\n"
                "6192842262393656514 របៀបដាក់ Robux ចុចទិញ Robux\n"
                "5368324170671202286 ជ្រើសរើសចំនួន Robux និងតម្លៃ\n"
                "មានចម្ងល់ សូមទាក់ទង Admin\n\n"
                "អាចសរសេរ ID|អត្ថបទ ក៏បាន។ ចុច 🔄 ប្រើអត្ថបទដើម ដើម្បីត្រឡប់ទៅអត្ថបទដើម ឬ /cancel ដើម្បីបោះបង់។\n\n"
                f"អត្ថបទដែលបានកំណត់បច្ចុប្បន្ន៖\n{current_guide or 'មិនទាន់កំណត់ (ប្រើអត្ថបទលំនាំដើម)'}",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🔄 ប្រើអត្ថបទដើម")], [KeyboardButton("⬅️ ត្រឡប់ទៅ Admin")]], resize_keyboard=True)
            )
            return
        if text == BTN_SET_CONTACT:
            context.user_data["state"] = "admin_set_contact_message"
            current_contact = get_setting("contact_admin_message", DEFAULT_CONTACT_MESSAGE)
            await msg.reply_text(
                "💬 កំណត់សារទាក់ទង Admin\n"
                "សូមផ្ញើអត្ថបទ ឬ username ថ្មីដែលអ្នកប្រើនឹងឃើញពេលចុច ‘ទាក់ទង Admin’។\n"
                "ឧ. 💬 សូមផ្ញើសារទៅ Admin៖ @YourUsername\n\n"
                f"សារបច្ចុប្បន្ន៖\n{current_contact}\n\n"
                "ផ្ញើ /cancel ដើម្បីបោះបង់។"
            )
            return
        if text == BTN_BUTTON_EMOJI:
            labels = get_button_labels()
            choices = {labels[key]: key for key in BUTTON_DEFAULTS}
            choices["💎 Robux តម្លៃ / កញ្ចប់ទាំងអស់"] = "robux_package"
            context.user_data["premium_button_choices"] = choices
            context.user_data["state"] = "admin_choose_premium_button"
            rows = [[KeyboardButton(label)] for label in choices]
            rows.append([KeyboardButton("⬅️ ត្រឡប់ទៅ Admin")])
            await msg.reply_text(
                "💎 កំណត់ Premium Emoji តាមប៊ូតុង\nជ្រើសឈ្មោះប៊ូតុង (ឧ. 👤 គណនី) រួចផ្ញើ custom_emoji_id។\n\n"
                "ID នឹងបង្ហាញជារូប Premium icon នៅខាងមុខឈ្មោះប៊ូតុង បន្ទាប់ពីផ្ញើ /start ម្ដងទៀត។",
                reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
            )
            return
        if text == BTN_SAVED_EMOJIS:
            with db() as c:
                emoji_rows = c.execute("SELECT emoji_id FROM saved_custom_emojis ORDER BY added_at DESC LIMIT 50").fetchall()
            keyboard = [[InlineKeyboardButton(f"💎 Emoji {i+1}", callback_data=f"emoji:use:{row['emoji_id']}")] for i, row in enumerate(emoji_rows)]
            keyboard.append([InlineKeyboardButton("➕ បន្ថែម Emoji", callback_data="emoji:collect")])
            await msg.reply_text(
                "💎 Emoji ដែលបានរក្សាទុក\nចុច Emoji ដើម្បីឱ្យ Bot ផ្ញើវាមកវិញ ឬចុច ➕ បន្ថែម Emoji។",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        if text == BTN_PREMIUM_EMOJI:
            context.user_data["state"] = "admin_set_premium_emoji"
            current_id = get_setting("premium_emoji_id", "")
            await msg.reply_text(
                "💎 កំណត់ Premium Custom Emoji សម្រាប់សារស្វាគមន៍ /start\n"
                "សូមផ្ញើ custom_emoji_id ជាលេខ (មិនមែន username ឬ emoji ធម្មតាទេ)។\n"
                "អ្នកអាចរក ID ដោយប្រើ bot/tool ដែលបង្ហាញ entities របស់សារដែលមាន Premium Emoji។\n"
                f"ID បច្ចុប្បន្ន៖ {current_id or 'មិនទាន់កំណត់'}\n"
                "ផ្ញើ /off ដើម្បីបិទ ឬ /cancel ដើម្បីបោះបង់។"
            )
            return
        if text == "🛠️ គ្រប់គ្រង Copy Bot":
            if not is_admin(update):
                await msg.reply_text("⛔ មុខងារនេះសម្រាប់ Admin ប៉ុណ្ណោះ។")
                return
            await show_copybots(msg)
            return
        if text == BTN_COPY_BOT:
            context.user_data["state"] = "copy_bot_token"
            await msg.reply_text(
                "📋 Copy BOT (A1)\nសូមបញ្ចូល Bot Token ថ្មីពី BotFather។\n"
                "បន្ទាប់មកនឹងសួរ Admin ID ហើយបង្កើត Bot ថ្មីជាមួយ Database ដាច់ដោយឡែក។\n"
                "Bot ថ្មីប្រើកូដដូច Bot នេះ; ការកំណត់/ទិន្នន័យមិនត្រូវបានចម្លងទេ។\n"
                "កុំផ្ញើ Token ទៅអ្នកដទៃ។ វាយ /cancel ដើម្បីបោះបង់។")
            return
        if text == "➕ បន្ថែមសមតុល្យ":
            context.user_data["state"] = "admin_add_balance"
            await msg.reply_text("ផ្ញើទម្រង់៖ USER_ID AMOUNT\nឧ. 123456789 5")
            return
        if text == "📢 ផ្ញើសារទៅអ្នកប្រើទាំងអស់":
            context.user_data["state"] = "admin_broadcast"
            await msg.reply_text("សូមផ្ញើអត្ថបទដែលចង់ Broadcast ទៅអ្នកប្រើទាំងអស់។")
            return
        if text == "➕ បន្ថែមសេវា":
            context.user_data["state"] = "admin_add_service"
            await msg.reply_text("ផ្ញើទម្រង់៖ ឈ្មោះសេវា | តម្លៃ | ព័ត៌មាន\nឧ. TikTok Likes | 2 | 100 likes")
            return
        if text == "🗑️ លុបសេវាកម្ម":
            with db() as c:
                services = c.execute("SELECT id,name,price FROM services WHERE active=1 ORDER BY id").fetchall()
            if not services:
                await msg.reply_text("មិនមានសេវាកម្មសកម្មសម្រាប់លុបទេ។", reply_markup=ADMIN_KEYBOARD)
                return
            context.user_data["services_to_delete"] = set()
            rows = [[InlineKeyboardButton(f"⬜ {sv['name']} — ${sv['price']:.2f}", callback_data=f"svcdelete:toggle:{sv['id']}")] for sv in services]
            rows.append([InlineKeyboardButton("✅ លុបសេវាដែលបានជ្រើស", callback_data="svcdelete:confirm")])
            rows.append([InlineKeyboardButton("❌ បោះបង់", callback_data="svcdelete:cancel")])
            await msg.reply_text(
                "🗑️ ជ្រើសរើសសេវាកម្មដែលចង់លុប។ អាចជ្រើសច្រើនមុខក្នុងពេលតែមួយ ដោយចុចលើសេវានីមួយៗ រួចចុច ‘លុបសេវាដែលបានជ្រើស’។\n\nសេវាដែលលុបនឹងបាត់ពីបញ្ជីទិញរបស់អ្នកប្រើ ប៉ុន្តែប្រវត្តិ Order ចាស់នៅរក្សាទុក។",
                reply_markup=InlineKeyboardMarkup(rows)
            )
            return
        if text == "📋 គ្រប់គ្រងការបញ្ជាទិញ":
            with db() as c:
                rows = c.execute("SELECT id,user_id,service_name,price,status FROM orders ORDER BY id DESC LIMIT 10").fetchall()
            if not rows:
                await msg.reply_text("មិនទាន់មានការបញ្ជាទិញទេ។")
            else:
                await msg.reply_text("\n".join([f"#{r['id']} | User {r['user_id']} | {r['service_name']} | ${r['price']:.2f} | {r['status']}" for r in rows]))
            return
        if state == "admin_set_contact_message":
            if text == "/cancel":
                context.user_data.pop("state", None)
                await msg.reply_text("បានបោះបង់ការកំណត់ទំនាក់ទំនង Admin។", reply_markup=ADMIN_KEYBOARD)
                return
            contact_message = text.strip()
            if len(contact_message) < 2 or len(contact_message) > 500:
                await msg.reply_text("សារត្រូវមាន 2 ដល់ 500 តួអក្សរ។ សូមសាកម្ដងទៀត ឬវាយ /cancel ដើម្បីបោះបង់។")
                return
            save_setting("contact_admin_message", contact_message)
            context.user_data.pop("state", None)
            await msg.reply_text(
                f"✅ បានរក្សាទុកសារទាក់ទង Admin រួចហើយ។\n\nសារថ្មី៖\n{contact_message}",
                reply_markup=ADMIN_KEYBOARD
            )
            return
        if state == "admin_add_balance":
            try:
                uid_s, amount_s = text.split()
                uid, amount = int(uid_s), float(amount_s)
                if amount <= 0:
                    raise ValueError
            except ValueError:
                await msg.reply_text("ទម្រង់មិនត្រឹមត្រូវ។ ប្រើ USER_ID AMOUNT ឧ. 123456789 5")
                return
            with db() as c:
                exists = c.execute("SELECT user_id FROM users WHERE user_id=?", (uid,)).fetchone()
                if not exists:
                    await msg.reply_text("មិនឃើញ User ID នេះទេ។ អ្នកប្រើត្រូវចុច /start ជាមុន។")
                    return
                c.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount, uid))
            context.user_data.pop("state", None)
            await msg.reply_text(f"បានបន្ថែម ${amount:.2f} ទៅ User {uid}។")
            await context.bot.send_message(uid, f"💰 Admin បានបន្ថែម ${amount:.2f} ទៅសមតុល្យរបស់អ្នក។")
            return
        if state == "admin_broadcast":
            context.user_data.pop("state", None)
            with db() as c:
                users = c.execute("SELECT user_id FROM users").fetchall()
            sent = failed = 0
            for u in users:
                try:
                    await context.bot.send_message(u["user_id"], text)
                    sent += 1
                except Exception:
                    failed += 1
            await msg.reply_text(f"Broadcast រួចរាល់។ បានផ្ញើ {sent}; បរាជ័យ {failed}។")
            return
        if state == "admin_add_service":
            parts = [p.strip() for p in text.split("|", 2)]
            if len(parts) < 2 or not parts[0]:
                await msg.reply_text("ទម្រង់៖ ឈ្មោះសេវា | តម្លៃ | ព័ត៌មាន")
                return
            try:
                price = float(parts[1])
                if price < 0:
                    raise ValueError
            except ValueError:
                await msg.reply_text("តម្លៃមិនត្រឹមត្រូវទេ។")
                return
            description = parts[2] if len(parts) == 3 else ""
            with db() as c:
                c.execute("INSERT INTO services(name,price,description) VALUES(?,?,?)", (parts[0], price, description))
            context.user_data.pop("state", None)
            await msg.reply_text(f"បានបន្ថែមសេវា {parts[0]} តម្លៃ ${price:.2f}។")
            return

    # Menu router uses the current (possibly renamed) button labels.
    labels = get_button_labels()
    if text == labels["account"]:
        await send_button_custom_emoji(update, context, "account")
        await show_account(update, context)
    elif text == labels["deposit"]:
        await send_button_custom_emoji(update, context, "deposit")
        await deposit_menu(update, context)
    elif text == labels["order"]:
        await send_button_custom_emoji(update, context, "order")
        await order_menu(update, context)
    elif text == labels["buy_robux"]:
        await send_button_custom_emoji(update, context, "buy_robux")
        await robux_menu(update, context)
    elif text == labels.get("top_robux", "🏆 Top 10 Robux"):
        await show_top_robux(update, context)
    elif text == labels["ai_help"]:
        await send_button_custom_emoji(update, context, "ai_help")
        await smart_help_reply(update, context, "សួស្តី ជំនួយការ")
    elif text == labels["history"]:
        await send_button_custom_emoji(update, context, "history")
        await order_history(update, context)
    elif text == labels["track"]:
        await send_button_custom_emoji(update, context, "track")
        await track_order(update, context)
    elif text == labels["help"]:
        await send_button_custom_emoji(update, context, "help")
        await help_admin(update, context)
    elif text == labels["guide"]:
        await send_button_custom_emoji(update, context, "guide")
        await guide(update, context)
    elif text == BTN_ADMIN or text == "/admin":
        await admin_cmd(update, context)
    else:
        await smart_help_reply(update, context, text)

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.photo:
        return
    if context.user_data.get("state") == "robux_waiting_proof":
        amount = int(context.user_data.get("robux_amount", 0))
        price = float(context.user_data.get("robux_price", 0))
        roblox_username = context.user_data.get("robux_username", "(មិនបានបញ្ចូល)")
        user = msg.from_user
        details = (
            f"🛍️ សំណើទិញ Robux ថ្មី\n"
            f"👤 Telegram: {user.full_name} (@{user.username or 'គ្មាន'})\n"
            f"🆔 User ID: {user.id}\n"
            f"🎮 Roblox Username: {roblox_username}\n"
            f"💎 ចំនួន: {amount} Robux\n"
            f"💵 តម្លៃ: ${price:.2f}\n"
            "📸 រូបបញ្ជាក់ការទូទាត់នៅភ្ជាប់ខាងក្រោម។ សូមពិនិត្យប្រាក់ដោយដៃ មុនបំពេញការបញ្ជាទិញ។"
        )
        with db() as c:
            cur = c.execute(
                "INSERT INTO robux_orders(user_id, username, roblox_username, amount, price, status, created_at) VALUES(?,?,?,?,?,'pending',?)",
                (user.id, user.username or "", roblox_username, amount, price, now()))
            robux_order_id = cur.lastrowid
        completion_markup = InlineKeyboardMarkup([[InlineKeyboardButton(
            "✅ Robux រួចរាល់ / ជូនដំណឹងអ្នកប្រើ", callback_data=f"robux:complete:{robux_order_id}")]])
        notified = 0
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(chat_id=admin_id, text=details + f"\n🧾 Robux Order ID: #{robux_order_id}")
                await context.bot.send_photo(
                    chat_id=admin_id,
                    photo=msg.photo[-1].file_id,
                    caption=f"ភស្តុតាងទូទាត់ Robux {amount} — ${price:.2f} | User ID {user.id} | Order #{robux_order_id}",
                    reply_markup=completion_markup
                )
                notified += 1
            except Exception as exc:
                log.warning("Could not send Robux proof to admin %s: %s", admin_id, exc)
        context.user_data.pop("state", None)
        context.user_data.pop("robux_amount", None)
        context.user_data.pop("robux_price", None)
        context.user_data.pop("robux_username", None)
        await msg.reply_text(
            "✅ បានទទួលរូបបញ្ជាក់ការទូទាត់ហើយ។ សំណើរបស់អ្នកត្រូវបានផ្ញើទៅ Admin ដើម្បីពិនិត្យ។\n"
            "សូមរង់ចាំការបញ្ជាក់។ កុំផ្ញើ Password Roblox។",
            reply_markup=main_keyboard()
        )
        return

    if context.user_data.get("state") == "admin_set_robux_qr":
        if not is_admin(update):
            context.user_data.pop("state", None)
            await msg.reply_text("⛔ មុខងារនេះសម្រាប់ Admin ប៉ុណ្ណោះ។")
            return
        photo_file_id = msg.photo[-1].file_id
        caption = (msg.caption or "").strip() or DEFAULT_ROBUX_QR_CAPTION
        if len(caption) > 600:
            await msg.reply_text("Caption QR វែងពេក។ សូមផ្ញើរូប QR ម្តងទៀតជាមួយអត្ថបទមិនលើស 600 តួអក្សរ។")
            return
        save_setting("robux_qr_file_id", photo_file_id)
        save_setting("robux_qr_caption", caption)
        context.user_data.pop("state", None)
        await msg.reply_text(
            "✅ បានរក្សាទុក QR និងអត្ថបទសម្រាប់ទិញ Robux ទាំងអស់រួចហើយ។\n"
            "ពេលអ្នកប្រើជ្រើសកញ្ចប់ Robux នឹងបង្ហាញ QR និងសារនេះ។",
            reply_markup=ADMIN_KEYBOARD
        )
        return

    if context.user_data.get("state") == "admin_set_welcome_photo":
        if not is_admin(update):
            context.user_data.pop("state", None)
            await msg.reply_text("⛔ មុខងារនេះសម្រាប់ Admin ប៉ុណ្ណោះ។")
            return
        photo_file_id = msg.photo[-1].file_id
        welcome_text = (msg.caption or "").strip()
        if not welcome_text:
            await msg.reply_text(
                "សូមផ្ញើរូបភាពម្តងទៀត ហើយបញ្ចូលអត្ថបទស្វាគមន៍ក្នុង Caption ជាមួយរូបភាព។"
            )
            return
        if len(welcome_text) > 1000:
            await msg.reply_text("អត្ថបទស្វាគមន៍វែងពេក។ សូមកុំឱ្យលើស 1000 តួអក្សរ។")
            return
        save_setting("welcome_photo_file_id", photo_file_id)
        save_setting("welcome_text", welcome_text)
        context.user_data.pop("state", None)
        await msg.reply_text(
            "✅ បានរក្សាទុករូប និងអត្ថបទស្វាគមន៍រួចហើយ។\n"
            "សាកល្បងចុច /start ដើម្បីមើល។",
            reply_markup=ADMIN_KEYBOARD
        )
        return

    if context.user_data.get("state") == "admin_set_deposit_qr":
        if not is_admin(update):
            context.user_data.pop("state", None)
            await msg.reply_text("⛔ មុខងារនេះសម្រាប់ Admin ប៉ុណ្ណោះ។")
            return
        file_id = msg.photo[-1].file_id
        save_setting("deposit_qr_file_id", file_id)
        context.user_data.pop("state", None)
        await msg.reply_text(
            "✅ បានរក្សាទុក QR ដាក់ប្រាក់រួចហើយ។\n"
            "ចាប់ពីពេលនេះ ពេលអ្នកប្រើចុច $1, $2, $5, $10, $20 ឬ $50 Bot នឹងផ្ញើរូប QR នេះ។",
            reply_markup=ADMIN_KEYBOARD
        )
        return


async def approve_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("ប្រើ៖ /approve_deposit ID")
        return
    did = int(context.args[0])
    with db() as c:
        d = c.execute("SELECT * FROM deposits WHERE id=?", (did,)).fetchone()
        if not d:
            await update.message.reply_text("មិនឃើញសំណើនេះទេ។")
            return
        if d["status"] != "pending":
            await update.message.reply_text(f"សំណើនេះមានស្ថានភាព {d['status']} រួចហើយ។")
            return
        c.execute("UPDATE deposits SET status='approved' WHERE id=?", (did,))
        c.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (d["amount"], d["user_id"]))
    await update.message.reply_text(f"បានអនុម័ត Deposit #{did} ចំនួន ${d['amount']:.2f}។")
    await context.bot.send_message(d["user_id"], f"✅ សំណើបញ្ចូលលុយ #{did} ត្រូវបានអនុម័ត។ +${d['amount']:.2f}")

async def reject_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("ប្រើ៖ /reject_deposit ID")
        return
    did = int(context.args[0])
    with db() as c:
        d = c.execute("SELECT * FROM deposits WHERE id=?", (did,)).fetchone()
        if not d:
            await update.message.reply_text("មិនឃើញសំណើនេះទេ។")
            return
        if d["status"] != "pending":
            await update.message.reply_text(f"សំណើនេះមានស្ថានភាព {d['status']} រួចហើយ។")
            return
        c.execute("UPDATE deposits SET status='rejected' WHERE id=?", (did,))
    await update.message.reply_text(f"បានបដិសេធ Deposit #{did}។")
    await context.bot.send_message(d["user_id"], f"❌ សំណើបញ្ចូលលុយ #{did} ត្រូវបានបដិសេធ។ សូមទាក់ទង Admin។")

def main():
    init_db()
    _sync_copybots_to_latest()
    app = Application.builder().token(TOKEN).post_init(setup_bot_commands).build()
    try:
        import telegram
        log.info("python-telegram-bot version: %s (Custom Emoji button icons require 22.7+)", telegram.__version__)
    except Exception:
        pass
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("stars", stars_cmd))
    app.add_handler(CommandHandler("toprobux", show_top_robux))
    app.add_handler(CommandHandler("premium_buttons", premium_buttons_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(CommandHandler("approve_deposit", approve_deposit))
    app.add_handler(CommandHandler("reject_deposit", reject_deposit))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
