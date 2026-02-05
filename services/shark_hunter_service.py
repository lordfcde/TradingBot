import json
import os
import threading
import time
from datetime import datetime, timedelta
from services.watchlist_service import WatchlistService

# ==========================================
# CONFIGURATION & CONSTANTS
# ==========================================
CONFIG_FILE = "scanner_config.json"
STATS_FILE = "shark_stats.json"

# Default Constants (Fallback)
DEFAULT_MIN_VALUE = 1_000_000_000  # 1 Billion VND
DEFAULT_COOLDOWN = 60
DEFAULT_START_TIME = "09:00"  # Market opens at 9:00 AM
MAINTENANCE_INTERVAL = 60
VOLATILITY_THRESHOLD = 5.0  # Alert if price change >= ±5%
MIN_VOLUME_FOR_VOLATILITY = 200_000  # Minimum total volume to trigger volatility alert

class SharkHunterService:
    def __init__(self, bot):
        self.bot = bot
        self.alert_chat_id = self._load_bot_config()
        self.watchlist_service = WatchlistService()
        
        # Load Dictionary Config
        self.config = self._load_dictionary()
        self.min_value = self.config.get("settings", {}).get("min_shark_value", DEFAULT_MIN_VALUE)
        self.cooldown = self.config.get("settings", {}).get("alert_cooldown_seconds", DEFAULT_COOLDOWN)
        self.cooldown = self.config.get("settings", {}).get("cooldown_seconds", DEFAULT_COOLDOWN)
        self.start_time = self.config.get("settings", {}).get("start_time", DEFAULT_START_TIME)
        
        # Thread Synchronization
        self.lock = threading.Lock()
        
        # State Management
        self.alert_history = {}
        self.shark_stats = {}
        self.trade_history = []  # Store detailed trade logs
        self.price_tracker = {}  # Track price changes for all stocks
        
        self.last_maintenance = time.time()
        self.last_reset_date = datetime.now().strftime("%Y-%m-%d")
        self._load_stats()
        
        print(f"🦈 Shark Hunter Service Ready (Dict-Driven)")
        print(f"   - Threshold: {self.min_value/1e9} Billion VND")
        print(f"   - Cooldown: {self.cooldown}s")
        print(f"   - Start Time: {self.start_time}")
        
        # TEST: FOX Monitoring
        self.fox_test_count = 0
        
    def enable_alerts(self, chat_id):
        """Enable alerts for this chat ID and verify stream subscription."""
        self.alert_chat_id = chat_id
        
        # Save to file
        with open("scanner_config.json", "w") as f:
            json.dump({"chat_id": chat_id, "active": True}, f)
            
        return True

    def send_test_alert(self):
        """Send a forced test message to verify Telegram connectivity."""
        if not self.alert_chat_id:
            print("⚠️ No Chat ID for Test Alert.")
            return
        
        try:
            print(f"🧪 Sending TEST ALERT to {self.alert_chat_id}...")
            self.bot.send_message(self.alert_chat_id, "🔔 **TEST ALERT**: Bot connected & scanning!\n\nNếu bạn thấy tin nhắn này, hệ thống cảnh báo đang hoạt động tốt. 🦈", parse_mode='Markdown')
            print("✅ TEST ALERT SENT SUCCESS.")
        except Exception as e:
            print(f"❌ TEST ALERT FAILED: {e}")

    def _load_dictionary(self):
        try:
            path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "MaterialsDnse", "Dictionary.json")
            if os.path.exists(path):
                with open(path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"⚠️ Failed to load Dictionary.json: {e}")
        return {}

    def _load_bot_config(self):
        try:
            path = os.path.join(os.path.dirname(os.path.dirname(__file__)), CONFIG_FILE)
            if os.path.exists(path):
                with open(path, 'r') as f:
                    return json.load(f).get("chat_id")
        except: return None
        return None

    def set_alert_chat_id(self, chat_id):
        self.alert_chat_id = chat_id
        try:
            path = os.path.join(os.path.dirname(os.path.dirname(__file__)), CONFIG_FILE)
            with open(path, 'w') as f:
                json.dump({"chat_id": chat_id}, f)
        except: pass
        self.bot.send_message(chat_id, "🦈 **Shark Hunter Activated (Senior Logic)**\nMonitoring > 1 Billion VND...", parse_mode='Markdown')

    # ==========================================
    # CORE LOGIC
    # ==========================================
    def process_tick(self, payload):
        try:
            self._do_maintenance()
            symbol = payload.get("symbol")
            if not symbol: return
            
            # DEBUG: Print Symbol to verify stream
            print(f"Tick received: {symbol}", end="\r")

            # Time Check
            current_hm = datetime.now().strftime("%H:%M")
            if current_hm < self.start_time:
                # pass # Bypass time check for FOX test? 
                # Better to keep time check active, user is testing now (active session).
                pass

            # Value Extraction (Dictionary Compatible + Fallbacks)
            raw_vol = int(
                payload.get("matchQuantity", 0) or 
                payload.get("matchVolume", 0) or 
                payload.get("matchQtty", 0) or 
                payload.get("lastVol", 0) or 
                payload.get("vol", 0) or 0
            )
            # User Correction: Unit is 10 shares (Step 1629)
            vol = raw_vol * 10
            
            price = float(payload.get("matchPrice", 0) or payload.get("lastPrice", 0))
            total_vol = int(payload.get("totalVolumeTraded", 0) or payload.get("totalVol", 0))
            change_pc = float(payload.get("changedRatio", 0) or payload.get("changePc", 0))
            
            # FILTER: Only allow 3-letter Stock Symbols (Removes Warrants/Derivatives)
            if len(symbol) > 3:
                return

            # Price Scaling Logic
            real_price = price if price > 1000 else price * 1000
            order_value = real_price * vol

            # Extract Side (1=Buy, 2=Sell) - Stock Info doesn't have this field
            side_code = payload.get("side")
            if side_code == 1:
                side = "Buy"
            elif side_code == 2:
                side = "Sell"
            else:
                side = "Unknown"  # Stock Info topic doesn't provide side

            # Track price changes for all stocks (for volatility monitoring)
            if change_pc != 0:  # Only track if we have price change data
                is_new_symbol = symbol not in self.price_tracker
                
                if is_new_symbol:
                    self.price_tracker[symbol] = {
                        'change_pc': change_pc,
                        'price': real_price,
                        'total_vol': total_vol,  # Track total volume
                        'last_update': datetime.now(),
                        'alerted': False  # Track if we've alerted for this symbol today
                    }
                else:
                    # Update if newer data
                    self.price_tracker[symbol]['change_pc'] = change_pc
                    self.price_tracker[symbol]['price'] = real_price
                    self.price_tracker[symbol]['total_vol'] = total_vol
                    self.price_tracker[symbol]['last_update'] = datetime.now()
                
                # Check for HIGH VOLATILITY and send alert
                # Only alert if volume >= 200k to avoid low liquidity stocks
                if abs(change_pc) >= VOLATILITY_THRESHOLD and total_vol >= MIN_VOLUME_FOR_VOLATILITY:
                    # Check cooldown to avoid spam
                    alert_key = f"volatility_{symbol}"
                    now = time.time()
                    last_alert = self.alert_history.get(alert_key, 0)
                    
                    # Only alert once per hour for volatility
                    if (now - last_alert) > 3600:  # 1 hour cooldown
                        self.alert_history[alert_key] = now
                        
                        # Send volatility alert
                        direction = "TĂNG" if change_pc > 0 else "GIẢM"
                        icon = "📈" if change_pc > 0 else "📉"
                        self._send_volatility_alert(symbol, change_pc, real_price, total_vol, direction, icon)


            if order_value < self.min_value:
                # User Requirement: 1 order must be > min_value. Do not accumulate small orders.
                return

            # It is a SHARK order!
            # 1. Count trend FIRST (including current trade)
            # User Request: At least 3 orders in 5 MINUTES
            valid_trend_count = 1  # Start with 1 for current trade
            fmt = "%H:%M:%S"
            now_dt = datetime.now()
            
            # Look back in history (reversed for speed)
            for trade in reversed(self.trade_history):
                if trade['symbol'] == symbol:
                    try:
                        t_dt = datetime.strptime(trade['time'], fmt).replace(year=now_dt.year, month=now_dt.month, day=now_dt.day)
                        # Handle potential day wrap (unlikely for intraday bot)
                        delta = (now_dt - t_dt).total_seconds()
                        if 0 <= delta <= 300:  # 5 Minutes (300 seconds)
                            valid_trend_count += 1
                        else:
                            # If we hit a trade older than 5m, stop searching
                            if delta > 300: break 
                    except: pass
            
            # Add to watchlist if 3+ shark trades in 5 mins
            if valid_trend_count >= 3:
                self.watchlist_service.add_to_watchlist(symbol)
                print(f"🔥 HOT TREND: {symbol} in Watchlist ({valid_trend_count} sharks/5m)")
            
            # 2. Update Statistics and add to history AFTER counting
            self._update_stats(symbol, order_value, change_pc, side)
            
            # DEBUG: Log detected shark
            print(f"🦈 SHARK DETECTED: {symbol} ({side}) - {order_value:,.0f} VND")

            # 3. Check Cooldown for Alert (Separate for Buy vs Sell)
            now = time.time()
            alert_key = f"{symbol}_{side}"
            last_alert = self.alert_history.get(alert_key, 0)
            
            # User Request: Cooldown check restored (1 min+)
            if now - last_alert < self.cooldown:
               return

            # 4. Trigger Alert
            self.alert_history[alert_key] = now
            self.send_alert(symbol, real_price, change_pc, total_vol, order_value, vol, side)

        except Exception as e:
            print(f"❌ Tick Processing Error: {e}")
            import traceback
            traceback.print_exc()

    def _update_stats(self, symbol, value, change_pc, side="Unknown"):
        if symbol not in self.shark_stats:
            self.shark_stats[symbol] = {
                'total_shark_val': 0,
                'total_buy_val': 0,
                'total_sell_val': 0,
                'count': 0,
                'last_price_change': 0
            }
        
        if side == "Buy":
            self.shark_stats[symbol]['total_buy_val'] += value
        elif side == "Sell":
            self.shark_stats[symbol]['total_sell_val'] += value
            
        self.shark_stats[symbol]['total_shark_val'] += value
        self.shark_stats[symbol]['count'] += 1
        self.shark_stats[symbol]['last_price_change'] = change_pc

        # Add to History
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.trade_history.append({
            'time': timestamp,
            'symbol': symbol,
            'value': value,
            'change': change_pc,
            'side': side
        })
        # Keep last 50
        if len(self.trade_history) > 50:
            self.trade_history.pop(0)

        # Persistence: Save immediately
        self._save_stats()

    def get_stats_report(self):
        """Generate a summary report of Shark activity."""
        if not self.shark_stats:
            return "🦈 **Chưa phát hiện Cá Mập nào hôm nay.**"
            
        # Get Top Buyers
        top_buyers = sorted(
            [item for item in self.shark_stats.items() if item[1].get('total_buy_val', 0) > 0],
            key=lambda x: x[1].get('total_buy_val', 0),
            reverse=True
        )[:5]

        # Get Top Sellers
        top_sellers = sorted(
            [item for item in self.shark_stats.items() if item[1].get('total_sell_val', 0) > 0],
            key=lambda x: x[1].get('total_sell_val', 0),
            reverse=True
        )[:5]
        
        msg = "🦈 **THỐNG KÊ CÁ MẬP HÔM NAY** 🦈\n"
        msg += f"🕒 Cập nhật: {datetime.now().strftime('%H:%M:%S')}\n"
        msg += "=============================\n"
        
        if top_buyers:
            msg += "🏆 **TOP GOM HÀNG (MUA):**\n"
            for sym, data in top_buyers:
                val_billion = data['total_buy_val'] / 1_000_000_000
                msg += f"• **{sym}**: {val_billion:.1f} Tỷ 🟢\n"
            msg += "-----------------------------\n"
            
        if top_sellers:
            msg += "📉 **TOP XẢ HÀNG (BÁN):**\n"
            for sym, data in top_sellers:
                val_billion = data['total_sell_val'] / 1_000_000_000
                msg += f"• **{sym}**: {val_billion:.1f} Tỷ 🔴\n"
            msg += "=============================\n"
        msg += "\n📝 **LỆNH GẦN NHẤT:**\n"
        
        recent = list(reversed(self.trade_history))[:15]
        for trade in recent:
            val_billion = trade['value'] / 1_000_000_000
            s = trade.get('side', 'Unknown')
            icon = "🟢 MUA" if s == "Buy" else "🔴 BÁN" if s == "Sell" else "⚪️ ?"
            msg += f"• `{trade['time']}` {icon} **{trade['symbol']}**: {val_billion:.1f} Tỷ\n"
        
        # === PRICE VOLATILITY SECTION ===
        msg += "\n📊 **BIẾN ĐỘNG MẠNH HÔM NAY:**\n"
        msg += "=============================\n"
        
        if self.price_tracker:
            # Get top gainers and losers
            sorted_stocks = sorted(
                self.price_tracker.items(),
                key=lambda x: x[1]['change_pc'],
                reverse=True
            )
            
            # Top 5 Gainers
            gainers = [s for s in sorted_stocks if s[1]['change_pc'] > 0][:5]
            if gainers:
                msg += "📈 **TOP TĂNG MẠNH:**\n"
                for symbol, data in gainers:
                    price_k = data['price'] / 1000
                    msg += f"• **{symbol}**: +{data['change_pc']:.2f}% ({price_k:.1f}k)\n"
            
            # Top 5 Losers
            losers = sorted(
                [s for s in sorted_stocks if s[1]['change_pc'] < 0],
                key=lambda x: x[1]['change_pc']
            )[:5]
            if losers:
                msg += "\n📉 **TOP GIẢM MẠNH:**\n"
                for symbol, data in losers:
                    price_k = data['price'] / 1000
                    msg += f"• **{symbol}**: {data['change_pc']:.2f}% ({price_k:.1f}k)\n"
        else:
            msg += "⏳ Chưa có dữ liệu biến động...\n"
            
        return msg

    def get_volatility_report(self):
        """Generate standalone volatility report for menu."""
        msg = "📊 **BIẾN ĐỘNG MẠNH HÔM NAY**\n"
        msg += f"🕒 Cập nhật: {datetime.now().strftime('%H:%M:%S')}\n"
        msg += "=============================\n"
        
        if self.price_tracker:
            # Get top gainers and losers
            sorted_stocks = sorted(
                self.price_tracker.items(),
                key=lambda x: x[1]['change_pc'],
                reverse=True
            )
            
            # Top 10 Gainers
            gainers = [s for s in sorted_stocks if s[1]['change_pc'] > 0][:10]
            if gainers:
                msg += "\n📈 **TOP 10 TĂNG MẠNH:**\n"
                for symbol, data in gainers:
                    price_k = data['price'] / 1000
                    vol_k = data.get('total_vol', 0) / 1000
                    msg += f"• **{symbol}**: +{data['change_pc']:.2f}% | {price_k:.1f}k | Vol: {vol_k:.0f}k\n"
            
            # Top 10 Losers
            losers = sorted(
                [s for s in sorted_stocks if s[1]['change_pc'] < 0],
                key=lambda x: x[1]['change_pc']
            )[:10]
            if losers:
                msg += "\n📉 **TOP 10 GIẢM MẠNH:**\n"
                for symbol, data in losers:
                    price_k = data['price'] / 1000
                    vol_k = data.get('total_vol', 0) / 1000
                    msg += f"• **{symbol}**: {data['change_pc']:.2f}% | {price_k:.1f}k | Vol: {vol_k:.0f}k\n"
        else:
            msg += "\n⏳ Chưa có dữ liệu biến động...\n"
            
        return msg


    def send_alert(self, symbol, price, change_pc, total_vol, order_value, vol, side="Unknown"):
        print(f"🔍 DEBUG: send_alert called for {symbol}. ChatID: {self.alert_chat_id}")
        if not self.alert_chat_id:
            print("❌ Alert Chat ID is MISSING inside send_alert!")
            return

        icon = "📈" if change_pc >= 0 else "📉"
        val_billion = order_value / 1_000_000_000
        time_str = datetime.now().strftime("%H:%M:%S")
        
        # Simple title - no buy/sell distinction
        title = "🦈 CÁ MẬP XUẤT HIỆN"

        msg = (
            f"{title} 🕐 {time_str}\n"
            f"#{symbol} - 💰 {val_billion:,.1f} Tỷ VNĐ\n"
            f"=============================\n"
            f"⚡ Chi tiết lệnh:\n"
            f"• Khối lượng: {vol:,.0f} cp\n"
            f"• Giá khớp: {price:,.0f} ({change_pc:+.2f}% {icon})\n"
            f"• Tổng Vol phiên: {total_vol:,.0f}\n"
            f"=============================\n"
            f"⏳ Cooldown: Sẽ không báo lại trong {self.cooldown//60}p"
        )
        
        try:
            print(f"📤 Attempting to send TG message to {self.alert_chat_id}...")
            self.bot.send_message(self.alert_chat_id, msg) # Removed parse_mode risk
            print(f"✅ Alert Sent for {symbol}")
        except Exception as e:
            print(f"❌ SEND ERROR: {e}")

    def _send_volatility_alert(self, symbol, change_pc, price, total_vol, direction, icon):
        """Send alert for high volatility stock movements."""
        if not self.alert_chat_id:
            return
        
        price_k = price / 1000
        vol_k = total_vol / 1000  # Convert to thousands for display
        time_str = datetime.now().strftime("%H:%M:%S")
        
        title = f"📊 BIẾN ĐỘNG MẠNH - {direction}"
        
        msg = (
            f"{title} 🕐 {time_str}\n"
            f"#{symbol} {icon} {change_pc:+.2f}%\n"
            f"=============================\n"
            f"⚡ Chi tiết:\n"
            f"• Giá hiện tại: {price_k:,.1f}k\n"
            f"• Biến động: {change_pc:+.2f}%\n"
            f"• Tổng Vol: {vol_k:,.0f}k cp\n"
            f"=============================\n"
            f"⏳ Cooldown: Sẽ không báo lại trong 1 giờ"
        )
        
        try:
            print(f"📊 Sending VOLATILITY alert for {symbol} ({change_pc:+.2f}%, Vol: {vol_k:.0f}k)")
            self.bot.send_message(self.alert_chat_id, msg)
            print(f"✅ Volatility Alert Sent for {symbol}")
        except Exception as e:
            print(f"❌ VOLATILITY ALERT ERROR: {e}")

    # Helper Methods
    def _do_maintenance(self):
        try:
            now = time.time()
            if now - self.last_maintenance > 60:
                self.last_maintenance = now
                self._save_stats()
                
                # Daily Reset
                today = datetime.now().strftime("%Y-%m-%d")
                if today != self.last_reset_date:
                    self.shark_stats = {}
                    self.alert_history = {}
                    self.last_reset_date = today
                    self._save_stats()
        except Exception as e:
             print(f"Note: Maintenance error {e}")
        
        # Cleanup Alert History (Keep RAM low)
        # Remove entries older than 2 hours (irrelevant for Cooldown)
        expired = [k for k, v in self.alert_history.items() if now - v > 7200]
        for k in expired:
            del self.alert_history[k]
            
        # Daily Reset (08:30)
        dt_now = datetime.now()
        today_str = dt_now.strftime("%Y-%m-%d")
        is_reset_time = (dt_now.hour == 8 and dt_now.minute >= 30) or (dt_now.hour > 8)

        if is_reset_time and self.last_reset_date != today_str:
            print("🧹 Daily Stats Reset")
            self.shark_stats.clear()
            self.alert_history.clear()
            self.last_reset_date = today_str
            self._save_stats()
            
        # Save Stats
        if now - self.last_maintenance > 300: # Save every 5 mins
             self._save_stats()
             
        self.last_maintenance = now

    def _save_stats(self):
        try:
            path = os.path.join(os.path.dirname(os.path.dirname(__file__)), STATS_FILE)
            with open(path, 'w') as f:
                json.dump({"date": datetime.now().strftime("%Y-%m-%d"), "stats": self.shark_stats}, f)
        except: pass

    def _load_stats(self):
        try:
            path = os.path.join(os.path.dirname(os.path.dirname(__file__)), STATS_FILE)
            if os.path.exists(path):
                with open(path, 'r') as f:
                    data = json.load(f)
                    if data.get('date') == datetime.now().strftime("%Y-%m-%d"):
                        self.shark_stats = data.get('stats', {})
        except: pass

    def process_ohlc(self, payload):
        pass
