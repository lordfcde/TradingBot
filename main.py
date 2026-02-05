# main.py
import telebot
from telebot import types
import config
import logging

# Services
from services.dnse_service import DNSEService
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
    
    dnse_service = DNSEService()
    gold_service = GoldService()

    # Register Commands Hint
    print("🔹 Setting Search Commands...")
    bot.set_my_commands([
        types.BotCommand("start", "🚀 Menu Chính"),
        types.BotCommand("stock", "📈 Xem giá Cổ phiếu (Real-time)"),
        types.BotCommand("shark_on", "🦈 Bật Săn Cá Mập"),
        types.BotCommand("pricegold", "💰 Xem giá Vàng Thế Giới"),
        types.BotCommand("help", "ℹ️ Hướng dẫn sử dụng")
    ])

    shark_service = SharkHunterService(bot)
    watchlist_viewer = WatchlistService() # For UI

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
def watchlist_clear(message):
    """Clear all entries from watchlist"""
    try:
        watchlist_viewer.clear_watchlist()
        bot.reply_to(message, "✅ Đã xóa toàn bộ Watchlist!")
    except Exception as e:
        bot.reply_to(message, f"❌ Lỗi khi xóa watchlist: {e}")

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
    elif text == "🔎 Tra cứu Cổ phiếu":
        handle_stock_search_request(bot, message, dnse_service, shark_service)
    elif text == "⭐ Watchlist":
        handle_show_watchlist(bot, message, watchlist_viewer)
    elif text == "📊 Biến Động Mạnh":
        # Show volatility report
        report = shark_service.get_volatility_report()
        bot.send_message(message.chat.id, report, parse_mode='Markdown')
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
