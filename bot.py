import json
import sqlite3
import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, ContextTypes,
                          MessageHandler, CallbackQueryHandler, filters)

# Load konfigurasi
with open("config.json") as f:
    config = json.load(f)

TOKEN = config["token"]
ADMIN_IDS = config.get("admin_ids", [])
DB_PATH = "data/bot.db"

def connect_db():
    return sqlite3.connect(DB_PATH)

# === Command Handlers ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db = connect_db()
    cur = db.cursor()
    cur.execute("SELECT id FROM users WHERE id = ?", (user.id,))
    if not cur.fetchone():
        cur.execute("INSERT INTO users (id, username, first_name, registered_at) VALUES (?, ?, ?, ?)",
                    (user.id, user.username, user.first_name, datetime.datetime.now().isoformat()))
        db.commit()
        await update.message.reply_text("✅ Anda berhasil terdaftar!")
    else:
        await update.message.reply_text("📌 Anda sudah terdaftar.")
    db.close()

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Perintah:
/start
/saldo
/transaksi
/user [id] (admin)
/broadcast [pesan] (admin)")

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💰 Cek Saldo", callback_data="saldo")],
        [InlineKeyboardButton("📈 Histori Transaksi", callback_data="transaksi")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🔘 Pilih menu:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if query.data == "saldo":
        await send_saldo(query, user_id)
    elif query.data == "transaksi":
        await send_transaksi(query, user_id)

async def send_saldo(dest, user_id):
    db = connect_db()
    cur = db.cursor()
    cur.execute("SELECT COALESCE(SUM(CASE WHEN type='income' THEN amount ELSE -amount END), 0) FROM transactions WHERE user_id=?", (user_id,))
    saldo = cur.fetchone()[0]
    db.close()
    await dest.edit_message_text(f"💰 Saldo Anda: Rp {saldo:,.0f}")

async def send_transaksi(dest, user_id):
    db = connect_db()
    cur = db.cursor()
    cur.execute("SELECT type, amount, timestamp, description FROM transactions WHERE user_id=? ORDER BY timestamp DESC LIMIT 5", (user_id,))
    rows = cur.fetchall()
    db.close()
    if not rows:
        await dest.edit_message_text("📭 Belum ada transaksi.")
    else:
        lines = [f"[{t}] {desc or '-'}: {'+' if typ=='income' else '-'}Rp {amt:,.0f}" for typ, amt, t, desc in rows]
        await dest.edit_message_text("\n".join(lines))

# === Admin Only Commands ===
def is_admin(user_id):
    return user_id in ADMIN_IDS

async def user_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return await update.message.reply_text("🚫 Perintah ini hanya untuk admin.")
    if context.args:
        target_id = int(context.args[0])
        db = connect_db()
        cur = db.cursor()
        cur.execute("SELECT * FROM users WHERE id=?", (target_id,))
        row = cur.fetchone()
        db.close()
        if row:
            await update.message.reply_text(f"👤 ID: {row[0]}\nUsername: {row[1]}\nNama: {row[2]}\nDaftar: {row[3]}")
        else:
            await update.message.reply_text("❌ User tidak ditemukan.")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender_id = update.effective_user.id
    if not is_admin(sender_id):
        return await update.message.reply_text("🚫 Perintah ini hanya untuk admin.")
    msg = " ".join(context.args)
    if not msg:
        return await update.message.reply_text("⚠️ Masukkan pesan setelah perintah.")
    db = connect_db()
    cur = db.cursor()
    cur.execute("SELECT id FROM users")
    ids = [row[0] for row in cur.fetchall()]
    db.close()
    count = 0
    for uid in ids:
        try:
            await context.bot.send_message(chat_id=uid, text=f"📢 {msg}")
            count += 1
        except:
            pass
    await update.message.reply_text(f"✅ Pesan dikirim ke {count} user.")

# === Auto Reply ===
async def auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    if "halo" in text:
        await update.message.reply_text("Halo juga 👋")
    elif "gas" in text:
        await update.message.reply_text("🔥 GASSKAN 🔥")
    elif "anjay" in text:
        await update.message.reply_text("🛑 ANJAY DILARANG 🛑")

# === Main App ===
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("menu", menu))
app.add_handler(CommandHandler("user", user_cmd))
app.add_handler(CommandHandler("broadcast", broadcast))
app.add_handler(CallbackQueryHandler(button_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auto_reply))

app.run_polling()
