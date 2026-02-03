import json
import os
import threading
import time
from datetime import datetime, timedelta
from services.watchlist_service import WatchlistService
from data.stock_lists import VN100

CONFIG_FILE = "scanner_config.json"
STATS_FILE = "shark_stats.json"

# Shark Cluster Constants
SHARK_MIN_VAL = 1_000_000_000  # 1 Billion VND
MIN_HIT_COUNT = 3              # 3 Hits to Trigger
CLUSTER_TIMEOUT = 300          # 5 Minutes window
ALERT_COOLDOWN = 1800          # 30 Minutes cooldown
MAINTENANCE_INTERVAL = 60      # Check every minute

class SharkHunterService:
    def __init__(self, bot):
        self.bot = bot
        self.alert_chat_id = self._load_config()
        self.watchlist_service = WatchlistService()
        
        # Thread-safe Cache
        self.lock = threading.Lock()
        
        # Tracker State: {symbol: {'count', 'last_seen', 'last_alert'}}
        self.shark_tracker = {}
        
        # Statistics State: {symbol: {'buy_val': 0, 'sell_val': 0}}
        self.shark_stats = {}
        
        # Load persisted stats
        self._load_stats()
        
        self.last_maintenance = time.time()
        self.last_reset_date = datetime.now().strftime("%Y-%m-%d")
        
        print(f"🦈 Shark Cluster Detector Initialized (Threshold: {SHARK_MIN_VAL/1e9}B, Hits: {MIN_HIT_COUNT})")

    def _load_config(self):
        try:
            path = os.path.join(os.path.dirname(os.path.dirname(__file__)), CONFIG_FILE)
            if os.path.exists(path):
                with open(path, 'r') as f:
                    return json.load(f).get("chat_id")
        except: pass
        return None

    def _load_stats(self):
        try:
            path = os.path.join(os.path.dirname(os.path.dirname(__file__)), STATS_FILE)
            if os.path.exists(path):
                with open(path, 'r') as f:
                    data = json.load(f)
                    # Check if stale (Previous Day?)
                    saved_date = data.get('date')
                    current_date = datetime.now().strftime("%Y-%m-%d")
                    
                    # If date matches, load. Else start fresh.
                    # Logic: User says reset at 8:30 AM.
                    # If saved data is from yesterday, discard.
                    if saved_date == current_date:
                        self.shark_stats = data.get('stats', {})
                        print(f"🔹 Loaded accumulated stats for {len(self.shark_stats)} symbols.")
                    else:
                        print("🔸 Stats file is directly from previous day. Starting fresh.")
        except Exception as e:
            print(f"Load Stats Error: {e}")

    def _save_stats(self):
        try:
            path = os.path.join(os.path.dirname(os.path.dirname(__file__)), STATS_FILE)
            with open(path, 'w') as f:
                json.dump({
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "stats": self.shark_stats
                }, f)
        except Exception as e:
            print(f"Save Stats Error: {e}")

    def set_alert_chat_id(self, chat_id):
        self.alert_chat_id = chat_id
        try:
            path = os.path.join(os.path.dirname(os.path.dirname(__file__)), CONFIG_FILE)
            with open(path, 'w') as f:
                json.dump({"chat_id": chat_id}, f)
        except: pass
        self.bot.send_message(chat_id, "🦈 **SHARK FILTER UPDATED**\nChế độ: Phát hiện Cụm Cá Mập (Shark Cluster)\nSẵn sàng săn mồi...", parse_mode='Markdown')

    def _do_maintenance(self):
        """Periodic cleanup, saving, and reset logic"""
        now = time.time()
        if now - self.last_maintenance < MAINTENANCE_INTERVAL:
            return
            
        with self.lock:
            # 1. Cleanup Tracker (RAM)
            expired = [k for k, v in self.shark_tracker.items() if now - v['last_seen'] > 7200]
            for k in expired:
                del self.shark_tracker[k]
                
            # 2. Check 08:30 AM Reset
            dt_now = datetime.now()
            today_str = dt_now.strftime("%Y-%m-%d")
            
            # If current time is > 08:30 AND we haven't reset for 'today' yet
            # But wait, if we initialized AFTER 8:30, we verify date.
            # If we run continuously overnight:
            # At 08:30, we must clear stats.
            
            is_reset_time = (dt_now.hour == 8 and dt_now.minute >= 30) or (dt_now.hour > 8)
            
            if is_reset_time and self.last_reset_date != today_str:
                print("🧹 **AUTO-RESET** (08:30 AM): Clearing Daily Stats...")
                self.shark_stats.clear()
                self.last_reset_date = today_str
            
            # 3. Save Stats
            self._save_stats()
        
        self.last_maintenance = now

    def process_tick(self, payload):
        """
        Real-time Packet Processing
        Logic: Cluster Detection (3 hits within 5 mins)
        """
        try:
            # Frequent Maintenance Check
            self._do_maintenance()
            
            symbol = payload.get("symbol")
            if not symbol:
                return

            # Parse Data
            price = float(payload.get("matchPrice", 0))
            vol = int(payload.get("matchVolume", 0)) 
            total_vol = int(payload.get("totalVolumeTraded", 0))
            change_pc = float(payload.get("changedRatio", 0))
            
            if not (-6.5 <= change_pc <= 6.5):
                return
                
            order_value = price * vol
            
            if order_value < SHARK_MIN_VAL:
                return
                
            # --- SHARK ORDER DETECTED ---
            now = time.time()
            
            with self.lock:
                if symbol not in self.shark_tracker:
                    self.shark_tracker[symbol] = {
                        'count': 0, 
                        'last_seen': 0, 
                        'last_alert': 0
                    }
                
                # Update Stats (For Dashboard)
                if symbol not in self.shark_stats:
                    self.shark_stats[symbol] = {'buy_val': 0, 'sell_val': 0}
                
                # Heuristic: Green/Ref = Buy flow, Red = Sell flow
                if change_pc >= 0:
                    self.shark_stats[symbol]['buy_val'] += order_value
                else:
                    self.shark_stats[symbol]['sell_val'] += order_value
                
                tracker = self.shark_tracker[symbol]
                
                # 2. Logic Hit Counting
                time_diff = now - tracker['last_seen']
                
                if time_diff > CLUSTER_TIMEOUT:
                    # Timeout -> Reset sequence
                    tracker['count'] = 1
                else:
                    tracker['count'] += 1
                
                tracker['last_seen'] = now
                
                # 3. Trigger Logic
                if tracker['count'] >= MIN_HIT_COUNT:
                    if now - tracker['last_alert'] > ALERT_COOLDOWN:
                        self.send_alert(symbol, price, change_pc, total_vol, tracker['count'], order_value)
                        tracker['last_alert'] = now
                        self.watchlist_service.add_to_watchlist(symbol)

        except Exception as e:
            pass

    def process_ohlc(self, payload):
        pass

    def send_alert(self, symbol, price, change_pc, total_vol, hit_count, last_val):
        if not self.alert_chat_id:
            return

        icon = "📈" if change_pc >= 0 else "📉"
        
        msg = (
            f"-----------------------------------\n"
            f"🦈 **CÁ MẬP GOM LIÊN TỤC**: #{symbol}\n"
            f"-----------------------------------\n"
            f"🔥 **Tín hiệu**: Phát hiện {hit_count} lệnh > 1 Tỷ\n"
            f"⏱️ **Trong vòng**: {CLUSTER_TIMEOUT//60} phút vừa qua\n"
            f"-----------------------------------\n"
            f"📍 **Chi tiết lệnh gần nhất**:\n"
            f"• Giá trị: `{last_val/1e9:,.1f}` Tỷ đồng\n"
            f"• Giá khớp: `{price:,.0f}` ({change_pc:+.2f}% {icon})\n"
            f"-----------------------------------\n"
            f"💾 Đã thêm vào Watchlist (48h)"
        )
        
        try:
            self.bot.send_message(self.alert_chat_id, msg, parse_mode='Markdown')
        except Exception as e:
            print(f"Alert Failed: {e}") 

    def get_shark_stats(self, symbol):
        """Return (buy_val, sell_val) for a symbol"""
        with self.lock:
            data = self.shark_stats.get(symbol, {'buy_val': 0, 'sell_val': 0})
            return data['buy_val'], data['sell_val'] 
