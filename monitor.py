#!/usr/bin/env python3
"""
JKT48 Ticket Monitor — GitHub Actions Version
Cek quota tiket dari API, simpan state di file JSON,
kirim notifikasi Telegram jika ada perubahan.
Fitur heartbeat: kirim laporan otomatis setiap 6 jam.

Mode tes: jalankan dengan argumen --test
  python monitor.py --test
"""

import requests
import json
import os
import sys
from datetime import datetime, timezone, timedelta

# ─────────────────────────────────────────────
#  KONFIGURASI
# ─────────────────────────────────────────────

API_URL        = "https://jkt48.com/api/v1/exclusives/EX579E/bonus?lang=id"
EXCLUSIVE_CODE = "EX579E"
STATE_FILE     = "state.json"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

# Kosongkan [] untuk pantau SEMUA member
WATCH_MEMBERS = []

# Interval heartbeat dalam jam
HEARTBEAT_EVERY_HOURS = 6

# ─────────────────────────────────────────────
#  WAKTU (WIB = UTC+7)
# ─────────────────────────────────────────────

def now_wib() -> datetime:
    return datetime.now(timezone(timedelta(hours=7)))

def now_str() -> str:
    return now_wib().strftime("%Y-%m-%d %H:%M WIB")

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
        print("✅ Telegram terkirim")
        return True
    except requests.RequestException as e:
        print(f"❌ Gagal kirim Telegram: {e}")
        return False

# ─────────────────────────────────────────────
#  STATE
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
#  HEARTBEAT — cek apakah sudah waktunya kirim
# ─────────────────────────────────────────────

def should_send_heartbeat(state: dict) -> bool:
    last_hb = state.get("last_heartbeat")
    if not last_hb:
        return True
    try:
        last_dt = datetime.fromisoformat(last_hb)
        elapsed = now_wib() - last_dt
        return elapsed.total_seconds() >= HEARTBEAT_EVERY_HOURS * 3600
    except Exception:
        return True

def send_heartbeat(state: dict, sessions: list, total_slots: int):
    now = now_wib()
    # Hitung berapa slot yang masih sold out vs tersedia
    available = sum(
        1 for s in sessions
        for m in s.get("session_members", [])
        if m.get("quota", 0) > 0
    )
    sold_out = total_slots - available

    # Hitung run count
    run_count = state.get("run_count", 0)

    # Waktu heartbeat berikutnya
    next_hb = now + timedelta(hours=HEARTBEAT_EVERY_HOURS)
    next_hb_str = next_hb.strftime("%H:%M WIB")

    status_line = "😴 Semua slot masih sold out" if available == 0 \
        else f"🎟 {available} slot tersedia!"

    msg = (
        f"💓 <b>Laporan Berkala — JKT48 Monitor</b>\n\n"
        f"✅ Sistem berjalan normal\n"
        f"🕐 Waktu: {now.strftime('%Y-%m-%d %H:%M WIB')}\n\n"
        f"📊 <b>Status tiket:</b>\n"
        f"   • Total slot dipantau: {total_slots}\n"
        f"   • Sold out: {sold_out}\n"
        f"   • Tersedia: {available}\n\n"
        f"{status_line}\n\n"
        f"🔁 Laporan berikutnya: {next_hb_str}\n"
        f"📈 Total pengecekan: {run_count:,}x"
    )
    print(f"💓 Mengirim heartbeat ({HEARTBEAT_EVERY_HOURS} jam sekali)...")
    send_telegram(msg)
    state["last_heartbeat"] = now.isoformat()

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
#  MODE TES
# ─────────────────────────────────────────────

def run_test():
    now = now_str()
    print("=" * 50)
    print("🧪 MODE TES — JKT48 Monitor")
    print("=" * 50)

    # 1. Tes koneksi API
    print("\n[1/4] Mengecek koneksi ke API JKT48...")
    sessions = fetch_tickets()
    if sessions is None:
        print("❌ GAGAL: Tidak bisa mengakses API JKT48")
        sys.exit(1)
    total = sum(len(s.get("session_members", [])) for s in sessions)
    print(f"✅ API OK — {len(sessions)} sesi, {total} slot member ditemukan")

    # 2. Tes kirim notifikasi tiket
    print("\n[2/4] Mengirim contoh notifikasi tiket ke Telegram...")
    purchase_url = f"https://jkt48.com/purchase/exclusive?code={EXCLUSIVE_CODE}"
    test_msg = (
        f"🧪 <b>PESAN TES — JKT48 Monitor</b>\n\n"
        f"✅ Sistem berjalan normal!\n"
        f"📡 API JKT48 terhubung\n"
        f"🎟 {len(sessions)} sesi | {total} slot dipantau\n"
        f"🕐 Waktu tes: {now}\n\n"
        f"Contoh notifikasi saat tiket tersedia:\n\n"
        f"🎉 <b>TIKET TERSEDIA!</b>\n"
        f"👤 <b>Member:</b> Shabilqis Naila\n"
        f"📋 <b>Sesi:</b> Sesi 5 (15:00 WIB)\n"
        f"🚪 <b>Jalur:</b> Jalur 5\n"
        f"🎟 <b>Quota:</b> 3 tiket\n"
        f"💰 <b>Harga:</b> Rp180,000\n"
        f"🔗 <a href='{purchase_url}'>Beli sekarang →</a>"
    )
    ok = send_telegram(test_msg)
    if not ok:
        print("❌ GAGAL: Pesan Telegram tidak terkirim")
        sys.exit(1)

    # 3. Tes kirim heartbeat
    print("\n[3/4] Mengirim contoh laporan berkala (heartbeat) ke Telegram...")
    available = sum(
        1 for s in sessions
        for m in s.get("session_members", [])
        if m.get("quota", 0) > 0
    )
    hb_msg = (
        f"🧪 <b>CONTOH LAPORAN BERKALA</b>\n\n"
        f"💓 Ini adalah contoh pesan yang akan kamu terima\n"
        f"setiap <b>{HEARTBEAT_EVERY_HOURS} jam sekali</b> sebagai bukti sistem masih aktif.\n\n"
        f"✅ Sistem berjalan normal\n"
        f"🕐 Waktu: {now}\n\n"
        f"📊 <b>Status tiket:</b>\n"
        f"   • Total slot dipantau: {total}\n"
        f"   • Sold out: {total - available}\n"
        f"   • Tersedia: {available}\n\n"
        f"😴 Semua slot masih sold out\n\n"
        f"🔁 Laporan berikutnya: 6 jam lagi\n"
        f"📈 Total pengecekan: 1x"
    )
    ok2 = send_telegram(hb_msg)
    if not ok2:
        print("❌ GAGAL: Heartbeat tidak terkirim")
        sys.exit(1)

    # 4. Tes state file
    print("\n[4/4] Mengecek baca/tulis state file...")
    test_state = {"test_key": 99}
    save_state(test_state)
    loaded = load_state()
    if loaded.get("test_key") == 99:
        print("✅ State file OK")
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
    else:
        print("❌ GAGAL: State file tidak bisa dibaca/ditulis")
        sys.exit(1)

    print("\n" + "=" * 50)
    print("✅ SEMUA TES PASSED — Sistem siap berjalan!")
    print(f"   Heartbeat akan dikirim setiap {HEARTBEAT_EVERY_HOURS} jam")
    print("=" * 50)

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

def main():
    now = now_str()
    print(f"[{now}] Mulai pengecekan tiket JKT48...")

    sessions = fetch_tickets()
    if sessions is None:
        print("❌ Gagal ambil data, skip.")
        sys.exit(1)

    state = load_state()

    # Tambah run counter
    state["run_count"] = state.get("run_count", 0) + 1

    new_quota = {}
    notif_count = 0
    total_slots = 0

    for sesi in sessions:
        sesi_label = sesi.get("label", "?")
        sesi_time  = sesi.get("start_time", "")[:5]

        for member in sesi.get("session_members", []):
            name      = member.get("member_name", "")
            jalur     = member.get("label", "")
            quota     = member.get("quota", 0)
            price     = member.get("price", 0)
            detail_id = str(member.get("session_detail_id", ""))
            total_slots += 1

            if WATCH_MEMBERS and name not in WATCH_MEMBERS:
                new_quota[detail_id] = quota
                continue

            prev_quota = state.get("quota", {}).get(detail_id, 0)
            new_quota[detail_id] = quota

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

            elif quota == 0 and prev_quota > 0:
                print(f"❌ Kembali sold out: {name} | {sesi_label} | {jalur}")
            else:
                status = f"quota={quota}" if quota > 0 else "sold out"
                print(f"   {name} | {sesi_label} {jalur} — {status}")

    # Simpan quota ke dalam state
    state["quota"] = new_quota

    # Cek apakah waktunya kirim heartbeat
    if should_send_heartbeat(state):
        send_heartbeat(state, sessions, total_slots)

    save_state(state)

    print(f"\n📊 Hasil: {total_slots} slot, {notif_count} notifikasi, "
          f"run #{state['run_count']}")
    if notif_count == 0:
        print("😴 Semua masih sold out.")

if __name__ == "__main__":
    if "--test" in sys.argv:
        run_test()
    else:
        main()
