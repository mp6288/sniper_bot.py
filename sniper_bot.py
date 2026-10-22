import os
import json
import time
import asyncio
import threading
import urllib.request
import requests
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Bot

# ========================================================
# ၁။ CONFIGURATION (Token & Channel ID)
# ========================================================
BOT_TOKEN = "8923086070:AAFhc6g7npe9Cw9p1zKESXVRw8QN24y7CNo"
CHANNEL_ID = "-1004325746548"
STATE_FILE = "sniper_state.json"
bot = Bot(token=BOT_TOKEN)

# ========================================================
# ၂။ RENDER HEALTH CHECK SERVER (Port 10000)
# ========================================================
class SimpleHealth(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHealth)
    server.serve_forever()

threading.Thread(target=run_server, daemon=True).start()

# ========================================================
# ၃။ SELF-PING KEEP-ALIVE WORKER (Render အိပ်မပျော်စေမည့် စနစ်)
# ========================================================
def self_ping_worker():
    render_url = os.environ.get("RENDER_EXTERNAL_URL", "https://sniper-shot-v1.onrender.com")
    while True:
        try:
            time.sleep(300)
            req = urllib.request.Request(render_url, headers={"User-Agent": "SelfPingBot/1.0"})
            with urllib.request.urlopen(req, timeout=15) as response:
                pass
            print("🔔 Keep-Alive Ping Successful", flush=True)
        except Exception as e:
            print(f"Ping Error: {e}", flush=True)

threading.Thread(target=self_ping_worker, daemon=True).start()

# ========================================================
# ၄။ STATE MANAGEMENT (DATA PERSISTENCE စနစ် - စာရင်းမပျောက်စေရန်)
# ========================================================
default_state = {
    "total_signals": 0,
    "win_count": 0,
    "loss_count": 0,
    "current_streak_type": "W",
    "current_streak_count": 0,
    "max_win_streak": 0,
    "max_loss_streak": 0,
    "last_reset_date": "",
    "pattern_stats": {
        "B_Super_Pullback": {"name": "B-SuperTrend Strict Pullback", "total": 0, "win": 0, "loss": 0},
        "S_Super_Pullback": {"name": "S-SuperTrend Strict Pullback", "total": 0, "win": 0, "loss": 0}
    }
}

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Load state error: {e}", flush=True)
    return default_state.copy()

def save_state(s):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Save state error: {e}", flush=True)

state = load_state()

last_reported_block = None
last_reported_period = None
active_target_period = None
target_bet_side = None
active_setup_key = None
history_50_rounds = []

# ========================================================
# ၅။ ၆ထီ တိကျသော BLOCK & HASH ရယူခြင်း (:54 စက္ကန့် စနစ်)
# ========================================================
def fetch_exact_6lottery_block():
    """၆ထီ၏ Block time (:54 စက္ကန့်) တွင် ထွက်ပေါ်သော Block အစစ်အမှန်ကိုသာ ရယူခြင်း"""
    try:
        url = "https://apilist.tronscanapi.com/api/block?sort=-number&limit=25"
        res = requests.get(url, timeout=5).json()
        blocks = res.get('data', [])

        if not blocks:
            return None, None, None, None

        target_b = None
        for b in blocks:
            b_ts = b['timestamp'] / 1000.0
            dt = datetime.fromtimestamp(b_ts, tz=timezone.utc)
            if dt.second in (53, 54, 55):
                target_b = b
                break

        if not target_b:
            return None, None, None, None

        block_num = target_b['number']
        block_hash = target_b['hash']

        last_digit = None
        for char in reversed(block_hash):
            if char.isdigit():
                last_digit = int(char)
                break

        result_type = "BIG" if last_digit >= 5 else "SMALL"
        return block_num, block_hash, last_digit, result_type
    except Exception as e:
        print(f"Fetch Error: {e}", flush=True)
        return None, None, None, None

def prefill_history():
    """Bot စတင်ချိန်တွင် ပြီးခဲ့သော အလှည့် ၅၀ ကို ဒေတာ ဖြည့်သွင်းခြင်း"""
    global history_50_rounds
    try:
        url = "https://apilist.tronscanapi.com/api/block?sort=-number&limit=100"
        res = requests.get(url, timeout=10).json()
        blocks = res.get('data', [])
        
        matched = []
        for b in blocks:
            b_ts = b['timestamp'] / 1000.0
            dt = datetime.fromtimestamp(b_ts, tz=timezone.utc)
            if dt.second in (53, 54, 55):
                b_hash = b.get('hash', '')
                for char in reversed(b_hash):
                    if char.isdigit():
                        matched.append("B" if int(char) >= 5 else "S")
                        break
        matched.reverse()
        history_50_rounds = matched[-50:]
        print(f"✅ Pre-filled {len(history_50_rounds)} exact 6Lottery rounds into history!", flush=True)
    except Exception as e:
        print(f"Pre-fill Error: {e}", flush=True)

prefill_history()

# ========================================================
# ၆။ STRICT 2-STEP PULLBACK & LOSS SKIP STRATEGY
# ========================================================
def check_sniper_strategy(history):
    """
    အရှေ့တွင် မူလရေစီးရှိပြီးမှ အတိအကျ ၂ လုံးတည်း အနားယူကျဆင်းမှုကိုသာ ၁ ကြိမ် ပစ်ခတ်မည်။
    အကယ်၍ ၃ လုံးမြောက်၊ ၄ လုံးမြောက်ပါ ဆက်တိုက်လွဲပါက အလိုအလျောက် Skip လုပ်မည်။
    """
    if len(history) < 20:
        return None, None, None
    
    recent_50 = history[-50:]
    b_count = recent_50.count("B")
    s_count = recent_50.count("S")
    
    # Super Uptrend: B >= 30 ကြိမ် (၆၀%+)
    # အရှေ့တွင် BIG ရှိပြီးမှ အသေး အတိအကျ ၂ လုံးကျဆင်းခြင်း (B, S, S) ဖြစ်မှသာ BIG ထိုးမည်
    if b_count >= 30:
        if len(history) >= 3 and history[-3:] == ["B", "S", "S"]:
            return "BIG", "B-SuperTrend Strict Pullback 55.4%", "B_Super_Pullback"
            
    # Super Downtrend: S >= 30 ကြိမ် (၆၀%+)
    # အရှေ့တွင် SMALL ရှိပြီးမှ အကြီး အတိအကျ ၂ လုံးတက်ခြင်း (S, B, B) ဖြစ်မှသာ SMALL ထိုးမည်
    elif s_count >= 30:
        if len(history) >= 3 and history[-3:] == ["S", "B", "B"]:
            return "SMALL", "S-SuperTrend Strict Pullback 55.4%", "S_Super_Pullback"
            
    return None, None, None

async def main_worker_loop():
    global last_reported_block, last_reported_period, active_target_period, target_bet_side, active_setup_key, state

    print("🎯 Sniper Bot Strict Pullback with Persistent Daily Report Engine Online...", flush=True)

    while True:
        try:
            now_dt = datetime.fromtimestamp(time.time() + 6.5 * 3600, tz=timezone.utc)
            today_str = now_dt.strftime("%Y-%m-%d")

            # နေ့စဉ် မနက် ၆:၀၀ တိတိတွင် Daily Report ပို့ပြီး စာရင်းပြန်စခြင်း (Reset)
            if now_dt.hour == 6 and now_dt.minute == 0 and state.get("last_reset_date") != today_str:
                state["last_reset_date"] = today_str
                w_cnt = state.get("win_count", 0)
                l_cnt = state.get("loss_count", 0)
                tot_sig = state.get("total_signals", 0)
                total_played = w_cnt + l_cnt
                win_rate = (w_cnt / total_played * 100) if total_played > 0 else 0.0

                pattern_text = ""
                for k, v in state.get("pattern_stats", {}).items():
                    tot = v["total"]
                    w = v["win"]
                    l = v["loss"]
                    wr = (w / tot * 100) if tot > 0 else 0.0
                    pattern_text += f"• <b>{v['name']}</b>: {tot} ပွဲ ({w} နိုင် / {l} ရှုံး | WR: {wr:.2f}%)\n"

                report_msg = (
                    f"📊 <b>SNIPER SHOT V4.0 DAILY REPORT</b> 📊\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"📅 ရက်စွဲ: <b>{today_str}</b>\n"
                    f"🎰 ၆ထီ တစ်နေ့တာ Round ပေါင်း: <b>1,440 ပွဲ</b>\n"
                    f"🎯 Ultra-Sniper Signal ပေးခဲ့သောပွဲရေ: <b>{tot_sig} ပွဲ</b>\n"
                    f"🏆 အနိုင်ပွဲ: <b>{w_cnt}</b> | ❌ အရှုံးပွဲ: <b>{l_cnt}</b>\n"
                    f"📈 စုစုပေါင်း Win Rate: <b>{win_rate:.2f}%</b>\n"
                    f"🔥 Max Win Streak: <b>{state.get('max_win_streak', 0)} ပွဲဆက်</b>\n"
                    f"⚠️ Max Loss Streak: <b>{state.get('max_loss_streak', 0)} ပွဲဆက်</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"📈 <b>ULTRA-SNIPER SETUPS BREAKDOWN:</b>\n"
                    f"{pattern_text}"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔄 ယနေ့အတွက် စာရင်းအင်းများ (W:0 | L:0) ပြန်လည်စတင်ပါပြီ။"
                )
                try:
                    await bot.send_message(chat_id=CHANNEL_ID, text=report_msg, parse_mode="HTML")
                except Exception as e:
                    print(f"Report Send Error: {e}", flush=True)

                # Reset daily counters
                state["total_signals"] = 0
                state["win_count"] = 0
                state["loss_count"] = 0
                state["current_streak_count"] = 0
                state["max_win_streak"] = 0
                state["max_loss_streak"] = 0
                for k in state.get("pattern_stats", {}):
                    state["pattern_stats"][k]["total"] = 0
                    state["pattern_stats"][k]["win"] = 0
                    state["pattern_stats"][k]["loss"] = 0
                save_state(state)

            # ၆ထီ အလှည့်နံပါတ် တွက်ချက်ခြင်း
            total_minutes = now_dt.hour * 60 + now_dt.minute
            calc_p = (total_minutes - 390) % 1440
            expected_period = 1440 if calc_p == 0 else calc_p

            # ၆ထီ :54 စက္ကန့် Block ဖမ်းယူခြင်း
            block_num, block_hash, num_val, side_val = fetch_exact_6lottery_block()

            if block_num and block_num != last_reported_block and expected_period != last_reported_period:
                last_reported_block = block_num
                last_reported_period = expected_period
                current_period = expected_period
                short_hash = f"**{block_hash[-4:]}"

                # ၁။ ရလဒ်စာတို ထုတ်ပြန်ခြင်း
                if active_target_period == current_period:
                    is_win = (side_val == target_bet_side)
                    
                    pstats = state.get("pattern_stats", {})
                    if active_setup_key in pstats:
                        pstats[active_setup_key]["total"] += 1
                        if is_win:
                            pstats[active_setup_key]["win"] += 1
                        else:
                            pstats[active_setup_key]["loss"] += 1

                    if is_win:
                        state["win_count"] = state.get("win_count", 0) + 1
                        if state.get("current_streak_type") == "W":
                            state["current_streak_count"] = state.get("current_streak_count", 0) + 1
                        else:
                            state["current_streak_type"] = "W"
                            state["current_streak_count"] = 1
                        if state["current_streak_count"] > state.get("max_win_streak", 0):
                            state["max_win_streak"] = state["current_streak_count"]

                        streak_text = f"🔥 {state['current_streak_count']} ပွဲဆက်နိုင်"
                        result_msg = (
                            f"🎯 SNIPER SHOT SIGNAL 🎯\n"
                            f"🏆 WIN #{current_period:04d}: {num_val} [{side_val}] ✅ (Hash: {short_hash})\n"
                            f"🎉 Boom 🔥 (W:{state['win_count']} | L:{state['loss_count']} | Total:{state['total_signals']})\n"
                            f"⚡️ အနိုင်ဆက်: {streak_text} (Max: {state['max_win_streak']})\n"
                            f"🎯 Mission Complete.\n"
                            f"💰 ငွေထုတ်ပိုက်မယ်။\n"
                        )
                    else:
                        state["loss_count"] = state.get("loss_count", 0) + 1
                        if state.get("current_streak_type") == "L":
                            state["current_streak_count"] = state.get("current_streak_count", 0) + 1
                        else:
                            state["current_streak_type"] = "L"
                            state["current_streak_count"] = 1
                        if state["current_streak_count"] > state.get("max_loss_streak", 0):
                            state["max_loss_streak"] = state["current_streak_count"]

                        streak_text = f"⚠️ {state['current_streak_count']} ပွဲဆက်လွဲ"
                        result_msg = (
                            f"🎯 SNIPER SHOT SIGNAL 🎯\n"
                            f"❌ LOSS #{current_period:04d}: {num_val} [{side_val}] ❌ (Hash: {short_hash})\n"
                            f"🥺 Target Miss (W:{state['win_count']} | L:{state['loss_count']} | Total:{state['total_signals']})\n"
                            f"⚡️ အရှုံးဆက်: {streak_text} (Max: {state['max_loss_streak']})\n"
                            f"🤧 ကံမကောင်းပါ။\n"
                        )
                    save_state(state)
                    active_target_period = None
                    target_bet_side = None
                    active_setup_key = None
                else:
                    result_msg = (
                        f"🎯 SNIPER SHOT SIGNAL 🎯\n"
                        f"⌛️ #{current_period:04d}: {num_val} {side_val} (Hash: {short_hash})\n"
                    )

                # History မှတ်တမ်းသွင်းခြင်း
                short_bs = "B" if side_val == "BIG" else "S"
                history_50_rounds.append(short_bs)
                if len(history_50_rounds) > 50:
                    history_50_rounds.pop(0)

                # ၂။ Strict 2-Step Pullback Strategy စစ်ဆေးခြင်း
                next_p_calc = (current_period + 1) % 1440
                next_period = 1440 if next_p_calc == 0 else next_p_calc
                sniper_signal, setup_name, setup_key = check_sniper_strategy(history_50_rounds)

                if sniper_signal:
                    state["total_signals"] = state.get("total_signals", 0) + 1
                    save_state(state)
                    active_target_period = next_period
                    target_bet_side = sniper_signal
                    active_setup_key = setup_key

                    await bot.send_message(chat_id=CHANNEL_ID, text=result_msg)

                    alert_msg = (
                        f"🎯 SNIPER SHOT ALERT 🎯\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"🗯 ပစ်မှတ်တွေ့ပီ (Super Trend 60%+)\n"
                        f"🎯 Target Lock - #{next_period:04d}\n"
                        f"💣 {sniper_signal} ထိုးရန် ❗\n"
                        f"📊 Setup:\n{setup_name}\n"
                        f"📈 ယနေ့ Signal ပွဲစဉ်: #{state['total_signals']} ကြိမ်မြောက်\n"
                        f"Signal Power - High Precision Shot\n"
                        f"━━━━━━━━━━━━━━━━━━━━"
                    )
                    await bot.send_message(chat_id=CHANNEL_ID, text=alert_msg)
                else:
                    w_cnt = state.get("win_count", 0)
                    l_cnt = state.get("loss_count", 0)
                    tot_sig = state.get("total_signals", 0)
                    s_type = state.get("current_streak_type", "W")
                    s_cnt = state.get("current_streak_count", 0)
                    streak_status = f"{s_cnt}W" if s_type == "W" else f"{s_cnt}L"
                    result_msg += (
                        f"🎯 #{next_period:04d}: 👁️ စောင့်ကြည့်ဆဲ (W:{w_cnt} | L:{l_cnt} | Total:{tot_sig} | Streak:{streak_status})\n"
                        f"🔎 ပစ်မှတ်ကို ရှာဖွေနေသည်။"
                    )
                    await bot.send_message(chat_id=CHANNEL_ID, text=result_msg)

            await asyncio.sleep(1)

        except Exception as e:
            print(f"Loop Error: {e}", flush=True)
            await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(main_worker_loop())
