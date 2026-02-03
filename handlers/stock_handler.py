import threading
from telebot import types

def register_stock_handlers(bot, dnse_service, gold_service):
    
    @bot.message_handler(commands=['pricegold'])
    def command_price_gold(message):
        handle_gold_price(bot, message, gold_service)

    @bot.message_handler(commands=['stock'])
    def command_stock(message):
        handle_stock_price(bot, message, dnse_service)

    # Route text messages for buttons
    # Note: These need to be registered in main or a centralrouter if we split files like this. 
    # Or, we can just export the logic functions and call them from main's router.
    # The 'register' approach works best if we register all handlers there.
    # But for text filters, it's tricky if multiple files want to handle text.
    # For now, I will export the Handle Functions and register them in main or here if I can.
    pass

def handle_gold_price(bot, message, gold_service):
    """Xử lý khi bấm nút Giá Vàng hoặc /pricegold"""
    try:
        msg_wait = bot.reply_to(message, "⏳ Đang lấy dữ liệu giá Vàng thế giới...")
        
        data = gold_service.get_gold_price()
        
        if not data:
            bot.edit_message_text("❌ Không lấy được dữ liệu. Vui lòng thử lại sau.", chat_id=message.chat.id, message_id=msg_wait.message_id)
            return

        change_icon = "🟢" if data['change_percent'] >= 0 else "🔴"
        
        reply_msg = (
            f"🌟 **GOLD PRICE UPDATE** 🌟\n"
            f"🕒 Cập nhật: `{data['timestamp']}`\n\n"
            f"💰 **Giá hiện tại**: `{data['price']:,.1f}` USD {change_icon} (`{data['change_percent']:+.2f}%`)\n"
            f"---------------------------------\n"
            f"📈 Cao nhất: `{data['high']:,.1f}`\n"
            f"📉 Thấp nhất: `{data['low']:,.1f}`\n"
            f"🚪 Mở cửa: `{data['open']:,.1f}`\n"
        )
        
        bot.delete_message(chat_id=message.chat.id, message_id=msg_wait.message_id)
        bot.send_message(message.chat.id, reply_msg, parse_mode='Markdown')
        
    except Exception as e:
        print(f"Lỗi Gold: {e}")
        bot.reply_to(message, "❌ Có lỗi xảy ra khi lấy dữ liệu.")

from datetime import datetime

# ... (imports)

def format_stock_reply(data):
    """
    Helper function to format stock data message.
    """
    stock_id = data.get("symbol", "UNKNOWN")
    price = float(data.get("matchPrice", 0))
    change_pc = float(data.get("changedRatio", 0))
    ref_price = float(data.get("referencePrice", 0))
    
    # New fields
    high_price = float(data.get("highestPrice", 0) or data.get("highPrice", 0))
    low_price = float(data.get("lowestPrice", 0) or data.get("lowPrice", 0))
    avg_price = float(data.get("avgPrice", 0) or data.get("averagePrice", 0))
    
    # If Avg is 0, leave it or hide it? unique request: "calculate if not exists"
    # We assume API gives it. If 0, we show 0.
    
    vol_str = str(data.get("totalVolumeTraded", "0"))
    total_vol = int(vol_str) if vol_str.isdigit() else 0
    
    # Date
    # data might have 'time' or 'transactTime'
    # Default to current time if missing
    log_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    
    if change_pc > 0: trend_icon = "📈"
    elif change_pc < 0: trend_icon = "📉"
    else: trend_icon = "🟡"

    return (
        f"-----------------------------\n"
        f"🔥 **{stock_id}** (Real-time)\n"
        f"🕒 `{log_time}`\n"
        f"-----------------------------\n"
        f"💰 Giá: `{price:,.2f}` ({change_pc:+.2f}% {trend_icon})\n"
        f"⚖️ Tham chiếu: `{ref_price:,.2f}`\n"
        f"📊 Tổng Vol: `{total_vol:,.0f}`\n"
        f"-----------------------------\n"
        f"📈 Cao nhất: `{high_price:,.2f}`\n"
        f"📉 Thấp nhất: `{low_price:,.2f}`\n"
        f"➗ Trung bình: `{avg_price:,.2f}`\n"
        f"-----------------------------"
    )

def handle_stock_price(bot, message, dnse_service):
    """Xử lý lệnh /stock"""
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "⚠️ Vui lòng nhập mã cổ phiếu. Ví dụ: `/stock HPG`", parse_mode='Markdown')
            return
            
        symbol = parts[1].upper()
        msg_wait = bot.reply_to(message, f"⏳ Đang kết nối lấy dữ liệu **{symbol}** qua MQTT...", parse_mode='Markdown')
        
        # Event to wait for data
        data_event = threading.Event()
        received_data = {}

        def on_stock_data(payload):
            received_data.update(payload)
            data_event.set()

        # Call service
        dnse_service.get_realtime_price(symbol, on_stock_data)
        
        # Wait max 10 seconds
        if data_event.wait(timeout=10.0):
            reply_msg = format_stock_reply(received_data)
            bot.delete_message(chat_id=message.chat.id, message_id=msg_wait.message_id)
            bot.send_message(message.chat.id, reply_msg, parse_mode='Markdown')
        else:
            bot.edit_message_text(f"❌ Không nhận được dữ liệu **{symbol}** (Timeout). CODE: {symbol}", chat_id=message.chat.id, message_id=msg_wait.message_id, parse_mode='Markdown')

    except Exception as e:
        print(f"Stock Error: {e}")
        bot.reply_to(message, "❌ Lỗi hệ thống.")

def handle_stock_search_request(bot, message, dnse_service):
    """
    Bước 1: Hỏi người dùng nhập mã stock
    """
    prompt_msg = bot.reply_to(message, "🔠 **Nhập mã Cổ phiếu** bạn muốn xem (Ví dụ: HPG, SSI):", parse_mode='Markdown')
    
    # Register next step
    bot.register_next_step_handler(prompt_msg, lambda m: process_stock_search_step(bot, m, dnse_service))

def process_stock_search_step(bot, message, dnse_service):
    """
    Bước 2: Nhận mã stock và gọi logic lấy giá
    """
    try:
        symbol = message.text.upper().strip()
        
        # Validation checks
        if not symbol.isalnum() or len(symbol) > 6:
            bot.reply_to(message, "⚠️ Mã cổ phiếu không hợp lệ. Vui lòng thử lại.")
            return

        msg_wait = bot.reply_to(message, f"⏳ Đang tải dữ liệu **{symbol}**...", parse_mode='Markdown')
        
        data_event = threading.Event()
        received_data = {}
        
        def on_stock_data(payload):
            received_data.update(payload)
            data_event.set()
            
        dnse_service.get_realtime_price(symbol, on_stock_data)
        
        if data_event.wait(timeout=10.0):
            reply_msg = format_stock_reply(received_data)
            bot.delete_message(chat_id=message.chat.id, message_id=msg_wait.message_id)
            bot.send_message(message.chat.id, reply_msg, parse_mode='Markdown')
        else:
             bot.edit_message_text(f"❌ Không tìm thấy mã **{symbol}** or Timeout.", chat_id=message.chat.id, message_id=msg_wait.message_id, parse_mode='Markdown')

    except Exception as e:
        print(f"Search Step Error: {e}")
        bot.reply_to(message, "❌ Lỗi xử lý.")

    except Exception as e:
        print(f"Search Step Error: {e}")
        bot.reply_to(message, "❌ Lỗi xử lý.")

def handle_show_watchlist(bot, message, watchlist_service):
    try:
        items = watchlist_service.get_active_watchlist()
        
        if not items:
            bot.reply_to(message, "📭 Watchlist của bạn đang trống.\n(Hệ thống chưa phát hiện Cá Mập nào trong 3 ngày qua)")
            return
            
        # Format list
        lines = []
        for idx, item in enumerate(items, 1):
            sym = item['symbol']
            t_str = item['time_str']
            lines.append(f"{idx}. **#{sym}** (Báo: {t_str})")
            
        list_str = "\n".join(lines)
        
        msg = (
            f"-----------------------------------\n"
            f"⭐ **DANH SÁCH CÁ MẬP** (3 Ngày qua)\n"
            f"-----------------------------------\n"
            f"{list_str}\n"
            f"-----------------------------------\n"
            f"💡 Các mã sẽ tự động xóa sau 72h."
        )
        bot.reply_to(message, msg, parse_mode='Markdown')
        
    except Exception as e:
        print(f"Watchlist Error: {e}")
        bot.reply_to(message, "❌ Lỗi đọc Watchlist.")

def handle_market_overview(bot, message, dnse_service):
    """
    Xử lý: 📊 Tổng quan thị trường
    Lấy VNINDEX, VN30, HNX
    """
    try:
        msg_wait = bot.reply_to(message, "⏳ Đang tổng hợp dữ liệu toàn thị trường...", parse_mode='Markdown')
        
        # descriptors for indices (ALL FOUND)
        target_indices = [
            "VNINDEX", "VN30", "VN100", "VNXALLSHARE", "VN50GROWTH", "VNDIVIDEND", "VNMITECH",
            "HNX", "HNX30", "UPCOM"
        ]
        collected_data = {}
        
        # Event to wait for all data
        data_event = threading.Event()
        
        def on_index_data(payload):
            # Payload validation
            index_name = payload.get("indexName", "").upper()
            
            # Fallback if name is missing but code exists
            if not index_name:
                idx_code = payload.get("indexTypeCode", "")
                if idx_code == "001": index_name = "VNINDEX"
                elif idx_code == "101": index_name = "VN30"
                elif idx_code == "002": index_name = "HNX"
                elif idx_code == "301": index_name = "UPCOM"
            
            if index_name:
                collected_data[index_name] = payload
            
            # Check if we have most of them? 
            # Waiting for ALL might be slow if one is silent.
            # We rely on the 3.0s timeout to just show what we have.
            if len(collected_data) >= len(target_indices):
                data_event.set()

        # Subscribe
        dnse_service.get_multiple_indices(target_indices, on_index_data)
        
        # Wait 3 seconds
        data_event.wait(timeout=3.0)
        
        # Helper to format line
        def fmt_index(name, data):
            if not data: return f"• {name:<12}: (Đang cập nhật...)"
            
            val = float(data.get("valueIndexes", 0))
            chg = float(data.get("changedValue", 0))
            pct = float(data.get("changedRatio", 0))
            
            icon = "🟢" if chg >= 0 else "🔴"
            sign = "+" if chg >= 0 else ""
            
            # Formatting: Name specific padding
            # VN50GROWTH is long (10 chars), VNXALLSHARE (11)
            return f"{icon} {name:<11}: {val:,.2f} ({sign}{chg:,.2f} / {sign}{pct:,.2f}%)"

        # Prepare Data items sorted/ordered
        # Priority: VNINDEX -> VN30 -> VN100 -> HNX -> UPCOM -> Others
        ordered_keys = [
            "VN30", "VN100", "HNX", "HNX30", "UPCOM", 
            "VNXALLSHARE", "VN50GROWTH", "VNDIVIDEND", "VNMITECH"
        ]
        
        # Header (VNINDEX)
        vni = collected_data.get("VNINDEX")
        if not collected_data and not vni:
             bot.edit_message_text("❌ Không nhận được dữ liệu.", chat_id=message.chat.id, message_id=msg_wait.message_id)
             return

        headline = fmt_index("VNINDEX", vni)
        
        # Details loop
        details_str = ""
        for key in ordered_keys:
            data = collected_data.get(key)
            details_str += fmt_index(key, data) + "\n"
        
        # Liquidity (Use VNINDEX grossTradeAmount)
        gtgd_val = 0
        if vni: gtgd_val = float(vni.get("grossTradeAmount", 0))
        
        reply_msg = (
            f"-----------------------------------\n"
            f"📊 **TỔNG QUAN THỊ TRƯỜNG**\n"
            f"-----------------------------------\n"
            f"{headline}\n\n"
            f"**Chi tiết nhóm:**\n"
            f"{details_str}\n"
            f"💰 **Thanh khoản (VNINDEX)**: `{gtgd_val:,.0f}` Tỷ đồng\n"
            f"-----------------------------------"
        )
        
        bot.delete_message(chat_id=message.chat.id, message_id=msg_wait.message_id)
        bot.send_message(message.chat.id, reply_msg, parse_mode='Markdown')
        
    except Exception as e:
        print(f"Overview Error: {e}")
        bot.reply_to(message, "❌ Lỗi hiển thị.")
