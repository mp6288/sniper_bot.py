import os
import time
import asyncio
import requests
from telegram import Bot

# --- Configuration ---
BOT_TOKEN = "7547900898:AAFiF4E1w4Dq-x73F3W0y4JzB-hK7V4nQ8A"  # မိမိ Sniper Bot Token
CHANNEL_ID = "-1002345678901"                                # မိမိ Sniper Channel ID
bot = Bot(token=BOT_TOKEN)

# --- Tracking State Variables (စာရင်းအင်း မှတ်တမ်းများ) ---
last_processed_block = None
active_target_period = None
target_bet_side = None

# Stats
total_signals = 19       # လက်ရှိ Screenshot အထိ Signal ထွက်ခဲ့သော စုစုပေါင်း ပွဲရေ
win_count = 11           # စုစုပေါင်း နိုင်ပွဲ
loss_count = 8           # စုစုပေါင်း ရှုံးပွဲ
current_streak_type = "L"  # "W" သို့မဟုတ် "L"
current_streak_count = 1   # လက်ရှိ ဆက်တိုက် ဖြစ်နေသော ပွဲရေ
max_win_streak = 4       # အများဆုံး ဆက်တိုက်နိုင်ခဲ့သည့် စံချိန်
max_loss_streak = 2      # အများဆုံး ဆက်တိုက်ရှုံးခဲ့သည့် စံချိန်

history_50_rounds = []   # Window 50 Strategy အတွက်

def get_latest_tron_data():
    try:
        url = "https://apilist.tronscanapi.com/api/block?sort=-number&limit=1"
        res = requests.get(url, timeout=5).json()
        block_info = res['data'][0]
        block_num = block_info['number']
        block_hash = block_info['hash']
        
        # Last digit logic
        last_digit = None
        for char in reversed(block_hash):
            if char.isdigit():
                last_digit = int(char)
                break
        
        result_type = "BIG" if last_digit >= 5 else "SMALL"
        return block_num, block_hash, last_digit, result_type
    except Exception as e:
        return None, None, None, None

# (လက်ရှိ sniper_bot.py ထဲက check_sniper_strategy function ကို မူလအတိုင်း မပြောင်းဘဲ ထားပါ)

async def main_worker_loop():
    global last_processed_block, active_target_period, target_bet_side
    global total_signals, win_count, loss_count
    global current_streak_type, current_streak_count, max_win_streak, max_loss_streak

    print("🎯 Sniper Bot Engine V3.2 Active...")

    while True:
        try:
            block_num, block_hash, num_val, side_val = get_latest_tron_data()

            if block_num and block_num != last_processed_block:
                last_processed_block = block_num
                current_period = (block_num % 1000)

                # ၆ထီ Hash နှင့် တိုက်စစ်ရန် Hash အဆုံးပိုင်း ၅ လုံး (သို့မဟုတ် အပြည့်အစုံ) ယူခြင်း
                short_hash = f"...{block_hash[-5:]}" if block_hash else "N/A"

                # ==========================================
                # အဆင့် (၁): Block အလိုက် B/S ရလဒ်စာတို ပို့ဆောင်ခြင်း
                # ==========================================
                if active_target_period == current_period:
                    # Signal အလှည့်ဖြစ်ပါက အနိုင်/အရှုံး စစ်ဆေးပြီး Streak တွက်ချက်ခြင်း
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
                            f"⚡️ ဆက်တိုက်အနိုင်: {streak_text} (Max: {max_win_streak})\n"
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
                            f"⚡️ ဆက်တိုက်အရှုံး: {streak_text} (Max: {max_loss_streak})\n"
                            f"🤧 ကံမကောင်းပါ။\n"
                        )
                    active_target_period = None
                    target_bet_side = None
                else:
                    # သာမန် ပုံမှန်အလှည့် ရလဒ်စာတို
                    result_msg = f"⌛️ #{current_period:03d}: {num_val} {side_val} (Hash: {short_hash})\n"

                # History စာရင်းသွင်းခြင်း
                short_bs = "B" if side_val == "BIG" else "S"
                history_50_rounds.append(short_bs)
                if len(history_50_rounds) > 50:
                    history_50_rounds.pop(0)

                # ==========================================
                # အဆင့် (၂): နောက်တစ်ပွဲအတွက် Strategy စစ်ဆေးခြင်း
                # ==========================================
                next_period = (current_period + 1) % 1000
                sniper_signal, setup_name = check_sniper_strategy(history_50_rounds)

                if sniper_signal:
                    total_signals += 1
                    active_target_period = next_period
                    target_bet_side = sniper_signal

                    # အရင် Block ရလဒ်စာတိုကို အရင်ဆုံး ပို့မည်
                    await bot.send_message(chat_id=CHANNEL_ID, text=result_msg)

                    # Signal Alert ကို အောက်ကနေ သီးသန့် ခွဲထုတ်ပို့မည်
                    alert_msg = (
                        f"🚨 Sniper Shot Alert 🚨\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"🗯 ပစ်မှတ်တွေ့ပီ\n"
                        f"🎯 Target Lock - #{next_period:03d}\n"
                        f"💣 {sniper_signal} ထိုးရန် ❗\n"
                        f"📊 Setup: {setup_name}\n"
                        f"📈 ယနေ့ Signal ပွဲစဉ်: #{total_signals} ကြိမ်မြောက်\n"
                        f"Signal Power - Head Shot\n"
                        f"━━━━━━━━━━━━━━━━━━━━"
                    )
                    await bot.send_message(chat_id=CHANNEL_ID, text=alert_msg)
                else:
                    # Signal မရှိပါက မျက်လုံးပုံ (👁️) ဖြင့် စောင့်ကြည့်စာသား ပေါင်းစပ်ပို့မည်
                    streak_status = f"{current_streak_count}W" if current_streak_type == "W" else f"{current_streak_count}L"
                    result_msg += (
                        f"🎯 #{next_period:03d}: 👁️ စောင့်ကြည့်ဆဲ (W:{win_count} | L:{loss_count} | Total:{total_signals} | Streak:{streak_status})\n"
                        f"🔎 ပစ်မှတ်ကို ရှာဖွေနေသည်။"
                    )
                    await bot.send_message(chat_id=CHANNEL_ID, text=result_msg)

            await asyncio.sleep(2)  # Block မလွတ်စေရန် ၂ စက္ကန့်တိုင်း မပြတ်စစ်ဆေးခြင်း

        except Exception as e:
            print(f"Loop Error: {e}")
            await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(main_worker_loop())
