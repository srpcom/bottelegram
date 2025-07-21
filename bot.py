
import logging
import json
import sqlite3
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
)

# Load configuration
with open("config.json") as f:
    config = json.load(f)

BOT_TOKEN = config["BOT_TOKEN"]
ADMIN_IDS = config["ADMIN_IDS"]

# Database setup
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT
    )
""")
conn.commit()

# Logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    cursor.execute(
        "INSERT OR IGNORE INTO users (id, username, first_name, last_name) VALUES (?, ?, ?, ?)",
        (user.id, user.username, user.first_name, user.last_name)
    )
    conn.commit()
await update.message.reply_text(
    "Perintah:\n"
    "/start - Memulai bot\n"
    "/help - Menampilkan bantuan\n"
    "/user <id> - Info pengguna (admin saja)\n"
    "/broadcast <pesan> - Kirim pesan ke semua user (admin saja)"
)
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text("Perintah:
/start - Mulai bot
/broadcast - Khusus admin")

async def reply_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    if "halo" in text:
        await update.message.reply_text("Halo juga!")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Anda tidak diizinkan menggunakan perintah ini.")
        return

    if context.args:
        message = " ".join(context.args)
        cursor.execute("SELECT id FROM users")
        recipients = cursor.fetchall()
        for (uid,) in recipients:
            try:
                await context.bot.send_message(chat_id=uid, text=message)
            except Exception as e:
                logger.warning(f"Could not send message to {uid}: {e}")
        await update.message.reply_text("✅ Pesan telah dikirim.")
    else:
        await update.message.reply_text("⚠️ Format salah. Gunakan: /broadcast <pesan>")

async def userinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Anda tidak diizinkan menggunakan perintah ini.")
        return

    if context.args:
        try:
            uid = int(context.args[0])
            cursor.execute("SELECT * FROM users WHERE id = ?", (uid,))
            data = cursor.fetchone()
            if data:
                await update.message.reply_text(f"ID: {data[0]}
Username: {data[1]}
Nama: {data[2]} {data[3]}")
            else:
                await update.message.reply_text("User tidak ditemukan.")
        except ValueError:
            await update.message.reply_text("ID harus berupa angka.")
    else:
        await update.message.reply_text("Gunakan format: /user <id>")

# Main function
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("user", userinfo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply_message))

    app.run_polling()

if __name__ == "__main__":
    main()
