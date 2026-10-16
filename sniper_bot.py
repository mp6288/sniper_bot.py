import os
import time
import asyncio
import threading
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Bot

# --- Configuration (Channel ID & Token တိကျစွာ ထည့်သွင်းထားပါသည်) ---
BOT_TOKEN = "7547900898:AAFiF4E1w4Dq-x73F3W0y4JzB-hK7V4nQ8A"
CHANNEL_ID = "-1004325746548"
bot = Bot(token=BOT_TOKEN)

# --- Render Port Error ကို ဖြေရှင်းပေးမည့် Web Server ---
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

# --- Tracking State Variables ---
last_processed_block = None
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

def get_latest_tron_data():
    try:
        url = "https://apilist.tronscanapi.com/api/block?sort=-number&limit=1"
        res = requests.get(url, timeout=5).json()
        block_info = res['data'][0]
        block_num = block_info['number']
        block_hash = block_info['hash']
        
        last_digit = None
        for char in reversed(block_hash):
            if char.isdigit():
                last_digit = int(char)
                break
        
        result_type = "BIG" if last_digit >= 5 else "SMALL"
        return block_num, block_hash, last_digit, result_type
    except Exception as e:
        return None, None, None, None

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
    global last_processed_block, active_target_period, target_bet_side
    global total_signals, win_count, loss_count
    global current_streak_type, current_streak_count, max_win_streak, max_loss_streak

    print("🎯 Sniper Bot Engine V3.2 Online...", flush=True)

    while True:
        try:
            block_num, block_hash, num_val, side_val = get_latest_tron_data()

            if block_num and block_num != last_processed_block:
                last_processed_block = block_num
                current_period = (block_num % 1000)
                short_hash = f"**{block_hash[-4:]}" if block_hash else "N/A"

                # ==========================================
                # အဆင့် ၁: B/S ရလဒ်စာတို ပို့ဆောင်ခြင်း
                # ==========================================
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
                            f"🏆 WIN #{current_period:03d}: {num_val} [{side_val}] ✅ (Hash: {short_hash})\n"
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
                            f"❌ LOSS #{current_period:03d}: {num_val} [{side_val}] ❌ (Hash: {short_hash})\n"
                            f"🥺 Target Miss (W:{win_count} | L:{loss_count} | Total:{total_signals})\n"
                            f"⚡️ အရှုံးဆက်: {streak_text} (Max: {max_loss_streak})\n"
                            f"🤧 ကံမကောင်းပါ။\n"
                        )
                    active_target_period = None
                    target_bet_side = None
                else:
                    result_msg = f"⌛️ #{current_period:03d}: {num_val} {side_val} (Hash: {short_hash})\n"

                # History မှတ်တမ်းသွင်းခြင်း
                short_bs = "B" if side_val == "BIG" else "S"
                history_50_rounds.append(short_bs)
                if len(history_50_rounds) > 50:
                    history_50_rounds.pop(0)

                # ==========================================
                # အဆင့် ၂: Strategy စစ်ဆေးပြီး အောက်ကနေ တွဲဖက်ပို့ခြင်း
                # ==========================================
                next_period = (current_period + 1) % 1000
                sniper_signal, setup_name = check_sniper_strategy(history_50_rounds)

                if sniper_signal:
                    total_signals += 1
                    active_target_period = next_period
                    target_bet_side = sniper_signal

                    await bot.send_message(chat_id=CHANNEL_ID, text=result_msg)

                    alert_msg = (
                        f"🚨 Sniper Shot Alert 🚨\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"🗯 ပစ်မှတ်တွေ့ပီ\n"
                        f"🎯 Target Lock - #{next_period:03d}\n"
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
                        f"🎯 #{next_period:03d}: 👁️ စောင့်ကြည့်ဆဲ (W:{win_count} | L:{loss_count} | Total:{total_signals} | Streak:{streak_status})\n"
                        f"🔎 ပစ်မှတ်ကို ရှာဖွေနေသည်။"
                    )
                    await bot.send_message(chat_id=CHANNEL_ID, text=result_msg)

            await asyncio.sleep(2)

        except Exception as e:
            print(f"Loop Error: {e}", flush=True)
            await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(main_worker_loop())
