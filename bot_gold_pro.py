from datetime import datetime
import threading
from telebot.types import BotCommand, InlineKeyboardMarkup, InlineKeyboardButton
import telebot
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import time
import json
import os
import logging

# Cấu hình Logging
logging.basicConfig(
    filename='bot_activity.log',
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# ==========================================
# 1. CẤU HÌNH (User tự điền)
# ==========================================
API_TOKEN = "8288173761:AAEhh0Km0LVNZIel15flHEGGh3ixY-4v0Nw"
CHAT_ID = '1622117094'
SYMBOL = 'GC=F'  # Vàng (Gold Futures)
INTERVAL = '15m'
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

# Lưu trạng thái tín hiệu gần nhất
last_signal = None  # 'BUY', 'SELL', hoặc None

# Khởi tạo Bot
bot = telebot.TeleBot(API_TOKEN)

# ==========================================
# 2. LOGIC TÍNH TOÁN & FORMAT TIN NHẮN
# ==========================================
def format_message(signal_type, price, prev_price):
    if signal_type == 'MUA':
        tp = price * (1 + 0.005)
        sl = price * (1 - 0.003)
    else:  # BÁN
        tp = price * (1 - 0.005)
        sl = price * (1 + 0.003)
    
    pct_price_change = ((price - prev_price) / prev_price) * 100
    current_time = datetime.now().strftime("%H:%M:%S %d/%m")
    
    return (
        f"🏆 **GOLD SIGNAL** | {current_time} |\n"
        f"| Signal: {signal_type} | Price: {price:.1f} |\n"
        f"| TP: {tp:.1f} | SL: {sl:.1f} |\n"
        f"| Change: {pct_price_change:+.2f}% |"
    )

def fetch_and_analyze():
    global last_signal
    try:
        df = yf.download(tickers=SYMBOL, period='5d', interval=INTERVAL, progress=False)
        if df.empty or len(df) < RSI_PERIOD + 2:
            print("⏳ Dữ liệu Gold chưa sẵn sàng...")
            return

        try:
            close = df['Close']
            if isinstance(close, pd.DataFrame): close = close.iloc[:, 0]
        except: return

        rsi = ta.rsi(close, length=RSI_PERIOD)
        current_rsi = rsi.iloc[-2]
        current_price = close.iloc[-2]
        prev_price = close.iloc[-3]
        timestamp = df.index[-2]
        
        print(f"⏰ {timestamp} | Price: {current_price:.2f} | RSI: {current_rsi:.2f}")

        # Logic Tín hiệu
        signal_type = None
        if current_rsi < RSI_OVERSOLD: signal_type = 'MUA'
        elif current_rsi > RSI_OVERBOUGHT: signal_type = 'BÁN'
            
        if signal_type and signal_type != last_signal:
            print(f"🚀 PHÁT HIỆN TÍN HIỆU: {signal_type}")
            logging.info(f"GOLD_SIGNAL: {signal_type} | Price: {current_price} | RSI: {current_rsi}")
            
            msg = format_message(signal_type, current_price, prev_price)
            try:
                bot.send_message(CHAT_ID, msg, parse_mode='Markdown')
                print("✅ Đã gửi tin nhắn Telegram thành công!")
                last_signal = signal_type
            except Exception as e:
                print(f"❌ Lỗi gửi Telegram: {e}")
                
        if 35 < current_rsi < 65:
            last_signal = None
            
    except Exception as e:
        print(f"❌ Lỗi phân tích Gold: {e}")

# ==========================================
# 3. COMMAND HANDLERS
# ==========================================
def get_main_menu():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("💰 Check Vàng", callback_data="check_gold"))
    return markup

@bot.message_handler(commands=['start', 'help', 'menu'])
def send_welcome(message):
    welcome_msg = "🤖 **GOLD BOT PRO** 🤖\nBot chuyên tín hiệu Vàng (RSI)."
    bot.reply_to(message, welcome_msg, parse_mode='Markdown', reply_markup=get_main_menu())

@bot.callback_query_handler(func=lambda call: call.data == "check_gold")
def callback_check_gold(call):
    do_check_gold(call.message)

@bot.message_handler(commands=['pricegold', 'gold', 'price'])
def check_price_command(message):
    do_check_gold(message)

def do_check_gold(message):
    try:
        msg_wait = bot.reply_to(message, "⏳ Đang lấy giá Vàng...")
        df = yf.download(tickers=SYMBOL, period='5d', interval=INTERVAL, progress=False)
        
        if df.empty:
            bot.edit_message_text("❌ Lỗi dữ liệu Gold.", chat_id=message.chat.id, message_id=msg_wait.message_id)
            return

        try:
            close = df['Close']
            if isinstance(close, pd.DataFrame): close = close.iloc[:, 0]
        except: return

        rsi = ta.rsi(close, length=RSI_PERIOD)
        current_price = close.iloc[-1]
        current_rsi = rsi.iloc[-1]
        
        rsi_status = "Trung tính 😐"
        if current_rsi > RSI_OVERBOUGHT: rsi_status = "QUÁ MUA 🔴"
        elif current_rsi < RSI_OVERSOLD: rsi_status = "QUÁ BÁN 🟢"
        
        reply_msg = (
            f"💰 **GOLD UPDATE** 💰\n"
            f"Price: `{current_price:.2f}`\n"
            f"RSI: `{current_rsi:.2f}` ({rsi_status})\n"
            f"Time: `{datetime.now().strftime('%H:%M %d/%m')}`"
        )
        
        bot.delete_message(chat_id=message.chat.id, message_id=msg_wait.message_id)
        bot.send_message(message.chat.id, reply_msg, parse_mode='Markdown')
        
    except Exception as e:
        print(f"Lỗi Gold: {e}")

# ==========================================
# 4. THREAD & MAIN
# ==========================================
def run_alert_schedule():
    print("⏰ Gold Alert Thread Started...")
    while True:
        try:
            fetch_and_analyze()
            time.sleep(60) 
        except Exception as e:
            print(f"⚠️ Gold Thread Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    print("🤖 Bot Gold Pro (Lite) đang chạy... (Ctrl+C để dừng)")
    print(f"Theo dõi: {SYMBOL} | Khung: {INTERVAL}")
    
    try:
        commands = [
            BotCommand("pricegold", "💰 Xem giá Vàng"),
            BotCommand("start", "🚀 Menu")
        ]
        bot.set_my_commands(commands)
    except: pass

    # Thread quét tín hiệu tự động
    t1 = threading.Thread(target=run_alert_schedule)
    t1.daemon = True
    t1.start()
    
    bot.infinity_polling()
