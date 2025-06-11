# ==============================================================================
# config.py - File Konfigurasi Bot
# Ini akan dibuat dan diisi oleh skrip instalasi.
# JANGAN UBAH SECARA MANUAL SETELAH INSTALASI KECUALI ANDA PAHAM.
# ==============================================================================
# TOKEN = 'YOUR_BOT_TOKEN_HERE'
# ADMIN_IDS = [YOUR_ADMIN_ID_HERE] # Contoh: [123456789, 987654321]


# ==============================================================================
# requirements.txt - Dependensi Python
# Ini adalah daftar library Python yang dibutuhkan oleh bot.
# Skrip instalasi akan menginstal ini secara otomatis.
# ==============================================================================
# python-telegram-bot==21.2 # Versi terbaru yang stabil per Juni 2024
# SQLAlchemy==2.0.30 # Jika Anda ingin menggunakan ORM yang lebih canggih (saat ini belum digunakan, SQLite bawaan)


# ==============================================================================
# guardianbot_main.py - Kode Utama GuardianBot
# Ini adalah file utama bot Telegram Anda.
# ==============================================================================

import logging
import sqlite3
import json
import os
from datetime import datetime, timedelta
import re

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatMember,
    Chat,
    constants,
    ChatPermissions # PENTING: Tambahkan import ini untuk mengunci grup
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
    ChatMemberHandler
)
from functools import wraps

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Global Variables for Configuration ---
# Variabel ini akan diisi dari config.py saat bot dimulai.
TOKEN = None
ADMIN_IDS = []

# --- Database Manager ---
DATABASE_NAME = 'guardianbot.db'
DB_CONNECTION = None

def init_db():
    """Menginisialisasi database dan membuat tabel jika belum ada."""
    global DB_CONNECTION
    try:
        DB_CONNECTION = sqlite3.connect(DATABASE_NAME, check_same_thread=False)
        cursor = DB_CONNECTION.cursor()

        # Tabel Pengguna (untuk masa aktif bot)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                joined_date TEXT,
                expiry_date TEXT
            )
        ''')

        # Tabel Pengaturan Bot (on/off fitur, pesan welcome, dll.)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')

        # Tabel Whitelist Tautan
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS whitelist_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                link TEXT UNIQUE
            )
        ''')

        # Tabel Kata Kunci Terlarang
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS forbidden_keywords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT UNIQUE
            )
        ''')

        # Tabel Log Chat Grup
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_logs (
                message_id INTEGER PRIMARY KEY,
                chat_id INTEGER,
                user_id INTEGER,
                username TEXT,
                message_text TEXT,
                timestamp TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')

        # Tabel Log Kontak Grup (anggota)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS contact_logs (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_seen TEXT
            )
        ''')

        # Tabel Peringatan Pengguna
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                group_id INTEGER,
                admin_id INTEGER,
                reason TEXT,
                timestamp TEXT
            )
        ''')

        # Tabel Log Aktivitas Admin
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                action TEXT,
                target_id INTEGER,
                timestamp TEXT
            )
        ''')

        DB_CONNECTION.commit()
        logger.info("Database berhasil diinisialisasi.")
    except sqlite3.Error as e:
        logger.error(f"Kesalahan inisialisasi database: {e}")
        # Tambahkan penanganan error yang lebih baik di sini, misalnya keluar dari aplikasi

def close_db():
    """Menutup koneksi database."""
    if DB_CONNECTION:
        DB_CONNECTION.close()
        logger.info("Koneksi database ditutup.")

def execute_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    """Fungsi pembantu untuk menjalankan query database."""
    cursor = DB_CONNECTION.cursor()
    try:
        cursor.execute(query, params)
        if commit:
            DB_CONNECTION.commit()
        if fetchone:
            return cursor.fetchone()
        if fetchall:
            return cursor.fetchall()
        return None
    except sqlite3.Error as e:
        logger.error(f"Kesalahan query database: {e} | Query: {query} | Params: {params}")
        return None

# --- Fungsi Database untuk Pengguna ---
def add_user_db(user_id, username, expiry_days):
    joined_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    expiry_date = (datetime.now() + timedelta(days=expiry_days)).strftime("%Y-%m-%d %H:%M:%S")
    return execute_query(
        "INSERT OR REPLACE INTO users (user_id, username, joined_date, expiry_date) VALUES (?, ?, ?, ?)",
        (user_id, username, joined_date, expiry_date),
        commit=True
    )

def delete_user_db(user_id):
    return execute_query("DELETE FROM users WHERE user_id = ?", (user_id,), commit=True)

def get_user_details_db(user_id):
    return execute_query("SELECT user_id, username, joined_date, expiry_date FROM users WHERE user_id = ?", (user_id,), fetchone=True)

def list_all_users_db():
    return execute_query("SELECT user_id, username, expiry_date FROM users ORDER BY expiry_date ASC", fetchall=True)

# --- Fungsi Database untuk Pengaturan ---
def get_setting_db(key, default_value=None):
    result = execute_query("SELECT value FROM settings WHERE key = ?", (key,), fetchone=True)
    return result[0] if result else default_value

def set_setting_db(key, value):
    return execute_query(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, str(value)),
        commit=True
    )

def get_all_settings_db():
    return execute_query("SELECT key, value FROM settings", fetchall=True)

# --- Fungsi Database untuk Perlindungan ---
def add_whitelist_link_db(link):
    return execute_query("INSERT OR IGNORE INTO whitelist_links (link) VALUES (?)", (link,), commit=True)

def remove_whitelist_link_db(link):
    return execute_query("DELETE FROM whitelist_links WHERE link = ?", (link,), commit=True)

def get_whitelist_links_db():
    return [row[0] for row in execute_query("SELECT link FROM whitelist_links", fetchall=True) or []]

def add_keyword_db(keyword):
    return execute_query("INSERT OR IGNORE INTO forbidden_keywords (keyword) VALUES (?)", (keyword,), commit=True)

def remove_keyword_db(keyword):
    return execute_query("DELETE FROM forbidden_keywords WHERE keyword = ?", (keyword,), commit=True)

def get_keywords_db():
    return [row[0] for row in execute_query("SELECT keyword FROM forbidden_keywords", fetchall=True) or []]

# --- Fungsi Database untuk Log Chat & Kontak ---
def log_chat_db(message_id, chat_id, user_id, username, message_text, date):
    return execute_query(
        "INSERT INTO chat_logs (message_id, chat_id, user_id, username, message_text, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (message_id, chat_id, user_id, username, message_text, date.strftime("%Y-%m-%d %H:%M:%S")),
        commit=True
    )

def log_contact_db(user_id, username):
    return execute_query(
        "INSERT OR REPLACE INTO contact_logs (user_id, username, first_seen) VALUES (?, ?, COALESCE((SELECT first_seen FROM contact_logs WHERE user_id = ?), ?))",
        (user_id, username, user_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        commit=True
    )

def get_all_chats_db():
    return execute_query("SELECT chat_id, user_id, username, message_text, timestamp FROM chat_logs ORDER BY timestamp DESC", fetchall=True)

def get_all_contacts_db():
    return execute_query("SELECT user_id, username, first_seen FROM contact_logs ORDER BY username ASC", fetchall=True)

# --- Fungsi Database untuk Warnings ---
def add_warning_db(user_id, group_id, admin_id, reason):
    return execute_query(
        "INSERT INTO warnings (user_id, group_id, admin_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
        (user_id, group_id, admin_id, reason, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        commit=True
    )

def get_user_warnings_db(user_id):
    return execute_query(
        "SELECT group_id, admin_id, reason, timestamp FROM warnings WHERE user_id = ? ORDER BY timestamp DESC",
        (user_id,),
        fetchall=True
    )

# --- Fungsi Database untuk Log Aktivitas Admin ---
def log_admin_action_db(admin_id, action, target_id=None):
    return execute_query(
        "INSERT INTO admin_actions (admin_id, action, target_id, timestamp) VALUES (?, ?, ?, ?)",
        (admin_id, action, target_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        commit=True
    )

def get_all_admin_actions_db():
    return execute_query("SELECT admin_id, action, target_id, timestamp FROM admin_actions ORDER BY timestamp DESC", fetchall=True)

# --- Helper Functions & Decorator ---
def is_admin(user_id):
    """Mengecek apakah user_id adalah salah satu ID admin."""
    return user_id in ADMIN_IDS

def admin_only(func):
    """Decorator untuk membatasi perintah hanya untuk admin."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user and is_admin(update.effective_user.id):
            return await func(update, context)
        else:
            if update.effective_chat.type == Chat.PRIVATE:
                await update.message.reply_text("Maaf, Anda tidak memiliki akses ke perintah ini.")
            else:
                # Di grup, bisa diabaikan atau dihapus pesan perintahnya.
                # Untuk keamanan, kita hanya log dan tidak merespons di grup.
                logger.warning(f"Non-admin {update.effective_user.id} mencoba mengakses perintah admin: {update.effective_message.text}")
    return wrapper

def get_user_mention(user):
    """Mengembalikan format mention untuk pengguna."""
    if user.username:
        return f"@{user.username}"
    return f"<a href='tg://user?id={user.id}'>{user.full_name}</a>"

# --- Handler Perintah Telegram ---
@admin_only
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mengirim pesan sambutan dengan tombol untuk admin."""
    user = update.effective_user
    logger.info(f"Admin {user.id} ({user.full_name}) menggunakan /start.")

    message = (
        f"Halo, {user.full_name}! Saya GuardianBot, pelindung grup Telegram Anda.\n"
        "Sebagai admin, Anda memiliki akses penuh ke pengaturan bot.\n\n"
        "Silakan pilih menu di bawah ini untuk mulai berinteraksi:"
    )

    keyboard = [
        [InlineKeyboardButton("🛡️ Perlindungan Grup", callback_data='menu_protection')],
        [InlineKeyboardButton("👥 Manajemen Pengguna", callback_data='menu_user_management')],
        [InlineKeyboardButton("⚙️ Pengaturan Bot", callback_data='menu_settings')],
        [InlineKeyboardButton("📢 Siaran & Log", callback_data='menu_broadcast_log')],
        [InlineKeyboardButton("❓ Bantuan & Info", callback_data='help_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_html(message, reply_markup=reply_markup)
    log_admin_action_db(user.id, "Used /start command")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menampilkan menu bantuan utama."""
    query = update.callback_query
    if query:
        await query.answer()

    message = "❓ *Menu Bantuan GuardianBot*\n\nPilih kategori bantuan di bawah ini:"
    keyboard = [
        [InlineKeyboardButton("Perintah Umum", callback_data='help_general')],
        [InlineKeyboardButton("Perintah Admin", callback_data='help_admin')],
        [InlineKeyboardButton("Panduan Perlindungan", callback_data='help_protection')],
        [InlineKeyboardButton("Manajemen Pengguna", callback_data='help_user_management')],
        [InlineKeyboardButton("Tips & Trik", callback_data='help_tips')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN)
    else:
        await update.message.reply_markdown(message, reply_markup=reply_markup)

# --- Handlers Callback Query (Tombol Inline) ---
async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menangani semua callback dari tombol inline."""
    query = update.callback_query
    await query.answer() # Pastikan query dijawab untuk menghilangkan loading di tombol

    data = query.data
    user_id = query.from_user.id
    chat_id = query.message.chat_id

    if not is_admin(user_id) and not data.startswith('help_'):
        await query.edit_message_text("Maaf, Anda tidak memiliki akses ke fitur ini.")
        return

    logger.info(f"User {user_id} clicked button: {data}")
    log_admin_action_db(user_id, f"Clicked button: {data}")

    # --- Menu Utama ---
    if data == 'main_menu':
        await start_command(query, context) # Panggil kembali fungsi start untuk admin
    elif data == 'help_menu':
        await help_command(query, context)

    # --- Menu Perlindungan Grup ---
    elif data == 'menu_protection':
        message = "🛡️ *Pengaturan Perlindungan Grup*\n\nPilih opsi perlindungan:"
        keyboard = [
            [InlineKeyboardButton("Pengaturan Perlindungan", callback_data='protection_settings')],
            [InlineKeyboardButton("Whitelist Tautan", callback_data='whitelist_links_menu')],
            [InlineKeyboardButton("Daftar Kata Kunci", callback_data='forbidden_keywords_menu')],
            [InlineKeyboardButton("Mode Baca Saja (Lock Group)", callback_data='lock_group_menu')],
            [InlineKeyboardButton("Anti-Spam Media & Bot Baru", callback_data='advanced_protection_menu')],
            [InlineKeyboardButton("⬅️ Kembali ke Menu Utama", callback_data='main_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN)

    # --- Pengaturan Perlindungan (On/Off) ---
    elif data == 'protection_settings':
        message = "⚙️ *Aktifkan/Nonaktifkan Perlindungan*:\n\n"
        keyboard = []

        link_protection = get_setting_db('link_protection', 'off') == 'on'
        invite_protection = get_setting_db('invite_protection', 'off') == 'on'
        keyword_protection = get_setting_db('keyword_protection', 'off') == 'on'

        message += f"🔗 Perlindungan Link: {'✅ ON' if link_protection else '❌ OFF'}\n"
        message += f"📨 Perlindungan Undangan Grup: {'✅ ON' if invite_protection else '❌ OFF'}\n"
        message += f"🚫 Perlindungan Kata Kunci: {'✅ ON' if keyword_protection else '❌ OFF'}\n"

        keyboard.append([
            InlineKeyboardButton(f"🔗 Link: {'OFF' if link_protection else 'ON'}", callback_data=f'toggle_protection_link_{"off" if link_protection else "on"}'),
            InlineKeyboardButton(f"📨 Undangan: {'OFF' if invite_protection else 'ON'}", callback_data=f'toggle_protection_invite_{"off" if invite_protection else "on"}'),
            InlineKeyboardButton(f"🚫 Kata Kunci: {'OFF' if keyword_protection else 'ON'}", callback_data=f'toggle_protection_keyword_{"off" if keyword_protection else "on"}'),
        ])
        keyboard.append([InlineKeyboardButton("⬅️ Kembali ke Perlindungan Grup", callback_data='menu_protection')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN)

    elif data.startswith('toggle_protection_'):
        _, feature, status = data.split('_')
        feature_map = {
            'link': 'link_protection',
            'invite': 'invite_protection',
            'keyword': 'keyword_protection',
            'media': 'media_spam_protection',
            'flood': 'flood_protection',
            'new_bot': 'new_bot_protection',
        }
        setting_key = feature_map.get(feature)
        if setting_key:
            set_setting_db(setting_key, status)
            await query.edit_message_text(f"Perlindungan {feature} berhasil diatur ke {'AKTIF' if status == 'on' else 'NONAKTIF'}.")
            log_admin_action_db(user_id, f"Toggled {setting_key} to {status}")
            # Kembali ke menu pengaturan perlindungan
            await button_callback_handler(update, context) # Panggil ulang handler untuk refresh menu
        else:
            await query.edit_message_text("Pengaturan tidak ditemukan.")

    # --- Menu Whitelist Tautan ---
    elif data == 'whitelist_links_menu':
        links = get_whitelist_links_db()
        message = "✅ *Daftar Tautan di Whitelist*:\n"
        if not links:
            message += "Belum ada tautan di whitelist.\n"
        else:
            for i, link in enumerate(links):
                message += f"{i+1}. `{link}`\n"
        message += "\nGunakan `/add_link_whitelist <link>` untuk menambah.\n"
        message += "Gunakan `/del_link_whitelist <link>` untuk menghapus.\n"
        keyboard = [[InlineKeyboardButton("⬅️ Kembali ke Perlindungan Grup", callback_data='menu_protection')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN)

    # --- Menu Kata Kunci Terlarang ---
    elif data == 'forbidden_keywords_menu':
        keywords = get_keywords_db()
        message = "🚫 *Daftar Kata Kunci Terlarang*:\n"
        if not keywords:
            message += "Belum ada kata kunci terlarang.\n"
        else:
            for i, keyword in enumerate(keywords):
                message += f"{i+1}. `{keyword}`\n"
        message += "\nGunakan `/add_keyword <kata_kunci>` untuk menambah.\n"
        message += "Gunakan `/del_keyword <kata_kunci>` untuk menghapus.\n"
        keyboard = [[InlineKeyboardButton("⬅️ Kembali ke Perlindungan Grup", callback_data='menu_protection')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN)

    # --- Advanced Protection Menu (Media Spam, Flood, New Bot) ---
    elif data == 'advanced_protection_menu':
        message = "⚙️ *Perlindungan Tingkat Lanjut*:\n\n"
        keyboard = []

        media_protection = get_setting_db('media_spam_protection', 'off') == 'on'
        flood_protection = get_setting_db('flood_protection', 'off') == 'on'
        new_bot_protection = get_setting_db('new_bot_protection', 'off') == 'on'

        message += f"🖼️ Anti-Spam Media: {'✅ ON' if media_protection else '❌ OFF'}\n"
        message += f"⚡ Batas Pesan Cepat: {'✅ ON' if flood_protection else '❌ OFF'}\n"
        message += f"🤖 Perlindungan Bot Baru: {'✅ ON' if new_bot_protection else '❌ OFF'}\n"

        keyboard.append([
            InlineKeyboardButton(f"🖼️ Media: {'OFF' if media_protection else 'ON'}", callback_data=f'toggle_protection_media_{"off" if media_protection else "on"}'),
            InlineKeyboardButton(f"⚡ Flood: {'OFF' if flood_protection else 'ON'}", callback_data=f'toggle_protection_flood_{"off" if flood_protection else "on"}'),
            InlineKeyboardButton(f"🤖 Bot Baru: {'OFF' if new_bot_protection else 'ON'}", callback_data=f'toggle_protection_new_bot_{"off" if new_bot_protection else "on"}'),
        ])
        keyboard.append([InlineKeyboardButton("⬅️ Kembali ke Perlindungan Grup", callback_data='menu_protection')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN)


    # --- Menu Manajemen Pengguna ---
    elif data == 'menu_user_management':
        message = "👥 *Manajemen Pengguna Bot*\n\nPilih opsi manajemen pengguna:"
        keyboard = [
            [InlineKeyboardButton("➕ Tambah Pengguna", callback_data='add_user_prompt')],
            [InlineKeyboardButton("➖ Hapus Pengguna", callback_data='delete_user_prompt')],
            [InlineKeyboardButton("📋 Daftar Pengguna", callback_data='list_users')],
            [InlineKeyboardButton("📝 Rincian Pengguna", callback_data='detail_user_prompt')],
            [InlineKeyboardButton("⬅️ Kembali ke Menu Utama", callback_data='main_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN)

    elif data == 'add_user_prompt':
        await query.edit_message_text("Untuk menambah pengguna, gunakan perintah:\n`/tambah_pengguna <user_id> <nama_pengguna> <jumlah_hari_aktif>`\n\nContoh: `/tambah_pengguna 123456789 JohnDoe 30`")
    elif data == 'delete_user_prompt':
        await query.edit_message_text("Untuk menghapus pengguna, gunakan perintah:\n`/hapus_pengguna <user_id>`\n\nContoh: `/hapus_pengguna 123456789`")
    elif data == 'detail_user_prompt':
        await query.edit_message_text("Untuk melihat rincian pengguna, gunakan perintah:\n`/detail_pengguna <user_id>`\n\nContoh: `/detail_pengguna 123456789`")
    elif data == 'list_users':
        users = list_all_users_db()
        if not users:
            message = "Belum ada pengguna terdaftar."
        else:
            message = "📋 *Daftar Pengguna Bot*:\n\n"
            for user_id, username, expiry_date in users:
                expiry_dt = datetime.strptime(expiry_date, "%Y-%m-%d %H:%M:%S")
                status = "Aktif" if expiry_dt > datetime.now() else "Kadaluarsa"
                message += f"• `{user_id}` | {username} | Kadaluarsa: {expiry_dt.strftime('%d-%m-%Y')} ({status})\n"
        keyboard = [[InlineKeyboardButton("⬅️ Kembali ke Manajemen Pengguna", callback_data='menu_user_management')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN)

    # --- Menu Pengaturan Bot ---
    elif data == 'menu_settings':
        message = "⚙️ *Pengaturan Umum Bot*\n\nPilih opsi pengaturan:"
        keyboard = [
            [InlineKeyboardButton("Cek Status & Pengaturan", callback_data='check_status_settings')],
            [InlineKeyboardButton("Backup Pengaturan", callback_data='backup_settings')],
            [InlineKeyboardButton("Restore Pengaturan", callback_data='restore_settings_prompt')],
            [InlineKeyboardButton("Konfigurasi Pesan Selamat Datang", callback_data='welcome_message_config')],
            [InlineKeyboardButton("Sistem Peringatan", callback_data='warnings_config')],
            [InlineKeyboardButton("⬅️ Kembali ke Menu Utama", callback_data='main_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN)

    elif data == 'check_status_settings':
        settings = get_all_settings_db()
        message = "✅ *Status & Pengaturan Bot*:\n\n"
        if not settings:
            message += "Belum ada pengaturan tersimpan. Fitur mungkin menggunakan default.\n"
        else:
            for key, value in settings:
                message += f"• `{key}`: `{value}`\n"
        keyboard = [[InlineKeyboardButton("⬅️ Kembali ke Pengaturan Bot", callback_data='menu_settings')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN)

    elif data == 'backup_settings':
        await backup_command(query, context) # Panggil fungsi backup
        await button_callback_handler(update, context) # Refresh menu
    elif data == 'restore_settings_prompt':
        await query.edit_message_text("Untuk restore, balas pesan file backup (.json) yang sebelumnya dikirim oleh bot dengan perintah `/restore`.\n\n"
                                      "Contoh:\n1. Kirim file backup ke bot (atau temukan di riwayat chat).\n2. Balas file tersebut dengan perintah `/restore`.")


    # --- Menu Siaran & Log ---
    elif data == 'menu_broadcast_log':
        message = "📢 *Menu Siaran & Log Bot*\n\nPilih opsi:"
        keyboard = [
            [InlineKeyboardButton("Kirim Pesan Siaran", callback_data='broadcast_prompt')],
            [InlineKeyboardButton("Lihat Log Chat Grup", callback_data='view_chat_log')],
            [InlineKeyboardButton("Lihat Kontak Grup", callback_data='view_contact_log')],
            [InlineKeyboardButton("Lihat Log Aktivitas Admin", callback_data='view_admin_log')],
            [InlineKeyboardButton("Lihat Statistik Grup", callback_data='stats_command_menu')],
            [InlineKeyboardButton("⬅️ Kembali ke Menu Utama", callback_data='main_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN)

    elif data == 'broadcast_prompt':
        await query.edit_message_text("Untuk mengirim pesan siaran, gunakan perintah:\n`/siarkan_pesan <pesan_yang_ingin_disiarkan>`\n\nContoh: `/siarkan_pesan Halo semua, ada pengumuman penting!`")

    elif data == 'view_chat_log':
        chats = get_all_chats_db()
        if not chats:
            message = "Belum ada log chat tersimpan. Pastikan fitur logging diaktifkan."
        else:
            message = "📝 *Log Chat Terbaru* (20 pesan terakhir):\n\n"
            # Tampilkan 20 pesan terakhir atau lebih, sesuai kebutuhan
            for i, chat in enumerate(chats[:20]):
                chat_id, user_id, username, text, timestamp = chat
                message += f"*{timestamp}* | `{username}` ({user_id}): {text[:50]}{'...' if len(text) > 50 else ''}\n"
            message += "\nUntuk melihat semua log, Anda mungkin perlu mengekspornya."
        keyboard = [[InlineKeyboardButton("⬅️ Kembali ke Siaran & Log", callback_data='menu_broadcast_log')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN)

    elif data == 'view_contact_log':
        contacts = get_all_contacts_db()
        if not contacts:
            message = "Belum ada kontak grup tersimpan."
        else:
            message = "👥 *Daftar Kontak Grup*:\n\n"
            for user_id, username, first_seen in contacts:
                message += f"• `{username}` ({user_id}) - Terdaftar: {datetime.strptime(first_seen, '%Y-%m-%d %H:%M:%S').strftime('%d-%m-%Y')}\n"
            message += "\n(Hanya menampilkan nama pengguna yang tersedia)"
        keyboard = [[InlineKeyboardButton("⬅️ Kembali ke Siaran & Log", callback_data='menu_broadcast_log')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN)

    elif data == 'view_admin_log':
        admin_logs = get_all_admin_actions_db()
        if not admin_logs:
            message = "Belum ada log aktivitas admin."
        else:
            message = "📜 *Log Aktivitas Admin Terbaru* (20 log terakhir):\n\n"
            for i, log in enumerate(admin_logs[:20]):
                admin_id, action, target_id, timestamp = log
                message += f"*{timestamp}* | Admin `{admin_id}`: `{action}` (Target: {target_id if target_id else 'N/A'})\n"
        keyboard = [[InlineKeyboardButton("⬅️ Kembali ke Siaran & Log", callback_data='menu_broadcast_log')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN)

    # --- Menu Bantuan (Sub-kategori) ---
    elif data.startswith('help_'):
        category = data.split('_')[1]
        response_text = ""
        back_button = InlineKeyboardButton("⬅️ Kembali ke Menu Bantuan", callback_data='help_menu')
        keyboard = [[back_button]]

        if category == 'general':
            response_text = (
                "*Perintah Umum:*\n\n"
                "• `/start`: Menampilkan pesan sambutan dan menu utama (untuk admin).\n"
                "• `/help`: Menampilkan menu bantuan ini.\n"
                "• `/cek_pengaturan`: Melihat status umum bot dan fitur yang aktif.\n"
            )
        elif category == 'admin':
            response_text = (
                "*Perintah Admin:*\n\n"
                "• `/tambah_pengguna <user_id> <nama_pengguna> <hari>`: Menambah pengguna bot dengan masa aktif.\n"
                "• `/hapus_pengguna <user_id>`: Menghapus pengguna bot.\n"
                "• `/daftar_pengguna`: Menampilkan daftar semua pengguna bot (via tombol).\n"
                "• `/detail_pengguna <user_id>`: Menampilkan rincian pengguna.\n"
                "• `/backup`: Membuat file backup pengaturan bot.\n"
                "• `/restore`: Memuat pengaturan dari file backup (balas file backup dengan perintah ini).\n"
                "• `/siarkan_pesan <pesan>`: Mengirim pesan ke semua grup yang bot ini ada di dalamnya.\n"
                "• `/lock_group`: Mengunci grup (hanya admin yang bisa kirim pesan).\n"
                "• `/unlock_group`: Membuka kunci grup.\n"
                "• `/welcome_config`: Mengatur pesan sambutan anggota baru.\n"
                "• `/set_welcome_message <pesan_baru>`: Mengubah pesan selamat datang.\n"
                "• `/toggle_welcome_message`: Mengaktifkan/menonaktifkan pesan selamat datang.\n"
                "• `/add_link_whitelist <link>`: Menambah tautan ke daftar putih.\n"
                "• `/del_link_whitelist <link>`: Menghapus tautan dari daftar putih.\n"
                "• `/add_keyword <kata_kunci>`: Menambah kata kunci terlarang.\n"
                "• `/del_keyword <kata_kunci>`: Menghapus kata kunci terlarang.\n"
                "• `/warn <user_id> [alasan]`: Memberikan peringatan kepada pengguna.\n"
                "• `/warnings_config`: Mengatur ambang batas peringatan dan melihat log peringatan.\n"
                "• `/set_warning_limit <jumlah>`: Mengubah ambang batas peringatan.\n"
                "• `/view_user_warnings <user_id>`: Melihat riwayat peringatan pengguna.\n"
                "• `/stats`: Menampilkan statistik grup.\n"
                "• `/set_flood_limit <jml_msg> <detik>`: Atur batas pesan cepat.\n"
                "• `/view_chat_log`: Melihat sebagian log chat terbaru (via tombol).\n"
                "• `/view_contact_log`: Melihat daftar kontak grup (via tombol).\n"
                "• `/view_admin_log`: Melihat log aktivitas admin (via tombol).\n"
            )
        elif category == 'protection':
            response_text = (
                "*Panduan Perlindungan:*\n\n"
                "• *Perlindungan Link*: Otomatis menghapus pesan yang mengandung tautan (URL). Aktifkan/nonaktifkan dari 'Pengaturan Perlindungan'.\n"
                "• *Perlindungan Undangan Grup*: Otomatis menghapus tautan undangan grup Telegram. Aktifkan/nonaktifkan dari 'Pengaturan Perlindungan'.\n"
                "• *Perlindungan Kata Kunci*: Menghapus pesan yang mengandung kata kunci terlarang yang Anda definisikan. Konfigurasi dari 'Daftar Kata Kunci'.\n"
                "• *Mode Baca Saja (Lock Group)*: Membuat grup hanya bisa diisi pesan oleh admin. Gunakan `/lock_group` dan `/unlock_group`.\n"
                "• *Anti-Spam Media*: Menghapus pesan yang hanya berisi media (gambar/video) tanpa teks. Aktifkan/nonaktifkan dari 'Perlindungan Tingkat Lanjut'.\n"
                "• *Batas Pesan Cepat (Flood Protection)*: Mencegah pengguna mengirim terlalu banyak pesan dalam waktu singkat. Aktifkan/nonaktifkan dari 'Perlindungan Tingkat Lanjut'.\n"
                "• *Perlindungan Bot Baru*: Otomatis menghapus bot yang baru ditambahkan ke grup tanpa izin. Aktifkan/nonaktifkan dari 'Perlindungan Tingkat Lanjut'.\n"
            )
        elif category == 'user_management':
            response_text = (
                "*Manajemen Pengguna:*\n\n"
                "Anda dapat mengelola pengguna bot (bukan anggota grup secara umum) melalui menu 'Manajemen Pengguna'. Fitur ini cocok jika bot Anda memiliki fungsi yang hanya dapat diakses oleh pengguna terdaftar dengan masa aktif.\n\n"
                "• `/tambah_pengguna <user_id> <nama_pengguna> <hari>`: Tambah pengguna baru.\n"
                "• `/hapus_pengguna <user_id>`: Hapus pengguna.\n"
                "• `/daftar_pengguna`: Lihat daftar pengguna dan masa aktifnya.\n"
                "• `/detail_pengguna <user_id>`: Lihat detail spesifik pengguna.\n"
            )
        elif category == 'tips':
            response_text = (
                "*Tips & Trik GuardianBot:*\n\n"
                "• *Whitelist Tautan*: Jika Anda ingin mengizinkan tautan dari sumber tertentu (misalnya, situs berita atau channel YouTube Anda), tambahkan ke whitelist untuk menghindari penghapusan otomatis.\n"
                "• *Log Chat*: Aktifkan fitur log chat untuk memantau aktivitas di grup Anda, terutama jika ada masalah atau ingin menganalisis interaksi.\n"
                "• *Peringatan Otomatis*: Konfigurasi ambang batas peringatan agar bot bisa secara otomatis menindak pengguna yang melanggar aturan berulang kali.\n"
                "• *Backup Rutin*: Selalu lakukan backup pengaturan secara rutin untuk mencegah kehilangan konfigurasi penting.\n"
            )

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(response_text, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN)


# --- Perintah Admin Spesifik ---
@admin_only
async def add_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menambah pengguna baru ke database dengan masa aktif."""
    try:
        if len(context.args) != 3:
            await update.message.reply_text("Penggunaan: `/tambah_pengguna <user_id> <nama_pengguna> <jumlah_hari_aktif>`")
            return
        user_id = int(context.args[0])
        username = context.args[1]
        expiry_days = int(context.args[2])

        add_user_db(user_id, username, expiry_days)
        expiry_date = (datetime.now() + timedelta(days=expiry_days)).strftime("%d-%m-%Y")
        await update.message.reply_text(f"Pengguna `{username}` (ID: `{user_id}`) berhasil ditambahkan. Masa aktif hingga {expiry_date}.")
        log_admin_action_db(update.effective_user.id, "Added user", user_id)
    except ValueError:
        await update.message.reply_text("ID pengguna dan jumlah hari aktif harus berupa angka.")
    except Exception as e:
        logger.error(f"Error adding user: {e}")
        await update.message.reply_text("Terjadi kesalahan saat menambah pengguna.")

@admin_only
async def delete_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menghapus pengguna dari database."""
    try:
        if len(context.args) != 1:
            await update.message.reply_text("Penggunaan: `/hapus_pengguna <user_id>`")
            return
        user_id = int(context.args[0])
        if delete_user_db(user_id):
            await update.message.reply_text(f"Pengguna dengan ID `{user_id}` berhasil dihapus.")
            log_admin_action_db(update.effective_user.id, "Deleted user", user_id)
        else:
            await update.message.reply_text(f"Pengguna dengan ID `{user_id}` tidak ditemukan.")
    except ValueError:
        await update.message.reply_text("ID pengguna harus berupa angka.")
    except Exception as e:
        logger.error(f"Error deleting user: {e}")
        await update.message.reply_text("Terjadi kesalahan saat menghapus pengguna.")

@admin_only
async def detail_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menampilkan rincian pengguna."""
    try:
        if len(context.args) != 1:
            await update.message.reply_text("Penggunaan: `/detail_pengguna <user_id>`")
            return
        user_id = int(context.args[0])
        user_details = get_user_details_db(user_id)
        if user_details:
            u_id, username, joined_date, expiry_date = user_details
            message = (
                f"📝 *Rincian Pengguna*:\n"
                f"• ID: `{u_id}`\n"
                f"• Nama Pengguna: `{username}`\n"
                f"• Tanggal Bergabung: {datetime.strptime(joined_date, '%Y-%m-%d %H:%M:%S').strftime('%d-%m-%Y %H:%M')}\n"
                f"• Tanggal Kadaluarsa: {datetime.strptime(expiry_date, '%Y-%m-%d %H:%M:%S').strftime('%d-%m-%Y %H:%M')}\n"
            )
            await update.message.reply_markdown(message)
            log_admin_action_db(update.effective_user.id, "Viewed user details", user_id)
        else:
            await update.message.reply_text(f"Pengguna dengan ID `{user_id}` tidak ditemukan.")
    except ValueError:
        await update.message.reply_text("ID pengguna harus berupa angka.")
    except Exception as e:
        logger.error(f"Error getting user details: {e}")
        await update.message.reply_text("Terjadi kesalahan saat mengambil rincian pengguna.")

# Daftar pengguna sudah ada di callback handler untuk 'list_users'

@admin_only
async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Membuat dan mengirim file backup pengaturan bot."""
    backup_data = {
        "users": list_all_users_db(),
        "settings": get_all_settings_db(),
        "whitelist_links": get_whitelist_links_db(),
        "forbidden_keywords": get_keywords_db(),
        "warnings": execute_query("SELECT * FROM warnings", fetchall=True) or [], # Backup all warnings
        "admin_actions": execute_query("SELECT * FROM admin_actions", fetchall=True) or [] # Backup admin actions
    }
    backup_filename = f"guardianbot_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    try:
        with open(backup_filename, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, indent=4, ensure_ascii=False)

        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=open(backup_filename, 'rb'),
            caption="✅ Backup pengaturan GuardianBot berhasil dibuat."
        )
        os.remove(backup_filename) # Hapus file lokal setelah dikirim
        log_admin_action_db(update.effective_user.id, "Created backup")
    except Exception as e:
        logger.error(f"Error during backup: {e}")
        await update.message.reply_text("❌ Terjadi kesalahan saat membuat backup. Periksa log bot.")

@admin_only
async def restore_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Memuat pengaturan dari file backup yang dibalas oleh admin."""
    if not update.message.reply_to_message or not update.message.reply_to_message.document:
        await update.message.reply_text("❌ Untuk restore, Anda harus membalas file backup (.json) yang sebelumnya dikirim oleh bot dengan perintah `/restore`.")
        return

    document = update.message.reply_to_message.document
    if not document.file_name.endswith('.json'):
        await update.message.reply_text("❌ File yang dibalas bukan file JSON. Mohon balas file backup yang benar.")
        return

    await update.message.reply_text("⏳ Memulai proses restore pengaturan...")
    file_id = document.file_id
    new_file = await context.bot.get_file(file_id)
    downloaded_file = await new_file.download_as_bytearray()

    try:
        backup_data = json.loads(downloaded_file.decode('utf-8'))

        # Hapus data lama sebelum restore (ini opsional, bisa juga merge)
        # Untuk kesederhanaan, kita akan menghapus dan mengisi ulang
        execute_query("DELETE FROM users", commit=True)
        execute_query("DELETE FROM settings", commit=True)
        execute_query("DELETE FROM whitelist_links", commit=True)
        execute_query("DELETE FROM forbidden_keywords", commit=True)
        execute_query("DELETE FROM warnings", commit=True)
        execute_query("DELETE FROM admin_actions", commit=True)


        # Restore Users
        if "users" in backup_data:
            for user_data in backup_data["users"]:
                # user_data bisa berupa tuple (user_id, username, expiry_date) atau (user_id, username, joined_date, expiry_date)
                if len(user_data) == 3: # Old format from list_all_users_db
                    user_id, username, expiry_date = user_data
                    joined_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S") # Placeholder, as old backup didn't save this
                elif len(user_data) == 4: # Proper format from get_user_details_db or full backup
                    user_id, username, joined_date, expiry_date = user_data
                add_user_db(user_id, username, (datetime.strptime(expiry_date, "%Y-%m-%d %H:%M:%S") - datetime.now()).days) # Calculate days

        # Restore Settings
        if "settings" in backup_data:
            for key, value in backup_data["settings"]:
                set_setting_db(key, value)

        # Restore Whitelist Links
        if "whitelist_links" in backup_data:
            for link in backup_data["whitelist_links"]:
                add_whitelist_link_db(link)

        # Restore Forbidden Keywords
        if "forbidden_keywords" in backup_data:
            for keyword in backup_data["forbidden_keywords"]:
                add_keyword_db(keyword)

        # Restore Warnings
        if "warnings" in backup_data:
            for warning_data in backup_data["warnings"]:
                # Assuming the warnings table stores: id, user_id, group_id, admin_id, reason, timestamp
                if len(warning_data) == 6: # Check if it's the full row including id
                    _, user_id, group_id, admin_id, reason, timestamp = warning_data
                else: # Fallback if only relevant data is in backup (less robust)
                    user_id, group_id, admin_id, reason, timestamp = warning_data
                # Directly insert without auto-incrementing id for simplicity, assuming uniqueness or letting DB handle it
                execute_query("INSERT INTO warnings (user_id, group_id, admin_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
                              (user_id, group_id, admin_id, reason, timestamp), commit=True)


        # Restore Admin Actions
        if "admin_actions" in backup_data:
            for action_data in backup_data["admin_actions"]:
                if len(action_data) == 5: # Assuming full row: id, admin_id, action, target_id, timestamp
                    _, admin_id, action, target_id, timestamp = action_data
                else:
                    admin_id, action, target_id, timestamp = action_data
                execute_query("INSERT INTO admin_actions (admin_id, action, target_id, timestamp) VALUES (?, ?, ?, ?)",
                              (admin_id, action, target_id, timestamp), commit=True)


        await update.message.reply_text("✅ Restore pengaturan berhasil dilakukan!")
        log_admin_action_db(update.effective_user.id, "Restored settings from backup")
    except json.JSONDecodeError:
        await update.message.reply_text("❌ File yang dibalas bukan format JSON yang valid.")
    except Exception as e:
        logger.error(f"Error during restore: {e}")
        await update.message.reply_text(f"❌ Terjadi kesalahan saat restore: {e}. Periksa log bot.")

@admin_only
async def check_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menampilkan semua pengaturan bot (sama seperti check_status_settings callback)."""
    # Panggil callback handler untuk check_status_settings, yang akan menampilkan menu
    await button_callback_handler(update, context)


@admin_only
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mengirim pesan ke semua grup yang bot ini ada di dalamnya."""
    if not context.args:
        await update.message.reply_text("Penggunaan: `/siarkan_pesan <pesan_yang_ingin_disiarkan>`")
        return

    message_to_broadcast = " ".join(context.args)
    
    # Dapatkan daftar semua chat_id yang pernah bot simpan lognya
    # Ini adalah cara sederhana untuk mendapatkan grup yang aktif.
    # Untuk yang lebih canggih, Anda bisa menyimpan daftar chat_id aktif.
    unique_chat_ids = execute_query("SELECT DISTINCT chat_id FROM chat_logs", fetchall=True)
    if not unique_chat_ids:
        await update.message.reply_text("Tidak ada grup yang ditemukan untuk disiarkan.")
        return

    sent_count = 0
    failed_count = 0
    
    await update.message.reply_text(f"⏳ Memulai siaran pesan ke {len(unique_chat_ids)} grup...")

    for chat_id_tuple in unique_chat_ids:
        chat_id = chat_id_tuple[0]
        try:
            # Periksa apakah bot masih anggota grup sebelum mengirim
            chat_member = await context.bot.get_chat_member(chat_id, context.bot.id)
            if chat_member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR]:
                await context.bot.send_message(chat_id=chat_id, text=message_to_broadcast, parse_mode=constants.ParseMode.MARKDOWN)
                sent_count += 1
            else:
                logger.warning(f"Bot bukan lagi anggota di chat {chat_id}. Melewatkan.")
                failed_count += 1
        except Exception as e:
            logger.error(f"Gagal mengirim pesan ke chat {chat_id}: {e}")
            failed_count += 1

    await update.message.reply_text(f"✅ Siaran selesai!\nBerhasil terkirim ke {sent_count} grup.\nGagal ke {failed_count} grup.")
    log_admin_action_db(update.effective_user.id, "Broadcast message", f"Sent: {sent_count}, Failed: {failed_count}")


@admin_only
async def add_link_whitelist_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menambah link ke whitelist."""
    if not context.args:
        await update.message.reply_text("Penggunaan: `/add_link_whitelist <link>`")
        return
    link = context.args[0]
    if add_whitelist_link_db(link):
        await update.message.reply_text(f"Tautan `{link}` berhasil ditambahkan ke whitelist.")
        log_admin_action_db(update.effective_user.id, "Added link to whitelist", link)
    else:
        await update.message.reply_text(f"Tautan `{link}` sudah ada di whitelist atau terjadi kesalahan.")

@admin_only
async def del_link_whitelist_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menghapus link dari whitelist."""
    if not context.args:
        await update.message.reply_text("Penggunaan: `/del_link_whitelist <link>`")
        return
    link = context.args[0]
    if remove_whitelist_link_db(link):
        await update.message.reply_text(f"Tautan `{link}` berhasil dihapus dari whitelist.")
        log_admin_action_db(update.effective_user.id, "Removed link from whitelist", link)
    else:
        await update.message.reply_text(f"Tautan `{link}` tidak ditemukan di whitelist atau terjadi kesalahan.")

@admin_only
async def add_keyword_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menambah kata kunci terlarang."""
    if not context.args:
        await update.message.reply_text("Penggunaan: `/add_keyword <kata_kunci>`")
        return
    keyword = " ".join(context.args).lower()
    if add_keyword_db(keyword):
        await update.message.reply_text(f"Kata kunci `{keyword}` berhasil ditambahkan.")
        log_admin_action_db(update.effective_user.id, "Added keyword", keyword)
    else:
        await update.message.reply_text(f"Kata kunci `{keyword}` sudah ada atau terjadi kesalahan.")

@admin_only
async def del_keyword_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menghapus kata kunci terlarang."""
    if not context.args:
        await update.message.reply_text("Penggunaan: `/del_keyword <kata_kunci>`")
        return
    keyword = " ".join(context.args).lower()
    if remove_keyword_db(keyword):
        await update.message.reply_text(f"Kata kunci `{keyword}` berhasil dihapus.")
        log_admin_action_db(update.effective_user.id, "Removed keyword", keyword)
    else:
        await update.message.reply_text(f"Kata kunci `{keyword}` tidak ditemukan atau terjadi kesalahan.")

@admin_only
async def lock_group_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mengaktifkan mode read-only untuk grup (hanya admin yang bisa kirim pesan)."""
    if update.effective_chat.type not in [Chat.GROUP, Chat.SUPERGROUP]:
        await update.message.reply_text("Perintah ini hanya bisa digunakan di dalam grup.")
        return

    chat_id = update.effective_chat.id
    try:
        # Mengatur izin chat: hanya admin yang bisa mengirim pesan
        await context.bot.set_chat_permissions(
            chat_id=chat_id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
                can_change_info=False, # Admin harus tetap bisa mengubah info
                can_invite_users=False, # Admin harus tetap bisa mengundang
                can_pin_messages=False, # Admin harus tetap bisa menyematkan
                can_manage_topics=False # Admin harus tetap bisa mengatur topik
            )
        )
        set_setting_db(f'lock_group_{chat_id}', 'on')
        await update.message.reply_text("🔒 Grup berhasil dikunci! Hanya admin yang dapat mengirim pesan.")
        log_admin_action_db(update.effective_user.id, "Locked group", chat_id)
    except Exception as e:
        logger.error(f"Error locking group {chat_id}: {e}")
        await update.message.reply_text(f"❌ Gagal mengunci grup. Pastikan bot memiliki izin 'Manage Group' dan 'Restrict Members'. Error: {e}")

@admin_only
async def unlock_group_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menonaktifkan mode read-only untuk grup."""
    if update.effective_chat.type not in [Chat.GROUP, Chat.SUPERGROUP]:
        await update.message.reply_text("Perintah ini hanya bisa digunakan di dalam grup.")
        return

    chat_id = update.effective_chat.id
    try:
        # Mengatur izin chat: semua anggota bisa mengirim pesan lagi
        await context.bot.set_chat_permissions(
            chat_id=chat_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_change_info=False, # Admin harus tetap bisa mengubah info
                can_invite_users=True, # Admin harus tetap bisa mengundang
                can_pin_messages=False, # Admin harus tetap bisa menyematkan
                can_manage_topics=False # Admin harus tetap bisa mengatur topik
            )
        )
        set_setting_db(f'lock_group_{chat_id}', 'off')
        await update.message.reply_text("🔓 Grup berhasil dibuka! Semua anggota sekarang dapat mengirim pesan.")
        log_admin_action_db(update.effective_user.id, "Unlocked group", chat_id)
    except Exception as e:
        logger.error(f"Error unlocking group {chat_id}: {e}")
        await update.message.reply_text(f"❌ Gagal membuka kunci grup. Error: {e}")

@admin_only
async def welcome_config_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mengatur pesan sambutan dan status on/off."""
    message = "👋 *Konfigurasi Pesan Selamat Datang*:\n\n"
    welcome_message = get_setting_db('welcome_message_text', "Selamat datang di grup, {nama_pengguna}!")
    welcome_enabled = get_setting_db('welcome_message_enabled', 'off') == 'on'

    message += f"Pesan saat ini: `{welcome_message}`\n"
    message += f"Status: {'✅ AKTIF' if welcome_enabled else '❌ NONAKTIF'}\n\n"
    message += "Gunakan `/set_welcome_message <pesan_baru>` untuk mengubah pesan (gunakan `{nama_pengguna}` sebagai placeholder).\n"
    message += "Gunakan `/toggle_welcome_message` untuk mengaktifkan/nonaktifkan."

    keyboard = [
        [InlineKeyboardButton(f"Toggle Welcome: {'OFF' if welcome_enabled else 'ON'}", callback_data='toggle_welcome_message')],
        [InlineKeyboardButton("⬅️ Kembali ke Pengaturan Bot", callback_data='menu_settings')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_markdown(message, reply_markup=reply_markup)

@admin_only
async def set_welcome_message_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menetapkan pesan sambutan baru."""
    if not context.args:
        await update.message.reply_text("Penggunaan: `/set_welcome_message <pesan_baru>`\n"
                                      "Contoh: `/set_welcome_message Halo {nama_pengguna}, selamat datang!`")
        return
    new_message = " ".join(context.args)
    set_setting_db('welcome_message_text', new_message)
    await update.message.reply_text(f"Pesan sambutan berhasil diubah menjadi: `{new_message}`")
    log_admin_action_db(update.effective_user.id, "Set welcome message", new_message)

@admin_only
async def toggle_welcome_message_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mengaktifkan/menonaktifkan pesan sambutan."""
    welcome_enabled = get_setting_db('welcome_message_enabled', 'off') == 'on'
    new_status = 'off' if welcome_enabled else 'on'
    set_setting_db('welcome_message_enabled', new_status)
    await update.message.reply_text(f"Pesan sambutan otomatis berhasil diatur ke {'AKTIF' if new_status == 'on' else 'NONAKTIF'}.")
    log_admin_action_db(update.effective_user.id, "Toggled welcome message", new_status)
    # Refresh menu welcome_config
    await welcome_config_command(update, context)


@admin_only
async def warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Memberikan peringatan kepada pengguna."""
    if len(context.args) < 1:
        await update.message.reply_text("Penggunaan: `/warn <user_id> [alasan]`")
        return
    try:
        user_id = int(context.args[0])
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else "Tidak ada alasan"
        
        add_warning_db(user_id, update.effective_chat.id, update.effective_user.id, reason)
        warnings_count = len(get_user_warnings_db(user_id))
        
        await update.message.reply_text(f"✅ Pengguna `{user_id}` telah diberi peringatan. Total peringatan: {warnings_count}.")
        log_admin_action_db(update.effective_user.id, "Issued warning", user_id)

        warning_limit = int(get_setting_db('warning_limit', '3'))
        if warnings_count >= warning_limit:
            await update.message.reply_text(f"⚠️ Pengguna `{user_id}` telah mencapai batas peringatan ({warning_limit}). Tindakan otomatis mungkin diperlukan (misalnya, mute/kick).")
            # Di sini Anda bisa menambahkan logika otomatis untuk mute/kick
            # Contoh: await context.bot.kick_chat_member(update.effective_chat.id, user_id)
            # Pastikan bot memiliki izin yang cukup!
    except ValueError:
        await update.message.reply_text("ID pengguna harus berupa angka.")
    except Exception as e:
        logger.error(f"Error giving warning: {e}")
        await update.message.reply_text("Terjadi kesalahan saat memberikan peringatan.")

@admin_only
async def warnings_config_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mengatur ambang batas peringatan dan melihat log peringatan."""
    warning_limit = get_setting_db('warning_limit', '3')
    message = (
        f"🚨 *Sistem Peringatan*:\n\n"
        f"• Ambang Batas Peringatan: `{warning_limit}` (setelah batas ini, tindakan otomatis mungkin diambil)\n"
        f"Gunakan `/set_warning_limit <jumlah>` untuk mengubahnya.\n\n"
        "• Gunakan `/view_user_warnings <user_id>` untuk melihat riwayat peringatan pengguna.\n"
    )
    keyboard = [[InlineKeyboardButton("⬅️ Kembali ke Pengaturan Bot", callback_data='menu_settings')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_markdown(message, reply_markup=reply_markup)

@admin_only
async def set_warning_limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menetapkan ambang batas peringatan."""
    if len(context.args) != 1:
        await update.message.reply_text("Penggunaan: `/set_warning_limit <jumlah>`")
        return
    try:
        limit = int(context.args[0])
        if limit < 1:
            await update.message.reply_text("Batas peringatan harus angka positif.")
            return
        set_setting_db('warning_limit', str(limit))
        await update.message.reply_text(f"Ambang batas peringatan berhasil diatur ke `{limit}`.")
        log_admin_action_db(update.effective_user.id, "Set warning limit", limit)
    except ValueError:
        await update.message.reply_text("Jumlah harus berupa angka.")
    except Exception as e:
        logger.error(f"Error setting warning limit: {e}")
        await update.message.reply_text("Terjadi kesalahan saat mengatur batas peringatan.")

@admin_only
async def view_user_warnings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Melihat riwayat peringatan untuk pengguna tertentu."""
    if len(context.args) != 1:
        await update.message.reply_text("Penggunaan: `/view_user_warnings <user_id>`")
        return
    try:
        user_id = int(context.args[0])
        warnings = get_user_warnings_db(user_id)
        if not warnings:
            message = f"Tidak ada peringatan untuk pengguna `{user_id}`."
        else:
            message = f"🚨 *Riwayat Peringatan untuk Pengguna `{user_id}`*:\n\n"
            for group_id, admin_id, reason, timestamp in warnings:
                message += f"• *{timestamp}* | Grup: `{group_id}` | Admin: `{admin_id}` | Alasan: _{reason}_\n"
        await update.message.reply_markdown(message)
        log_admin_action_db(update.effective_user.id, "Viewed user warnings", user_id)
    except ValueError:
        await update.message.reply_text("ID pengguna harus berupa angka.")
    except Exception as e:
        logger.error(f"Error viewing user warnings: {e}")
        await update.message.reply_text("Terjadi kesalahan saat melihat peringatan pengguna.")


@admin_only
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menampilkan statistik grup dasar."""
    # Ini akan menjadi fungsi dasar. Statistik yang lebih canggih memerlukan analisis log yang lebih dalam.
    # Untuk demo, kita akan mengambil jumlah pesan total dan jumlah kontak.
    total_messages = execute_query("SELECT COUNT(*) FROM chat_logs WHERE chat_id = ?", (update.effective_chat.id,), fetchone=True)
    total_contacts = execute_query("SELECT COUNT(*) FROM contact_logs", fetchone=True)

    if not total_messages or not total_contacts:
        message = "Tidak ada statistik yang tersedia. Pastikan fitur logging diaktifkan."
    else:
        message = (
            f"📊 *Statistik Grup*:\n\n"
            f"• Total Pesan di Grup Ini: `{total_messages[0]}`\n"
            f"• Total Kontak Tercatat: `{total_contacts[0]}`\n"
            "\n(Statistik ini berdasarkan data yang telah disimpan oleh bot.)"
        )
    
    keyboard = [[InlineKeyboardButton("⬅️ Kembali ke Siaran & Log", callback_data='menu_broadcast_log')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_markdown(message, reply_markup=reply_markup)
    log_admin_action_db(update.effective_user.id, "Viewed group stats", update.effective_chat.id)


# --- Handlers Pesan untuk Perlindungan & Logging ---
async def new_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menangani anggota baru bergabung dengan grup."""
    chat = update.effective_chat
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            # Bot baru saja ditambahkan ke grup
            logger.info(f"Bot ditambahkan ke grup: {chat.title} ({chat.id})")
            await context.bot.send_message(
                chat_id=chat.id,
                text="Terima kasih telah menambahkan saya! Saya GuardianBot, siap melindungi grup Anda dari spam dan membantu manajemen. "
                     "Gunakan `/start` di chat pribadi dengan saya untuk memulai konfigurasi sebagai admin."
            )
            continue # Lewati jika anggota baru adalah bot itu sendiri

        # Log kontak baru
        log_contact_db(member.id, member.full_name)

        # Cek apakah fitur welcome message diaktifkan
        if get_setting_db('welcome_message_enabled', 'off') == 'on':
            welcome_text = get_setting_db('welcome_message_text', "Selamat datang, {nama_pengguna}!")
            parsed_welcome_text = welcome_text.replace("{nama_pengguna}", get_user_mention(member))
            await context.bot.send_message(chat_id=chat.id, text=parsed_welcome_text, parse_mode=constants.ParseMode.HTML)
            logger.info(f"Welcome message sent to {member.full_name} in {chat.title}.")

        # Cek perlindungan bot baru
        if get_setting_db('new_bot_protection', 'off') == 'on' and member.is_bot and not is_admin(member.id):
            try:
                await context.bot.kick_chat_member(chat.id, member.id)
                await context.bot.send_message(chat_id=chat.id, text=f"🤖 Bot {get_user_mention(member)} telah dihapus karena perlindungan bot baru aktif.", parse_mode=constants.ParseMode.HTML)
                logger.info(f"Bot baru {member.full_name} ({member.id}) dihapus dari {chat.title}.")
                log_admin_action_db(context.bot.id, "Removed new bot", member.id)
            except Exception as e:
                logger.error(f"Gagal menghapus bot baru {member.full_name}: {e}")
                await context.bot.send_message(chat_id=chat.id, text=f"⚠️ Gagal menghapus bot baru {get_user_mention(member)}. Bot mungkin tidak memiliki izin yang cukup.", parse_mode=constants.ParseMode.HTML)


# Dictionary untuk melacak pesan terakhir pengguna untuk flood control
user_last_message_time = {}

async def message_protection_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menangani pesan untuk berbagai fitur perlindungan dan logging."""
    message = update.effective_message
    if not message: # Pastikan ada pesan
        return

    user = update.effective_user
    chat = update.effective_chat

    # Jika pesan bukan dari grup atau supergrup, abaikan perlindungan
    if chat.type not in [Chat.GROUP, Chat.SUPERGROUP]:
        if user and is_admin(user.id) and message.text: # Jika admin chat pribadi, tetap log chat
            log_chat_db(message.message_id, chat.id, user.id, user.full_name, message.text, message.date)
        return

    # Jika pengirim adalah bot itu sendiri atau admin bot, abaikan sebagian besar perlindungan
    if user and (user.id == context.bot.id or is_admin(user.id)):
        # Namun, tetap log chat jika itu pesan admin di grup
        if message.text: # Hanya log pesan teks dari admin
            log_chat_db(message.message_id, chat.id, user.id, user.full_name, message.text, message.date)
        return

    # --- Logging Chat & Kontak untuk non-admin di grup ---
    if message.text: # Hanya log pesan teks
        log_chat_db(message.message_id, chat.id, user.id, user.full_name, message.text, message.date)
    log_contact_db(user.id, user.full_name)


    # --- Mode Baca Saja (Lock Group) ---
    # Periksa apakah grup terkunci dan pengirim bukan admin bot
    if get_setting_db(f'lock_group_{chat.id}', 'off') == 'on':
        try:
            await message.delete()
            logger.info(f"Pesan dari {user.full_name} dihapus karena grup terkunci.")
            return # Hentikan pemrosesan lebih lanjut jika pesan dihapus
        except Exception as e:
            logger.error(f"Gagal menghapus pesan di grup terkunci: {e}")
            # Lanjutkan, karena tidak berhasil dihapus.

    # --- Perlindungan Link ---
    if get_setting_db('link_protection', 'off') == 'on':
        if message.text: # Hanya cek link di pesan teks
            # Regex untuk mendeteksi URL (http/https) atau domain.
            url_pattern = r'https?://[^\s/$.?#].[^\s]*'
            if re.search(url_pattern, message.text, re.IGNORECASE):
                # Cek Whitelist
                whitelisted_links = get_whitelist_links_db()
                is_whitelisted = False
                for wl_link in whitelisted_links:
                    if wl_link in message.text: # Cek jika link yang dikirim mengandung link whitelist
                        is_whitelisted = True
                        break
                
                if not is_whitelisted:
                    try:
                        await message.delete()
                        await context.bot.send_message(
                            chat_id=chat.id,
                            text=f"{get_user_mention(user)}, pesan Anda dihapus karena mengandung tautan. Mohon tidak mengirim tautan di grup ini.",
                            parse_mode=constants.ParseMode.HTML
                        )
                        logger.info(f"Link dari {user.full_name} dihapus di {chat.title}.")
                        return # Hentikan pemrosesan lebih lanjut
                    except Exception as e:
                        logger.error(f"Gagal menghapus link dari {user.full_name}: {e}")

    # --- Perlindungan Undangan Grup Telegram ---
    if get_setting_db('invite_protection', 'off') == 'on':
        if message.text: # Hanya cek undangan di pesan teks
            # Regex untuk undangan grup Telegram (t.me/joinchat atau telegram.me/joinchat)
            invite_pattern = r'(t\.me|telegram\.me)\/joinchat\/[a-zA-Z0-9_-]+'
            if re.search(invite_pattern, message.text, re.IGNORECASE):
                try:
                    await message.delete()
                    await context.bot.send_message(
                        chat_id=chat.id,
                        text=f"{get_user_mention(user)}, pesan Anda dihapus karena mengandung undangan grup Telegram. Mohon tidak mengirim undangan grup di sini.",
                        parse_mode=constants.ParseMode.HTML
                    )
                    logger.info(f"Undangan grup dari {user.full_name} dihapus di {chat.title}.")
                    return # Hentikan pemrosesan lebih lanjut
                except Exception as e:
                    logger.error(f"Gagal menghapus undangan grup dari {user.full_name}: {e}")

    # --- Perlindungan Kata Kunci ---
    if get_setting_db('keyword_protection', 'off') == 'on':
        if message.text: # Hanya cek kata kunci di pesan teks
            forbidden_keywords = get_keywords_db()
            for keyword in forbidden_keywords:
                if keyword.lower() in message.text.lower():
                    try:
                        await message.delete()
                        await context.bot.send_message(
                            chat_id=chat.id,
                            text=f"{get_user_mention(user)}, pesan Anda dihapus karena mengandung kata kunci terlarang.",
                            parse_mode=constants.ParseMode.HTML
                        )
                        logger.info(f"Pesan dengan kata kunci terlarang dari {user.full_name} dihapus di {chat.title}.")
                        return # Hentikan pemrosesan lebih lanjut
                    except Exception as e:
                        logger.error(f"Gagal menghapus pesan dengan kata kunci terlarang dari {user.full_name}: {e}")

    # --- Anti-Spam Media (jika hanya ada media tanpa teks) ---
    if get_setting_db('media_spam_protection', 'off') == 'on':
        # Cek jika ada foto, video, stiker, atau animasi DAN tidak ada teks (caption)
        if (message.photo or message.video or message.sticker or message.animation) and not message.caption:
            try:
                await message.delete()
                await context.bot.send_message(
                    chat_id=chat.id,
                    text=f"{get_user_mention(user)}, pesan Anda dihapus karena hanya berisi media tanpa teks. Mohon sertakan deskripsi.",
                    parse_mode=constants.ParseMode.HTML
                )
                logger.info(f"Media spam dari {user.full_name} dihapus di {chat.title}.")
                return
            except Exception as e:
                logger.error(f"Gagal menghapus media spam dari {user.full_name}: {e}")

    # --- Batas Pesan Cepat (Flood Protection) ---
    if get_setting_db('flood_protection', 'off') == 'on':
        user_id = user.id
        current_time = datetime.now()
        
        # Ambil pengaturan ambang batas flood (misal: 3 pesan dalam 5 detik)
        flood_message_limit = int(get_setting_db('flood_message_limit', '3'))
        flood_time_window = int(get_setting_db('flood_time_window', '5')) # dalam detik

        if user_id not in user_last_message_time:
            user_last_message_time[user_id] = []
        
        # Hapus timestamp yang sudah terlalu lama
        user_last_message_time[user_id] = [
            t for t in user_last_message_time[user_id] 
            if current_time - t < timedelta(seconds=flood_time_window)
        ]
        user_last_message_time[user_id].append(current_time)

        if len(user_last_message_time[user_id]) > flood_message_limit:
            try:
                await message.delete()
                await context.bot.send_message(
                    chat_id=chat.id,
                    text=f"{get_user_mention(user)}, Anda mengirim pesan terlalu cepat. Mohon perlambat. Pesan Anda dihapus.",
                    parse_mode=constants.ParseMode.HTML
                )
                logger.info(f"Flood detection: Pesan dari {user.full_name} dihapus di {chat.title}.")
                # Opsional: mute user untuk beberapa saat
                # await context.bot.restrict_chat_member(chat.id, user_id, permissions=ChatPermissions(can_send_messages=False), until_date=current_time + timedelta(minutes=5))
                return
            except Exception as e:
                logger.error(f"Gagal menghapus pesan flood dari {user.full_name}: {e}")

# --- Set Flood Limit Command ---
@admin_only
async def set_flood_limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mengatur ambang batas flood protection (jumlah pesan dan waktu)."""
    if len(context.args) != 2:
        await update.message.reply_text("Penggunaan: `/set_flood_limit <jumlah_pesan> <detik>`\n"
                                      "Contoh: `/set_flood_limit 3 5` (3 pesan dalam 5 detik)")
        return
    try:
        message_limit = int(context.args[0])
        time_window = int(context.args[1])
        if message_limit < 1 or time_window < 1:
            await update.message.reply_text("Jumlah pesan dan detik harus angka positif.")
            return
        set_setting_db('flood_message_limit', str(message_limit))
        set_setting_db('flood_time_window', str(time_window))
        await update.message.reply_text(f"Batas pesan cepat diatur ke {message_limit} pesan dalam {time_window} detik.")
        log_admin_action_db(update.effective_user.id, "Set flood limit", f"{message_limit} in {time_window}s")
    except ValueError:
        await update.message.reply_text("Jumlah pesan dan detik harus berupa angka.")
    except Exception as e:
        logger.error(f"Error setting flood limit: {e}")
        await update.message.reply_text("Terjadi kesalahan saat mengatur batas pesan cepat.")

# --- Error Handler ---
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Updates."""
    logger.warning(f'Update "{update}" caused error "{context.error}"')
    if update.effective_chat and update.effective_user and is_admin(update.effective_user.id):
        try:
            await update.effective_chat.send_message(
                f"⚠️ Terjadi kesalahan: `{context.error}`\n"
                "Mohon cek log bot untuk detail lebih lanjut.",
                parse_mode=constants.ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Failed to send error message to admin: {e}")

def main() -> None:
    """Mulai bot."""
    global TOKEN, ADMIN_IDS

    # Memuat konfigurasi dari config.py
    try:
        from config import TOKEN, ADMIN_IDS
        if not TOKEN or not ADMIN_IDS:
            raise ValueError("TOKEN atau ADMIN_IDS tidak terkonfigurasi di config.py")
    except (ImportError, ValueError) as e:
        logger.critical(f"Kesalahan memuat konfigurasi: {e}. Pastikan config.py ada dan terisi dengan benar.")
        print("Pastikan file 'config.py' ada dan berisi TOKEN dan ADMIN_IDS yang valid.")
        print("Anda mungkin perlu menjalankan ulang skrip instalasi jika ini adalah masalah konfigurasi.")
        return

    # Inisialisasi database
    init_db()

    # Buat aplikasi Updater dan teruskan token bot Anda.
    application = Application.builder().token(TOKEN).build()

    # --- Daftarkan Command Handlers ---
    # Perintah /start akan mengarah ke start_command (yang admin-only).
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))

    # Perintah Admin
    application.add_handler(CommandHandler("tambah_pengguna", add_user_command))
    application.add_handler(CommandHandler("hapus_pengguna", delete_user_command))
    application.add_handler(CommandHandler("detail_pengguna", detail_user_command))
    application.add_handler(CommandHandler("backup", backup_command))
    application.add_handler(CommandHandler("restore", restore_command)) # Restore dilakukan dengan membalas file
    application.add_handler(CommandHandler("cek_pengaturan", check_settings_command))
    application.add_handler(CommandHandler("siarkan_pesan", broadcast_command))
    application.add_handler(CommandHandler("add_link_whitelist", add_link_whitelist_command))
    application.add_handler(CommandHandler("del_link_whitelist", del_link_whitelist_command))
    application.add_handler(CommandHandler("add_keyword", add_keyword_command))
    application.add_handler(CommandHandler("del_keyword", del_keyword_command))
    application.add_handler(CommandHandler("lock_group", lock_group_command))
    application.add_handler(CommandHandler("unlock_group", unlock_group_command))
    application.add_handler(CommandHandler("welcome_config", welcome_config_command))
    application.add_handler(CommandHandler("set_welcome_message", set_welcome_message_command))
    application.add_handler(CommandHandler("toggle_welcome_message", toggle_welcome_message_command))
    application.add_handler(CommandHandler("warn", warn_command))
    application.add_handler(CommandHandler("warnings_config", warnings_config_command))
    application.add_handler(CommandHandler("set_warning_limit", set_warning_limit_command))
    application.add_handler(CommandHandler("view_user_warnings", view_user_warnings_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("set_flood_limit", set_flood_limit_command)) # New command for flood limit

    # --- Daftarkan Callback Query Handlers (untuk tombol inline) ---
    application.add_handler(CallbackQueryHandler(button_callback_handler))

    # --- Daftarkan Message Handlers untuk Perlindungan & Logging ---
    # Handler untuk anggota baru (termasuk bot itu sendiri ditambahkan ke grup)
    application.add_handler(ChatMemberHandler(new_member_handler, ChatMemberHandler.CHAT_MEMBER))
    
    # Handler untuk semua pesan (teks, media dengan/tanpa caption) untuk perlindungan dan logging
    # Pastikan ini berjalan setelah handler command, agar command tidak terhapus.
    # filter ~filters.COMMAND memastikan handler ini tidak memproses perintah bot.
    application.add_handler(MessageHandler(
        filters.TEXT | filters.PHOTO | filters.VIDEO | filters.STICKER | filters.ANIMATION | filters.Document.ALL & ~filters.COMMAND,
        message_protection_handler
    ))


    # Daftarkan Error Handler
    application.add_error_handler(error_handler)

    # Jalankan bot sampai Ctrl-C ditekan
    logger.info("GuardianBot sedang berjalan...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    
    # Pastikan database ditutup saat bot berhenti
    close_db()

if __name__ == '__main__':
    main()

