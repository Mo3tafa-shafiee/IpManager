import logging
import sqlite3
import json
import os
import datetime
import threading

from flask import Flask, request, jsonify
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ParseMode, Bot
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
from apscheduler.schedulers.background import BackgroundScheduler
import requests

# --- تنظیمات اولیه لاگ ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- تعریف ثابت‌ها ---
ADMIN_CHAT_ID = None  # مقدارش از ورودی نصب میاد
BOT_TOKEN = None      # مقدارش از ورودی نصب میاد

DB_FILE = "license_manager.db"
BACKUP_FILE = "backup.json"

# مراحل کانورسیشن
(
    ADMIN_MENU, ADD_USER_NAME, ADD_USER_IP, ADD_USER_DURATION,
    MANAGE_USERS, USER_DETAIL, BROADCAST_CHOOSE, BROADCAST_MESSAGE,
    USER_MENU, USER_STATUS, USER_SERVICES, USER_IPS, USER_SUPPORT,
    CF_ADD_TOKEN, CF_ADD_ZONE,
) = range(15)

# --- ایجاد و اتصال دیتابیس ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS licenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_name TEXT NOT NULL,
            ip_address TEXT NOT NULL,
            start_date TEXT NOT NULL,
            expire_date TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            change_ip_count INTEGER DEFAULT 0
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS cloudflare_services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_id INTEGER,
            api_token TEXT,
            domain TEXT,
            zone_id TEXT,
            FOREIGN KEY (license_id) REFERENCES licenses(id)
        )
    ''')
    conn.commit()
    conn.close()

# --- افزودن کاربر ---
def add_license(user_name, ip_address, duration_days):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    start = datetime.date.today()
    expire = start + datetime.timedelta(days=duration_days)
    c.execute('''
        INSERT INTO licenses (user_name, ip_address, start_date, expire_date, active)
        VALUES (?, ?, ?, ?, 1)
    ''', (user_name, ip_address, start.isoformat(), expire.isoformat()))
    conn.commit()
    conn.close()

# --- گرفتن لیست کاربران ---
def get_all_licenses():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, user_name, ip_address, expire_date, active FROM licenses')
    rows = c.fetchall()
    conn.close()
    return rows

# --- گرفتن جزئیات کاربر ---
def get_license_by_id(license_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT * FROM licenses WHERE id = ?', (license_id,))
    row = c.fetchone()
    conn.close()
    return row

# --- به‌روزرسانی اعتبار ---
def update_license_expire(license_id, extra_days):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    license = get_license_by_id(license_id)
    if license:
        expire_date = datetime.datetime.strptime(license[4], "%Y-%m-%d").date()
        new_expire = expire_date + datetime.timedelta(days=extra_days)
        c.execute('UPDATE licenses SET expire_date = ? WHERE id = ?', (new_expire.isoformat(), license_id))
        conn.commit()
    conn.close()

# --- غیر فعال کردن کاربر ---
def deactivate_license(license_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE licenses SET active = 0 WHERE id = ?', (license_id,))
    conn.commit()
    conn.close()

# --- افزایش شمارنده تغییر IP ---
def increment_ip_change(license_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE licenses SET change_ip_count = change_ip_count + 1 WHERE id = ?', (license_id,))
    conn.commit()
    conn.close()

# --- تهیه گزارش‌ها ---
def report_ip_changes_last_24h():
    # این بخش باید بر اساس دیتا تغییر IP های واقعی باشه
    # فرض میکنیم شمارش تغییر IP در جدول لایسنس‌ها هست
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT user_name, ip_address, change_ip_count FROM licenses WHERE active=1')
    rows = c.fetchall()
    conn.close()
    text = "گزارش تغییر IP در ۲۴ ساعت گذشته:\n"
    for row in rows:
        text += f"کاربر: {row[0]} - آی‌پی: {row[1]} - تعداد تغییرات IP: {row[2]}\n"
    return text

def report_licenses_status():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT user_name, ip_address, expire_date FROM licenses')
    rows = c.fetchall()
    conn.close()
    text = "وضعیت کلی لایسنس‌ها:\n"
    today = datetime.date.today()
    for row in rows:
        expire = datetime.datetime.strptime(row[2], "%Y-%m-%d").date()
        days_left = (expire - today).days
        text += f"کاربر: {row[0]} - آی‌پی: {row[1]} - باقی‌مانده اعتبار: {days_left} روز\n"
    return text

# --- بکاپ روزانه ---
def backup_to_json(bot: Bot):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT * FROM licenses')
    licenses = c.fetchall()
    c.execute('SELECT * FROM cloudflare_services')
    services = c.fetchall()
    conn.close()
    data = {
        "licenses": [dict(zip(["id","user_name","ip_address","start_date","expire_date","active","change_ip_count"], l)) for l in licenses],
        "cloudflare_services": [dict(zip(["id","license_id","api_token","domain","zone_id"], s)) for s in services]
    }
    with open(BACKUP_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    # ارسال به ادمین
    with open(BACKUP_FILE, "rb") as f:
        bot.send_document(chat_id=ADMIN_CHAT_ID, document=f, filename=BACKUP_FILE)

# --- زمان‌بندی‌ها ---
scheduler = BackgroundScheduler()

def start_scheduled_jobs(bot: Bot):
    # هر 6 ساعت گزارش IP changes
    scheduler.add_job(lambda: bot.loop.create_task(send_report_ip_changes(bot)), "interval", hours=6)
    # هر 24 ساعت گزارش وضعیت کلی لایسنس‌ها
    scheduler.add_job(lambda: bot.loop.create_task(send_report_license_status(bot)), "interval", hours=24)
    # هر 24 ساعت بکاپ روزانه
    scheduler.add_job(lambda: backup_to_json(bot), "interval", hours=24)
    scheduler.start()

async def send_report_ip_changes(bot: Bot):
    text = report_ip_changes_last_24h()
    await bot.send_message(chat_id=ADMIN_CHAT_ID, text=text)

async def send_report_license_status(bot: Bot):
    text = report_licenses_status()
    await bot.send_message(chat_id=ADMIN_CHAT_ID, text=text)

# --- شروع ربات ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id == ADMIN_CHAT_ID:
        keyboard = [
            [InlineKeyboardButton("کاربر جدید ➕", callback_data='admin_add_user')],
            [InlineKeyboardButton("مدیریت کاربران 👥", callback_data='admin_manage_users')],
            [InlineKeyboardButton("وضعیت لایسنس‌ها 📊", callback_data='admin_license_status')],
            [InlineKeyboardButton("ارسال پیام همگانی 📣", callback_data='admin_broadcast')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("خوش آمدید ادمین عزیز! منوی مدیریت:", reply_markup=reply_markup)
        return ADMIN_MENU
    else:
        keyboard = [
            [InlineKeyboardButton("وضعیت اعتبار 💳", callback_data='user_status')],
            [InlineKeyboardButton("مدیریت سرویس‌ها ☁️", callback_data='user_services')],
            [InlineKeyboardButton("مدیریت آی‌پی‌ها 🌐", callback_data='user_ips')],
            [InlineKeyboardButton("آموزش 📚", callback_data='user_education')],
            [InlineKeyboardButton("ارتباط با پشتیبانی 🆘", callback_data='user_support')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("به ربات خوش آمدید! منوی کاربری:", reply_markup=reply_markup)
        return USER_MENU

# ... ادامه کد: پیاده‌سازی callback ها، handler ها، مدیریت مراحل، ارسال گزارش، مدیریت کاربران و غیره ...

# در صورت تمایل من ادامه کد رو هم کامل برایت آماده کنم و ارسال کنم.

# اما اگر می‌خواهی ابتدا این قسمت پایه‌ای را تست کنی و بعد ادامه بدهیم، بگو.

if __name__ == '__main__':
    import sys
    if len(sys.argv) != 3:
        print("Usage: python main.py <BOT_TOKEN> <ADMIN_CHAT_ID>")
        exit(1)
    BOT_TOKEN = sys.argv[1]
    ADMIN_CHAT_ID = int(sys.argv[2])

    init_db()

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))

    print("Bot is running...")
    start_scheduled_jobs(application.bot)
    application.run_polling()
