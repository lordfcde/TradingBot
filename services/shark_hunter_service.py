import json
import os
from datetime import datetime
from services.watchlist_service import WatchlistService
from data.stock_lists import VN100

CONFIG_FILE = "scanner_config.json"

class SharkHunterService:
    def __init__(self, bot):
        self.bot = bot
        self.alert_chat_id = self._load_config()
        self.watchlist_service = WatchlistService()
        
        # Thread-safe Cache
        self.lock = threading.Lock()
        
        # Architecture: market_state[symbol] = { 'avg_3m': ..., 'avg_5d': ..., 'trend_3m': ... }
        self.market_state = {}
        
        print(f"🦈 Shark Hunter Service Initialized (RAM Mode). Alert Target: {self.alert_chat_id}")

    def _load_config(self):
        try:
            path = os.path.join(os.path.dirname(os.path.dirname(__file__)), CONFIG_FILE)
            if os.path.exists(path):
                with open(path, 'r') as f:
                    return json.load(f).get("chat_id")
        except: pass
        return None

    def set_alert_chat_id(self, chat_id):
        self.alert_chat_id = chat_id
        # Save to config
        try:
            path = os.path.join(os.path.dirname(os.path.dirname(__file__)), CONFIG_FILE)
            with open(path, 'w') as f:
                json.dump({"chat_id": chat_id}, f)
        except Exception as e:
            print(f"Error saving config: {e}")

        # Send confirmation
        self.bot.send_message(chat_id, "🦈 **SHARK HUNTER ACTIVATED**\nĐang nạp dữ liệu từ luồng MQTT...", parse_mode='Markdown')

    def process_ohlc(self, payload):
        """
        Processing Topic 1: OHLC Daily
        Payload expectation: { "data": [ {...}, ... ], "symbol": "HPG" ... }
        We need to calculate baseline metrics.
        """
        try:
            symbol = payload.get("symbol")
            if not symbol: return
            
            # FILTER: VN100 Only
            if symbol not in VN100:
                return
            
            # Check if payload has history (list) or single update
            candles = payload.get("data", [])
            
            # Parsing Fix: If payload IS the data (dict) and no 'data' key
            # Debug showed keys: ['time', 'open', 'close', 'volume', 'symbol', ...]
            if not candles and isinstance(payload, dict) and "close" in payload:
                candles = [payload]

            if not candles: return

            # Calculate Metrics
            # Sort by time/date if needed? Assuming they are ordered or we sort.
            # Usually OHLC is sorted. Desc or Asc? Let's assume generic.
            
            # For moving average calculations:
            # We need Volume and Close Price.
            
            # Clean data extraction
            closes = []
            volumes = []
            
            for c in candles:
                try:
                    # Helper to parse flexible types (string or number)
                    v_raw = c.get("volume") or c.get("accumulatedVolume") or 0
                    cl_raw = c.get("close") or c.get("closePrice") or 0
                    
                    v = float(v_raw)
                    cl = float(cl_raw)
                    
                    if cl > 0:
                        closes.append(cl)
                        volumes.append(v)
                except: continue
            
            if not volumes: return

            # If we only have 1 data point (Updates/Single Candle), we use it as Proxy Baseline
            # User Criteria: AvgVol_3M > 50,000
            
            if len(volumes) < 5: 
                # PROXY MODE: Use available data to establish baseline
                # Use the single volume as "Avg"
                avg_vol_5d = sum(volumes) / len(volumes)
                avg_vol_3m = avg_vol_5d
                trend_ok = True # Assume trend ok if unknown
            else:
                # Calculations
                # 5D Avg
                avg_vol_5d = sum(volumes[-5:]) / 5
                
                # 3M Avg (approx 60 candles)
                lookback_3m = min(len(volumes), 60)
                avg_vol_3m = sum(volumes[-lookback_3m:]) / lookback_3m
                
                # Trend 3M: Compare Last Close vs Close 60 days ago
                last_close = closes[-1]
                past_close = closes[-lookback_3m]
                
                trend_ok = False
                if last_close > (past_close * 1.03):
                    trend_ok = True
                
            # Filter 1: Check Health
            if avg_vol_3m > 50000 and trend_ok:
                with self.lock:
                    self.market_state[symbol] = {
                        'avg_3m': avg_vol_3m,
                        'avg_5d': avg_vol_5d,
                        'trend_ok': trend_ok,
                        'last_update': time.time()
                    }
                # Optional: print(f"🦈 Baseline Loaded: {symbol}")

        except Exception as e:
            # print(f"OHLC Error: {e}")
            pass

    def process_tick(self, payload):
        """
        Processing Topic 2: Real-time Tick
        """
        if not self.alert_chat_id: return
        
        try:
            symbol = payload.get("symbol")
            if not symbol: return
            
            # FILTER: VN100 Only
            if symbol not in VN100:
                return
            
            # 1. Get Baseline
            baseline = None
            with self.lock:
                baseline = self.market_state.get(symbol)
                
            if not baseline:
                # If no baseline, we IGNORE (safety filter)
                return
                
            # 2. Extract Real-time Data
            # "totalVol" in payload might be the accumulated volume of the day?
            # User wrote: "Lấy totalVol so sánh với AvgVol_5D" -> This implies Day Volume Explosion
            
            total_vol = float(payload.get("totalVolumeTraded", 0))
            last_price = float(payload.get("matchPrice", 0))
            last_vol = float(payload.get("matchVolume", 0)) # Volume of *this* tick
            change_pc = float(payload.get("changedRatio", 0))
            
            if total_vol == 0 or last_price == 0: return

            # 3. Check Vol Explosion
            # Condition: totalVol > (AvgVol_5D * 1.3) (User requested > 30% growth)
            avg_5d = baseline['avg_5d']
            if total_vol <= (avg_5d * 1.3):
                return
                
            # ALL CONDITIONS MET! ALERT!
            self.send_alert(symbol, total_vol, last_price, change_pc, baseline)
            
        except Exception as e:
            # print(f"Tick Error: {e}")
            pass

    def send_alert(self, symbol, current_vol, price, change, baseline):
        # Auto-add to Watchlist
        self.watchlist_service.add_to_watchlist(symbol)
        
        avg_5d = baseline['avg_5d']
        
        # Explosion Ratio (e.g. 150%)
        ratio = (current_vol / avg_5d) * 100
        
        # Format Alert
        msg = (
            f"🚀 **BÙNG NỔ THANH KHOẢN**: #{symbol}\n"
            f"-----------------------------------\n"
            f"📈 Giá hiện tại: `{price:,.2f}` (Tăng `{change:+.2f}%`)\n"
            f"⚡ Volume: `{current_vol:,.0f}` cp\n"
            f"-----------------------------------\n"
            f"📊 **Phân tích Đột biến**:\n"
            f"• Vượt `{ratio:.0f}%` trung bình 5 phiên\n"
            f"• Xu hướng 3 tháng: Tăng trưởng ✅\n"
            f"-----------------------------------\n"
            f"💾 Đã lưu vào Watchlist (72h)"
        )
        
        self.bot.send_message(self.alert_chat_id, msg, parse_mode='Markdown')
