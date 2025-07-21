# -*- coding: utf-8 -*-
import logging
import json
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler, ConversationHandler
)

# --- Konfigurasi dan Inisialisasi ---

# Data konfigurasi sekarang dimasukkan langsung ke dalam skrip
BOT_TOKEN = "7964749149:AAFPLAEwCTpr2yEbPvMy6YfRxJOnncjkLko"
ADMIN_IDS = [5666536947]
SHOP_NAME = "SRPCOM STORE"
DEFAULT_BALANCE = 0
ENABLE_DIGITAL_PRODUCTS = True
BOT_VERSION = "v.1.2" # Menambahkan variabel versi

# Membuat dictionary 'config' tiruan agar bagian kode lain yang mungkin menggunakannya tidak error
config = {
    "BOT_TOKEN": BOT_TOKEN,
    "ADMIN_IDS": ADMIN_IDS,
    "SHOP_NAME": SHOP_NAME,
    "DEFAULT_BALANCE": DEFAULT_BALANCE,
    "ENABLE_DIGITAL_PRODUCTS": ENABLE_DIGITAL_PRODUCTS
}


# --- Pengaturan Database ---

conn = sqlite3.connect("bot.db", check_same_thread=False, isolation_level=None)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

def setup_database():
    """Membuat tabel database dan melakukan migrasi otomatis jika perlu."""
    # 1. Definisikan skema yang benar dalam pernyataan CREATE TABLE.
    # Ini berfungsi untuk database baru.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            balance REAL DEFAULT 0,
            transaction_count INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL, product_code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL, price REAL NOT NULL, description TEXT,
            stock_data TEXT, stock_numeric INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, transaction_id TEXT UNIQUE NOT NULL, user_id INTEGER NOT NULL,
            product_name TEXT NOT NULL, price REAL NOT NULL, details TEXT, status TEXT DEFAULT 'SUCCESS',
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)

    # 2. Untuk database yang sudah ada, lakukan migrasi untuk menambahkan kolom yang hilang.
    # Ini menangani kasus di mana DB dibuat dengan skema yang lebih lama.
    try:
        logger.info("Memeriksa skema database untuk migrasi...")
        cursor.execute("PRAGMA table_info(users)")
        columns = [row['name'].lower() for row in cursor.fetchall()]
        
        if 'first_name' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN first_name TEXT")
            logger.info("Migrasi DB: Menambahkan kolom 'first_name' ke tabel 'users'.")
        if 'last_name' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN last_name TEXT")
            logger.info("Migrasi DB: Menambahkan kolom 'last_name' ke tabel 'users'.")
        if 'balance' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN balance REAL DEFAULT 0")
            logger.info("Migrasi DB: Menambahkan kolom 'balance' ke tabel 'users'.")
        if 'transaction_count' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN transaction_count INTEGER DEFAULT 0")
            logger.info("Migrasi DB: Menambahkan kolom 'transaction_count' ke tabel 'users'.")

    except sqlite3.Error as e:
        logger.error(f"Gagal melakukan migrasi database: {e}")

    print("Database berhasil disiapkan.")


# --- Pengaturan Logging ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- State untuk ConversationHandler ---
(SELECTING_ACTION, ADD_PRODUCT_CATEGORY, ADD_PRODUCT_CODE, ADD_PRODUCT_NAME, 
 ADD_PRODUCT_PRICE, ADD_PRODUCT_DESC, ADD_PRODUCT_STOCK,
 MANAGE_USER_BALANCE) = range(8)

# --- Fungsi Helper Database ---

def get_user(user_id):
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return cursor.fetchone()

def get_all_users():
    cursor.execute("SELECT * FROM users ORDER BY id")
    return cursor.fetchall()

def register_user(user):
    try:
        cursor.execute(
            "INSERT OR IGNORE INTO users (id, username, first_name, last_name, balance) VALUES (?, ?, ?, ?, ?)",
            (user.id, user.username, user.first_name, user.last_name, DEFAULT_BALANCE)
        )
        logger.info(f"Pengguna baru terdaftar: {user.id} - {user.username}")
    except sqlite3.Error as e:
        logger.error(f"Gagal mendaftarkan pengguna {user.id}: {e}")

def get_product_by_code(product_code):
    cursor.execute("SELECT * FROM products WHERE product_code = ?", (product_code,))
    return cursor.fetchone()

def get_categories():
    cursor.execute("SELECT DISTINCT category FROM products ORDER BY category")
    return [row['category'] for row in cursor.fetchall()]

def get_products_by_category(category):
    cursor.execute("SELECT * FROM products WHERE category = ? ORDER BY name", (category,))
    return cursor.fetchall()

def get_user_transactions(user_id, limit=10):
    cursor.execute("SELECT * FROM transactions WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?", (user_id, limit))
    return cursor.fetchall()

def create_transaction(user_id, product, details):
    trx_id = f"TRX-{user_id}-{int(datetime.now().timestamp())}"
    cursor.execute(
        "INSERT INTO transactions (transaction_id, user_id, product_name, price, details) VALUES (?, ?, ?, ?, ?)",
        (trx_id, user_id, product['name'], product['price'], details)
    )
    cursor.execute(
        "UPDATE users SET balance = balance - ?, transaction_count = transaction_count + 1 WHERE id = ?",
        (product['price'], user_id)
    )

def admin_update_balance(user_id, amount, reason):
    """Mencatat perubahan saldo oleh admin dan memperbarui saldo pengguna."""
    cursor.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id))
    trx_id = f"ADM-{user_id}-{int(datetime.now().timestamp())}"
    action = "Ditambah" if amount > 0 else "Dipotong"
    desc = f"Saldo {action} oleh Admin"
    cursor.execute(
        "INSERT INTO transactions (transaction_id, user_id, product_name, price, details, status) VALUES (?, ?, ?, ?, ?, ?)",
        (trx_id, user_id, desc, abs(amount), reason, "ADMIN_ACTION")
    )
    logger.info(f"Admin mengubah saldo user {user_id} sebesar {amount}. Alasan: {reason}")


# --- Handler Perintah Pengguna ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menyapa pengguna dan menampilkan menu utama."""
    user = update.effective_user
    if not get_user(user.id):
        register_user(user)
    
    await send_main_menu(user.id, context)
    return ConversationHandler.END

async def send_main_menu(chat_id, context, message_id=None):
    """Mengirim atau mengedit pesan untuk menampilkan menu utama."""
    db_user = get_user(chat_id)
    
    # Pemeriksaan keamanan untuk mencegah error jika pengguna tidak ditemukan
    if not db_user:
        logger.error(f"Kritis: Gagal mengambil data pengguna untuk chat_id {chat_id} di send_main_menu.")
        await context.bot.send_message(chat_id=chat_id, text="Maaf, terjadi kesalahan saat memuat data Anda. Silakan coba lagi dengan /start.")
        return

    shop_name_str = str(SHOP_NAME) if SHOP_NAME is not None else "Toko Bot"
    
    # Menggunakan kode Unicode untuk emoji agar selalu tampil benar
    party_popper = "\U0001F389"
    user_icon = "\U0001F464"
    card_icon = "\U0001F4B3"
    money_icon = "\U0001F4B5"
    cart_icon = "\U0001F6D2"

    # PERUBAHAN: Menambahkan versi bot
    profile_text = (
        f"{party_popper} <b>SELAMAT DATANG DI {shop_name_str.upper()}</b> {party_popper}\n"
        f"<i>{BOT_VERSION}</i>\n\n"
        f"{user_icon} <b>Nama:</b> {db_user['first_name']}\n"
        f"{card_icon} <b>ID User:</b> <code>{db_user['id']}</code>\n"
        f"{money_icon} <b>Saldo:</b> Rp{db_user['balance']:,.0f}\n"
        f"{cart_icon} <b>Total Transaksi:</b> {db_user['transaction_count']} kali"
    )
    
    keyboard = []
    if config.get("ENABLE_DIGITAL_PRODUCTS"):
        keyboard.append([InlineKeyboardButton("📦 Beli Produk Digital", callback_data="list_kategori")])
    
    keyboard.append([
        InlineKeyboardButton("💰 TopUp Saldo", callback_data="deposit"),
        InlineKeyboardButton("🔑 Akunku", callback_data="my_account")
    ])

    if chat_id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("⚙️ Panel Admin", callback_data="admin_main")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    
    full_message = f"{profile_text}\n\nSilakan pilih tombol untuk melanjutkan:"

    if message_id:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=full_message, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await context.bot.send_message(chat_id=chat_id, text=full_message, reply_markup=reply_markup, parse_mode='HTML')

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Membatalkan proses saat ini (misal: tambah produk)."""
    context.user_data.clear()
    await update.message.reply_text("Proses telah dibatalkan.")
    await send_main_menu(update.effective_chat.id, context)
    return ConversationHandler.END


# --- Handler Callback Query (Tombol Inline) ---

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menangani input dari tombol inline."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    chat_id = query.message.chat_id
    message_id = query.message.message_id

    # Routing
    if data == "main_menu":
        await send_main_menu(chat_id, context, message_id)
    elif data == "list_kategori":
        await show_categories(query)
    elif data.startswith("list_produk:"):
        await show_products_in_category(query)
    elif data.startswith("beli:"):
        await show_purchase_confirmation(query)
    elif data.startswith("konfirmasi_beli:"):
        await process_purchase(query, context)
    elif data == "my_account":
        await show_my_account(query)
    elif data == "deposit":
        await query.edit_message_text(text="Fitur TopUp Saldo sedang dalam pengembangan. Untuk saat ini, silakan hubungi admin.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="main_menu")]]))
    
    # Admin routing
    elif data == "admin_main":
        await send_admin_panel(query)
    elif data == "admin_manage_users":
        await admin_list_users(query)
    elif data.startswith("admin_user_details:"):
        await admin_show_user_details(query)
    elif data.startswith("admin_user_balance:"):
        await admin_ask_balance_amount(query, context)
    elif data == "admin_manage_products":
        await send_product_management_menu(query)
    elif data == "admin_add_product":
        await admin_ask_product_category(query, context)

async def show_categories(query):
    categories = get_categories()
    if not categories:
        await query.edit_message_text(text="Maaf, belum ada produk.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="main_menu")]]))
        return
    keyboard = [[InlineKeyboardButton(cat, callback_data=f"list_produk:{cat}")] for cat in categories]
    keyboard.append([InlineKeyboardButton("⬅️ Kembali", callback_data="main_menu")])
    await query.edit_message_text(text="Silakan pilih kategori:", reply_markup=InlineKeyboardMarkup(keyboard))

async def show_products_in_category(query):
    category = query.data.split(":")[1]
    products = get_products_by_category(category)
    if not products:
        await query.edit_message_text(text=f"Tidak ada produk di kategori {category}.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="list_kategori")]]))
        return
    keyboard = [[InlineKeyboardButton(f"{p['name']} - Rp{p['price']:,.0f}", callback_data=f"beli:{p['product_code']}")] for p in products]
    keyboard.append([InlineKeyboardButton("⬅️ Kembali", callback_data="list_kategori")])
    await query.edit_message_text(text=f"Produk dalam kategori *{category}*:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def show_purchase_confirmation(query):
    product_code = query.data.split(":")[1]
    product = get_product_by_code(product_code)
    if not product:
        await query.edit_message_text(text="Produk tidak ditemukan.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="list_kategori")]]))
        return
    text = (f"<b>KONFIRMASI PESANAN</b>\n\nAnda akan membeli:\n<b>{product['name']}</b>\n\n"
            f"Harga: <b>Rp{product['price']:,.0f}</b>\nDeskripsi: {product['description']}\n\nLanjutkan pesanan?")
    keyboard = [[InlineKeyboardButton("✅ YA, LANJUTKAN", callback_data=f"konfirmasi_beli:{product_code}")],
                [InlineKeyboardButton("❌ BATALKAN", callback_data=f"list_produk:{product['category']}")] ]
    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def process_purchase(query, context):
    product_code = query.data.split(":")[1]
    product = get_product_by_code(product_code)
    user = get_user(query.message.chat_id)
    if not product or not user:
        await query.edit_message_text(text="Terjadi kesalahan, produk atau pengguna tidak ditemukan.")
        return

    if user['balance'] < product['price']:
        await query.edit_message_text(text=f"❌ Saldo Anda tidak mencukupi. Saldo: Rp{user['balance']:,.0f}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data=f"list_produk:{product['category']}")]]) )
        return

    stock_data_list = (product['stock_data'] or "").split('|')
    if not stock_data_list or stock_data_list[0] == '':
        await query.edit_message_text(text="Maaf, stok produk ini habis.")
        return
    
    item_diberikan = stock_data_list.pop(0)
    sisa_stok = "|".join(stock_data_list)
    cursor.execute("UPDATE products SET stock_data = ? WHERE product_code = ?", (sisa_stok, product_code))
    create_transaction(user['id'], product, item_diberikan)
    
    await query.edit_message_text(text=f"✅ <b>TRANSAKSI BERHASIL</b>\n\nTerima kasih telah membeli <b>{product['name']}</b>.\n\nBerikut detail produk Anda:\n<pre>{item_diberikan}</pre>", parse_mode='HTML')
    updated_user = get_user(user['id'])
    await context.bot.send_message(chat_id=user['id'], text=f"Saldo Anda sekarang: Rp{updated_user['balance']:,.0f}")

async def show_my_account(query):
    transactions = get_user_transactions(query.message.chat_id)
    if not transactions:
        await query.edit_message_text(text="Anda belum memiliki riwayat transaksi.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="main_menu")]]))
        return
    
    history_text = "📜 *10 Transaksi Terakhir Anda*\n\n"
    for trx in transactions:
        tgl = datetime.fromisoformat(trx['timestamp']).strftime('%d-%m-%y %H:%M')
        price_formatted = f"Rp{trx['price']:,.0f}"
        history_text += f"*{trx['product_name']}* - {price_formatted}\n"
        history_text += f"  _ID: {trx['transaction_id']}_\n"
        history_text += f"  _Tgl: {tgl}_\n\n"
    
    await query.edit_message_text(text=history_text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="main_menu")]]))

# --- Handler Admin ---

async def send_admin_panel(query):
    keyboard = [
        [InlineKeyboardButton("👥 Manajemen Pengguna", callback_data="admin_manage_users")],
        [InlineKeyboardButton("📦 Manajemen Produk", callback_data="admin_manage_products")],
        [InlineKeyboardButton("⬅️ Kembali ke Menu Utama", callback_data="main_menu")]
    ]
    await query.edit_message_text(text="⚙️ *Panel Admin*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def admin_list_users(query):
    users = get_all_users()
    keyboard = [[InlineKeyboardButton(f"{u['first_name']} (@{u['username'] or 'N/A'})", callback_data=f"admin_user_details:{u['id']}")] for u in users]
    keyboard.append([InlineKeyboardButton("⬅️ Kembali", callback_data="admin_main")])
    await query.edit_message_text(text="Pilih pengguna untuk dikelola:", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_show_user_details(query):
    user_id = int(query.data.split(":")[1])
    user = get_user(user_id)
    text = (f"<b>Detail Pengguna:</b> {user['first_name']}\n"
            f"<b>ID:</b> <code>{user['id']}</code>\n"
            f"<b>Username:</b> @{user['username']}\n"
            f"<b>Saldo:</b> Rp{user['balance']:,.0f}")
    keyboard = [
        [InlineKeyboardButton("💰 Ubah Saldo", callback_data=f"admin_user_balance:{user_id}")],
        [InlineKeyboardButton("⬅️ Kembali ke Daftar Pengguna", callback_data="admin_manage_users")]
    ]
    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def admin_ask_balance_amount(query, context):
    user_id = int(query.data.split(":")[1])
    context.user_data['managed_user_id'] = user_id
    await query.edit_message_text(text="Masukkan jumlah untuk mengubah saldo (gunakan - untuk mengurangi, misal: -5000). Ketik /batal untuk membatalkan.")
    return MANAGE_USER_BALANCE

async def admin_receive_balance_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        user_id = context.user_data['managed_user_id']
        context.user_data['balance_change_amount'] = amount
        await update.message.reply_text("Sekarang masukkan alasan perubahan saldo (misal: 'Bonus' atau 'Koreksi').")
        return SELECTING_ACTION # Use a generic state for reason
    except (ValueError, KeyError):
        await update.message.reply_text("Input tidak valid. Harap masukkan angka. Proses dibatalkan.")
        context.user_data.clear()
        return ConversationHandler.END

async def admin_receive_balance_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reason = update.message.text
    user_id = context.user_data['managed_user_id']
    amount = context.user_data['balance_change_amount']
    
    admin_update_balance(user_id, amount, reason)
    
    user = get_user(user_id)
    await update.message.reply_text(f"✅ Saldo untuk {user['first_name']} berhasil diubah. Saldo baru: Rp{user['balance']:,.0f}")
    
    # Notifikasi ke pengguna
    action_text = "ditambahkan" if amount > 0 else "dipotong"
    await context.bot.send_message(
        chat_id=user_id,
        text=f"ℹ️ Saldo Anda telah {action_text} oleh admin sebesar Rp{abs(amount):,.0f}.\nAlasan: {reason}\nSaldo Anda sekarang: Rp{user['balance']:,.0f}"
    )
    
    context.user_data.clear()
    return ConversationHandler.END

# --- Admin Product Management ---
async def send_product_management_menu(query):
    keyboard = [
        [InlineKeyboardButton("➕ Tambah Produk", callback_data="admin_add_product")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="admin_main")]
    ]
    await query.edit_message_text(text="📦 *Manajemen Produk*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def admin_ask_product_category(query, context):
    await query.edit_message_text(text="Masukkan nama Kategori untuk produk baru (misal: Streaming, Voucher Game). Ketik /batal untuk membatalkan.")
    return ADD_PRODUCT_CATEGORY

async def admin_receive_product_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['new_product'] = {'category': update.message.text}
    await update.message.reply_text("✅ Kategori diatur. Sekarang masukkan Kode Produk unik (misal: NETFLIX1).")
    return ADD_PRODUCT_CODE

async def admin_receive_product_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['new_product']['code'] = update.message.text.upper()
    await update.message.reply_text("✅ Kode diatur. Sekarang masukkan Nama Produk (misal: Netflix Premium 1 Bulan).")
    return ADD_PRODUCT_NAME

async def admin_receive_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['new_product']['name'] = update.message.text
    await update.message.reply_text("✅ Nama diatur. Sekarang masukkan Harga (hanya angka, misal: 50000).")
    return ADD_PRODUCT_PRICE

async def admin_receive_product_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['new_product']['price'] = float(update.message.text)
        await update.message.reply_text("✅ Harga diatur. Sekarang masukkan Deskripsi singkat produk.")
        return ADD_PRODUCT_DESC
    except ValueError:
        await update.message.reply_text("Harga tidak valid. Harap masukkan angka. Coba lagi.")
        return ADD_PRODUCT_PRICE

async def admin_receive_product_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['new_product']['desc'] = update.message.text
    await update.message.reply_text("✅ Deskripsi diatur. Terakhir, masukkan Stok Data (pisahkan setiap item dengan '|', misal: user1:pass1|user2:pass2).")
    return ADD_PRODUCT_STOCK

async def admin_receive_product_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    product = context.user_data['new_product']
    product['stock'] = update.message.text
    
    try:
        cursor.execute(
            "INSERT INTO products (category, product_code, name, price, description, stock_data) VALUES (?, ?, ?, ?, ?, ?)",
            (product['category'], product['code'], product['name'], product['price'], product['desc'], product['stock'])
        )
        await update.message.reply_text(f"✅ Produk '{product['name']}' berhasil ditambahkan!")
    except sqlite3.IntegrityError:
        await update.message.reply_text(f"❌ Gagal! Kode produk '{product['code']}' sudah ada. Proses dibatalkan.")
    except Exception as e:
        await update.message.reply_text(f"❌ Terjadi kesalahan: {e}. Proses dibatalkan.")
    
    context.user_data.clear()
    return ConversationHandler.END


# --- Fungsi Utama ---
def main():
    """Membangun dan menjalankan aplikasi bot Telegram."""
    setup_database()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Conversation handler untuk proses multi-langkah
    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_ask_product_category, pattern="^admin_add_product$"),
            CallbackQueryHandler(admin_ask_balance_amount, pattern="^admin_user_balance:"),
        ],
        states={
            ADD_PRODUCT_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_product_category)],
            ADD_PRODUCT_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_product_code)],
            ADD_PRODUCT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_product_name)],
            ADD_PRODUCT_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_product_price)],
            ADD_PRODUCT_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_product_desc)],
            ADD_PRODUCT_STOCK: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_product_stock)],
            MANAGE_USER_BALANCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_balance_amount)],
            SELECTING_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_balance_reason)],
        },
        fallbacks=[CommandHandler("batal", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("batal", cancel)) # Command /batal
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(handle_callback_query)) # Harus setelah conv_handler

    print("Bot sedang berjalan...")
    app.run_polling()

    print("Bot berhenti. Menutup koneksi database.")
    conn.close()

if __name__ == "__main__":
    main()
