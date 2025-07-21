#!/bin/bash

echo "🚀 Memulai instalasi bot Telegram..."

# Update sistem dan instal dependensi
sudo apt update && sudo apt install -y python3 python3-pip git

# Tanya interaktif
read -p "Masukkan token API Telegram bot Anda: " token

# Buat folder target
mkdir -p /opt/telegram-bot

# Clone repo
git clone https://github.com/srpcom/bottelegram.git /opt/telegram-bot

# Simpan token ke config
cat <<EOF > /opt/telegram-bot/config.json
{
  "token": "$token"
}
EOF

# Masuk ke folder bot dan instal dependensi
cd /opt/telegram-bot
pip3 install -r requirements.txt

# Buat systemd service
sudo tee /etc/systemd/system/telegrambot.service > /dev/null <<EOF
[Unit]
Description=Telegram Auto Reply Bot
After=network.target

[Service]
ExecStart=/usr/bin/python3 /opt/telegram-bot/bot.py
WorkingDirectory=/opt/telegram-bot
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF

# Aktifkan dan mulai service
sudo systemctl daemon-reexec
sudo systemctl daemon-reload
sudo systemctl enable telegrambot
sudo systemctl restart telegrambot

echo "✅ Bot Telegram berhasil diinstal dan berjalan sebagai service systemd!"
