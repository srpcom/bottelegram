#!/bin/bash

# =================================================================
# SKRIP INSTALLER BOT TELEGRAM SRPCOM STORE
# Dibuat oleh Gemini
# Versi: 1.1 (Support APScheduler untuk Backup)
# =================================================================

# --- Warna untuk Output ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# --- Variabel Konfigurasi ---
BOT_DIR="/opt/srpcom_bot"
VENV_DIR="$BOT_DIR/venv"
SERVICE_NAME="srpcom-bot"
ADMIN_ID="5666536947" # ID Admin Utama
TRIPAY_API_KEY="B0RS3FtI9tMrfh1wI7eZjsruBoUlybY18tEXSEo2x"
TRIPAY_PRIVATE_KEY="GqoGJ-86JmH-knzMg-Zmu6n-XZaYRx"
TRIPAY_MERCHANT_CODE="T40281x"
CALLBACK_PORT="8443" # Port untuk menerima callback dari Tripay

# --- Fungsi untuk menampilkan pesan ---
log_info() {
    echo -e "${GREEN}[INFO] $1${NC}"
}

log_warn() {
    echo -e "${YELLOW}[PERINGATAN] $1${NC}"
}

log_error() {
    echo -e "${RED}[ERROR] $1${NC}"
}

# --- Memastikan skrip dijalankan sebagai root ---
if [ "$(id -u)" -ne 0 ]; then
    log_error "Skrip ini harus dijalankan sebagai root. Coba gunakan 'sudo bash'."
    exit 1
fi

# --- Memulai Instalasi ---
log_info "Memulai instalasi Bot Telegram SRPCOM STORE..."

# 1. Meminta Token Bot
read -p "$(echo -e ${YELLOW}"Masukkan Token Bot Telegram Anda: "${NC})" BOT_TOKEN
if [ -z "$BOT_TOKEN" ]; then
    log_error "Token Bot tidak boleh kosong. Instalasi dibatalkan."
    exit 1
fi

# 2. Update Sistem dan Instal Dependensi
log_info "Memperbarui sistem dan menginstal dependensi..."
apt-get update > /dev/null 2>&1
apt-get install -y python3-pip python3-venv sqlite3 jq > /dev/null 2>&1
log_info "Dependensi sistem berhasil diinstal."

# 3. Membuat Struktur Direktori dan Virtual Environment
log_info "Membuat direktori bot di $BOT_DIR..."
mkdir -p $BOT_DIR
chown -R $(logname):$(logname) $BOT_DIR
python3 -m venv $VENV_DIR
log_info "Virtual environment berhasil dibuat."

# 4. Membuat File Konfigurasi (config.ini)
log_info "Membuat file konfigurasi config.ini..."
cat << EOF > $BOT_DIR/config.ini
[telegram]
token = $BOT_TOKEN
admin_id = $ADMIN_ID

[tripay]
api_key = $TRIPAY_API_KEY
private_key = $TRIPAY_PRIVATE_KEY
merchant_code = $TRIPAY_MERCHANT_CODE

[webhook]
listen_ip = 0.0.0.0
port = $CALLBACK_PORT
# Pastikan VPS Anda memiliki domain/IP publik dan port $CALLBACK_PORT terbuka
# URL Callback Anda adalah: http://IP_VPS_ANDA:$CALLBACK_PORT/tripay-callback
EOF

# 5. Membuat File requirements.txt (DIPERBARUI)
log_info "Membuat file requirements.txt..."
cat << EOF > $BOT_DIR/requirements.txt
python-telegram-bot==21.0.1
requests
flask
waitress
apscheduler
EOF

# 6. Menginstal Library Python
log_info "Menginstal library Python dari requirements.txt..."
source $VENV_DIR/bin/activate
pip install -r $BOT_DIR/requirements.txt > /dev/null 2>&1
deactivate
log_info "Library Python berhasil diinstal."

# 7. Membuat Skrip Inisialisasi Database (setup_db.py) (DIPERBARUI)
log_info "Membuat skrip inisialisasi database..."
cat << 'EOF' > $BOT_DIR/setup_db.py
import sqlite3
import os

DB_FILE = os.path.join(os.path.dirname(__file__), 'srpcom.db')

def create_connection():
    """ create a database connection to a SQLite database """
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        print(f"SQLite version: {sqlite3.sqlite_version}")
        print(f"Database created at {DB_FILE}")
        return conn
    except sqlite3.Error as e:
        print(e)
    return conn

def create_table(conn, create_table_sql):
    """ create a table from the create_table_sql statement
    :param conn: Connection object
    :param create_table_sql: a CREATE TABLE statement
    """
    try:
        c = conn.cursor()
        c.execute(create_table_sql)
    except sqlite3.Error as e:
        print(e)

def main():
    sql_create_users_table = """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL UNIQUE,
        username TEXT,
        balance INTEGER NOT NULL DEFAULT 0,
        join_date TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'member',
        discount_percentage INTEGER NOT NULL DEFAULT 0
    );
    """

    sql_create_servers_table = """
    CREATE TABLE IF NOT EXISTS servers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        host TEXT NOT NULL,
        api_key TEXT NOT NULL
    );
    """

    sql_create_server_prices_table = """
    CREATE TABLE IF NOT EXISTS harga_server (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        server_id INTEGER NOT NULL,
        tipe_layanan TEXT NOT NULL,
        harga_harian INTEGER NOT NULL,
        FOREIGN KEY (server_id) REFERENCES servers (id) ON DELETE CASCADE,
        UNIQUE(server_id, tipe_layanan)
    );
    """

    sql_create_transactions_table = """
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        description TEXT NOT NULL,
        amount INTEGER NOT NULL,
        timestamp TEXT NOT NULL,
        type TEXT NOT NULL,
        reference TEXT,
        message_id INTEGER
    );
    """

    sql_create_vpn_accounts_table = """
    CREATE TABLE IF NOT EXISTS vpn_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        vpn_username TEXT NOT NULL,
        server_name TEXT NOT NULL,
        service_type TEXT NOT NULL,
        details TEXT NOT NULL,
        expiry_date TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """
    
    sql_create_settings_table = """
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    """

    conn = create_connection()
    if conn is not None:
        create_table(conn, sql_create_users_table)
        create_table(conn, sql_create_servers_table)
        create_table(conn, sql_create_server_prices_table)
        create_table(conn, sql_create_transactions_table)
        create_table(conn, sql_create_vpn_accounts_table)
        create_table(conn, sql_create_settings_table)
        
        # Menambahkan nilai default untuk settings
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('backup_status', 'OFF')")
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('backup_frequency', '2')")
        conn.commit()

        conn.close()
        print("Semua tabel berhasil dibuat atau sudah ada.")
    else:
        print("Error! Tidak dapat membuat koneksi database.")

if __name__ == '__main__':
    main()
EOF

# 8. Menjalankan Skrip Database
log_info "Menginisialisasi database srpcom.db..."
source $VENV_DIR/bin/activate
python3 $BOT_DIR/setup_db.py
deactivate

# 9. Membuat File Bot Utama (bot.py)
log_info "Membuat file utama bot.py..."
# Konten bot.py akan disalin di langkah berikutnya.
# Untuk sekarang, kita buat file kosong agar bisa mengatur service.
touch $BOT_DIR/bot.py
chmod +x $BOT_DIR/bot.py

# 10. Membuat Service systemd
log_info "Membuat service systemd agar bot berjalan otomatis..."
CURRENT_USER=$(logname)
CURRENT_GROUP=$(id -gn $CURRENT_USER)
cat << EOF > /etc/systemd/system/$SERVICE_NAME.service
[Unit]
Description=Telegram Bot SRPCOM STORE
After=network.target

[Service]
User=$CURRENT_USER
Group=$CURRENT_GROUP
WorkingDirectory=$BOT_DIR
ExecStart=$VENV_DIR/bin/python3 $BOT_DIR/bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 11. Mengaktifkan dan Menjalankan Service
log_info "Mengaktifkan dan menjalankan service bot..."
systemctl daemon-reload
systemctl enable $SERVICE_NAME
# Kita belum start, karena bot.py masih kosong.

# --- Selesai ---
log_info "========================================================"
log_info "INSTALASI DASAR SELESAI!"
log_warn "LANGKAH SELANJUTNYA:"
log_warn "1. Salin konten untuk 'bot.py' dari Gemini (versi terbaru)."
log_warn "2. Buka file bot kosong dengan: nano $BOT_DIR/bot.py"
log_warn "3. Tempelkan kode, lalu simpan (Ctrl+X, Y, Enter)."
log_warn "4. Jalankan bot dengan: sudo systemctl start $SERVICE_NAME"
log_warn "5. Cek status bot dengan: sudo systemctl status $SERVICE_NAME"
log_warn "PENTING: Pastikan port $CALLBACK_PORT terbuka di firewall VPS Anda."
log_info "========================================================"
