#!/usr/bin/env python3
"""
JKT48 Ticket Monitor — GitHub Actions Version
Cek quota tiket dari API, simpan state di file JSON,
kirim notifikasi Telegram jika ada perubahan.
"""

import requests
import json
import os
import sys
from datetime import datetime

# ─────────────────────────────────────────────
#  KONFIGURASI
# ─────────────────────────────────────────────

API_URL = "https://jkt48.com/api/v1/exclusives/EX579E/bonus?lang=id"
EXCLUSIVE_CODE = "EX579E"
STATE_FILE = "state.json"

# Ambil dari GitHub Secrets (diset otomatis saat Actions jalan)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

# Kosongkan [] untuk pantau SEMUA member
# Contoh: WATCH_MEMBERS = ["Shabilqis Naila", "Freya Jayawardana"]
WATCH_MEMBERS = []

# ─────────────────────────────────────────────
#  TELEGRAM
# ─────────────────────────────────────────────

def send_telegram(message: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ TELEGRAM_BOT_TOKEN atau TELEGRAM_CHAT_ID belum diset!")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        print(f"✅ Notifikasi Telegram terkirim")
        return True
    except requests.RequestException as e:
        print(f"❌ Gagal kirim Telegram: {e}")
        return False

# ─────────────────────────────────────────────
#  STATE (simpan quota terakhir di JSON)
# ─────────────────────────────────────────────

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

# ─────────────────────────────────────────────
#  FETCH API
# ─────────────────────────────────────────────

def fetch_tickets() -> list | None:
    try:
        r = requests.get(API_URL, timeout=10,
                         headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        data = r.json()
        if data.get("status") and "data" in data:
            return data["data"]
        print(f"⚠ Respons tidak terduga: {data.get('message')}")
        return None
    except Exception as e:
        print(f"❌ Gagal fetch API: {e}")
        return None

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] Mulai pengecekan tiket JKT48...")

    sessions = fetch_tickets()
    if sessions is None:
        print("❌ Gagal ambil data, skip.")
        sys.exit(1)

    prev_state = load_state()
    new_state = {}
    notif_count = 0
    total_slots = 0

    for sesi in sessions:
        sesi_label = sesi.get("label", "?")
        sesi_time  = sesi.get("start_time", "")[:5]

        for member in sesi.get("session_members", []):
            name        = member.get("member_name", "")
            jalur       = member.get("label", "")
            quota       = member.get("quota", 0)
            price       = member.get("price", 0)
            detail_id   = str(member.get("session_detail_id", ""))
            detail_code = member.get("session_detail_code", "")
            total_slots += 1

            # Filter member jika WATCH_MEMBERS diisi
            if WATCH_MEMBERS and name not in WATCH_MEMBERS:
                new_state[detail_id] = quota
                continue

            prev_quota = prev_state.get(detail_id, 0)
            new_state[detail_id] = quota

            # Sold out → Tersedia
            if quota > 0 and prev_quota == 0:
                print(f"🎉 TERSEDIA: {name} | {sesi_label} ({sesi_time}) | {jalur} | quota={quota}")
                purchase_url = f"https://jkt48.com/purchase/exclusive?code={EXCLUSIVE_CODE}"
                msg = (
                    f"🎉 <b>TIKET TERSEDIA!</b>\n\n"
                    f"👤 <b>Member:</b> {name}\n"
                    f"📋 <b>Sesi:</b> {sesi_label} ({sesi_time} WIB)\n"
                    f"🚪 <b>Jalur:</b> {jalur}\n"
                    f"🎟 <b>Quota:</b> {quota} tiket\n"
                    f"💰 <b>Harga:</b> Rp{price:,}\n"
                    f"🕐 <b>Terdeteksi:</b> {now}\n\n"
                    f"🔗 <a href='{purchase_url}'>Beli sekarang →</a>"
                )
                send_telegram(msg)
                notif_count += 1

            # Tersedia → Sold out
            elif quota == 0 and prev_quota > 0:
                print(f"❌ Kembali sold out: {name} | {sesi_label} | {jalur}")

            else:
                status = f"quota={quota}" if quota > 0 else "sold out"
                print(f"   {name} | {sesi_label} {jalur} — {status}")

    save_state(new_state)

    print(f"\n📊 Hasil: {total_slots} slot dipantau, {notif_count} notifikasi dikirim")
    if notif_count == 0:
        print("😴 Semua masih sold out.")

if __name__ == "__main__":
    main()
