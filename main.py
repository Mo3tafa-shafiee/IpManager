import os
import json
import sqlite3
import asyncio
from datetime import datetime, timedelta
from threading import Thread

from flask import Flask, jsonify, request
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    CallbackQueryHandler, MessageHandler, filters
)

# Load env variables
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

DB_FILE = 'licenses.db'
BACKUP_FILE = 'backup.json'

# --- DB functions ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS licenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        ip TEXT,
        start_date TEXT,
        duration_days INTEGER,
        active INTEGER DEFAULT 1
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS ip_changes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        license_id INTEGER,
        change_date TEXT,
        FOREIGN KEY(license_id) REFERENCES licenses(id)
    )''')
    conn.commit()
    conn.close()

def add_license(username, ip, duration_days):
    start_date = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO licenses (username, ip, start_date, duration_days, active) VALUES (?, ?, ?, ?, 1)",
              (username, ip, start_date, duration_days))
    conn.commit()
    conn.close()

def get_all_licenses():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, username, ip, start_date, duration_days, active FROM licenses")
    rows = c.fetchall()
    conn.close()
    return rows

def get_license_by_id(license_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, username, ip, start_date, duration_days, active FROM licenses WHERE id=?", (license_id,))
    row = c.fetchone()
    conn.close()
    return row

def update_license_duration(license_id, extra_days):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Get current start_date and duration
    c.execute("SELECT start_date, duration_days FROM licenses WHERE id=?", (license_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return False
    start_date_str, duration_days = row
    start_date = datetime.fromisoformat(start_date_str)
    new_duration = duration_days + extra_days
    c.execute("UPDATE licenses SET duration_days=? WHERE id=?", (new_duration, license_id))
    conn.commit()
    conn.close()
    return True

def deactivate_license(license_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE licenses SET active=0 WHERE id=?", (license_id,))
    conn.commit()
    conn.close()

def record_ip_change(license_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO ip_changes (license_id, change_date) VALUES (?, ?)",
              (license_id, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def get_ip_changes_past_24h():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    since = datetime.utcnow() - timedelta(hours=24)
    c.execute("SELECT license_id, COUNT(*) FROM ip_changes WHERE change_date > ? GROUP BY license_id", (since.isoformat(),))
    rows = c.fetchall()
    conn.close()
    return rows

# --- Backup function ---
async def send_backup(application):
    while True:
        await asyncio.sleep(86400)  # 24 hours

        # Prepare data backup as JSON
        licenses = get_all_licenses()
        backup_data = []
        for lic in licenses:
            backup_data.append({
                "id": lic[0],
                "username": lic[1],
                "ip": lic[2],
                "start_date": lic[3],
                "duration_days": lic[4],
                "active": lic[5],
            })

        backup_json = json.dumps(backup_data, indent=4)
        with open(BACKUP_FILE, 'w') as f:
            f.write(backup_json)

        # Send backup file to admin
        try:
            with open(BACKUP_FILE, 'rb') as file:
                await application.bot.send_document(chat_id=ADMIN_ID, document=file, filename=BACKUP_FILE, caption="Daily backup of licenses")
        except Exception as e:
            print("Failed to send backup:", e)

# --- Telegram Bot handlers ---
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id == ADMIN_ID:
        keyboard = [
            [InlineKeyboardButton("کاربر جدید", callback_data="new_user")],
            [InlineKeyboardButton("مدیریت کاربران", callback_data="manage_users")],
            [InlineKeyboardButton("وضعیت لایسنس ها", callback_data="license_status")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("خوش آمدید ادمین! یکی از گزینه‌ها را انتخاب کنید:", reply_markup=reply_markup)
    else:
        keyboard = [
            [InlineKeyboardButton("وضعیت اعتبار", callback_data="user_status")],
            [InlineKeyboardButton("مدیریت سرویس ها", callback_data="manage_services")],
            [InlineKeyboardButton("مدیریت آی پی ها", callback_data="manage_ips")],
            [InlineKeyboardButton("آموزش", callback_data="tutorial")],
            [InlineKeyboardButton("ارتباط با پشتیبانی", callback_data="support")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("خوش آمدید! یکی از گزینه‌ها را انتخاب کنید:", reply_markup=reply_markup)

# --- Callback query handler ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()

    if user_id == ADMIN_ID:
        # Admin menu options
        if query.data == "new_user":
            await query.edit_message_text("لطفا اطلاعات کاربر جدید را به ترتیب با فرمت زیر ارسال کنید:\n\nنام کاربر | آی پی سرور خارج | مدت اعتبار به روز")
            context.user_data['awaiting_new_user'] = True

        elif query.data == "manage_users":
            # List users
            licenses = get_all_licenses()
            if not licenses:
                await query.edit_message_text("هیچ کاربری یافت نشد.")
                return

            text = "لیست کاربران:\n"
            for lic in licenses:
                lic_id, username, ip, start_date, duration_days, active = lic
                expire_date = datetime.fromisoformat(start_date) + timedelta(days=duration_days)
                remaining_days = (expire_date - datetime.utcnow()).days
                status = "فعال" if active else "غیرفعال"
                text += f"<a href='tg://user?id={lic_id}'>{username}</a> | IP: {ip} | باقی مانده: {remaining_days} روز | وضعیت: {status}\n"
            await query.edit_message_text(text, parse_mode='HTML')

        elif query.data == "license_status":
            # Status report summary
            licenses = get_all_licenses()
            now = datetime.utcnow()

            text = "گزارش وضعیت کلی لایسنس‌ها:\n"
            for lic in licenses:
                lic_id, username, ip, start_date, duration_days, active = lic
                expire_date = datetime.fromisoformat(start_date) + timedelta(days=duration_days)
                remaining_days = (expire_date - now).days
                status = "فعال" if active else "غیرفعال"
                text += f"نام: {username} | IP: {ip} | باقی مانده: {remaining_days} روز | وضعیت: {status}\n"
            await query.edit_message_text(text)

    else:
        # User menu options (simplified)
        if query.data == "user_status":
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT username, ip, start_date, duration_days FROM licenses WHERE active=1")
            lic = c.fetchone()
            conn.close()
            if lic:
                username, ip, start_date, duration_days = lic
                expire_date = datetime.fromisoformat(start_date) + timedelta(days=duration_days)
                remaining_days = (expire_date - datetime.utcnow()).days
                text = f"نام: {username}\nIP: {ip}\nمدت اعتبار باقی‌مانده: {remaining_days} روز\n\nتعرفه خرید اعتبار:\n1 ماهه: 2 تتر\n3 ماهه: 5 تتر\n6 ماهه: 10 تتر\n\nواریز به کیف پول: dhflaskfhlaksjfhlakdjsfhalkdfalf"
            else:
                text = "شما هیچ لایسنسی ندارید."
            await query.edit_message_text(text)

# --- Message handler for admin input ---
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if user_id == ADMIN_ID:
        if context.user_data.get('awaiting_new_user'):
            # Expecting: "username | ip | duration_days"
            try:
                username, ip, days = [x.strip() for x in text.split("|")]
                days = int(days)
                add_license(username, ip, days)
                await update.message.reply_text(f"کاربر {username} با آی‌پی {ip} و مدت {days} روز اضافه شد.")
            except Exception as e:
                await update.message.reply_text("خطا در فرمت ورودی. لطفا به شکل صحیح ارسال کنید: نام کاربر | آی پی | مدت اعتبار (روز)")
            finally:
                context.user_data['awaiting_new_user'] = False
        else:
            await update.message.reply_text("برای مدیریت از دکمه‌های منو استفاده کنید.")
    else:
        await update.message.reply_text("دسترسی ندارید.")

# --- Flask API ---

app = Flask(__name__)

@app.route('/api/licenses', methods=['GET'])
def api_get_licenses():
    licenses = get_all_licenses()
    result = []
    for lic in licenses:
        lic_id, username, ip, start_date, duration_days, active = lic
        expire_date = datetime.fromisoformat(start_date) + timedelta(days=duration_days)
        remaining_days = (expire_date - datetime.utcnow()).days
        result.append({
            "id": lic_id,
            "username": username,
            "ip": ip,
            "start_date": start_date,
            "duration_days": duration_days,
            "active": active,
            "remaining_days": remaining_days
        })
    return jsonify(result)

def run_flask():
    app.run(host="0.0.0.0", port=5000)

# --- Main ---

async def main():
    init_db()
    app_thread = Thread(target=run_flask, daemon=True)
    app_thread.start()

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler('start', start_handler))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler))

    # Start backup task
    asyncio.create_task(send_backup(application))

    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
