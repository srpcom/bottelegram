import logging
import json
import sqlite3
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
)

# --- Konfigurasi dan Inisialisasi ---

# Muat konfigurasi dari config.json
try:
    with open("config.json") as f:
        config = json.load(f)
    BOT_TOKEN = config["BOT_TOKEN"]
    ADMIN_IDS = config["ADMIN_IDS"]
except FileNotFoundError:
    print("Kesalahan: File 'config.json' tidak ditemukan. Harap buat file tersebut.")
    exit()
except KeyError as e:
    print(f"Kesalahan: Kunci yang diperlukan {e} tidak ditemukan di 'config.json'.")
    exit()

# Pengaturan database SQLite
# check_same_thread=False diperlukan karena python-telegram-bot berjalan di thread yang berbeda.
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

# Pengaturan logging untuk memantau aktivitas bot
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# --- Handler Perintah ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menyapa pengguna baru dan menyimpan informasi mereka ke database."""
    user = update.effective_user
    try:
        cursor.execute(
            "INSERT OR IGNORE INTO users (id, username, first_name, last_name) VALUES (?, ?, ?, ?)",
            (user.id, user.username, user.first_name, user.last_name)
        )
        conn.commit()
        await update.message.reply_text("Selamat datang! Bot telah diaktifkan. Ketik /help untuk melihat daftar perintah.")
    except sqlite3.Error as e:
        logger.error(f"Kesalahan database pada perintah /start: {e}")
        await update.message.reply_text("Maaf, terjadi kesalahan saat memproses permintaan Anda.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan pesan bantuan dengan daftar perintah yang tersedia."""
    help_text = (
        "Berikut adalah daftar perintah yang tersedia:\n\n"
        "/start - Memulai dan mendaftarkan diri Anda ke bot.\n"
        "/help - Menampilkan pesan bantuan ini.\n\n"
        "<b>Perintah Khusus Admin:</b>\n"
        "/user <code>&lt;id&gt;</code> - Mendapatkan informasi tentang pengguna tertentu.\n"
        "/broadcast <code>&lt;pesan&gt;</code> - Mengirim pesan ke semua pengguna bot."
    )
    await update.message.reply_text(help_text, parse_mode='HTML')

async def reply_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Memberikan balasan otomatis untuk pesan teks biasa."""
    text = update.message.text.lower()
    if "halo" in text:
        await update.message.reply_text("Halo juga!")
    # Anda bisa menambahkan lebih banyak balasan otomatis di sini jika perlu

# --- Handler Perintah Admin ---

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mengirim pesan ke semua pengguna yang terdaftar. Hanya untuk admin."""
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Anda tidak memiliki izin untuk menggunakan perintah ini.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Format salah. Gunakan: /broadcast <pesan yang akan dikirim>")
        return

    message = " ".join(context.args)
    try:
        cursor.execute("SELECT id FROM users")
        recipients = cursor.fetchall()
        count = 0
        for (uid,) in recipients:
            try:
                await context.bot.send_message(chat_id=uid, text=f"📢 Pesan dari Admin:\n\n{message}")
                count += 1
            except Exception as e:
                logger.warning(f"Gagal mengirim pesan broadcast ke ID {uid}: {e}")
        await update.message.reply_text(f"✅ Pesan berhasil dikirim ke {count} dari {len(recipients)} pengguna.")
    except sqlite3.Error as e:
        logger.error(f"Kesalahan database pada perintah /broadcast: {e}")
        await update.message.reply_text("Maaf, terjadi kesalahan saat mengambil data pengguna.")


async def userinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mendapatkan informasi pengguna berdasarkan ID. Hanya untuk admin."""
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Anda tidak memiliki izin untuk menggunakan perintah ini.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Format salah. Gunakan: /user <id_pengguna>")
        return

    try:
        uid = int(context.args[0])
        cursor.execute("SELECT * FROM users WHERE id = ?", (uid,))
        data = cursor.fetchone()

        if data:
            # Membersihkan nilai None agar tidak tampil sebagai "None" di pesan balasan
            username = f"@{data[1]}" if data[1] else "Tidak ada"
            first_name = data[2] if data[2] else ""
            last_name = data[3] if data[3] else ""
            full_name = f"{first_name} {last_name}".strip() or "Tidak ada"

            await update.message.reply_text(
                f"<b>👤 Informasi Pengguna</b>\n\n"
                f"<b>ID:</b> <code>{data[0]}</code>\n"
                f"<b>Username:</b> {username}\n"
                f"<b>Nama Lengkap:</b> {full_name}",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text("User dengan ID tersebut tidak ditemukan di dalam database.")
    except ValueError:
        await update.message.reply_text("⚠️ ID pengguna harus berupa angka.")
    except IndexError:
        # Ini seharusnya tidak terjadi karena sudah dicek dengan 'if not context.args'
        await update.message.reply_text("⚠️ Format salah. Gunakan: /user <id_pengguna>")
    except sqlite3.Error as e:
        logger.error(f"Kesalahan database pada perintah /userinfo: {e}")
        await update.message.reply_text("Maaf, terjadi kesalahan saat mencari data pengguna.")


# --- Fungsi Utama ---

def main():
    """Membangun dan menjalankan aplikasi bot Telegram."""
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Menambahkan handler untuk berbagai perintah
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("user", userinfo))

    # Menambahkan handler untuk pesan teks biasa (bukan perintah)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply_message))

    # Memulai bot untuk menerima pembaruan
    print("Bot sedang berjalan...")
    app.run_polling()

    # Menutup koneksi database saat bot berhenti (misal: dengan Ctrl+C)
    print("Bot berhenti. Menutup koneksi database.")
    conn.close()


if __name__ == "__main__":
    main()
