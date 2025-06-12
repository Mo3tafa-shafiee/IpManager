#!/bin/bash

set -e

echo "Starting installation..."

# تابع نصب پکیج پایتون در صورت نبودن
install_python_package() {
    PACKAGE=$1
    python3 -c "import $PACKAGE" &>/dev/null || pip3 install "$PACKAGE"
}

# نصب python3 و pip در صورت نبودن
if ! command -v python3 &>/dev/null; then
    echo "python3 not found. Installing..."
    apt update
    apt install -y python3
else
    echo "python3 is already installed."
fi

if ! command -v pip3 &>/dev/null; then
    echo "python3-pip not found. Installing..."
    apt update
    apt install -y python3-pip
else
    echo "python3-pip is already installed."
fi

# نصب curl در صورت نبودن
if ! command -v curl &>/dev/null; then
    echo "curl not found. Installing..."
    apt update
    apt install -y curl
else
    echo "curl is already installed."
fi

# حذف پکیج اشتباه telegram (اگر نصب است)
pip3 uninstall -y telegram || true

# نصب پکیج درست python-telegram-bot
pip3 install -U python-telegram-bot

# نصب پکیج apscheduler در صورت نبودن
install_python_package apscheduler

echo "All dependencies installed."

# ایجاد فایل bot.py برای اجرای بات تلگرام
cat > bot.py << 'EOF'
import os
import json
import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome to the license management bot!")

def backup_job(app):
    data = load_data()
    now = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    file_name = f'backup_{now}.json'
    with open(file_name, 'w') as f:
        json.dump(data, f, indent=4)
    app.bot.send_document(chat_id=ADMIN_ID, document=open(file_name, 'rb'), filename=file_name)
    os.remove(file_name)

def main():
    global ADMIN_ID

    TOKEN = input("Enter your bot token: ").strip()
    ADMIN_ID = int(input("Enter your Telegram numeric ID: ").strip())

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: backup_job(app), 'interval', hours=24)
    scheduler.start()

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
EOF

echo "Starting the bot..."
python3 bot.py
