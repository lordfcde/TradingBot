# main.py
import telebot
from telebot import types
import config
import logging
import threading
import time
from datetime import datetime
import os

# Services
from services.dnse_service import DNSEService
from services.vnstock_service import VnstockService
from services.gold_service import GoldService
from services.shark_hunter_service import SharkHunterService
from services.watchlist_service import WatchlistService
from services.trinity_monitor import TrinitySignalMonitor
from services.analyzer import TrinityAnalyzer

# Handlers
from handlers.stock_handler import handle_stock_price, handle_gold_price, handle_market_overview, handle_stock_search_request, handle_show_watchlist
from handlers.menu_handler import send_welcome, handle_help, handle_contact, handle_vn_stock, handle_back_main, create_main_menu, handle_shark_menu

# ==========================================
# 1. SETUP LOGGING & BOT
# ==========================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot_run.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("SmartTradeBot")

try:
    bot = telebot.TeleBot(config.API_TOKEN)
    logger.info("✅ Bot initializing...")
    
    # Initialize Services
    dnse_service = DNSEService()
    gold_service = GoldService()
    vnstock_service = VnstockService()
    watchlist_viewer = WatchlistService()
    
    # Shark & Trinity Setup
    shark_service = SharkHunterService(bot, vnstock_service)
    trinity_monitor = TrinitySignalMonitor(bot, vnstock_service, watchlist_viewer)
    
    # Link them
    trinity_monitor.set_chat_id(shark_service.alert_chat_id)
    shark_service.set_trinity_monitor(trinity_monitor)
    
    analyzer = TrinityAnalyzer()
    shark_service.set_analyzer(analyzer)
    
    # Register Streams
    if shark_service.alert_chat_id:
        dnse_service.register_shark_streams(
            ohlc_cb=shark_service.process_ohlc,
            tick_cb=shark_service.process_tick
        )

except Exception as e:
    logger.error(f"❌ Init Error: {e}")
    exit(1)

# ==========================================
# 2. SCHEDULER & SESSION LOGIC
# ==========================================
class BotScheduler:
    def __init__(self, dnse, shark, trinity):
        self.dnse = dnse
        self.shark = shark
        self.trinity = trinity
        self.current_state = "INIT"
        
    def start_morning_session(self):
        if self.current_state == "MORNING": return
        logger.info("🌅 STARTING MORNING SESSION (08:50 - 11:30)")
        
        # 1. Connect MQTT if down
        if not self.dnse.client or not self.dnse.client.is_connected():
            logger.info("🔌 Connecting DNSE MQTT...")
            if self.dnse.connect():
                self.dnse.subscribe_all_markets()
                logger.info("✅ MQTT Connected & Subscribed.")
        
        # 2. Start Trinity Monitor
        if self.shark.alert_chat_id and not self.trinity.is_monitoring:
            self.trinity.start_monitoring(self.shark.alert_chat_id)
            
        self.current_state = "MORNING"

    def midday_reset(self):
        if self.current_state == "LUNCH": return
        logger.info("🍱 MIDDAY RESET (11:30 - 13:00)")
        
        # 1. Disconnect MQTT to save resources
        if self.dnse.client and self.dnse.client.is_connected():
            logger.info("🔌 Disconnecting MQTT for Lunch...")
            self.dnse.client.disconnect()
            
        # 2. Stop Trinity
        # self.trinity.stop_monitoring() # Optionally keep running if 1H logic needs it, but usually stops
        
        # 3. Clear Caches for Afternoon Fresh Start
        logger.info("🧹 Clearing Alert History (Session Reset)...")
        self.shark.alert_history.clear() 
        self.shark.shark_stats.clear() # Optional: keep stats or clear? User said "báo lại từ đầu" implies alerts reset.
        # usually we clear alert_history (cooldowns) but keep stats (total value). 
        # But user said "báo lại từ đầu" -> clear 'alerted_symbols' logic.
        
        # Filter Watchlist (Liquidity check)
        self.shark.watchlist_service.filter_by_liquidity(min_avg_volume=100000)
        
        self.current_state = "LUNCH"

    def start_afternoon_session(self):
        if self.current_state == "AFTERNOON": return
        logger.info("☀️ STARTING AFTERNOON SESSION (13:00 - 15:05)")
        
        # 1. Reconnect MQTT
        if not self.dnse.client or not self.dnse.client.is_connected():
            logger.info("🔌 Reconnecting MQTT...")
            if self.dnse.connect():
                self.dnse.subscribe_all_markets()
                logger.info("✅ MQTT Reconnected.")
                
        # 2. Resume Trinity
        if self.shark.alert_chat_id and not self.trinity.is_monitoring:
            self.trinity.start_monitoring(self.shark.alert_chat_id)
            
        self.current_state = "AFTERNOON"

    def sleep_mode(self):
        if self.current_state == "SLEEP": 
            # Heartbeat log every 30 mins
            if time.time() % 1800 < 60: logger.info("💤 Bot Sleeping... (Market Closed)")
            return
            
        logger.info("🌙 MARKET CLOSED. SLEEP MODE.")
        
        if self.dnse.client and self.dnse.client.is_connected():
            self.dnse.client.disconnect()
            
        self.trinity.stop_monitoring()
        self.current_state = "SLEEP"

    def run_schedule(self):
        """Infinite Loop for Schedule Management"""
        logger.info("⏳ Scheduler Started...")
        while True:
            try:
                now = datetime.now()
                tick = now.strftime("%H:%M")
                weekday = now.weekday() # 0=Mon, 4=Fri
                
                # Weekend Check
                if weekday > 4:
                    self.sleep_mode()
                    time.sleep(60)
                    continue
                
                # Time Slots
                if "08:50" <= tick < "11:30":
                    self.start_morning_session()
                elif "11:30" <= tick < "13:00":
                    self.midday_reset()
                elif "13:00" <= tick < "15:05":
                    self.start_afternoon_session()
                else:
                    self.sleep_mode()
                    
                time.sleep(60) # Check every minute
                
            except Exception as e:
                logger.error(f"⚠️ Scheduler Error: {e}")
                time.sleep(60)

# Instantiate Scheduler
scheduler = BotScheduler(dnse_service, shark_service, trinity_monitor)

# ==========================================
# 3. COMMAND HANDLERS
# ==========================================
@bot.message_handler(commands=['start'])
def on_start(message):
    send_welcome(bot, message)

@bot.message_handler(commands=['help'])
def on_help(message):
    handle_help(bot, message)

@bot.message_handler(commands=['stock'])
def on_stock(message):
    handle_stock_price(bot, message, dnse_service, shark_service, vnstock_service, trinity_monitor)

@bot.message_handler(commands=['shark_on'])
def on_shark_on(message):
    chat_id = message.chat.id
    shark_service.enable_alerts(chat_id)
    # Manual trigger if inside session
    scheduler.start_morning_session() # Force connect check
    bot.reply_to(message, "🦈 **Shark Hunter & Trinity ON!**\nBot sẽ tự động chạy theo lịch trình:\n- Sáng: 08:50 - 11:30\n- Chiều: 13:00 - 15:05", parse_mode='Markdown')

@bot.message_handler(commands=['trinity_test'])
def on_trinity_test(message):
    chat_id = message.chat.id
    trinity_monitor.set_chat_id(chat_id)
    trinity_monitor.send_test_alert("TEST_STOCK")

# Callback & Text Handlers
@bot.callback_query_handler(func=lambda call: call.data.startswith('watchlist_'))
def watchlist_callback(call):
    from handlers.stock_handler import show_watchlist_view, show_top_symbols, show_today_buy_signals
    if call.data == 'watchlist_view': show_watchlist_view(bot, call, watchlist_viewer)
    elif call.data == 'watchlist_top': show_top_symbols(bot, call)
    elif call.data == 'watchlist_today': show_today_buy_signals(bot, call, watchlist_viewer)
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda message: True)
def on_text(message):
    text = message.text
    if text == "👋 Trang chủ": handle_back_main(bot, message)
    elif text == "🌟 Giá Vàng Thế Giới": handle_gold_price(bot, message, gold_service)
    elif text == "🇻🇳 Cổ Phiếu Việt Nam": handle_vn_stock(bot, message)
    elif text == "📊 Tổng quan thị trường": handle_market_overview(bot, message, dnse_service)
    elif text == "🔎 Tra cứu Cổ phiếu": handle_stock_search_request(bot, message, dnse_service, shark_service, vnstock_service, trinity_monitor)
    elif text == "⭐ Watchlist": handle_show_watchlist(bot, message, watchlist_viewer)
    elif text == "🔙 Quay lại": handle_back_main(bot, message)
    elif text == "🦈 Săn Cá Mập": handle_shark_menu(bot, message)
    elif text == "✅ Bật Cảnh Báo": on_shark_on(message)
    elif text == "📊 Thống Kê Hôm Nay": 
        bot.send_message(message.chat.id, shark_service.get_stats_report(), parse_mode='Markdown')
    elif text == "ℹ️ Hướng dẫn / Help": handle_help(bot, message)
    elif text == "📞 Liên hệ Admin": handle_contact(bot, message)
    else: bot.reply_to(message, "Vui lòng chọn menu bên dưới. 👇", reply_markup=create_main_menu())

# ==========================================
# 4. MAIN ENTRY POINT
# ==========================================
if __name__ == "__main__":
    print("🚀 Starting SmartTradeBot (Schedule Mode)...")
    
    # 1. Start Web Server (For Render)
    from flask import Flask
    app = Flask(__name__)
    @app.route('/')
    def health(): return "Bot Running 200 OK", 200
    
    def run_web():
        port = int(os.environ.get("PORT", 8080))
        app.run(host='0.0.0.0', port=port)
    
    threading.Thread(target=run_web, daemon=True).start()

    # 2. Start Scheduler (Background)
    threading.Thread(target=scheduler.run_schedule, daemon=True).start()

    # 3. Start Telebot (Blocking)
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        logger.error(f"❌ Main Loop Error: {e}")
