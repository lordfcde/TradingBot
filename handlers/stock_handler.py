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

from datetime import datetime, timedelta, timezone

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

    # 2. Trinity Analyzer (Deep Analysis — 1D)
    try:
        from services.analyzer import TrinityAnalyzer
        analyzer = TrinityAnalyzer(vnstock_service)
        analyzer_result = analyzer.check_signal(symbol, timeframe="1D")
        
        if trinity_analysis is None:
            # No fast signal — use deep analysis as-is
            trinity_analysis = analyzer_result
        else:
            # FIX: Deep analyzer is the BASE (has vol_climax, shakeout, wyckoff, etc.)
            # Fast monitor signal/signal_code overlays on top
            fast_signal = trinity_analysis.get('signal', '')
            fast_signal_code = trinity_analysis.get('signal_code', '')
            
            # Deep analyzer becomes the base result
            trinity_analysis = analyzer_result
            
            # Overlay fast monitor signal if it found something
            if fast_signal:
                trinity_analysis['signal'] = fast_signal
                trinity_analysis['signal_code'] = fast_signal_code
            
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
    Format stock data — AWM Portal-style Professional Analysis v2.0.
    4-section layout: Structure, Indicators, Strategy, Quality Gate.
    """
    stock_id = data.get("symbol", "UNKNOWN")
    price = float(data.get("matchPrice", 0))
    if price > 500:
        price = price / 1000
    
    change_pc = float(data.get("changedRatio", 0))
    vol_str = str(data.get("totalVolumeTraded", "0"))
    raw_total_vol = int(vol_str) if vol_str.isdigit() else 0
    
    if data.get('source') == 'VNSTOCK':
        total_vol = raw_total_vol
    else:
        total_vol = raw_total_vol * 10
    
    log_time = (datetime.now(timezone.utc) + timedelta(hours=7)).strftime("%H:%M %d/%m")
    
    if change_pc > 0: trend_icon = "📈"
    elif change_pc < 0: trend_icon = "📉"
    else: trend_icon = "🟡"

    # Shark Stats
    shark_msg = ""
    if shark_service:
        try:
            s_buy, s_sell = shark_service.get_shark_stats(stock_id)
            if s_buy > 0 or s_sell > 0:
                s_net = s_buy - s_sell
                icon = "🟢" if s_net >= 0 else "🔴"
                shark_msg = f"\n🦈 Cá Mập: {icon} `{s_net/1e9:,.1f}T` (M:{s_buy/1e9:.0f} - B:{s_sell/1e9:.0f})"
        except: pass

    # ── Extract v2.0 Trinity fields ──────────────────────────
    t = {
        'trend': 'N/A', 'adx_status': '⚪', 'signal': '', 'structure': '',
        'support': 0, 'resistance': 0, 'vol_avg': 0, 'rsi': 0, 'adx': 0,
        'cmf': 0, 'macd_hist': 0, 'chaikin': 0, 'reasons': [],
        'wyckoff_phase': 'NONE', 'ema_aligned': 'NONE', 'trailing_stop': 0,
        'atr': 0, 'supertrend_dir': 0, 'pump_dump_risk': False,
        'exhaustion_top': False, 'vol_climax': False, 'shakeout': False,
        'vol_dry': False, 'vol_accumulation': False,
        'rating': '', 'score': 0, 'ema20': 0, 'ema50': 0, 'is_bullish': False
    }
    if trinity_data:
        for k in t:
            if k in trinity_data:
                t[k] = trinity_data[k]

    # ════════════════════════════════════════════════════════
    # SECTION 1: CẤU TRÚC & MẪU HÌNH
    # ════════════════════════════════════════════════════════
    if "UPTREND" in t['trend']:
        trend_line = "📈 Xu hướng: Tăng trung hạn"
    elif "DOWNTREND" in t['trend']:
        trend_line = "📉 Xu hướng: Giảm, đang điều chỉnh"
    else:
        trend_line = "🟡 Xu hướng: Đi ngang"

    ema_line = ""
    if t['ema_aligned'] == "BULL":
        ema_line = "\n- 📊 EMA: Sóng tăng (20>50>144>233)"
    elif t['ema_aligned'] == "BEAR":
        ema_line = "\n- 📊 EMA: Xếp giảm — cẩn trọng"

    st_line = "Supertrend ✅ Tăng" if t['supertrend_dir'] > 0 else "Supertrend ⚠️ Giảm"

    wyckoff_line = ""
    if t['wyckoff_phase'] == "SOS":
        wyckoff_line = "\n- 💎 Wyckoff SOS: Breakout tích lũy, Smart Money xác nhận"
    elif t['wyckoff_phase'] == "SPRING":
        wyckoff_line = "\n- 🟢 Wyckoff SPRING: Rũ bỏ thành công, cơ hội mua"
    elif t['wyckoff_phase'] == "SOW":
        wyckoff_line = "\n- 🔴 Wyckoff SOW: Phân phối, Smart Money rút"
    elif t['wyckoff_phase'] == "UPTHRUST":
        wyckoff_line = "\n- 🔴 Wyckoff UPTHRUST: Bẫy tăng giá"

    # ════════════════════════════════════════════════════════
    # SECTION 2: DÒNG TIỀN & CHỈ BÁO
    # ════════════════════════════════════════════════════════
    rsi = t['rsi']
    if rsi > 70:   rsi_line = f"🔴 RSI: {rsi:.1f} — Quá mua, cẩn thận"
    elif rsi > 60: rsi_line = f"🟢 RSI: {rsi:.1f} — Mạnh"
    elif rsi > 40: rsi_line = f"🟡 RSI: {rsi:.1f} — Trung tính"
    elif rsi > 30: rsi_line = f"🟡 RSI: {rsi:.1f} — Yếu"
    else:          rsi_line = f"🟢 RSI: {rsi:.1f} — Quá bán, cơ hội"

    cmf = t['cmf']
    if cmf > 0.1:   cmf_line = f"🟢 CMF: {cmf:.3f} — Dòng tiền VÀO MẠNH"
    elif cmf > 0:    cmf_line = f"🟢 CMF: {cmf:.3f} — Dòng tiền vào nhẹ"
    elif cmf > -0.1: cmf_line = f"🔴 CMF: {cmf:.3f} — Dòng tiền ra nhẹ"
    else:            cmf_line = f"🔴 CMF: {cmf:.3f} — Dòng tiền RA MẠNH"

    macd_line = "🟢 MACD: Momentum tăng" if t['macd_hist'] > 0 else "🔴 MACD: Momentum giảm"

    vsa_line = "Bình thường"
    if t['vol_climax']: vsa_line = "💥 VOL CLIMAX — Đột biến khối lượng, Smart Money đổ vào"
    elif t['shakeout']: vsa_line = "🔄 SHAKEOUT — Rũ bỏ, Smart Money gom?"
    elif t['vol_accumulation']: vsa_line = "📈 TÍCH LŨY — Volume tăng + nến tăng (gom hàng)"
    elif t['vol_dry']: vsa_line = "📉 CẠN VOL — Thanh khoản thấp, chờ breakout"

    trap_lines = ""
    if t['pump_dump_risk']:
        trap_lines += "\n⛔ P&D Risk: RSI cực + Vol đột biến + giá spike"
    if t['exhaustion_top']:
        trap_lines += "\n⚠️ Đỉnh Cạn: RSI divergence — giá mới nhưng RSI yếu"

    # ════════════════════════════════════════════════════════
    # SECTION 3: CHIẾN LƯỢC / HÀNH ĐỘNG
    # ════════════════════════════════════════════════════════
    atr_val = t['atr'] if t['atr'] > 0 else price * 0.02
    tp1 = price + atr_val * 1.5
    tp2 = price + atr_val * 3
    sl = t['trailing_stop'] if t['trailing_stop'] > 0 else (price - atr_val * 2)
    sl_pct = abs((price - sl) / price * 100) if price > 0 else 0

    rating = t['rating']
    score = t['score']

    if "MUA MẠNH" in rating:
        strategy = (
            "💰 Vị thế MUA MỚI (Tiền mặt):\n"
            f"  + Điều kiện: Giá giữ trên {t['ema20']:,.0f} + volume\n"
            f"  + Hoặc hồi về {t['support']:,.0f}\n"
            "  + Kế hoạch: Chia 3 phần, không all-in\n"
            "\n"
            "📈 Vị thế ĐANG CẦM HÀNG:\n"
            "  ✅ Giữ/Gia tăng: Xu hướng mạnh\n"
            f"  🟡 Chốt lời 1 phần (30-50%): Chạm {tp1:,.0f}\n"
            f"  🔴 Thoát hết: Gãy mức {sl:,.0f}"
        )
    elif "MUA THĂM DÒ" in rating:
        strategy = (
            "💰 Vị thế MUA MỚI:\n"
            "  + Chỉ thăm dò 10-20% NAV\n"
            f"  + Điều kiện: Vượt {t['ema20']:,.0f} + volume tăng\n"
            "\n"
            "📈 ĐANG CẦM HÀNG:\n"
            f"  ✅ Giữ | 🟡 Chốt: {t['resistance']:,.0f}\n"
            f"  🔴 Cắt lỗ: {sl:,.0f}"
        )
    elif "BÁN" in t['signal'] or "KHÔNG MUA" in rating:
        strategy = (
            "⛔ KHÔNG MUA MỚI\n"
            "\n"
            "📉 ĐANG CẦM HÀNG:\n"
            f"  🔴 CHỐT LỜI / CẮT LỖ: {sl:,.0f}\n"
            "  + Không bắt dao rơi"
        )
    elif "MẠNH TĂNG" in t['adx_status']:
        strategy = (
            f"💰 MUA khi hồi về {t['ema20']:,.0f}\n"
            f"  + Hoặc breakout {t['resistance']:,.0f}\n"
            "📈 ĐANG CẦM: ✅ GIỮ — Gồng lãi"
        )
    elif "MẠNH GIẢM" in t['adx_status']:
        strategy = (
            "⛔ KHÔNG MUA (Downtrend mạnh)\n"
            f"📉 ĐANG CẦM: 🔴 Hạ tỷ trọng\n"
            f"  + Thoát nếu gãy {t['support']:,.0f}"
        )
    else:
        strategy = (
            "🟡 QUAN SÁT — Chờ xác nhận\n"
            f"  + Break {t['resistance']:,.0f} → MUA\n"
            f"  + Test {t['support']:,.0f} → Chờ"
        )

    tp_block = ""
    if "MUA" in rating:
        tp_block = (
            f"\n🎯 TP Ladder:\n"
            f"  + TP1: {tp1:,.0f} (chốt 30-40%)\n"
            f"  + TP2: {tp2:,.0f} (chốt 30-40%)\n"
            f"  + TP3: Trailing stop\n"
        )

    risk_block = (
        f"\n⚠️ QLRR:\n"
        f"  + SL: {sl:,.0f} (-{sl_pct:.1f}%)\n"
        f"  + Trailing: {t['trailing_stop']:,.0f}\n"
        f"  + Time-stop: Giằng co >10 phiên"
    )

    # ════════════════════════════════════════════════════════
    # SECTION 4: QUALITY GATE
    # ════════════════════════════════════════════════════════
    pros = []
    cons = []

    if t['cmf'] > 0: pros.append("CMF dương")
    if t['macd_hist'] > 0: pros.append("MACD dương")
    if t['supertrend_dir'] > 0: pros.append("Supertrend tăng")
    if t['ema_aligned'] == "BULL": pros.append("EMA sóng tăng")
    if t['wyckoff_phase'] in ("SOS", "SPRING"): pros.append(f"Wyckoff {t['wyckoff_phase']}")
    if 50 < rsi < 70: pros.append("RSI mạnh")
    if t['adx'] > 25 and t['is_bullish']: pros.append(f"ADX {t['adx']:.0f}")
    if t['vol_climax']: pros.append("Vol Climax")

    if t['cmf'] < 0: cons.append("CMF âm")
    if t['macd_hist'] < 0: cons.append("MACD âm")
    if t['supertrend_dir'] < 0: cons.append("Supertrend giảm")
    if rsi > 70: cons.append("RSI quá mua")
    if rsi < 30: cons.append("RSI quá bán")
    if t['wyckoff_phase'] in ("SOW", "UPTHRUST"): cons.append(f"Wyckoff {t['wyckoff_phase']}")
    if t['pump_dump_risk']: cons.append("Nghi P&D")
    if t['exhaustion_top']: cons.append("Đỉnh cạn")
    if t['ema_aligned'] == "BEAR": cons.append("EMA giảm")

    n_pro = len(pros)
    n_con = len(cons)
    if n_pro >= 4 and n_con <= 1:
        verdict = '✅ "Ưu tiên giữ/mua" — Đa số chỉ báo ủng hộ'
    elif n_pro >= 2 and n_con <= 2:
        verdict = '🟡 "Quan sát thêm" — Tín hiệu chưa đồng thuận'
    else:
        verdict = '🔴 "Cẩn trọng" — Nhiều cảnh báo, hạn chế rủi ro'

    pro_text = ", ".join(pros[:4]) if pros else "(Không có)"
    con_text = ", ".join(cons[:4]) if cons else "(Không có)"

    # ════════════════════════════════════════════════════════
    # ASSEMBLE MESSAGE
    # ════════════════════════════════════════════════════════
    d_vol_avg = data.get('avg_vol_5d', 0)
    vol_ratio = total_vol / d_vol_avg if d_vol_avg > 0 else 0

    msg = (
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 PHÂN TÍCH CHUYÊN SÂU {stock_id} (1D)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🕒 `{log_time}` | 💰 `{price:,.2f}` ({change_pc:+.2f}%) {trend_icon}\n"
        f"📊 Vol: `{total_vol/1e6:.1f}M` (TB: `{d_vol_avg/1e6:.1f}M` | `{vol_ratio:.1f}x`){shark_msg}\n"
        f"\n"
        f"**1. 📈 CẤU TRÚC & MẪU HÌNH:**\n"
        f"- {trend_line}\n"
        f"- 📉 Cấu trúc: {t['structure']}{ema_line}{wyckoff_line}\n"
        f"- 🔗 {st_line}\n"
        f"\n"
        f"**2. 📊 DÒNG TIỀN & CHỈ BÁO:**\n"
        f"- 🔍 VSA: {vsa_line}\n"
        f"- 📊 Indicator:\n"
        f"  • {rsi_line}\n"
        f"  • ADX: `{t['adx']:.1f}` ({t['adx_status']})\n"
        f"  • {cmf_line}\n"
        f"  • {macd_line}"
    )
    if trap_lines:
        msg += f"\n🚨 CẢNH BÁO:{trap_lines}"

    msg += (
        f"\n\n"
        f"**3. 🎯 CHIẾN LƯỢC / HÀNH ĐỘNG:**\n"
        f"🎯 Rating: **{rating if rating else 'QUAN SÁT 🟡'}** (Score: {score})\n\n"
        f"{strategy}\n"
        f"{tp_block}"
        f"{risk_block}\n"
        f"\n"
        f"**4. 🧠 QUALITY GATE:**\n"
        f"- {n_pro} tín hiệu ủng hộ: {pro_text}\n"
        f"- {n_con} tín hiệu cảnh báo: {con_text}\n"
        f"- {verdict}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
            
    return msg

def handle_stock_price(bot, message, dnse_service, shark_service=None, vnstock_service=None, trinity_service=None):
    """Xử lý lệnh /stock (Updated to match Search logic)"""
    try:
        symbol = message.text.split()[1].upper()
        # print(f"User requested stock: {symbol}")
        
        # Send "Searching..." message
        msg_wait = bot.send_message(message.chat.id, f"🔍 Đang phân tích kỹ thuật {symbol}...", parse_mode='Markdown')
        
        # 1. Fetch Realtime Data
        enriched_data = vnstock_service.get_stock_info(symbol)
        if not enriched_data:
             bot.edit_message_text("❌ Không tìm thấy mã này.", chat_id=message.chat.id, message_id=msg_wait.message_id)
             return

        # 2. Trinity Analysis
        # Ensure we pass the enriched data to Trinity calculator if possible, 
        # but TrinityAnalyzer largely fetches its own data.
        # Check get_enriched_trinity_analysis implementation.
        
        trinity_analysis_result = get_enriched_trinity_analysis(
            symbol, trinity_service, vnstock_service, 
            shark_service, bot, message.chat.id
        )
        
        # DEBUG: Print keys to see what we got
        # print(f"DEBUG TRINITY KEYS: {trinity_analysis_result.keys()}")
        
        # get_enriched_trinity_analysis returns a DICT.
        # STRUCTURE CONFIRMATION NEEDED. 
        # Typically it returns: { 'enriched_data': ..., 'trend': ..., 'adx': ... }
        # IF IT DOES NOT return 'enriched_data' inside, we must rely on 'enriched_data' fetched in step 1.
        
        # Let's inspect 'trinity_analysis_result'. 
        # If it contains flat keys like 'trend', 'adx_status', we pass it as 'trinity_data'.
        
        # FIX: The previous code was passing 'trinity_analysis['enriched_data']' which might fail 
        # if the key didn't exist, causing the entire block to crash or return empty?
        # Actually the previous code (before I touched it) was working.
        # My recent change:
        # analysis = get_enriched_trinity_analysis(...)
        # reply_msg = format_stock_reply(enriched_data, shark_service, analysis)
        
        # ISSUE: 'enriched_data' passed to format_stock_reply MUST contain 'avg_vol_5d'.
        # vnstock_service.get_stock_info returns it.
        # Check if 'avg_vol_5d' is 0 or None.
        
        if enriched_data.get('avg_vol_5d') == 0:
            # Try to populate it from Trinity Analysis if available
            if trinity_analysis_result.get('vol_avg'):
                enriched_data['avg_vol_5d'] = trinity_analysis_result.get('vol_avg')
        
        reply_msg = format_stock_reply(enriched_data, shark_service, trinity_analysis_result)
        bot.delete_message(chat_id=message.chat.id, message_id=msg_wait.message_id)
        bot.send_message(message.chat.id, reply_msg, parse_mode='Markdown')
        
    except IndexError:
        bot.reply_to(message, "⚠️ Vui lòng nhập mã cổ phiếu. Ví dụ: /stock HPG")
    except Exception as e:
        print(f"Stock Handler Error: {e}")
        import traceback
        traceback.print_exc()
        bot.send_message(message.chat.id, "❌ Lỗi hệ thống khi lấy dữ liệu.")
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
    """Show top 20 signals today + 3-day history"""
    try:
        from services.database_service import DatabaseService
        from datetime import datetime, timezone, timedelta

        vn_time = datetime.now(timezone.utc) + timedelta(hours=7)
        today_date = vn_time.strftime("%d/%m")

        # ── Section 1: Top 20 today sorted by signal_count ──
        top_query = """
            SELECT symbol, signal_count, display_time
            FROM watchlist
            WHERE RIGHT(display_time, 5) = %s
            ORDER BY signal_count DESC, entry_time DESC
            LIMIT 20
        """
        top_rows = DatabaseService.execute_query(top_query, (today_date,), fetch=True)

        lines = ["-----------------------------------",
                 f"⭐ **WATCHLIST HÔM NAY** ({today_date}) — Top 20",
                 "-----------------------------------"]

        if top_rows:
            for idx, row in enumerate(top_rows, 1):
                sym = row['symbol']
                count = row['signal_count']
                t = row['display_time']
                time_part = t.split(' ')[0] if t else "?"
                count_str = f" 🔥×{count}" if count > 1 else ""
                lines.append(f"{idx}. **#{sym}**  `{time_part}`{count_str}")
        else:
            lines.append("📭 Chưa có mã nào hôm nay")

        # ── Section 2: 3-day history ──
        lines.append("\n📊 **LỊCH SỬ 3 NGÀY GẦN NHẤT:**")
        lines.append("-----------------------------------")

        hist_query = """
            SELECT date, array_agg(symbol ORDER BY symbol) AS symbols
            FROM watchlist_history
            GROUP BY date
            ORDER BY date DESC
            LIMIT 3
        """
        hist_rows = DatabaseService.execute_query(hist_query, fetch=True)
        if hist_rows:
            for row in hist_rows:
                d = row['date']
                date_label = d.strftime('%d/%m') if hasattr(d, 'strftime') else str(d)
                syms = row['symbols']
                symbols_text = " | ".join([f"#{s}" for s in syms])
                lines.append(f"📅 *{date_label}* — {len(syms)} mã")
                lines.append(f"`{symbols_text}`")
        else:
            lines.append("_(Chưa có lịch sử)_")

        lines.append("-----------------------------------")
        lines.append("💡 Watchlist tự động xóa sau 72h | Lưu Top 20 sau 15:15")

        msg = "\n".join(lines)
        bot.edit_message_text(
            msg,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode='Markdown'
        )

    except Exception as e:
        print(f"Watchlist view error: {e}")
        bot.answer_callback_query(call.id, "❌ Lỗi hiển thị watchlist")

def show_top_symbols(bot, call):
    """Show top symbols by number of unique days they were added to watchlist"""
    try:
        from services.database_service import DatabaseService
        
        # Combine history dates and today's watchlist dates 
        # (entry_time converted to VN date)
        query = """
            WITH combined_data AS (
                SELECT date, symbol
                FROM watchlist_history
                UNION
                SELECT (TO_TIMESTAMP(entry_time) + INTERVAL '7 hours')::date as date, symbol
                FROM watchlist
            )
            SELECT symbol, COUNT(date) as day_count
            FROM combined_data
            GROUP BY symbol
            ORDER BY day_count DESC
            LIMIT 10
        """
        rows = DatabaseService.execute_query(query, fetch=True)
        
        if not rows:
            bot.answer_callback_query(call.id, "❌ Chưa có dữ liệu")
            return
            
        # Get total number of active days across both tables
        count_query = """
            WITH combined_data AS (
                SELECT date, symbol
                FROM watchlist_history
                UNION
                SELECT (TO_TIMESTAMP(entry_time) + INTERVAL '7 hours')::date as date, symbol
                FROM watchlist
            )
            SELECT COUNT(DISTINCT date) as total_days 
            FROM combined_data
        """
        count_res = DatabaseService.execute_query(count_query, fetch=True)
        total_days = count_res[0]['total_days'] if count_res else 0
        
        # Format message
        lines_msg = ["📊 **TOP MÃ XUẤT HIỆN LIÊN TỤC**", "━━━━━━━━━━━━━━━━━━━━━━━━"]
        for idx, row in enumerate(rows, 1):
            symbol = row['symbol']
            day_count = row['day_count']
            medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
            day_text = "ngày" if day_count > 1 else "ngày"
            lines_msg.append(f"{medal} **#{symbol}** — {day_count} {day_text}")
        
        lines_msg.append("━━━━━━━━━━━━━━━━━━━━━━━━")
        lines_msg.append(f"💡 Dựa trên {total_days} phiên giao dịch")
        
        msg = "\n".join(lines_msg)
        bot.edit_message_text(msg, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode='Markdown')
        
    except Exception as e:
        print(f"Top symbols error: {e}")
        bot.answer_callback_query(call.id, "❌ Lỗi thống kê")

def show_today_buy_signals(bot, call, watchlist_service):
    """Show top 20 symbols by signal count today"""
    try:
        from datetime import datetime, timezone, timedelta
        from services.database_service import DatabaseService
        
        vn_time = datetime.now(timezone.utc) + timedelta(hours=7)
        today_display = vn_time.strftime("%d/%m")
        
        # Top 20 mã được báo nhiều nhất hôm nay, không giới hạn chỉ mã có trinity
        query = """
            SELECT 
                symbol, 
                signal_count,
                CAST(COALESCE(trinity_data->>'adx', '0') AS FLOAT) as adx
            FROM watchlist
            WHERE RIGHT(display_time, 5) = %s
            ORDER BY signal_count DESC, adx DESC
            LIMIT 20
        """
        rows = DatabaseService.execute_query(query, (today_display,), fetch=True)
        
        if not rows:
            bot.edit_message_text(
                "🔥 **BUY SIGNAL HÔM NAY**\n━━━━━━━━━━━━━━━━━━━━━━━━\n📭 Chưa có BUY signal nào hôm nay",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode='Markdown'
            )
            return
            
        total_signals = sum(r['signal_count'] for r in rows)
        
        # Format message
        lines_msg = [f"🔥 **BUY SIGNAL HÔM NAY** ({today_display})",
                     "━━━━━━━━━━━━━━━━━━━━━━━━"]
        medals = ["🥇", "🥈", "🥉"]
        for idx, row in enumerate(rows, 1):
            symbol = row['symbol']
            count = row['signal_count']
            adx = row['adx']
            
            medal = medals[idx-1] if idx <= 3 else f"{idx}."
            count_str = f" 🔥×{count}" if count > 1 else ""
            adx_str = f" | ADX {adx:.0f}" if adx > 0 else ""
            lines_msg.append(f"{medal} **#{symbol}**{count_str}{adx_str}")
                
        lines_msg.append("━━━━━━━━━━━━━━━━━━━━━━━━")
        lines_msg.append(f"💎 {len(rows)} mã | {total_signals} tổng tín hiệu hôm nay")
        lines_msg.append("🔄 Tự reset lúc 08:30 sáng hôm sau")
        
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
