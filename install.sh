#!/bin/bash

clear
echo "شروع نصب پیش‌نیازها..."

# بررسی نصب بودن python3
if ! command -v python3 &> /dev/null
then
    echo "Python3 نصب نیست. نصب در حال انجام..."
    if [ -x "$(command -v apt)" ]; then
        sudo apt update && sudo apt install -y python3 python3-venv python3-pip
    elif [ -x "$(command -v yum)" ]; then
        sudo yum install -y python3 python3-pip
    else
        echo "مدیر بسته مناسب پیدا نشد. لطفا به صورت دستی Python3 نصب کنید."
        exit 1
    fi
else
    echo "Python3 از قبل نصب است."
fi

# بررسی نصب pip
if ! command -v pip3 &> /dev/null
then
    echo "pip نصب نیست. نصب در حال انجام..."
    if [ -x "$(command -v apt)" ]; then
        sudo apt install -y python3-pip
    elif [ -x "$(command -v yum)" ]; then
        sudo yum install -y python3-pip
    else
        echo "pip نصب نشد. لطفا به صورت دستی نصب کنید."
        exit 1
    fi
else
    echo "pip از قبل نصب است."
fi

# نصب پکیج‌های پایتون مورد نیاز
echo "نصب پکیج‌های Python مورد نیاز..."
pip3 install --upgrade pip
pip3 install python-telegram-bot flask apscheduler requests

# دسترسی اجرایی دادن به main.py
chmod +x main.py

echo "پیش‌نیازها نصب شدند."

echo "برای اجرای ربات، دستور زیر را با مقدار توکن بات و آیدی ادمین اجرا کنید:"
echo "python3 main.py <BOT_TOKEN> <ADMIN_CHAT_ID>"
echo "مثال:"
echo "python3 main.py 123456789:ABCdefGhIJKlmNoPQRstUvWXyz 123456789"

echo "نصب کامل شد. موفق باشید!"
