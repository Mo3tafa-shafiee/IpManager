#!/bin/bash

set -e

echo "Updating system and installing dependencies..."
apt update -y
apt install -y python3 python3-pip curl

echo "Installing python packages..."
pip3 install --no-cache-dir flask python-telegram-bot requests schedule

# دریافت توکن ربات و آیدی تلگرام ادمین
read -p "Enter your bot token: " BOT_TOKEN
read -p "Enter your Telegram numeric ID (Admin ID): " ADMIN_ID

# ذخیره در config.py
cat > config.py << EOF
BOT_TOKEN = "$BOT_TOKEN"
ADMIN_ID = $ADMIN_ID
EOF

# چک دانلود فایل main.py اگر موجود نبود
if [ ! -f main.py ]; then
    echo "Downloading main.py..."
    curl -L -o main.py https://raw.githubusercontent.com/Mo3tafa-shafiee/IpManager/main.py
fi

# ایجاد سرویس systemd
SERVICE_FILE="/etc/systemd/system/ipmanager.service"

if systemctl is-active --quiet ipmanager.service; then
    echo "Stopping existing service..."
    systemctl stop ipmanager.service
fi

echo "Creating systemd service file..."

cat > $SERVICE_FILE << EOF
[Unit]
Description=IP Manager Telegram Bot Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$(pwd)
ExecStart=/usr/bin/python3 $(pwd)/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo "Reloading systemd daemon and enabling service..."
systemctl daemon-reload
systemctl enable ipmanager.service
systemctl start ipmanager.service

echo "Sending welcome message to admin..."

python3 - << EOF
import telegram
bot = telegram.Bot(token="$BOT_TOKEN")
bot.send_message(chat_id=$ADMIN_ID, text="Welcome to the License Management Bot!\nInstallation completed successfully.")
EOF

echo "Installation finished. Bot is running."
