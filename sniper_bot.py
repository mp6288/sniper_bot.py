import os
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
# ၄။ STATE VARIABLES & COUNTERS
# ========================================================
last_processed_period = None
active_target_period = None
target_bet_side = None

total_signals = 0
win_count = 0
loss_count = 0
current_streak_type = "W"
current_streak_count = 0
max_win_streak = 0
max_loss_streak = 0

history_50_rounds = []

# ========================================================
# ၅။ ၆ထီ စက္ကန့် ၅၄ တိကျသော BLOCK ရယူခြင်းစနစ် (အမြဲမှန်စေမည့် Core)
# ========================================================
def get_6lottery_tron_data(target_unix_sec):
    """၆ထီ၏ Block time (:54) နှင့် ကွက်တိကျသော Tron Block ကို ရယူခြင်း"""
    try:
        url = "https://apilist.tronscanapi.com/api/block?sort=-number&limit=30"
        res = requests.get(url, timeout=5).json()
        blocks = res.get('data', [])

        if not blocks:
            return None, None, None, None

        # စက္ကန့် ၅၄ သို့မဟုတ် ၎င်းမတိုင်မီ နောက်ဆုံးထွက်ခဲ့သော Block ကို တိကျစွာ ရှာဖွေခြင်း
        target_ms = target_unix_sec * 1000
        best_block = None
        min_diff = float('inf')

        for b in blocks:
            b_ts = b['timestamp']
            # Target အချိန်နှင့် အနီးစပ်ဆုံး ကွာဟမှုအနည်းဆုံး block
            diff = abs(b_ts - target_ms)
            if diff < min_diff and b_ts <= target_ms + 1000:
                min_diff = diff
                best_block = b

        if not best_block:
            best_block = blocks[0]

        block_num = best_block['number']
        block_hash = best_block['hash']

        # ၆ထီ၏ သံမဏိစည်းမျဉ်းအတိုင်း Hash အဆုံး ဂဏန်းကို ရယူခြင်း
        last_digit = None
        for char in reversed(block_hash):
            if char.isdigit():
                last_digit = int(char)
                break

        result_type = "BIG" if last_digit >= 5 else "SMALL"
        return block_num, block_hash, last_digit, result_type
    except Exception as e:
        print(f"Tron Fetch Error: {e}", flush=True)
        return None, None, None, None

def prefill_history():
    """Bot စတင်သည်နှင့် ပြီးခဲ့သော အလှည့် ၅၀ ကို ကြိုဆွဲယူခြင်း"""
    global history_50_rounds
    try:
        url = "https://apilist.tronscanapi.com/api/block?sort=-number&limit=100"
        res = requests.get(url, timeout=10).json()
        blocks = res.get('data', [])
        
        # အလှည့် ၂၀ ခြားစီ ခွဲထုတ်ယူခြင်း
        sampled_blocks = blocks[::2][:50]
        sampled_blocks.reverse()
        
        history = []
        for b in sampled_blocks:
            b_hash = b['hash']
            for char in reversed(b_hash):
                if char.isdigit():
                    history.append("B" if int(char) >= 5 else "S")
                    break
        history_50_rounds = history
        print(f"✅ Pre-filled {len(history_50_rounds)} rounds into history!", flush=True)
    except Exception as e:
        print(f"Pre-fill Error: {e}", flush=True)

prefill_history()

def check_sniper_strategy(history):
    if len(history) < 15:
        return None, None
    
    recent_50 = history[-50:]
    b_count = recent_50.count("B")
    s_count = recent_50.count("S")
    
    # Uptrend Setup (B >= 28)
    if b_count >= 28:
        if len(history) >= 3 and history[-2:] == ["S", "S"]:
            return "BIG", "B-Trend Pullback Resumption 53.3%"
        if len(history) >= 4 and history[-4:] == ["B", "B", "B", "B"]:
            return "SMALL", "B-Trend Exhaustion Fade 50.6%"
            
    # Downtrend Setup (S >= 28)
    elif s_count >= 28:
        if len(history) >= 3 and history[-2:] == ["B", "B"]:
            return "SMALL", "S-Trend Pullback Resumption 52.0%"
        if len(history) >= 4 and history[-4:] == ["S", "S", "S", "S"]:
            return "BIG", "S-Trend Exhaustion Fade 50.6%"
            
    return None, None

async def main_worker_loop():
    global last_processed_period, active_target_period, target_bet_side
    global total_signals, win_count, loss_count
    global current_streak_type, current_streak_count, max_win_streak, max_loss_streak

    print("🎯 Sniper Bot Engine (Exact 6Lottery Timestamp Sync) Active...", flush=True)

    while True:
        try:
            now_ts = int(time.time())
            # မြန်မာစံတော်ချိန် (UTC+6:30) ဖြင့် အလှည့်နံပါတ် တွက်ချက်ခြင်း
            t = time.gmtime(now_ts + 6.5 * 3600)
            total_minutes = t.tm_hour * 60 + t.tm_min
            expected_period = (total_minutes - 390) % 1440

            # အလှည့်ပြီးဆုံးပြီး စက္ကန့် ၅၅ ကျော်သည်နှင့် တိကျသော Block ကို ဖမ်းယူမည်
            if expected_period != last_processed_period and t.tm_sec >= 55:
                # ထိုမိနစ်၏ စက္ကန့် ၅၄ သို့ ရောက်ရှိချိန် Unix timestamp
                target_sec = now_ts - (t.tm_sec - 54)
                block_num, block_hash, num_val, side_val = get_6lottery_tron_data(target_sec)

                if block_num:
                    last_processed_period = expected_period
                    current_period = expected_period
                    short_hash = f"**{block_hash[-4:]}" if block_hash else "N/A"

                    # ၁။ ရလဒ်စာတို ထုတ်ပြန်ခြင်း
                    if active_target_period == current_period:
                        if side_val == target_bet_side:
                            win_count += 1
                            if current_streak_type == "W":
                                current_streak_count += 1
                            else:
                                current_streak_type = "W"
                                current_streak_count = 1
                            if current_streak_count > max_win_streak:
                                max_win_streak = current_streak_count

                            streak_text = f"🔥 {current_streak_count} ပွဲဆက်နိုင်"
                            result_msg = (
                                f"🎯 SNIPER SHOT SIGNAL 🎯\n"
                                f"🏆 WIN #{current_period:04d}: {num_val} [{side_val}] ✅ (Hash: {short_hash})\n"
                                f"🎉 Boom 🔥 (W:{win_count} | L:{loss_count} | Total:{total_signals})\n"
                                f"⚡️ အနိုင်ဆက်: {streak_text} (Max: {max_win_streak})\n"
                                f"🎯 Mission Complete.\n"
                                f"💰 ငွေထုတ်ပိုက်မယ်။\n"
                            )
                        else:
                            loss_count += 1
                            if current_streak_type == "L":
                                current_streak_count += 1
                            else:
                                current_streak_type = "L"
                                current_streak_count = 1
                            if current_streak_count > max_loss_streak:
                                max_loss_streak = current_streak_count

                            streak_text = f"⚠️ {current_streak_count} ပွဲဆက်လွဲ"
                            result_msg = (
                                f"🎯 SNIPER SHOT SIGNAL 🎯\n"
                                f"❌ LOSS #{current_period:04d}: {num_val} [{side_val}] ❌ (Hash: {short_hash})\n"
                                f"🥺 Target Miss (W:{win_count} | L:{loss_count} | Total:{total_signals})\n"
                                f"⚡️ အရှုံးဆက်: {streak_text} (Max: {max_loss_streak})\n"
                                f"🤧 ကံမကောင်းပါ။\n"
                            )
                        active_target_period = None
                        target_bet_side = None
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

                    # ၂။ နောက်တစ်ပွဲအတွက် Strategy စစ်ဆေးခြင်း
                    next_period = (current_period + 1) % 1440
                    sniper_signal, setup_name = check_sniper_strategy(history_50_rounds)

                    if sniper_signal:
                        total_signals += 1
                        active_target_period = next_period
                        target_bet_side = sniper_signal

                        await bot.send_message(chat_id=CHANNEL_ID, text=result_msg)

                        alert_msg = (
                            f"🎯 SNIPER SHOT ALERT 🎯\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"🗯 ပစ်မှတ်တွေ့ပီ\n"
                            f"🎯 Target Lock - #{next_period:04d}\n"
                            f"💣 {sniper_signal} ထိုးရန် ❗\n"
                            f"📊 Setup:\n{setup_name}\n"
                            f"📈 ယနေ့ Signal ပွဲစဉ်: #{total_signals} ကြိမ်မြောက်\n"
                            f"Signal Power - Head Shot\n"
                            f"━━━━━━━━━━━━━━━━━━━━"
                        )
                        await bot.send_message(chat_id=CHANNEL_ID, text=alert_msg)
                    else:
                        streak_status = f"{current_streak_count}W" if current_streak_type == "W" else f"{current_streak_count}L"
                        result_msg += (
                            f"🎯 #{next_period:04d}: 👁️ စောင့်ကြည့်ဆဲ (W:{win_count} | L:{loss_count} | Total:{total_signals} | Streak:{streak_status})\n"
                            f"🔎 ပစ်မှတ်ကို ရှာဖွေနေသည်။"
                        )
                        await bot.send_message(chat_id=CHANNEL_ID, text=result_msg)

            await asyncio.sleep(0.5)

        except Exception as e:
            print(f"Loop Error: {e}", flush=True)
            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main_worker_loop())
