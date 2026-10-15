import os
import json
import asyncio
import threading
import urllib.request
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = "8902589333:AAGZVDc7oeua3KIQH-tLU35G6ZwlAtRwqSM"
MY_ADMIN_ID = 6519855560
SNIPER_CHANNEL_ID = -1004325746548
STATS_FILE = "sniper_stats.json"

def load_stats():
    default_stats = {
        "current_date": "",
        "today_wins": 0,
        "today_losses": 0,
        "alltime_wins": 0,
        "alltime_losses": 0
    }
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r") as f:
                return {**default_stats, **json.load(f)}
        except Exception:
            pass
    return default_stats

def save_stats():
    try:
        with open(STATS_FILE, "w") as f:
            json.dump(sniper_tracker, f)
    except Exception:
        pass

sniper_tracker = load_stats()

system_state = {
    "is_running": True,
    "last_reported_block": 0,
    "last_reported_period": 0,
    "history_bs": [],
    "sniper_pending": None,
    "sniper_win_streak": 0
}

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

def self_ping_worker():
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    while True:
        try:
            target = f"{render_url}/" if render_url else f"http://127.0.0.1:{os.environ.get('PORT', 10000)}/"
            req = urllib.request.Request(target, headers={"User-Agent": "Ping/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                pass
        except Exception:
            pass
        threading.Event().wait(300)

def fetch_tron_blocks():
    url = "https://apilist.tronscanapi.com/api/block?sort=-number&limit=15"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=6) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            return res_data.get("data", [])
    except Exception:
        return []

def get_settled_6lottery_block(blocks):
    """
    ၆ထီထက် ၁ ကြိမ် စောမထွက်စေရန်အတွက် ပြီးဆုံးသွားသော မိနစ်၏ :54 စက္ကန့် Block ကိုသာ တိကျစွာ ရယူခြင်း
    """
    if not blocks:
        return 0, ""
    
    # မိနစ်တိုင်း၏ :53 မှ :56 စက္ကန့်အတွင်း Tron Blockchain တွင် ထွက်ပေါ်ခဲ့သော Block ကို ရှာဖွေခြင်း
    for b in blocks:
        ts_ms = b.get("timestamp", 0)
        if ts_ms > 0:
            sec = (ts_ms // 1000) % 60
            if 53 <= sec <= 56:
                return b.get("number", 0), b.get("hash", "")
                
    # အကယ်၍ :54 စက္ကန့် တိတိမတွေ့ပါက နောက်ဆုံးထွက် Block အစား ယခင်ပြီးဆုံးပြီးသား Block ကိုသာ ကောက်ယူခြင်း
    if len(blocks) >= 2:
        return blocks[1].get("number", 0), blocks[1].get("hash", "")
    return 0, ""

def parse_trx_hash(hash_str):
    if not hash_str:
        return None, None
    digits = [c for c in hash_str if c.isdigit()]
    if not digits:
        return None, None
    last_num = int(digits[-1])
    side = "BIG" if last_num >= 5 else "SMALL"
    return last_num, side

def evaluate_sniper_v2(history):
    if len(history) < 6:
        return None, "Warming Up"

    last_5 = "".join(history[-5:])
    last_6 = "".join(history[-6:])
    macro_50 = history[-50:] if len(history) >= 50 else history
    b_count = macro_50.count("B")
    s_count = macro_50.count("S")

    if last_5 == "SSSSS" and s_count >= 26:
        return "BIG", "Macro Exhaustion Fade"
    elif last_5 == "BBBBB" and b_count >= 26:
        return "SMALL", "Macro Exhaustion Fade"
    elif len(macro_50) >= 20:
        if s_count >= 28 and last_5 == "SSSBB":
            return "SMALL", "Macro Downtrend Pullback"
        elif b_count >= 28 and last_5 == "BBBSS":
            return "BIG", "Macro Uptrend Pullback"
    if last_5 == "SSBSS":
        return "SMALL", "Trend Continuation"
    elif last_6 == "BBBSSS":
        return "BIG", "Symmetry Balance"

    return None, "စောင့်ဆိုင်းဆဲ"

async def sniper_standalone_worker(app):
    while True:
        try:
            if system_state["is_running"]:
                tz_mm = timezone(timedelta(hours=6, minutes=30))
                now = datetime.now(tz_mm)

                # ၁ ကြိမ် စောထွက်ခြင်း မဖြစ်စေရန် မိနစ်ပြည့်ပြီး စက္ကန့် ၀၂ မှ ၂၀ အတွင်းသာ Result စစ်ဆေးခြင်း
                if now.second >= 2:
                    today_str = now.strftime("%Y-%m-%d")
                    if sniper_tracker["current_date"] != today_str and now.hour == 6 and now.minute == 0:
                        sniper_tracker["current_date"] = today_str
                        sniper_tracker["today_wins"] = 0
                        sniper_tracker["today_losses"] = 0
                        save_stats()

                    # ၆ထီ ပွဲစဉ် Sequence တွက်ချက်ခြင်း (ပြီးဆုံးသွားသော အလှည့်)
                    total_minutes = now.hour * 60 + now.minute
                    base_seq = (total_minutes - 390) % 1440
                    if base_seq <= 0:
                        base_seq += 1440

                    raw_blocks = fetch_tron_blocks()
                    curr_num, curr_hash = get_settled_6lottery_block(raw_blocks)

                    if curr_num > 0 and curr_num != system_state["last_reported_block"]:
                        num_val, side_val = parse_trx_hash(curr_hash)

                        if num_val is not None:
                            if base_seq != system_state["last_reported_period"]:
                                system_state["last_reported_block"] = curr_num
                                system_state["last_reported_period"] = base_seq

                                short_code = "B" if side_val == "BIG" else "S"
                                system_state["history_bs"].append(short_code)
                                if len(system_state["history_bs"]) > 100:
                                    system_state["history_bs"].pop(0)

                                period_tail = str(base_seq)[-3:].zfill(3)
                                next_seq = 1 if base_seq >= 1440 else base_seq + 1
                                next_tail = str(next_seq)[-3:].zfill(3)

                                # ၁။ Win / Loss အတိုကောက် စစ်ဆေးခြင်း
                                sn_pending = system_state["sniper_pending"]
                                if sn_pending and sn_pending["period"] == period_tail:
                                    is_win = (side_val == sn_pending["choice"])
                                    if is_win:
                                        system_state["sniper_win_streak"] += 1
                                        sniper_tracker["today_wins"] += 1
                                        sniper_tracker["alltime_wins"] += 1
                                        res_msg = f"🏆 WIN #{period_tail}: {num_val} [{side_val}] ✅ (W:{sniper_tracker['today_wins']} | L:{sniper_tracker['today_losses']})"
                                    else:
                                        system_state["sniper_win_streak"] = 0
                                        sniper_tracker["today_losses"] += 1
                                        sniper_tracker["alltime_losses"] += 1
                                        res_msg = f"🌧 LOSS #{period_tail}: {num_val} [{side_val}] ❌ (W:{sniper_tracker['today_wins']} | L:{sniper_tracker['today_losses']})"

                                    save_stats()
                                    try:
                                        await app.bot.send_message(chat_id=SNIPER_CHANNEL_ID, text=res_msg)
                                    except Exception:
                                        pass
                                    system_state["sniper_pending"] = None

                                # ၂။ Sniper Setup စစ်ဆေးပြီး Alert / Waiting အတိုသာ ပို့ခြင်း
                                sniper_choice, setup_status = evaluate_sniper_v2(system_state["history_bs"])

                                if sniper_choice:
                                    system_state["sniper_pending"] = {
                                        "period": next_tail,
                                        "choice": sniper_choice,
                                        "setup": setup_status
                                    }
                                    alert_msg = (
                                        f"🎯 **[SNIPER ALERT] #{next_tail}**\n"
                                        f"👉 **{sniper_choice} ထိုးရန်** 💎\n"
                                        f"📊 Setup: `{setup_status}`"
                                    )
                                    try:
                                        await app.bot.send_message(chat_id=SNIPER_CHANNEL_ID, text=alert_msg, parse_mode="Markdown")
                                    except Exception:
                                        pass
                                else:
                                    # ၂ ကြောင်းတည်းသော အလွန်တိုတောင်းသည့် Waiting Message
                                    short_wait = (
                                        f"⏳ **#{period_tail}:** {num_val} [{side_val}] (Block: `{curr_num}`)\n"
                                        f"🎯 **#{next_tail}:** စောင့်ကြည့်ဆဲ (W:{sniper_tracker['today_wins']} | L:{sniper_tracker['today_losses']})"
                                    )
                                    try:
                                        await app.bot.send_message(chat_id=SNIPER_CHANNEL_ID, text=short_wait, parse_mode="Markdown")
                                    except Exception:
                                        pass

            await asyncio.sleep(4)
        except Exception:
            await asyncio.sleep(4)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ADMIN_ID:
        return
    system_state["is_running"] = True
    await update.message.reply_text("🎯 **Sniper Bot Online!**")

async def post_init(application):
    asyncio.create_task(sniper_standalone_worker(application))

if __name__ == "__main__":
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    ping_thread = threading.Thread(target=self_ping_worker, daemon=True)
    ping_thread.start()

    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.run_polling(drop_pending_updates=True, close_loop=False)
