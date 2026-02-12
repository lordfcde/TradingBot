# main.py
import telebot
from telebot import types
import config
import logging

# Services
from services.dnse_service import DNSEService
from services.vnstock_service import VnstockService
from services.gold_service import GoldService

# Handlers
from handlers.stock_handler import handle_stock_price, handle_gold_price, handle_market_overview, handle_stock_search_request, handle_show_watchlist
from handlers.menu_handler import send_welcome, handle_help, handle_contact, handle_vn_stock, handle_back_main, create_main_menu, handle_shark_menu
from services.shark_hunter_service import SharkHunterService
from services.watchlist_service import WatchlistService

# ==========================================
# 1. KHỞI TẠO BOT & SERVICES
# ==========================================
# ==========================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot_run.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

try:
    bot = telebot.TeleBot(config.API_TOKEN)
    print("✅ Bot đang khởi động...")
    
    # Initialize Services
    dnse_service = DNSEService()
    gold_service = GoldService()
    vnstock_service = VnstockService()  # New vnstock service
    
    # Note: Import Trinity after vnstock_service is created
    from services.trinity_monitor import TrinitySignalMonitor
    from services.analyzer import TrinityAnalyzer

    # Register Commands Hint
    print("🔹 Setting Search Commands...")
    bot.set_my_commands([
        types.BotCommand("start", "🚀 Menu Chính"),
        types.BotCommand("stock", "📈 Xem giá Cổ phiếu (Real-time)"),
        types.BotCommand("shark_on", "🦈 Bật Săn Cá Mập"),
        types.BotCommand("pricegold", "💰 Xem giá Vàng Thế Giới"),
        types.BotCommand("help", "ℹ️ Hướng dẫn sử dụng")
    ])


    shark_service = SharkHunterService(bot, vnstock_service)
    watchlist_viewer = WatchlistService() # For UI
    trinity_monitor = TrinitySignalMonitor(bot, vnstock_service, watchlist_viewer)  # Trinity Signal Monitor

    # 🧹 CLEANUP: Remove watchlist entries older than 72h on startup
    print("🧹 Cleaning up watchlist (removing entries >72h)...")
    _ = shark_service.watchlist_service.get_active_watchlist()  # This auto-cleans and saves
    print(f"✅ Watchlist cleaned. Active entries remain.")

    # Auto-Start Scanner if configured
    if shark_service.alert_chat_id:
        print(f"🔄 Auto-Starting Shark Hunter for Chat ID: {shark_service.alert_chat_id}")
        dnse_service.register_shark_streams(
            ohlc_cb=shark_service.process_ohlc,
            tick_cb=shark_service.process_tick
        )
        # Note: subscribe_all_markets will be called after connection? 
        # Actually dnse_service.connect() is called below.
        # But subscribe_all_markets() should be called AFTER connect.
        # dnse_service.connect() starts the loop but subscription needs connection.
        # We can queue it or just call it after connect returns?
        if dnse_service.connect():
            print("✅ Services Started Successfully.")
            
            # Auto-Subscribe Hook
            if shark_service.alert_chat_id:
                shark_service.enable_alerts(shark_service.alert_chat_id)
                
                # Auto-start Trinity Monitor as well
                trinity_monitor.start_monitoring(shark_service.alert_chat_id)
                print(f"🔄 Auto-Starting Trinity Monitor for Chat ID: {shark_service.alert_chat_id}")
                
                # Link Trinity to Shark Service
                shark_service.set_trinity_monitor(trinity_monitor)

                # Link Hybrid Analyzer to Shark Service
                analyzer = TrinityAnalyzer()
                shark_service.set_analyzer(analyzer)
                
                print("📡 Resuming Scanner Subscriptions...")
                print("📡 Resuming Scanner Subscriptions...")
                dnse_service.subscribe_all_markets()
                # Force Test Alert to Verify Connectivity
                shark_service.send_test_alert()
                
        else:
            print("❌ DNSE Connection Failed.")
        # Usually connect() returns then loop_start().
        
        # Let's add a hook or just call it after connect (Line ~55)

except Exception as e:
    print(f"❌ Lỗi khởi tạo: {e}")
    exit(1)

# ==========================================
# 2. REGISTER HANDLERS
# ==========================================

# --- Command Handlers ---
@bot.message_handler(commands=['start'])
def on_start(message):
    send_welcome(bot, message)

@bot.message_handler(commands=['help'])
def on_help(message):
    handle_help(bot, message)

@bot.message_handler(commands=['pricegold'])
def on_price_gold(message):
    handle_gold_price(bot, message, gold_service)

@bot.message_handler(commands=['stock'])
def on_stock(message):
    handle_stock_price(bot, message, dnse_service, shark_service)



@bot.message_handler(commands=['shark_on'])
def on_shark_on(message):
    chat_id = message.chat.id
    res = shark_service.enable_alerts(chat_id)
    
    # Ensure Global Stream is Active (Explicit FOX + Wildcard)
    dnse_service.subscribe_all_markets()
    
    bot.reply_to(message, "🦈 **ĐÃ BẬT CẢNH BÁO CÁ MẬP!**\n\n- Bot sẽ quét toàn bộ thị trường.\n- Lọc lệnh > 1 Tỷ VNĐ.\n\n⚡ **Test Mode**: Đang theo dõi FOX (báo 3 lệnh tiếp theo).")

@bot.message_handler(commands=['watchlist_clear'])
def on_watchlist_clear(message):
    chat_id = message.chat.id
    watchlist_viewer.clear_watchlist()
    bot.send_message(chat_id, "🗑️ Watchlist đã được xóa.")

@bot.message_handler(commands=['trinity_on'])
def on_trinity_on(message):
    """Start Trinity Signal Monitor"""
    chat_id = message.chat.id
    if trinity_monitor.start_monitoring(chat_id):
        bot.send_message(
            chat_id, 
            "✅ **Trinity Signal Monitor đã BẬT!**\n\n"
            "📊 Sẽ theo dõi tín hiệu MUA MẠNH 💪 và MUA MARGIN 🚀 trên khung 30m\n"
            "🎯 Theo dõi: Watchlist\n"
            "⏰ Cooldown: 30 phút\n\n"
            "Dùng /trinity_off để tắt.",
            parse_mode='Markdown'
        )
    else:
        bot.send_message(chat_id, "⚠️ Trinity Monitor đã đang chạy rồi!")

@bot.message_handler(commands=['trinity_off'])
def on_trinity_off(message):
    """Stop Trinity Signal Monitor"""
    chat_id = message.chat.id
    if trinity_monitor.stop_monitoring():
        bot.send_message(chat_id, "🛑 Trinity Signal Monitor đã TẮT.")
    else:
        bot.send_message(chat_id, "⚠️ Trinity Monitor chưa chạy!")

@bot.message_handler(commands=['trinity_test'])
def on_trinity_test(message):
    """Test Trinity Alert UI"""
    chat_id = message.chat.id
    trinity_monitor.set_chat_id(chat_id) # Ensure chat_id is set
    
    parts = message.text.split()
    symbol = parts[1].upper() if len(parts) > 1 else "TEST_STOCK"
    
    bot.reply_to(message, f"🧪 Đang gửi test alert cho {symbol}...")
    if trinity_monitor.send_test_alert(symbol):
        pass # Alert sent
    else:
        bot.reply_to(message, "❌ Lỗi gửi test alert.")

@bot.message_handler(commands=['shark_stats', 'sharks'])
def on_shark_stats(message):
    report = shark_service.get_stats_report()
    bot.send_message(message.chat.id, report, parse_mode='Markdown')

# --- Text Filters (Router) ---
@bot.message_handler(func=lambda message: True)
def on_text(message):
    text = message.text
    
    if text == "🌟 Giá Vàng Thế Giới":
        handle_gold_price(bot, message, gold_service)
    elif text == "🇻🇳 Cổ Phiếu Việt Nam":
        handle_vn_stock(bot, message)
    elif text == "📊 Tổng quan thị trường":
        handle_market_overview(bot, message, dnse_service)
    elif text == "🔎 Tra cứu Cổ phiếu": # This text-based entry point is kept for direct text input
        handle_stock_search_request(bot, message, dnse_service, shark_service, vnstock_service, trinity_monitor)
    elif text == "⭐ Watchlist":
        handle_show_watchlist(bot, message, watchlist_viewer)

    elif text == "🔙 Quay lại":
        handle_back_main(bot, message)

    # --- SHARK HUNTER MENU ---
    elif text == "🦈 Săn Cá Mập":
        handle_shark_menu(bot, message)
        
    elif text == "✅ Bật Cảnh Báo":
        if shark_service.enable_alerts(message.chat.id):
            bot.reply_to(message, "🦈 **ĐÃ BẬT CẢNH BÁO CÁ MẬP!**\n\n- Bot sẽ quét lệnh > 1 Tỷ VNĐ.\n\n_Hãy kiên nhẫn, Cá Mập sẽ xuất hiện!_ 🌊")
            
    elif text == "📊 Thống Kê Hôm Nay":
        report = shark_service.get_stats_report()
        bot.send_message(message.chat.id, report, parse_mode='Markdown')
    elif text == "ℹ️ Hướng dẫn / Help":
        handle_help(bot, message)
    elif text == "📞 Liên hệ Admin":
        handle_contact(bot, message)
    else:
        # Fallback
        bot.reply_to(message, "Tôi chưa hiểu lệnh này. Vui lòng chọn menu bên dưới. 👇", reply_markup=create_main_menu())

# ==========================================
# 3. MAIN LOOP
# ==========================================
if __name__ == "__main__":
    print("🚀 Super Bot đang chạy... (Nhấn Ctrl+C để dừng)")
    try:
        bot.infinity_polling()
    except KeyboardInterrupt:
        print("\n🛑 Bot đã dừng.")
    except Exception as e:
        print(f"❌ Lỗi Runtime: {e}")
