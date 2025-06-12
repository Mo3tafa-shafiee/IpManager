#!/bin/bash

# بررسی و نصب پیش‌نیازهای پایه
check_and_install() {
    PACKAGE_NAME=$1
    if ! command -v $PACKAGE_NAME &> /dev/null; then
        echo "$PACKAGE_NAME not found. Installing..."
        if [ -x "$(command -v apt)" ]; then
            apt update && apt install -y $PACKAGE_NAME
        elif [ -x "$(command -v yum)" ]; then
            yum install -y $PACKAGE_NAME
        elif [ -x "$(command -v dnf)" ]; then
            dnf install -y $PACKAGE_NAME
        else
            echo "Package manager not supported. Please install $PACKAGE_NAME manually."
            exit 1
        fi
    else
        echo "$PACKAGE_NAME is already installed."
    fi
}

check_and_install python3
check_and_install python3-pip
check_and_install curl

# نصب کتابخانه‌های پایتون در صورت نیاز
install_python_package() {
    PACKAGE=$1
    python3 -c "import $PACKAGE" 2>/dev/null || pip3 install $PACKAGE
}

install_python_package telegram
install_python_package apscheduler

# اجرای اسکریپت اصلی
python3 <<EOF
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackContext, CallbackQueryHandler
from apscheduler.schedulers.background import BackgroundScheduler
import os, json, datetime

TOKEN = input("Enter your bot token: ").strip()
ADMIN_ID = int(input("Enter your Telegram numeric ID: ").strip())

DATA_FILE = 'user_data.json'
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, 'w') as f:
        json.dump({}, f)

def load_data():
    with open(DATA_FILE, 'r') as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def backup_job(app):
    data = load_data()
    now = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M')
    file_name = f'backup_{now}.json'
    with open(file_name, 'w') as f:
        json.dump(data, f, indent=4)
    app.bot.send_document(chat_id=ADMIN_ID, document=open(file_name, 'rb'), filename=file_name)
    os.remove(file_name)

async def start(update: Update, context: CallbackContext):
    await update.message.reply_text("به ربات مدیریت لایسنس خوش آمدید!")

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: backup_job(app), 'interval', days=1)
    scheduler.start()

    print("Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()
EOF
