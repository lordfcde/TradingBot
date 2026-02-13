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

from datetime import datetime, timedelta

# ... (imports)

def get_enriched_trinity_analysis(symbol, trinity_service, vnstock_service, shark_service=None, bot=None, chat_id=None):
    """
    Common logic to get Trinity Monitor (1H) + Trinity Analyzer (Deep) data.
    Also handles auto-adding to Watchlist if signal found.
    """
    trinity_analysis = None
    
    # 1. Trinity Monitor (Fast Signal)
    if trinity_service:
        try:
            trinity_analysis = trinity_service.get_analysis(symbol, timeframe="1H")
            
            if trinity_analysis and trinity_analysis.get('signal'):
                sig_name = trinity_analysis['signal']
                
                # Auto-add to Watchlist
                if shark_service and bot and chat_id:
                    shark_service.watchlist_service.add_to_watchlist(symbol)
                    bot.send_message(
                        chat_id, 
                        f"🚀 **TRINITY SIGNAL**: {symbol} - {sig_name}\n"
                        f"✅ Đã tự động thêm vào Watchlist!", 
                        parse_mode='Markdown'
                    )
        except Exception as e:
            print(f"⚠️ Trinity check error: {e}")

    # 2. Trinity Analyzer (Deep Analysis)
    try:
        from services.analyzer import TrinityAnalyzer
        # Initialize with shared service
        analyzer = TrinityAnalyzer(vnstock_service)
        analyzer_result = analyzer.check_signal(symbol)
        
        if trinity_analysis is None:
            trinity_analysis = analyzer_result
        else:
            # Merge logic
            trinity_analysis['rating'] = analyzer_result.get('rating', 'WATCH')
            
    except Exception as e:
        print(f"⚠️ Analyzer error: {e}")
        if trinity_analysis:
            trinity_analysis['rating'] = 'UNKNOWN'
            
    return trinity_analysis

def get_realtime_price_async(dnse_service, symbol, timeout=5.0):
    """
    Fetch real-time price from DNSE MQTT with timeout.
    Returns dict or None.
    """
    if not dnse_service:
        return None
        
    data_event = threading.Event()
    received_data = {}
    
    def on_stock_data(payload):
        # print(f"🔹 DEBUG: MQTT Data received for {symbol}")
        received_data.update(payload)
        data_event.set()
        
    # Subscribe and wait
    dnse_service.get_realtime_price(symbol, on_stock_data)
    
    if data_event.wait(timeout=timeout):
        return received_data
    else:
        print(f"⚠️ MQTT Timeout for {symbol}")
        return None

def format_stock_reply(data, shark_service=None, trinity_data=None):
    """
    Helper function to format stock data message.
    """
    stock_id = data.get("symbol", "UNKNOWN")
    price = float(data.get("matchPrice", 0))
    change_pc = float(data.get("changedRatio", 0))
    ref_price = float(data.get("referencePrice", 0))
    
    print(f"🔹 DEBUG STOCK PAYLOAD [{stock_id}]: {data}")

    # New fields
    high_price = float(data.get("highestPrice", 0) or data.get("highPrice", 0))
    low_price = float(data.get("lowestPrice", 0) or data.get("lowPrice", 0))
    avg_price = float(data.get("avgPrice", 0) or data.get("averagePrice", 0))
    
    # If Avg is 0, leave it or hide it? unique request: "calculate if not exists"
    # We assume API gives it. If 0, we show 0.
    
    vol_str = str(data.get("totalVolumeTraded", "0"))
    raw_total_vol = int(vol_str) if vol_str.isdigit() else 0
    total_vol = raw_total_vol * 10  # Fix: Multiply by 10 to match real volume
    
    # Date
    # data might have 'time' or 'transactTime'
    # Default to current time if missing -> Force to UTC+7 (Vietnam Time)
    log_time = (datetime.utcnow() + timedelta(hours=7)).strftime("%d/%m/%Y %H:%M:%S")
    
    # Buy/Sell Surplus Removed as per request
    # Add Last Match Volume (User says Unit is 10, so x10)
    # FILTER: odd lots (<100) are ignored.
    raw_match_vol = int(data.get("matchQuantity", 0) or data.get("matchVolume", 0) or data.get("lastVol", 0) or 0)
    match_vol = raw_match_vol * 10
    
    # Hide if Odd Lot (Volume < 100)
    if match_vol < 100:
        match_vol = 0

    if change_pc > 0: trend_icon = "📈"
    elif change_pc < 0: trend_icon = "📉"
    else: trend_icon = "🟡"

    # Get industry and avg volume if available
    industry = data.get("industry", "N/A")
    avg_vol_5d = data.get("avg_vol_5d", 0)
    rsi = data.get("rsi", None)

    # Match Time (from payload or current)
    # MQTT often returns time in HH:mm:ss format (e.g., 05:00:00 for 12:00 UTC+7?)
    # or it might be raw UTC. User reports 5AM -> 12PM gap (7 hours).
    match_time_raw = data.get("time") or log_time.split(" ")[1]
    
    # Try to fix timezone if it looks like early morning (UTC)
    match_time = match_time_raw
    try:
        if ":" in match_time_raw and len(match_time_raw.split(":")) >= 2:
            parts = match_time_raw.split(":")
            h = int(parts[0])
            m = int(parts[1])
            s = int(parts[2]) if len(parts) > 2 else 0
            
            # Simple heuristic: If hour < 7, add 7 to match Vietnam Time (UTC+7)
            # Market opens 9:00. If we see 02:00 (9AM), 05:00 (12PM), etc.
            if h < 8: 
                h += 7
                match_time = f"{h:02d}:{m:02d}:{s:02d}"
    except:
        pass

    base_msg = (
        f"-----------------------------\n"
        f"🔥 **{stock_id}** (Real-time)\n"
        f"🕒 Cập nhật: `{log_time}`\n"
        f"-----------------------------\n"
        f"💰 Giá: `{price:,.2f}` ({change_pc:+.2f}% {trend_icon})\n"
        f"🔨 **Khớp Lệnh**: `{match_time}`\n"
        f"📦 **KL Khớp Cuối**: `{match_vol:,.0f}`\n"
        f"⚖️ Tham chiếu: `{ref_price:,.2f}`\n"
        f"📊 Tổng Vol: `{total_vol:,.0f}`\n"
    )
    
    # Add industry if available
    if industry and industry != "N/A":
        base_msg += f"🏢 Ngành: `{industry}`\n"
    
    # Add 5-day avg volume if available
    if avg_vol_5d > 0:
        base_msg += f"📉 TB Vol 5D: `{avg_vol_5d:,.0f}`\n"
        
    # Add RSI if available
    if rsi is not None:
        rsi_icon = "🔴" if rsi > 70 else "🟢" if rsi < 30 else "🟡"
        rsi_status = "Quá mua" if rsi > 70 else "Quá bán" if rsi < 30 else "Trung lập"
        base_msg += f"📈 RSI(14): `{rsi:.1f}` {rsi_icon} ({rsi_status})\n"
    
    base_msg += (
        f"-----------------------------\n"
        f"📈 Cao nhất: `{high_price:,.2f}`\n"
        f"📉 Thấp nhất: `{low_price:,.2f}`\n"
        f"➗ Trung bình: `{avg_price:,.2f}`"
    )

    # 🦈 Shark Stats (Added)
    if shark_service:
        try:
            s_buy, s_sell = shark_service.get_shark_stats(stock_id)
            if s_buy > 0 or s_sell > 0:
                s_net = s_buy - s_sell
                icon = "🟢" if s_net >= 0 else "🔴"
                base_msg += (
                    f"\n-----------------------------\n"
                    f"🦈 **Cá mập (>1Tỷ)**: {icon} `{s_net/1e9:,.1f}` Tỷ\n"
                    f"(Mua: {s_buy/1e9:.1f}T - Bán: {s_sell/1e9:.1f}T)"
                )
        except: pass
    
    base_msg += "\n-----------------------------"
    
    # Add Trinity Analysis if available
    if trinity_data:
        t_trend = trinity_data.get('trend', 'N/A')
        t_cmf = trinity_data.get('cmf', 0)
        t_chaikin = trinity_data.get('chaikin', 0)
        t_rsi = trinity_data.get('rsi', 0)
        t_signal = trinity_data.get('signal')
        t_rating = trinity_data.get('rating', 'UNKNOWN')  # From analyzer
        cmf_st = trinity_data.get('cmf_status', '')
        t_trigger = trinity_data.get('trigger', '')

        base_msg += f"\n⚡ **Trinity Fast 1H:**\n"
        base_msg += f"• Xu hướng: {t_trend}\n"
        base_msg += f"• Dòng tiền: {t_cmf:.2f} ({cmf_st})\n"
        base_msg += f"• Chaikin: {t_chaikin:+,.0f}\n"
        base_msg += f"• RSI: {t_rsi:.1f}\n"
        if t_trigger:
            trigger_label = "🔄 Rũ bỏ" if t_trigger == 'SHAKEOUT' else "💥 Vol đột biến"
            base_msg += f"• Trigger: {trigger_label}\n"
        if t_signal:
            base_msg += f"⚡ **Tín hiệu: {t_signal}**\n"
        
        # === MULTI-LAYER SCORING SYSTEM ===
        base_msg += "\n-----------------------------\n"
        base_msg += "📊 **PHÂN TÍCH ĐA TẦNG**\n"
        
        score = 0
        reasons = []
        
        # Layer 1: Real-time signals
        if change_pc > 2:
            score += 2
            reasons.append("✅ Tăng giá mạnh")
        elif change_pc > 0:
            score += 1
            reasons.append("✅ Tăng giá nhẹ")
        elif change_pc < -2:
            score -= 1
            reasons.append("⚠️ Giảm giá mạnh")
        
        # Volume ratio
        vol_ratio = (total_vol / avg_vol_5d * 100) if avg_vol_5d > 0 else 0
        if vol_ratio > 150:
            score += 2
            reasons.append("✅ Vol đột biến")
        elif vol_ratio > 100:
            score += 1
            reasons.append("✅ Vol tăng")
        elif vol_ratio < 50 and vol_ratio > 0:
            score -= 1
            reasons.append("⚠️ Vol thấp")
        
        # Layer 2: Trinity signals
        if t_rating == "BUY" or (t_signal and "MUA" in str(t_signal).upper()):
            score += 3
            reasons.append("✅ Trinity: BUY (Signal)")
        elif t_rating == "WATCH":
            score += 1
            reasons.append("⚪ Trinity: WATCH")
            
        # Bonus for Uptrend
        if t_trend and "UPTREND" in str(t_trend).upper():
            score += 1
            reasons.append("✅ Xu hướng Tăng")
        
        if t_rsi > 70:
            score -= 1
            reasons.append("⚠️ RSI quá mua")
        elif t_rsi > 50:
            score += 1
            reasons.append("✅ RSI mạnh")
        
        if t_cmf > 0.1:
            score += 2
            reasons.append("✅ Tiền vào mạnh")
        elif t_cmf > 0:
            score += 1
            reasons.append("✅ Tiền vào nhẹ")
        elif t_cmf < -0.1:
            score -= 1
            reasons.append("⚠️ Tiền ra mạnh")
        
        # Display reasons
        base_msg += "📋 Yếu tố:\n"
        for r in reasons[:5]:  # Limit to 5 key reasons
            base_msg += f"  {r}\n"
        
        # Final score and recommendation
        base_msg += f"\n🔢 Điểm: **{score}/10**\n"
        
        if score >= 6:
            recommendation = "🟢 THÊM WATCHLIST"
            rec_icon = "🟢"
        elif score >= 3:
            recommendation = "🟡 THEO DÕI"
            rec_icon = "🟡"
        else:
            recommendation = "🔴 BỎ QUA"
            rec_icon = "🔴"
        
        base_msg += f"💡 Gợi ý: **{rec_icon} {recommendation}**"
            
    return base_msg

def handle_stock_price(bot, message, dnse_service, shark_service=None, vnstock_service=None, trinity_service=None):
    """Xử lý lệnh /stock (Updated to match Search logic)"""
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "⚠️ Vui lòng nhập mã cổ phiếu. Ví dụ: `/stock HPG`", parse_mode='Markdown')
            return
            
        symbol = parts[1].upper().strip()
        
        # Validation checks
        if not symbol.isalnum() or len(symbol) > 6:
            bot.reply_to(message, "⚠️ Mã cổ phiếu không hợp lệ.")
            return

        msg_wait = bot.reply_to(message, f"⏳ Đang tải dữ liệu **{symbol}** (MQTT)...", parse_mode='Markdown')
        
        # 1. Fetch Real-time Data (MQTT) - Priority
        mqtt_data = get_realtime_price_async(dnse_service, symbol)
        
        # 2. Enrich with Vnstock (History/Context)
        enriched_data = {}
        if mqtt_data:
            enriched_data = mqtt_data
            # Initialize vnstock helper if available to get extra info
            if vnstock_service:
                try:
                    # We utilize vnstock just for Static/History info (Industry, AvgVol, RSI)
                    # Implementation detail: vnstock_service.get_stock_info does full fetch,
                    # but we can overwrite price with MQTT_data.
                    # Or better: Add a specific enrichment method in vnstock_service.
                    # For now, we reuse get_stock_info but prioritize MQTT fields.
                    vn_data = vnstock_service.get_stock_info(symbol)
                    if vn_data:
                        # Merge: Keep MQTT price/vol, take Industry/AvgVol from Vnstock
                        enriched_data['industry'] = vn_data.get('industry')
                        enriched_data['avg_vol_5d'] = vn_data.get('avg_vol_5d')
                        enriched_data['rsi'] = vn_data.get('rsi')
                except:
                    pass
        elif vnstock_service:
            # Fallback to pure Vnstock if MQTT fails
            print(f"⚠️ MQTT failed for {symbol}, falling back to Vnstock HTTP.")
            enriched_data = vnstock_service.get_stock_info(symbol)
        
        if enriched_data:
            # Check RSI Watchlist (using enriched data)
            if shark_service and enriched_data.get('rsi') is not None:
                added = shark_service.check_rsi_watchlist(
                    symbol, 
                    enriched_data.get('rsi'), 
                    enriched_data.get('totalVolumeTraded', 0), 
                    enriched_data.get('avg_vol_5d', 0)
                )
                if added:
                    bot.send_message(message.chat.id, f"🔔 **{symbol}** đã được thêm vào Watchlist (RSI + Vol đột biến)!", parse_mode='Markdown')

            # Unified Analysis Logic
            trinity_analysis = get_enriched_trinity_analysis(
                symbol, trinity_service, vnstock_service, 
                shark_service, bot, message.chat.id
            )

            reply_msg = format_stock_reply(enriched_data, shark_service, trinity_analysis)
            bot.delete_message(chat_id=message.chat.id, message_id=msg_wait.message_id)
            bot.send_message(message.chat.id, reply_msg, parse_mode='Markdown')
        else:
             bot.edit_message_text(f"❌ Không tìm thấy mã **{symbol}** (Kiểm tra lại kết nối/mã).", chat_id=message.chat.id, message_id=msg_wait.message_id, parse_mode='Markdown')

    except Exception as e:
        print(f"Stock Error: {e}")
        bot.reply_to(message, "❌ Lỗi hệ thống.")

def handle_stock_search_request(bot, message, dnse_service=None, shark_service=None, vnstock_service=None, trinity_service=None):
    """
    Bước 1: Hỏi người dùng nhập mã stock
    """
    prompt_msg = bot.reply_to(message, "🔠 **Nhập mã Cổ phiếu** bạn muốn xem (Ví dụ: HPG, SSI):", parse_mode='Markdown')
    
    # Register next step
    bot.register_next_step_handler(prompt_msg, lambda m: process_stock_search_step(bot, m, dnse_service, shark_service, vnstock_service, trinity_service))

def process_stock_search_step(bot, message, dnse_service=None, shark_service=None, vnstock_service=None, trinity_service=None):
    """
    Bước 2: Nhận mã stock và gọi vnstock API
    """
    try:
        symbol = message.text.upper().strip()
        
        # Validation checks
        if not symbol.isalnum() or len(symbol) > 6:
            bot.reply_to(message, "⚠️ Mã cổ phiếu không hợp lệ. Vui lòng thử lại.")
            return

        msg_wait = bot.reply_to(message, f"⏳ Đang tải dữ liệu **{symbol}** (MQTT)...", parse_mode='Markdown')
        
        # 1. Fetch Real-time Data (MQTT) - Priority
        mqtt_data = get_realtime_price_async(dnse_service, symbol)
        
        # 2. Enrich with Vnstock (History/Context)
        enriched_data = {}
        if mqtt_data:
            enriched_data = mqtt_data
            # Initialize vnstock helper if available to get extra info
            if vnstock_service:
                try:
                    vn_data = vnstock_service.get_stock_info(symbol)
                    if vn_data:
                        enriched_data['industry'] = vn_data.get('industry')
                        enriched_data['avg_vol_5d'] = vn_data.get('avg_vol_5d')
                        enriched_data['rsi'] = vn_data.get('rsi')
                except:
                    pass
        elif vnstock_service:
            # Fallback to pure Vnstock
            enriched_data = vnstock_service.get_stock_info(symbol)

        if enriched_data:
            # Check RSI Watchlist Trigger
            if shark_service and enriched_data.get('rsi') is not None:
                added = shark_service.check_rsi_watchlist(
                    symbol, 
                    enriched_data.get('rsi'), 
                    enriched_data.get('totalVolumeTraded', 0), 
                    enriched_data.get('avg_vol_5d', 0)
                )
                if added:
                    bot.send_message(message.chat.id, f"b🔔 **{symbol}** đã được thêm vào Watchlist (RSI + Vol đột biến)!", parse_mode='Markdown')

            # Unified Analysis Logic
            trinity_analysis = get_enriched_trinity_analysis(
                symbol, trinity_service, vnstock_service, 
                shark_service, bot, message.chat.id
            )

            reply_msg = format_stock_reply(enriched_data, shark_service, trinity_analysis)
            bot.delete_message(chat_id=message.chat.id, message_id=msg_wait.message_id)
            bot.send_message(message.chat.id, reply_msg, parse_mode='Markdown')
        else:
            bot.edit_message_text(f"❌ Không tìm thấy mã **{symbol}** or Timeout.", chat_id=message.chat.id, message_id=msg_wait.message_id, parse_mode='Markdown')

    except Exception as e:
        print(f"Search Step Error: {e}")
        bot.reply_to(message, "❌ Lỗi xử lý.")

def handle_show_watchlist(bot, message, watchlist_service):
    """
    """
    try:
        from telebot import types
        
        # Show inline keyboard menu for statistics options
        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton("📋 Xem Watchlist", callback_data="watchlist_view"),
            types.InlineKeyboardButton("📊 Top Mã", callback_data="watchlist_top")
        )
        markup.row(
            types.InlineKeyboardButton("🔥 BUY Signal Hôm Nay", callback_data="watchlist_today")
        )
        
        bot.reply_to(message, "⭐ **WATCHLIST MENU**\nChọn chức năng:", reply_markup=markup, parse_mode='Markdown')
        
    except Exception as e:
        print(f"Watchlist Error: {e}")
        bot.reply_to(message, "❌ Lỗi hiển thị menu Watchlist.")

def show_watchlist_view(bot, call, watchlist_service):
    """Show current watchlist + 3-day history"""
    try:
        items = watchlist_service.get_active_watchlist()
        
        # Build message with current watchlist
        lines = []
        if items:
            lines.append("-----------------------------------")
            lines.append("⭐ **WATCHLIST HIỆN TẠI** (72h)")
            lines.append("-----------------------------------")
            for idx, item in enumerate(items[:10], 1):
                sym = item['symbol']
                t_str = item['time_str']
                lines.append(f"{idx}. **#{sym}** (Báo: {t_str})")
            
            if len(items) > 10:
                lines.append(f"... và {len(items)-10} mã khác")
        else:
            lines.append("📭 Watchlist hiện tại đang trống")
        
        # Add history section (3 days instead of 7)
        lines.append("\n📊 **LỊCH SỬ 3 NGÀY GẦN NHẤT:**")
        lines.append("-----------------------------------")
        
        history_file = "watchlist_history.txt"
        try:
            import os
            if os.path.exists(history_file):
                with open(history_file, 'r', encoding='utf-8') as f:
                    all_lines = f.readlines()
                
                if all_lines:
                    # Show last 3 days
                    recent = all_lines[-3:]
                    for line in recent:
                        lines.append(line.strip())
                else:
                    lines.append("(Chưa có lịch sử)")
            else:
                lines.append("(Chưa có lịch sử)")
        except Exception as e:
            print(f"History read error: {e}")
            lines.append("(Lỗi đọc lịch sử)")
        
        lines.append("-----------------------------------")
        lines.append("💡 Watchlist tự động xóa sau 72h")
        
        msg = "\n".join(lines)
        bot.edit_message_text(msg, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode='Markdown')
        
    except Exception as e:
        print(f"Watchlist view error: {e}")
        bot.answer_callback_query(call.id, "❌ Lỗi hiển thị watchlist")

def show_top_symbols(bot, call):
    """Show top symbols by number of unique days they were added to watchlist"""
    try:
        history_file = "watchlist_history.txt"
        import os
        from collections import defaultdict
        
        if not os.path.exists(history_file):
            bot.answer_callback_query(call.id, "❌ Chưa có lịch sử")
            return
        
        with open(history_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        if not lines:
            bot.answer_callback_query(call.id, "❌ Chưa có dữ liệu")
            return
        
        # Track which dates each symbol appeared on
        symbol_dates = defaultdict(set)  # symbol -> set of dates
        
        for line in lines:
            if '|' in line:
                parts = line.split('|')
                if len(parts) >= 3:
                    # Extract date (format: "2026-02-12 15:15")
                    date_str = parts[0].strip().split()[0]  # Get "2026-02-12"
                    
                    # Extract symbols (format: #SYMBOL)
                    symbols_part = '|'.join(parts[2:])
                    symbols = [s.strip().replace('#', '') for s in symbols_part.split('|') if s.strip().startswith('#')]
                    
                    # Add this date to each symbol's set
                    for symbol in symbols:
                        symbol_dates[symbol].add(date_str)
        
        # Count unique days per symbol
        symbol_day_counts = [(symbol, len(dates)) for symbol, dates in symbol_dates.items()]
        symbol_day_counts.sort(key=lambda x: x[1], reverse=True)
        
        # Get top 10
        top_symbols = symbol_day_counts[:10]
        
        if not top_symbols:
            bot.answer_callback_query(call.id, "❌ Không có dữ liệu")
            return
        
        # Format message
        lines_msg = ["📊 **TOP MÃ XUẤT HIỆN LIÊN TỤC**", "━━━━━━━━━━━━━━━━━━━━━━━━"]
        for idx, (symbol, day_count) in enumerate(top_symbols, 1):
            medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
            day_text = "ngày" if day_count > 1 else "ngày"
            lines_msg.append(f"{medal} **#{symbol}** — {day_count} {day_text}")
        
        lines_msg.append("━━━━━━━━━━━━━━━━━━━━━━━━")
        lines_msg.append(f"💡 Dựa trên {len(lines)} phiên giao dịch")
        
        msg = "\n".join(lines_msg)
        bot.edit_message_text(msg, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode='Markdown')
        
    except Exception as e:
        print(f"Top symbols error: {e}")
        bot.answer_callback_query(call.id, "❌ Lỗi thống kê")

def show_today_buy_signals(bot, call, watchlist_service):
    """Show symbols with most BUY signals today"""
    try:
        from datetime import datetime
        from collections import Counter
        
        data = watchlist_service._load_data()
        
        if not data:
            bot.answer_callback_query(call.id, "❌ Watchlist trống")
            return
        
        # Filter for today only
        today = datetime.now().strftime("%Y-%m-%d")
        today_symbols = []
        
        for symbol, info in data.items():
            entry_time = info.get('entry_time', 0)
            entry_date = datetime.fromtimestamp(entry_time).strftime("%Y-%m-%d")
            
            if entry_date == today and info.get('trinity', {}).get('rating') == 'BUY':
                today_symbols.append(symbol)
        
        if not today_symbols:
            bot.edit_message_text(
                "🔥 **BUY SIGNAL HÔM NAY**\n━━━━━━━━━━━━━━━━━━━━━━━━\n📭 Chưa có BUY signal nào hôm nay",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode='Markdown'
            )
            return
        
        # Count occurrences (in case symbol added multiple times)
        symbol_counts = Counter(today_symbols)
        top_symbols = symbol_counts.most_common(10)
        
        # Format message
        lines_msg = ["🔥 **BUY SIGNAL HÔM NAY**", "━━━━━━━━━━━━━━━━━━━━━━━━"]
        for idx, (symbol, count) in enumerate(top_symbols, 1):
            if count > 1:
                lines_msg.append(f"{idx}. **#{symbol}** — {count} lần")
            else:
                lines_msg.append(f"{idx}. **#{symbol}**")
        
        lines_msg.append("━━━━━━━━━━━━━━━━━━━━━━━━")
        lines_msg.append(f"💎 Tổng {len(today_symbols)} BUY signal hôm nay")
        
        msg = "\n".join(lines_msg)
        bot.edit_message_text(msg, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode='Markdown')
        
    except Exception as e:
        print(f"Today signals error: {e}")
        bot.answer_callback_query(call.id, "❌ Lỗi thống kê")


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
            f"💰 **Thanh khoản (VNINDEX)**: `{gtgd_val:,.0f}` Tỷ đồng"
        )

        # Foreign Flow (Khối ngoại) - Added logic
        if vni:
            # Try different keys typical for KRX feeds
            f_buy = float(vni.get("totalForeignBuyValue", 0) or vni.get("foreignBuyValue", 0))
            f_sell = float(vni.get("totalForeignSellValue", 0) or vni.get("foreignSellValue", 0))
            
            # If 0, maybe keys are different (e.g. 'foreignTotal...'). 
            # We show it if NON-ZERO to avoid noise if data is missing.
            if f_buy != 0 or f_sell != 0:
                f_net = f_buy - f_sell
                net_icon = "🟢" if f_net >= 0 else "🔴"
                net_txt = "Mua ròng" if f_net >= 0 else "Bán ròng"
                
                reply_msg += (
                    f"\n🌍 **Khối ngoại**: {net_icon} {net_txt} `{abs(f_net):,.0f}` Tỷ"
                )

        reply_msg += "\n-----------------------------------"

        
        bot.delete_message(chat_id=message.chat.id, message_id=msg_wait.message_id)
        bot.send_message(message.chat.id, reply_msg, parse_mode='Markdown')
        
    except Exception as e:
        print(f"Overview Error: {e}")
        bot.reply_to(message, "❌ Lỗi hiển thị.")
