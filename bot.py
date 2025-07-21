import logging
import json
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler
)

# --- Konfigurasi dan Inisialisasi ---

# Fungsi untuk memuat konfigurasi dari config.json
def load_config():
    try:
        with open("config.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print("Kesalahan: File 'config.json' tidak ditemukan. Harap buat file tersebut.")
        # Membuat file config.json contoh jika tidak ada
        default_config = {
            "BOT_TOKEN": "7964749149:AAFPLAEwCTpr2yEbPvMy6YfRxJOnncjkLko",
            "ADMIN_IDS": [5666536947],
            "SHOP_NAME": "SRPCOM STORE",
            "DEFAULT_BALANCE": 0,
            "ENABLE_DIGITAL_PRODUCTS": True
        }
        with open("config.json", "w") as f:
            json.dump(default_config, f, indent=4)
        print("File 'config.json' contoh telah dibuat. Harap isi dengan data Anda.")
        exit()
    except KeyError as e:
        print(f"Kesalahan: Kunci yang diperlukan {e} tidak ditemukan di 'config.json'.")
        exit()

config = load_config()
BOT_TOKEN = config["BOT_TOKEN"]
ADMIN_IDS = config["ADMIN_IDS"]
SHOP_NAME = config.get("SHOP_NAME", "Toko Bot")
DEFAULT_BALANCE = config.get("DEFAULT_BALANCE", 0)

# --- Pengaturan Database ---

# check_same_thread=False diperlukan karena python-telegram-bot berjalan di thread yang berbeda.
conn = sqlite3.connect("bot.db", check_same_thread=False, isolation_level=None)
conn.row_factory = sqlite3.Row # Memungkinkan akses kolom berdasarkan nama
cursor = conn.cursor()

def setup_database():
    """Membuat tabel database jika belum ada."""
    # Perluas tabel users
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
    # Tambah tabel baru
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            product_code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            description TEXT,
            stock_data TEXT, -- Untuk produk tipe data/akun, dipisah dengan '|'
            stock_numeric INTEGER DEFAULT 0 -- Untuk produk tipe file/stok angka
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id TEXT UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            price REAL NOT NULL,
            details TEXT,
            status TEXT DEFAULT 'SUCCESS',
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    print("Database berhasil disiapkan.")

# --- Pengaturan Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Fungsi Helper Database ---

def get_user(user_id):
    """Mengambil data pengguna dari database."""
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return cursor.fetchone()

def register_user(user):
    """Mendaftarkan pengguna baru ke database."""
    try:
        cursor.execute(
            "INSERT OR IGNORE INTO users (id, username, first_name, last_name, balance) VALUES (?, ?, ?, ?, ?)",
            (user.id, user.username, user.first_name, user.last_name, DEFAULT_BALANCE)
        )
        logger.info(f"Pengguna baru terdaftar: {user.id} - {user.username}")
    except sqlite3.Error as e:
        logger.error(f"Gagal mendaftarkan pengguna {user.id}: {e}")

def update_user_balance(user_id, new_balance):
    """Memperbarui saldo pengguna."""
    cursor.execute("UPDATE users SET balance = ? WHERE id = ?", (new_balance, user_id))

def get_product_by_code(product_code):
    """Mengambil produk berdasarkan kodenya."""
    cursor.execute("SELECT * FROM products WHERE product_code = ?", (product_code,))
    return cursor.fetchone()

def get_categories():
    """Mengambil semua kategori produk yang unik."""
    cursor.execute("SELECT DISTINCT category FROM products ORDER BY category")
    return [row['category'] for row in cursor.fetchall()]

def get_products_by_category(category):
    """Mengambil semua produk dalam kategori tertentu."""
    cursor.execute("SELECT * FROM products WHERE category = ? ORDER BY name", (category,))
    return cursor.fetchall()

def create_transaction(user_id, product, details):
    """Mencatat transaksi baru."""
    trx_id = f"TRX-{user_id}-{int(datetime.now().timestamp())}"
    cursor.execute(
        "INSERT INTO transactions (transaction_id, user_id, product_name, price, details) VALUES (?, ?, ?, ?, ?)",
        (trx_id, user_id, product['name'], product['price'], details)
    )
    cursor.execute(
        "UPDATE users SET balance = balance - ?, transaction_count = transaction_count + 1 WHERE id = ?",
        (product['price'], user_id)
    )

# --- Handler Perintah Utama ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menyapa pengguna, mendaftarkan jika perlu, dan menampilkan menu utama."""
    user = update.effective_user
    db_user = get_user(user.id)

    if not db_user:
        register_user(user)
        db_user = get_user(user.id)

    # Teks selamat datang yang lebih kaya
    profile_text = (
        f"<b>SELAMAT DATANG DI {SHOP_NAME.upper()}</b>\n\n"
        f"👤 <b>Nama:</b> {user.first_name}\n"
        f"🆔 <b>ID User:</b> <code>{db_user['id']}</code>\n"
        f"💰 <b>Saldo:</b> Rp{db_user['balance']:,.0f}\n"
        f"📊 <b>Total Transaksi:</b> {db_user['transaction_count']} kali"
    )
    
    # Kirim pesan profil terlebih dahulu
    await update.message.reply_text(profile_text, parse_mode='HTML')
    # Kemudian kirim menu utama sebagai pesan baru
    await send_main_menu(update.message.chat_id, context)


async def send_main_menu(chat_id, context, message_id=None):
    """Mengirim atau mengedit pesan untuk menampilkan menu utama."""
    keyboard = []
    
    if config.get("ENABLE_DIGITAL_PRODUCTS"):
        keyboard.append([InlineKeyboardButton("📦 Beli Produk Digital", callback_data="list_kategori")])
    
    # Tambahkan tombol lain di sini jika perlu
    keyboard.append([
        InlineKeyboardButton("💰 TopUp Saldo", callback_data="deposit"),
        InlineKeyboardButton("🔑 Akunku", callback_data="my_account")
    ])

    if chat_id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("⚙️ Panel Admin", callback_data="admin_panel")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    menu_text = "Silakan pilih tombol untuk melanjutkan:"

    if message_id:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=menu_text,
            reply_markup=reply_markup
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=menu_text,
            reply_markup=reply_markup
        )

# --- Handler Callback Query (Tombol Inline) ---

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menangani semua input dari tombol inline."""
    query = update.callback_query
    await query.answer() # Wajib untuk mengonfirmasi callback telah diterima

    data = query.data
    chat_id = query.message.chat_id
    message_id = query.message.message_id

    # Routing berdasarkan data callback
    if data == "main_menu":
        await send_main_menu(chat_id, context, message_id)

    elif data == "list_kategori":
        categories = get_categories()
        if not categories:
            await query.edit_message_text(
                text="Maaf, belum ada produk yang tersedia.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="main_menu")]])
            )
            return

        keyboard = [[InlineKeyboardButton(cat, callback_data=f"list_produk:{cat}")] for cat in categories]
        keyboard.append([InlineKeyboardButton("⬅️ Kembali", callback_data="main_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="Silakan pilih kategori produk:", reply_markup=reply_markup)

    elif data.startswith("list_produk:"):
        category = data.split(":")[1]
        products = get_products_by_category(category)
        
        if not products:
            await query.edit_message_text(
                text=f"Tidak ada produk di kategori {category}.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali ke Kategori", callback_data="list_kategori")]])
            )
            return
            
        keyboard = [
            [InlineKeyboardButton(f"{p['name']} - Rp{p['price']:,.0f}", callback_data=f"beli:{p['product_code']}")]
            for p in products
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Kembali ke Kategori", callback_data="list_kategori")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text=f"Produk dalam kategori *{category}*:", reply_markup=reply_markup, parse_mode='Markdown')

    elif data.startswith("beli:"):
        product_code = data.split(":")[1]
        product = get_product_by_code(product_code)
        if not product:
            await query.edit_message_text(text="Produk tidak ditemukan.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="list_kategori")]]))
            return

        text = (
            f"<b>KONFIRMASI PESANAN</b>\n\n"
            f"Anda akan membeli:\n"
            f"<b>{product['name']}</b>\n\n"
            f"Harga: <b>Rp{product['price']:,.0f}</b>\n"
            f"Deskripsi: {product['description']}\n\n"
            f"Lanjutkan pesanan?"
        )
        keyboard = [
            [InlineKeyboardButton("✅ YA, LANJUTKAN", callback_data=f"konfirmasi_beli:{product_code}")],
            [InlineKeyboardButton("❌ BATALKAN", callback_data=f"list_produk:{product['category']}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode='HTML')
        
    elif data.startswith("konfirmasi_beli:"):
        product_code = data.split(":")[1]
        product = get_product_by_code(product_code)
        user = get_user(chat_id)

        if not product or not user:
            await query.edit_message_text(text="Terjadi kesalahan, produk atau pengguna tidak ditemukan.")
            return

        if user['balance'] < product['price']:
            await query.edit_message_text(
                text=f"❌ Saldo Anda tidak mencukupi. Saldo saat ini: Rp{user['balance']:,.0f}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data=f"list_produk:{product['category']}")]])
            )
            return

        # Logika untuk memberikan produk (contoh sederhana)
        stock_data_list = (product['stock_data'] or "").split('|')
        if not stock_data_list or stock_data_list[0] == '':
            await query.edit_message_text(text="Maaf, stok produk ini habis.")
            return
        
        item_diberikan = stock_data_list.pop(0)
        sisa_stok = "|".join(stock_data_list)

        # Update stok di database
        cursor.execute("UPDATE products SET stock_data = ? WHERE product_code = ?", (sisa_stok, product_code))

        # Buat transaksi
        create_transaction(chat_id, product, item_diberikan)
        
        # Kirim pesan sukses ke pengguna
        await query.edit_message_text(
            text=f"✅ <b>TRANSAKSI BERHASIL</b>\n\n"
                 f"Terima kasih telah membeli <b>{product['name']}</b>.\n\n"
                 f"Berikut adalah detail produk Anda:\n<pre>{item_diberikan}</pre>",
            parse_mode='HTML'
        )
        
        # Kirim notifikasi saldo baru
        updated_user = get_user(chat_id)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Saldo Anda sekarang: Rp{updated_user['balance']:,.0f}"
        )

    # Placeholder untuk fitur lain
    elif data == "deposit":
        await query.edit_message_text(text="Fitur TopUp Saldo sedang dalam pengembangan. Untuk saat ini, silakan hubungi admin.")
    elif data == "my_account":
        await query.edit_message_text(text="Fitur Akunku sedang dalam pengembangan.")
    elif data == "admin_panel":
        await query.edit_message_text(text="Panel Admin sedang dalam pengembangan.")


# --- Handler Perintah Admin (Contoh dari kode lama) ---
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
        for row in recipients:
            uid = row['id']
            try:
                await context.bot.send_message(chat_id=uid, text=f"📢 Pesan dari Admin:\n\n{message}")
                count += 1
            except Exception as e:
                logger.warning(f"Gagal mengirim pesan broadcast ke ID {uid}: {e}")
        await update.message.reply_text(f"✅ Pesan berhasil dikirim ke {count} dari {len(recipients)} pengguna.")
    except sqlite3.Error as e:
        logger.error(f"Kesalahan database pada perintah /broadcast: {e}")
        await update.message.reply_text("Maaf, terjadi kesalahan saat mengambil data pengguna.")

# --- Fungsi Utama ---
def main():
    """Membangun dan menjalankan aplikasi bot Telegram."""
    # Pastikan database sudah siap sebelum bot berjalan
    setup_database()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Menambahkan handler untuk perintah
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", broadcast))
    
    # Menambahkan handler untuk callback query dari tombol inline
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    # Memulai bot untuk menerima pembaruan
    print("Bot sedang berjalan...")
    app.run_polling()

    # Menutup koneksi database saat bot berhenti
    print("Bot berhenti. Menutup koneksi database.")
    conn.close()


if __name__ == "__main__":
    main()
