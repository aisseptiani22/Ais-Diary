
import os
import re
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters
)

TOKEN = os.getenv("BOT_TOKEN")
DB = "ais_money.db"
TZ = ZoneInfo("Asia/Jakarta")

CATEGORIES = {
    "makan": "Makan",
    "kucing": "Kucing",
    "setor arisan": "Setor Arisan",
    "get arisan": "Get Arisan",
    "bensin": "Bensin",
    "belanja": "Belanja",
    "lainnya": "Lainnya",
    "pemasukan": "Pemasukan",
}

def db():
    con = sqlite3.connect(DB)
    con.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_id INTEGER,
            kind TEXT,
            category TEXT,
            note TEXT,
            amount INTEGER,
            created_at TEXT
        )
    """)
    return con

def rupiah(n):
    return "Rp" + f"{n:,}".replace(",", ".")

def parse_amount(s):
    s = s.lower().replace(".", "").replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(rb|ribu|k|jt|juta)?", s)
    if not m:
        return None
    number = float(m.group(1))
    unit = m.group(2)
    if unit in ("rb", "ribu", "k"):
        number *= 1000
    elif unit in ("jt", "juta"):
        number *= 1000000
    return int(number)

def parse_transaction(text):
    raw = text.strip().lower()
    amount = parse_amount(raw)
    if not amount or amount <= 0:
        return None

    kind = "expense"
    if raw.startswith(("dapat ", "get ", "pemasukan ", "gaji ")):
        kind = "income"

    category = "Lainnya"
    note = raw

    for key, value in CATEGORIES.items():
        if raw.startswith(key + " ") or raw == key:
            category = value
            note = raw[len(key):].strip()
            if key == "get arisan":
                kind = "income"
            elif key == "pemasukan":
                kind = "income"
            else:
                kind = "expense"
            break

    if raw.startswith(("dapat ", "gaji ")):
        category = "Pemasukan"
        note = raw.split(" ", 1)[1]

    if raw.startswith("get arisan "):
        category = "Get Arisan"
        kind = "income"
        note = raw[len("get arisan "):].strip()

    if raw.startswith("setor arisan "):
        category = "Setor Arisan"
        kind = "expense"
        note = raw[len("setor arisan "):].strip()

    note = re.sub(
        r"\d+(?:[.,]\d+)?\s*(rb|ribu|k|jt|juta)?",
        "", note
    ).strip(" -")
    if not note:
        note = category

    return kind, category, note, amount

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Haiii! 💗 Aku Ais Money Bot.\n\n"
        "Kirim transaksi seperti:\n"
        "Makan 25rb\n"
        "Kucing 50rb\n"
        "Setor arisan 100rb\n"
        "Get arisan 1jt\n"
        "Dapat jasa dokter 300rb\n\n"
        "Ketik /rekap untuk melihat rekap."
    )

async def catat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Kirim transaksi dengan format:\n"
        "Makan 25rb\n"
        "Dapat jasa dokter 300rb"
    )

async def kategori(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Kategori:\n"
        "Pemasukan\nMakan\nKucing\nSetor Arisan\n"
        "Get Arisan\nBensin\nBelanja\nLainnya"
    )

async def saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    con = db()
    cid = update.effective_chat.id
    income = con.execute(
        "SELECT COALESCE(SUM(amount),0) FROM transactions "
        "WHERE chat_id=? AND kind='income'", (cid,)
    ).fetchone()[0]
    expense = con.execute(
        "SELECT COALESCE(SUM(amount),0) FROM transactions "
        "WHERE chat_id=? AND kind='expense'", (cid,)
    ).fetchone()[0]
    con.close()
    await update.message.reply_text(
        f"💰 Total pemasukan: {rupiah(income)}\n"
        f"🛍️ Total pengeluaran: {rupiah(expense)}\n"
        f"✨ Saldo: {rupiah(income-expense)}"
    )

async def rekap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    con = db()
    cid = update.effective_chat.id
    month = datetime.now(TZ).strftime("%Y-%m")
    rows = con.execute(
        "SELECT kind, category, SUM(amount) FROM transactions "
        "WHERE chat_id=? AND created_at LIKE ? "
        "GROUP BY kind, category ORDER BY kind, category",
        (cid, month + "%")
    ).fetchall()
    con.close()

    if not rows:
        await update.message.reply_text("Belum ada transaksi bulan ini 💗")
        return

    lines = ["📊 REKAP BULAN INI"]
    for kind, category, total in rows:
        label = "Pemasukan" if kind == "income" else "Pengeluaran"
        lines.append(f"{label} • {category}: {rupiah(total)}")
    await update.message.reply_text("\n".join(lines))

async def hapus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    con = db()
    cid = update.effective_chat.id
    row = con.execute(
        "SELECT id, category, amount FROM transactions "
        "WHERE chat_id=? ORDER BY id DESC LIMIT 1", (cid,)
    ).fetchone()
    if row:
        con.execute("DELETE FROM transactions WHERE id=?", (row[0],))
        con.commit()
        msg = f"Transaksi terakhir ({row[1]} {rupiah(row[2])}) dihapus."
    else:
        msg = "Belum ada transaksi yang bisa dihapus."
    con.close()
    await update.message.reply_text(msg)

async def edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Fitur edit akan kita aktifkan setelah versi awal bot berjalan 💗"
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parsed = parse_transaction(update.message.text)
    if not parsed:
        await update.message.reply_text(
            "Belum kebaca nih 😅 Contoh: Makan 25rb"
        )
        return

    kind, category, note, amount = parsed
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    con = db()
    con.execute(
        "INSERT INTO transactions "
        "(chat_id,user_id,kind,category,note,amount,created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (update.effective_chat.id, update.effective_user.id,
         kind, category, note, amount, now)
    )
    con.commit()
    con.close()

    label = "Pemasukan" if kind == "income" else "Pengeluaran"
    await update.message.reply_text(
        f"✅ Berhasil dicatat!\n"
        f"{label}: {category}\n"
        f"Keterangan: {note}\n"
        f"Nominal: {rupiah(amount)}"
    )

def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN belum diatur.")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("catat", catat))
    app.add_handler(CommandHandler("saldo", saldo))
    app.add_handler(CommandHandler("rekap", rekap))
    app.add_handler(CommandHandler("kategori", kategori))
    app.add_handler(CommandHandler("hapus", hapus))
    app.add_handler(CommandHandler("edit", edit))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.run_polling()

if __name__ == "__main__":
    main()
