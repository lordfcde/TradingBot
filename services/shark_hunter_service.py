import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from services.watchlist_service import WatchlistService

# ==========================================
# CONFIGURATION & CONSTANTS
# ==========================================
CONFIG_FILE = "scanner_config.json"
STATS_FILE = "shark_stats.json"

# Default Constants (Fallback)
DEFAULT_MIN_VALUE = 1_000_000_000  # 1 Billion VND (Production)
DEFAULT_COOLDOWN = 60
DEFAULT_START_TIME = "09:00"  # Market opens at 9:00 AM
MAINTENANCE_INTERVAL = 60
VOLATILITY_THRESHOLD = 5.0  # Alert if price change >= ±5%
MIN_VOLUME_FOR_VOLATILITY = 200_000  # Minimum total volume to trigger volatility alert

class SharkHunterService:
    def __init__(self, bot, vnstock_service=None):
        self.bot = bot
        self.alert_chat_id = self._load_bot_config()
        self.watchlist_service = WatchlistService()
        self.vnstock_service = vnstock_service  # For fetching avg volume
        self.trinity_monitor = None
        self.trinity_cache = {} # Cache for Trinity checks (symbol: timestamp)
        self.analyzer = None  # TrinityAnalyzer for hybrid signals
        
        # Load Dictionary Config
        self.config = self._load_dictionary()
        # Value Threshold: JSON > Env > Default
        self.min_value = self.config.get("settings", {}).get("min_shark_value")
        
        # DEBUG: Trace source
        env_val = os.getenv("SHARK_MIN_VALUE")
        print(f"DEBUG: Config Val: {self.min_value}")
        print(f"DEBUG: Env Val: {env_val}")
        print(f"DEBUG: Default Val: {DEFAULT_MIN_VALUE}")
        


        if not self.min_value:
            self.min_value = float(env_val) if env_val else DEFAULT_MIN_VALUE

        # Cooldown: JSON > Default
        self.cooldown = self.config.get("settings", {}).get("cooldown_seconds", DEFAULT_COOLDOWN)
        self.start_time = self.config.get("settings", {}).get("start_time", DEFAULT_START_TIME)
        
        # Thread Synchronization
        self.lock = threading.Lock()
        
        # State Management
        self.alert_history = {}
        self.shark_stats = {}
        self.trade_history = []  # Store detailed trade logs
        self.price_tracker = {}  # Track price changes for all stocks
        self.avg_volume_cache = {}  # Cache avg volume to reduce API calls
        
        # Lunch break tracking (to clear cache and avoid spam)
        self.is_lunch_break = False
        self.last_lunch_check = time.time()
        
        # Daily summary tracking
        self.last_summary_date = None
        self.summary_sent_today = False
        
        self.last_maintenance = time.time()
        self.last_reset_date = (datetime.now(timezone.utc) + timedelta(hours=7)).strftime("%Y-%m-%d")
        self._load_stats()
        
        print(f"🦈 Shark Hunter Service Ready (Dict-Driven)")
        print(f"   - Threshold: {self.min_value/1e9} Billion VND")
        print(f"   - Cooldown: {self.cooldown}s")
        print(f"   - Watchlist: Volume-based (current > 120% of 5d avg)")
        print(f"   - Start Time: {self.start_time}")
        
        # TEST: FOX Monitoring
        self.fox_test_count = 0
        
        # DEBUG: Notify Telegram on Startup to prove Local Version is running
        try:
            if self.bot and self.alert_chat_id:
               timestamp = datetime.now(timezone.utc).strftime('%H:%M:%S')
               startup_msg = f"🦈 Local Bot RESTARTED at {timestamp}.\n✅ Threshold: {self.min_value/1_000_000_000:,.1f} Billion VND\n(Alerts < 1B are from old Cloud version)"
               self.bot.send_message(self.alert_chat_id, startup_msg)
        except Exception as e:
            print(f"⚠️ Could not send startup msg: {e}")
        
    def set_trinity_monitor(self, monitor):
        """Inject Trinity Monitor dependency"""
        self.trinity_monitor = monitor
        print("✅ Shark Hunter: Trinity Monitor connected.")

    def set_analyzer(self, analyzer):
        """Inject TrinityAnalyzer for hybrid Shark+Trinity signals"""
        self.analyzer = analyzer
        print("✅ Shark Hunter: TrinityAnalyzer connected (Hybrid Mode).")
        
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
        # 1. Try JSON Config (Local)
        try:
            path = os.path.join(os.path.dirname(os.path.dirname(__file__)), CONFIG_FILE)
            if os.path.exists(path):
                with open(path, 'r') as f:
                    return json.load(f).get("chat_id")
        except: pass
        
        # 2. Try Env (Render)
        env_chat_id = os.getenv("SHARK_CHAT_ID") or os.getenv("ADMIN_CHAT_ID")
        if env_chat_id:
            try:
                return int(env_chat_id)
            except:
                return env_chat_id
                
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
        """Process real-time tick data for Shark detection"""
        try:
            # print(f"🔹 DEBUG: Tick received: {payload.get('symbol')}")  # Uncomment to debug stream
            # Check and clear cache during lunch break
            self._check_lunch_break()
            
            self._do_maintenance()
            symbol = payload.get("symbol")
            if not symbol: return
            
            # DEBUG: Print Symbol to verify stream
            print(f"Tick received: {symbol}", end="\r")

            # Time Check
            # Time Check (Strict Trading Hours)
            # FIX: Render runs on UTC, must convert to UTC+7
            utc_now = datetime.now(timezone.utc)
            vn_now = utc_now + timedelta(hours=7)
            current_hm = vn_now.strftime("%H:%M")
            
            # 1. Start Time Check (09:00 default)
            if current_hm < self.start_time:
                # print(f"⏳ Before Start Time ({self.start_time}). Tick ignored.", end="\r")
                return 

            # 2. End Time Check (15:00 - Stop scanning)
            # Allow up to 15:15 for ATC/Run-off, then hard stop.
            if current_hm > "15:15":
                # print(f"🛑 After Market Close (15:00). Tick ignored.", end="\r")
                return

            # Value Extraction (Dictionary Compatible + Fallbacks)
            raw_vol = int(
                payload.get("matchQuantity", 0) or 
                payload.get("matchVolume", 0) or 
                payload.get("matchQtty", 0) or 
                payload.get("lastVol", 0) or 
                payload.get("vol", 0) or 0
            )
            # User Correction: Unit is already in shares/lots (No need to multiply by 100)
            vol = raw_vol
            # Extract Data
            try:
                # DEBUG: Print FULL PAYLOAD to see keys
                # print(f"🔹 RAW PAYLOAD: {payload}") 

                price = float(payload.get("lastPrice", 0) or payload.get("matchPrice", 0) or payload.get("price", 0))
                vol = float(payload.get("lastVol", 0) or payload.get("matchVol", 0) or payload.get("vol", 0) or payload.get("matchQuantity", 0))
                
                total_vol = float(payload.get("totalVolumeTraded", 0) or payload.get("accumulatedVol", 0) or 0) * 10
                change_pc = float(payload.get("changedRatio", 0) or payload.get("changePc", 0) or 0)
            except ValueError:
                # If conversion fails (e.g. empty string), skip
                return

            match_time_str = payload.get("time") # HH:mm:ss format often

            # DEBUG: Print every tick value to see what's happening
            # real_price logic check
            real_price = price if price > 1000 else price * 1000
            order_value = real_price * vol
            
            # if order_value > 100_000_000: # Only log > 100M to reduce spam but see "near misses"
            # print(f"🔹 TICK: {symbol} | P: {price} | V: {vol} | Val: {order_value:,.0f} | Min: {self.min_value:,.0f} | Keys: {list(payload.keys())}")  
            
            # DEBUG: Log Raw Values for inspection
            # if symbol in ['ITD', 'VSC']:
            #     print(f"DEBUG {symbol}: Raw={raw_vol}, Vol={vol}, Price={price}")

            # Latency Check
            match_time_str = payload.get("time") # Format usually HH:mm:ss
            latency_msg = ""
            if match_time_str:
                try:
                    vn_now = datetime.now(timezone.utc) + timedelta(hours=7)
                    curr_hm_s = vn_now.strftime("%H:%M:%S")
                    # Simple comparison (ignoring date for speed)
                    if match_time_str < curr_hm_s:
                         time_diff = datetime.strptime(curr_hm_s, "%H:%M:%S") - datetime.strptime(match_time_str, "%H:%M:%S")
                         # latency_msg = f"(Latency: {time_diff.seconds}s)"
                except:
                    pass

            # FILTER: Only allow 3-letter Stock Symbols (Removes Warrants/Derivatives)
            if len(symbol) > 3:
                return

            # Price Scaling Logic
            # Note: Volume from DNSE is likely shares (based on PVS example 500 vol = 21M val)
            # Reverting x10 multiplier to fix inflated values
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
                        'last_update': datetime.now(timezone.utc) + timedelta(hours=7),
                        'alerted': False  # Track if we've alerted for this symbol today
                    }
                else:
                    # Update if newer data
                    self.price_tracker[symbol]['change_pc'] = change_pc
                    self.price_tracker[symbol]['price'] = real_price
                    self.price_tracker[symbol]['total_vol'] = total_vol
                    self.price_tracker[symbol]['last_update'] = datetime.now(timezone.utc) + timedelta(hours=7)
                
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



            # DEBUG THRESHOLD (Uncommented for debugging)
            print(f"DEBUG CHECK: {symbol} Val={order_value:,.0f} Min={self.min_value:,.0f} Skip={order_value < self.min_value}")
            if order_value < self.min_value:
                # User Requirement: 1 order must be > min_value. Do not accumulate small orders.
                print(f"  -> Skipped {symbol} (Value < Min)")
                return

            # It is a SHARK order!
            # NEW LOGIC: Check if current volume > 120% of 5-day avg volume
            print(f"🔍 WATCHLIST CHECK: {symbol} - Shark order detected (total_vol: {total_vol:,.0f}) | RawVol: {raw_vol} {latency_msg}")
            
            # Check volume condition for watchlist
            if self.vnstock_service and total_vol > 0:
                try:
                    # Check if we have cached avg volume (cache for 1 hour)
                    cache_key = symbol
                    now = time.time()
                    
                    if cache_key in self.avg_volume_cache:
                        cached_data = self.avg_volume_cache[cache_key]
                        # Cache valid for 1 hour
                        if (now - cached_data['timestamp']) < 3600:
                            avg_vol_5d = cached_data['avg_vol']
                            print(f"  📦 Using cached avg vol for {symbol}: {avg_vol_5d:,.0f}")
                        else:
                            # Cache expired, fetch new
                            avg_vol_5d = self._fetch_avg_volume(symbol)
                    else:
                        # No cache, fetch
                        avg_vol_5d = self._fetch_avg_volume(symbol)
                    
                    if avg_vol_5d > 0:
                        volume_threshold = avg_vol_5d * 1.2  # 120% of avg
                        vol_ratio = (total_vol / avg_vol_5d) * 100
                        
                        print(f"  📊 {symbol}: Current vol = {total_vol:,.0f}, Avg 5d = {avg_vol_5d:,.0f} ({vol_ratio:.1f}%)")
                        
                        if total_vol >= volume_threshold:
                            self.watchlist_service.add_to_watchlist(symbol)
                            print(f"🔥 WATCHLIST ADDED: {symbol} - Volume {vol_ratio:.1f}% of avg (>{120}%)")
                        else:
                            print(f"  ⚠️ {symbol} volume too low for watchlist ({vol_ratio:.1f}% < 120%)")
                    else:
                        print(f"  ⚠️ Could not get avg volume for {symbol}, skipping watchlist check")
                        
                except Exception as e:
                    print(f"  ❌ Watchlist volume check error for {symbol}: {e}")
            else:
                if not self.vnstock_service:
                    print(f"  ⚠️ vnstock service not available, cannot check volume")
            
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
            
            # 5. Hybrid Analysis (Async) — Shark + Trinity
            if self.analyzer:
                threading.Thread(
                    target=self._run_hybrid_analysis,
                    args=(symbol, real_price, change_pc, total_vol, order_value, vol, side),
                    daemon=True
                ).start()
            elif side == "Buy" and self.trinity_monitor:
                # Fallback to old trinity check if analyzer not set
                threading.Thread(target=self._check_trinity_signal, args=(symbol,), daemon=True).start()


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
        # FIX: VN Time
        vn_now = datetime.now(timezone.utc) + timedelta(hours=7)
        timestamp = vn_now.strftime("%H:%M:%S")
        self.trade_history.append({
            'time': timestamp,
            'symbol': symbol,
            'value': value,
            'change': change_pc,
            'side': side
        })
        # Keep last 200 trades (increased for better watchlist tracking)
        if len(self.trade_history) > 200:
            self.trade_history.pop(0)

        # Persistence: Save immediately
        self._save_stats()

    def _fetch_avg_volume(self, symbol):
        """
        Fetch 5-day average volume from vnstock API.
        Caches result for 1 hour to reduce API calls.
        
        Returns:
            int: 5-day average volume or 0 if error
        """
        try:
            if not self.vnstock_service:
                return 0
            
            # Get stock data with avg_vol_5d
            stock_data = self.vnstock_service.get_stock_info(symbol)
            
            if stock_data and 'avg_vol_5d' in stock_data:
                avg_vol = stock_data['avg_vol_5d']
                
                # Cache the result
                self.avg_volume_cache[symbol] = {
                    'avg_vol': avg_vol,
                    'timestamp': time.time()
                }
                
                print(f"  📥 Fetched avg vol for {symbol}: {avg_vol:,.0f} (cached for 1h)")
                return avg_vol
            else:
                print(f"  ⚠️ No avg_vol_5d data for {symbol}")
                return 0
                
        except Exception as e:
            print(f"  ❌ Error fetching avg volume for {symbol}: {e}")
            return 0


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
        vn_now = datetime.now(timezone.utc) + timedelta(hours=7)
        msg += f"🕒 Cập nhật: {vn_now.strftime('%H:%M:%S')}\n"
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
        
        return msg

    def get_volatility_report(self):
        return "⚠️ Tính năng Biến Động Mạnh đã được tắt theo yêu cầu."


    def send_alert(self, symbol, price, change_pc, total_vol, order_value, vol, side="Unknown"):
        print(f"🔍 DEBUG: send_alert called for {symbol}. ChatID: {self.alert_chat_id}")
        if not self.alert_chat_id:
            print("❌ Alert Chat ID is MISSING inside send_alert!")
            return

        icon = "📈" if change_pc >= 0 else "📉"
        val_billion = order_value / 1_000_000_000
        vn_now = datetime.now(timezone.utc) + timedelta(hours=7)
        time_str = vn_now.strftime("%H:%M:%S")
        
        # Compact horizontal format with pipe separators
        msg = (
            f"🦈 #{symbol} | 💰 {val_billion:.1f}T | "
            f"📦 {vol:,.0f} cp | 💵 {price:,.0f} ({change_pc:+.2f}% {icon}) | "
            f"📊 Vol: {total_vol:,.0f} | 🕐 {time_str}"
        )
        
        try:
            print(f"📤 Attempting to send TG message to {self.alert_chat_id}...")
            self.bot.send_message(self.alert_chat_id, msg) # Removed parse_mode risk
            print(f"✅ Alert Sent for {symbol}")
        except Exception as e:
            print(f"❌ SEND ERROR: {e}")

    def _send_daily_summary(self):
        """Send daily watchlist summary at end of trading day (15:15)"""
        if not self.alert_chat_id:
            return
        
        try:
            # Get today's watchlist entries
            watchlist = self.watchlist_service.get_active_watchlist()
            
            # Filter for entries added today
            from datetime import datetime
            vn_now = datetime.now(timezone.utc) + timedelta(hours=7)
            today = vn_now.strftime("%Y-%m-%d")
            today_symbols = []
            
            for entry in watchlist:
                entry_time = entry.get('entry_time', 0)
                entry_date = datetime.fromtimestamp(entry_time).strftime("%Y-%m-%d")
                if entry_date == today:
                    today_symbols.append(entry['symbol'])
            
            if today_symbols:
                # Format as horizontal list
                symbols_text = " | ".join([f"#{sym}" for sym in today_symbols])
                
                # Save to history file
                history_file = "watchlist_history.txt"
                log_line = f"{vn_now.strftime('%Y-%m-%d %H:%M')} | {len(today_symbols)} mã | {symbols_text}\n"
                
                try:
                    with open(history_file, 'a', encoding='utf-8') as f:
                        f.write(log_line)
                    print(f"💾 Saved to {history_file}")
                except Exception as e:
                    print(f"⚠️ Could not save to history file: {e}")
                
                # Send Telegram message
                msg = (
                    f"📊 <b>WATCHLIST HÔM NAY ({len(today_symbols)} mã)</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"{symbols_text}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"💎 Tất cả đều có rating <b>BUY</b> (Mua mạnh)\n"
                    f"⏰ Tóm tắt cuối phiên {vn_now.strftime('%d/%m/%Y')}\n"
                    f"💾 Đã lưu vào file lịch sử"
                )
                self.bot.send_message(self.alert_chat_id, msg, parse_mode='HTML')
                print(f"📊 Daily summary sent: {len(today_symbols)} symbols")
            else:
                print(f"📊 No watchlist entries today - skipping summary")
                
        except Exception as e:
            print(f"❌ Daily summary error: {e}")

    def _send_volatility_alert(self, symbol, change_pc, price, total_vol, direction, icon):
        """Send alert for high volatility stock movements."""
        # DISABLED AS PER USER REQUEST (Too much noise / low liquidity)
        pass 
        # Original logic removed to stop alerts

    def _run_hybrid_analysis(self, symbol, price, change_pc, total_vol, order_value, vol, side):
        """
        Hybrid Shark + Trinity: Run TrinityAnalyzer on 15m data after shark detection.
        Sends premium HTML SUPER SIGNAL alert.
        """
        try:
            now = time.time()

            # 1. Cache check (avoid API spam: 60s cache per symbol)
            # We skip cache for Judgement because Market Context might change? 
            # No, Market Context (MA20) is daily. Real-time index is fast.
            # But cache TrinityLite is fine.
            # Let's perform Judge call fresh to ensure context is verified.
            
            shark_payload = {
                'price': price,
                'change_pc': change_pc,
                'total_vol': total_vol,
                'order_value': order_value,
                'vol': vol,
                'side': side
            }
            
            print(f"⚖️ TRINITY JUDGE: Judging {symbol}...")
            result = self.analyzer.judge_signal(symbol, shark_payload)
            
            if result['approved']:
                # Send BREAKOUT Alert (High Quality)
                if self.alert_chat_id:
                    self.bot.send_message(self.alert_chat_id, result['message'], parse_mode='Markdown')
                    print(f"🚀 BREAKOUT ALERT SENT: {symbol}")
                
                # Add to Watchlist
                self.watchlist_service.add_enriched(symbol, shark_payload, result['analysis'])
                
            else:
                # REJECTED by Judge -> Send RAW SHARK STREAM (Sensitivity Test)
                # User request: "muốn một luồng... chuyên nhận lệnh cá mập... kiểm tra độ nhạy"
                # Logic: If order > 1B (which it is to get here), send Raw Alert with Warning.
                
                print(f"⛔ {symbol} REJECTED by Judge: {result['reason']}")
                
                if self.alert_chat_id:
                    # Construct Raw Message
                    val_billion = order_value / 1_000_000_000
                    side_text = "MUA" if side == "Buy" else "BÁN"
                    icon = "🟢" if side == "Buy" else "🔴"
                    
                    raw_msg = (
                        f"🦈 **SHARK BITE (RAW): #{symbol}**\n"
                        f"{icon} **{side_text} {val_billion:.1f} Tỷ** | Giá: `{price:,.0f}` ({change_pc:+.2f}%)\n"
                        f"⚠️ *Judge Reject: {result['reason']}*"
                    )
                    self.bot.send_message(self.alert_chat_id, raw_msg, parse_mode='Markdown')
                    print(f"🦈 RAW ALERT SENT: {symbol}")

        except Exception as e:
            print(f"❌ Hybrid Analysis Error for {symbol}: {e}")
            import traceback
            traceback.print_exc()

    def send_super_signal(self, symbol, price, change_pc, order_value, vol, side, analysis):
        """
        Send premium HTML SUPER SIGNAL alert combining Shark + Trinity data.
        (Detailed format - already filtered by Trinity)
        """
        if not self.alert_chat_id:
            return

        try:
            rating = analysis.get('rating', 'WATCH')
            error  = analysis.get('error')

            # ── Shark section ───────────────────────────────
            val_billion = order_value / 1_000_000_000
            pct_icon = "📈" if change_pc >= 0 else "📉"
            side_text = "MUA" if side == "Buy" else "BÁN" if side == "Sell" else "?"

            # ── Trinity section ─────────────────────────────
            if error:
                trend_text = f"⚠️ Lỗi: {error}"
                cmf_text = "N/A"
                rsi_text = "N/A"
            else:
                # Trend with text explanation
                trend_raw = analysis.get('trend', 'N/A')
                if 'UPTREND' in trend_raw:
                    trend_text = "🟢 XU HƯỚNG TĂNG (Giá > EMA50)"
                elif 'SIDEWAY' in trend_raw:
                    trend_text = "🟡 XU HƯỚNG NGANG (Sideway)"
                else:
                    trend_text = "🔴 XU HƯỚNG GIẢM (Giá < EMA50)"

                # CMF with text explanation
                cmf_val = analysis.get('cmf', 0)
                if cmf_val > 0.1:
                    cmf_text = f"🟢 DÒNG TIỀN VÀO MẠNH ({cmf_val:.3f})"
                elif cmf_val > 0:
                    cmf_text = f"🟢 DÒNG TIỀN VÀO NHẸ ({cmf_val:.3f})"
                else:
                    cmf_text = f"🔴 DÒNG TIỀN RA ({cmf_val:.3f})"

                rsi_val = analysis.get('rsi', 0)
                if rsi_val > 70:
                    rsi_text = f"🔴 QUÁ MUA: {rsi_val:.1f}"
                elif rsi_val > 50:
                    rsi_text = f"🟢 MẠNH: {rsi_val:.1f}"
                elif rsi_val > 30:
                    rsi_text = f"🟡 TRUNG LẬP: {rsi_val:.1f}"
                else:
                    rsi_text = f"🟢 QUÁ BÁN: {rsi_val:.1f}"

            # ── Rating with text ────────────────────────────
            if rating == "BUY":
                rating_text = "💎 MUA MẠNH"
            else:
                rating_text = "👀 THEO DÕI"

            vn_now = datetime.now(timezone.utc) + timedelta(hours=7)
            time_str = vn_now.strftime("%H:%M:%S")
            cooldown_min = self.cooldown // 60 if self.cooldown >= 60 else 1

            # Detailed multi-line format for filtered signals
            msg = (
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💎 <b>SUPER SIGNAL: #{symbol}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🦈 <b>CÁ MẬP PHÁT HIỆN (Real-time)</b>\n"
                f"• Loại lệnh: <b>{side_text}</b>\n"
                f"• Giá trị lệnh: <b>{val_billion:,.1f} TỶ VNĐ</b>\n"
                f"• Khối lượng: {vol:,.0f} cp\n"
                f"• Giá khớp: {price:,.0f} ({change_pc:+.2f}% {pct_icon})\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🧠 <b>PHÂN TÍCH TRINITY (15M)</b>\n"
                f"• {trend_text}\n"
                f"• {cmf_text}\n"
                f"• RSI(14): {rsi_text}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎯 <b>KẾT LUẬN: {rating_text}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⏰ {time_str} | ⏳ Cooldown: {cooldown_min}p | ✅ Đã lưu Watchlist"
            )

            self.bot.send_message(self.alert_chat_id, msg, parse_mode='HTML')
            print(f"💎 SUPER SIGNAL sent: {symbol} — {rating}")

        except Exception as e:
            print(f"❌ send_super_signal error for {symbol}: {e}")

    def _check_trinity_signal(self, symbol):
        """
        Legacy Trinity check (fallback when analyzer is not set).
        """
        try:
            if not self.trinity_monitor:
                return

            now = time.time()
            cached = self.trinity_cache.get(symbol)
            signal_data = None

            if cached and (now - cached['time'] < 60):
                signal_data = cached['data']
            else:
                signal_data = self.trinity_monitor.get_analysis(symbol)
                self.trinity_cache[symbol] = {'time': now, 'data': signal_data}

            if signal_data and signal_data.get('signal'):
                sig_name = signal_data['signal']
                self.watchlist_service.add_to_watchlist(symbol)

                msg = (
                    f"🦈🚀 <b>CÁ MẬP + TRINITY CONFIRMED!</b>\n"
                    f"#{symbol}\n"
                    f"💎 Tín hiệu: {sig_name}\n"
                    f"🌊 Dòng tiền: {signal_data.get('cmf',0):.2f} ({signal_data.get('cmf_status','')})\n"
                    f"✅ Đã thêm vào Watchlist!"
                )
                self.bot.send_message(self.alert_chat_id, msg, parse_mode='HTML')

        except Exception as e:
            print(f"❌ Trinity Check Error for {symbol}: {e}")


    # Helper Methods
    def _check_lunch_break(self):
        """Check if market is in lunch break and clear cache if needed"""
        # Only check every 60 seconds to avoid overhead
        if time.time() - self.last_lunch_check < 60:
            return
        
        self.last_lunch_check = time.time()
        
        try:
            from utils.market_hours import MarketHours
            
            is_lunch = MarketHours.is_lunch_break()
            
            # If entering lunch break, clear caches
            if is_lunch and not self.is_lunch_break:
                print("🍱 Entering lunch break - Clearing alert cache to avoid spam")
                with self.lock:
                    self.alert_history.clear()
                    if self.trinity_monitor:
                        self.trinity_monitor.alert_history.clear()
                
                # Filter watchlist by liquidity (remove illiquid stocks)
                print("🔍 Filtering watchlist by liquidity before afternoon session...")
                self.watchlist_service.filter_by_liquidity(min_avg_volume=250000)
                
                self.is_lunch_break = True
            
            # If exiting lunch break
            elif not is_lunch and self.is_lunch_break:
                print("✅ Exiting lunch break - Resuming monitoring")
                self.is_lunch_break = False
                
        except Exception as e:
            print(f"⚠️ Lunch break check error: {e}")
    
    def _do_maintenance(self):
        try:
            now = time.time()
            if now - self.last_maintenance > 60:
                self.last_maintenance = now
                self._save_stats()
                
                # Daily Reset
                vn_now = datetime.now(timezone.utc) + timedelta(hours=7)
                today = vn_now.strftime("%Y-%m-%d")
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
        dt_now = datetime.now(timezone.utc) + timedelta(hours=7) # FIX: Use VN Time
        today_str = dt_now.strftime("%Y-%m-%d")
        is_reset_time = (dt_now.hour == 8 and dt_now.minute >= 30) or (dt_now.hour > 8)

        if is_reset_time and self.last_reset_date != today_str:
            print("🧹 Daily Stats Reset")
            self.shark_stats.clear()
            self.alert_history.clear()
            self.last_reset_date = today_str
            self.summary_sent_today = False  # Reset summary flag
        
        # Send Daily Watchlist Summary at 15:15 (after market close)
        if dt_now.hour == 15 and dt_now.minute >= 15:
            if not self.summary_sent_today and today_str != self.last_summary_date:
                # Filter by liquidity before sending summary
                print("🔍 Filtering watchlist by liquidity before daily summary...")
                self.watchlist_service.filter_by_liquidity(min_avg_volume=250000)
                
                self._send_daily_summary()
                self.summary_sent_today = True
                self.last_summary_date = today_str
            self._save_stats()
            
        # Save Stats
        if now - self.last_maintenance > 300: # Save every 5 mins
             self._save_stats()
             
        self.last_maintenance = now

    def _save_stats(self):
        try:
            path = os.path.join(os.path.dirname(os.path.dirname(__file__)), STATS_FILE)
            with open(path, 'w') as f:
                vn_now = datetime.now(timezone.utc) + timedelta(hours=7)
                json.dump({"date": vn_now.strftime("%Y-%m-%d"), "stats": self.shark_stats}, f)
        except: pass

    def _load_stats(self):
        try:
            path = os.path.join(os.path.dirname(os.path.dirname(__file__)), STATS_FILE)
            if os.path.exists(path):
                with open(path, 'r') as f:
                    data = json.load(f)
                    vn_now = datetime.now(timezone.utc) + timedelta(hours=7)
                    if data.get('date') == vn_now.strftime("%Y-%m-%d"):
                        self.shark_stats = data.get('stats', {})
        except: pass

    def process_ohlc(self, payload):
        pass

    def check_rsi_watchlist(self, symbol, rsi, current_vol, avg_vol_5d):
        """
        Check if stock should be added to watchlist based on RSI + volume.
        Logic:
        - RSI > 70 (Overbought) OR RSI < 30 (Oversold)
        - Current Volume > 120% of 5-day Avg Volume
        
        Args:
            symbol (str): Stock symbol
            rsi (float): RSI value
            current_vol (int): Current total volume
            avg_vol_5d (int): 5-day average volume
            
        Returns:
            bool: True if added, False otherwise
        """
        if rsi is None or avg_vol_5d == 0:
            return False
            
        try:
            # Check RSI condition
            is_overbought = rsi > 70
            is_oversold = rsi < 30
            
            if not (is_overbought or is_oversold):
                return False
                
            # Check Volume condition
            # Volume > 120% of avg
            vol_ratio = current_vol / avg_vol_5d
            is_high_volume = vol_ratio > 1.2
            
            if is_high_volume:
                # Add to watchlist
                self.watchlist_service.add_to_watchlist(symbol)
                
                signal = "QUÁ MUA" if is_overbought else "QUÁ BÁN"
                print(f"🔥 RSI WATCHLIST ADDED: {symbol} - RSI {rsi:.1f} ({signal}) + Vol {vol_ratio*100:.0f}%")
                return True
                
            return False
            
        except Exception as e:
            print(f"❌ Error checking RSI watchlist for {symbol}: {e}")
            return False
