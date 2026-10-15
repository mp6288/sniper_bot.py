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
    except Exception as e:
        print(f"Error saving stats: {e}")

sniper_tracker = load_stats()

system_state = {
    "is_running": True,
    "last_reported_block": 0,
    "last_reported_period": 0,
    "history_bs": [],
    "target_modulo": 4,
    "sniper_pending": None,
    "sniper_win_streak": 0
}

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"SNIPER STANDALONE LIVE")
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
            req = urllib.request.Request(target, headers={"User-Agent": "SniperStandalone/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                pass
        except Exception:
            pass
        threading.Event().wait(300)

def fetch_exact_6lottery_block():
    url = "https://apilist.tronscanapi.com/api/block?sort=-number&limit=15"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            for item in res_data.get("data", []):
                num = item.get("number", 0)
                hash_val = item.get("hash", "")
                if num > 0 and (num % 20 == system_state["target_modulo"]):
                    return num, hash_val
    except Exception as e:
        print(f"TronScan fetch error: {e}")
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
        return None, "အချက်အလက် စုဆောင်းဆဲ (Warming Up)"

    last_5 = "".join(history[-5:])
    last_6 = "".join(history[-6:])
    macro_50 = history[-50:] if len(history) >= 50 else history
    b_count = macro_50.count("B")
    s_count = macro_50.count("S")

    # Setup 1: Macro-Filtered Exhaustion Fade
    if last_5 == "SSSSS" and s_count >= 26:
        return "BIG", "⚡️ Macro Exhaustion Fade (5S ➡️ BIG Reversal)"
    elif last_5 == "BBBBB" and b_count >= 26:
        return "SMALL", "⚡️ Macro Exhaustion Fade (5B ➡️ SMALL Reversal)"

    # Setup 2: Deep Pullback in Strong Trend
    if len(macro_50) >= 20:
        if s_count >= 28 and last_5 == "SSSBB":
            return "SMALL", "📉 Macro Downtrend Pullback (SSSBB ➡️ SMALL)"
        elif b_count >= 28 and last_5 == "BBBSS":
            return "BIG", "📈 Macro Uptrend Pullback (BBBSS ➡️ BIG)"

    # Setup 3: High Win-Rate Fake Pullback Continuation
    if last_5 == "SSBSS":
        return "SMALL", "🎯 Trend Continuation (SSBSS ➡️ SMALL)"

    # Setup 4: Symmetry Balance Retest
    if last_6 == "BBBSSS":
        return "BIG", "⚖️ Symmetry Balance (BBB-SSS ➡️ BIG)"

    return None, f"လက်ရှိပုံစံ ({last_5}) - Sniper Pattern စောင့်ဆိုင်းနေပါသည်"

async def sniper_standalone_worker(app):
    await asyncio.sleep(2)
    try:
        await app.bot.send_message(
            chat_id=SNIPER_CHANNEL_ID,
            text="🎯 **Sniper Shot Standalone Engine Online!**\nသီးခြားလွတ်လပ်စွာ ၂၄ နာရီ စောင့်ကြည့်နေပါသည်..."
        )
    except Exception:
        pass

    while True:
        try:
            if system_state["is_running"]:
                tz_mm = timezone(timedelta(hours=6, minutes=30))
                now = datetime.now(tz_mm)
                today_str = now.strftime("%Y-%m-%d")

                if sniper_tracker["current_date"] != today_str and now.hour == 6 and now.minute == 0:
                    sniper_tracker["current_date"] = today_str
                    sniper_tracker["today_wins"] = 0
                    sniper_tracker["today_losses"] = 0
                    save_stats()

                total_minutes = now.hour * 60 + now.minute
                base_seq = (total_minutes - 389) % 1440
                if base_seq <= 0:
                    base_seq += 1440

                curr_num, curr_hash = fetch_exact_6lottery_block()

                if curr_num > 0 and curr_num != system_state["last_reported_block"]:
                    num_val, side_val = parse_trx_hash(curr_hash)

                    if num_val is not None:
                        if base_seq != system_state["last_reported_period"]:
                            system_state["last_reported_block"] = curr_num
                            system_state["last_reported_period"] = base_seq

                            short_code = "B" if side_val == "BIG" else "S"
                            system_state["history_bs"].append(short_code)
                            if len(system_state["history_bs"]) > 300:
                                system_state["history_bs"].pop(0)

                            period_tail = str(base_seq)[-3:].zfill(3)
                            next_seq = 1 if base_seq >= 1440 else base_seq + 1
                            next_tail = str(next_seq)[-3:].zfill(3)

                            sn_pending = system_state["sniper_pending"]
                            if sn_pending and sn_pending["period"] == period_tail:
                                is_win = (side_val == sn_pending["choice"])
                                if is_win:
                                    system_state["sniper_win_streak"] += 1
                                    sniper_tracker["today_wins"] += 1
                                    sniper_tracker["alltime_wins"] += 1
                                    status_header = f"🏆 ⚡️ SNIPER WIN {system_state['sniper_win_streak']} ⚡️ 🏆"
                                    result_sym = f"**{num_val} [{side_val}]** ✅"
                                else:
                                    system_state["sniper_win_streak"] = 0
                                    sniper_tracker["today_losses"] += 1
                                    sniper_tracker["alltime_losses"] += 1
                                    status_header = "🌧 ❌ SNIPER LOSS ❌ 🌧"
                                    result_sym = f"**{num_val} [{side_val}]** ❌"

                                save_stats()

                                t_tot = sniper_tracker["today_wins"] + sniper_tracker["today_losses"]
                                t_rate = (sniper_tracker["today_wins"] / t_tot * 100) if t_tot > 0 else 0
                                a_tot = sniper_tracker["alltime_wins"] + sniper_tracker["alltime_losses"]
                                a_rate = (sniper_tracker["alltime_wins"] / a_tot * 100) if a_tot > 0 else 0

                                sn_feedback_msg = (
                                    f"{status_header}\n"
                                    f"━━━━━━━━━━━━━━━━━━\n"
                                    f"• **အလှည့်:** `#{period_tail}` | **ရလဒ်:** {result_sym}\n\n"
                                    f"📅 **ယနေ့ စာရင်း (Today Stats):**\n"
                                    f"• နိုင်: `{sniper_tracker['today_wins']}` | ရှုံး: `{sniper_tracker['today_losses']}` (Win Rate: `{t_rate:.1f}%`)\n\n"
                                    f"🌐 **စတင်ချိန်မှ စုစုပေါင်း (All-Time Stats):**\n"
                                    f"• နိုင်: `{sniper_tracker['alltime_wins']}` | ရှုံး: `{sniper_tracker['alltime_losses']}` (Win Rate: `{a_rate:.1f}%`)\n"
                                    f"━━━━━━━━━━━━━━━━━━"
                                )
                                try:
                                    await app.bot.send_message(chat_id=SNIPER_CHANNEL_ID, text=sn_feedback_msg, parse_mode="Markdown")
                                except Exception:
                                    pass
                                system_state["sniper_pending"] = None

                            sniper_choice, setup_status = evaluate_sniper_v2(system_state["history_bs"])

                            if sniper_choice:
                                system_state["sniper_pending"] = {
                                    "period": next_tail,
                                    "choice": sniper_choice,
                                    "setup": setup_status
                                }
                                sniper_alert_msg = (
                                    f"🎯 **[SNIPER SHOT ENTRY ALERT]** 🎯\n"
                                    f"━━━━━━━━━━━━━━━━━━\n"
                                    f"🔹 **Trx {next_tail} မှာ {sniper_choice} ထိုးရန်** 💎\n"
                                    f"📊 **Setup:** `{setup_status}`\n"
                                    f"━━━━━━━━━━━━━━━━━━"
                                )
                                try:
                                    await app.bot.send_message(chat_id=SNIPER_CHANNEL_ID, text=sniper_alert_msg, parse_mode="Markdown")
                                except Exception:
                                    pass
                            else:
                                t_tot = sniper_tracker["today_wins"] + sniper_tracker["today_losses"]
                                t_rate = (sniper_tracker["today_wins"] / t_tot * 100) if t_tot > 0 else 0
                                sniper_wait_msg = (
                                    f"⏳ **[SNIPER STATUS - WAITING]** ⏳\n"
                                    f"• ပြီးဆုံးသည့် အလှည့်: #{period_tail} ရလဒ်: **{num_val} [{side_val}]**\n"
                                    f"• အခြေအနေ: `{setup_status}`\n"
                                    f"• စာရင်း: ယနေ့ နိုင် {sniper_tracker['today_wins']}/ရှုံး {sniper_tracker['today_losses']} ({t_rate:.1f}%) | All-Time: {sniper_tracker['alltime_wins']}W-{sniper_tracker['alltime_losses']}L\n"
                                    f"• နောက်အလှည့်: #{next_tail} စောင့်ကြည့်ဆဲ (No Entry)..."
                                )
                                try:
                                    await app.bot.send_message(chat_id=SNIPER_CHANNEL_ID, text=sniper_wait_msg)
                                except Exception:
                                    pass

            await asyncio.sleep(4)
        except Exception:
            await asyncio.sleep(4)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ADMIN_ID:
        return
    system_state["is_running"] = True
    await update.message.reply_text("🎯 **Sniper Shot Standalone Bot Online!**")

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
