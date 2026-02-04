import json
import os
import time
from datetime import datetime, timedelta

WATCHLIST_FILE = "watchlist.json"
EXPIRY_HOURS = 72

class WatchlistService:
    def __init__(self):
        self.file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), WATCHLIST_FILE)
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(self.file_path):
            with open(self.file_path, 'w') as f:
                json.dump({}, f)

    def _load_data(self):
        try:
            with open(self.file_path, 'r') as f:
                return json.load(f)
        except:
            return {}

    def _save_data(self, data):
        with open(self.file_path, 'w') as f:
            json.dump(data, f, indent=4)

    def add_to_watchlist(self, symbol):
        """
        Adds symbol with current timestamp. Updates time if exists.
        """
        data = self._load_data()
        symbol = symbol.upper()
        
        # entry_time as timestamp
        data[symbol] = {
            "entry_time": time.time(),
            "display_time": datetime.now().strftime("%H:%M %d/%m")
        }
        
        self._save_data(data)
        # print(f"⭐ Added {symbol} to Watchlist.")

    def get_active_watchlist(self):
        """
        Returns list of valid symbols. Cleans up expired ones.
        """
        data = self._load_data()
        now = time.time()
        expiry_seconds = EXPIRY_HOURS * 3600
        
        valid_data = {}
        sorted_items = []
        
        is_modified = False
        
        for symbol, info in data.items():
            entry_time = info.get("entry_time", 0)
            if (now - entry_time) < expiry_seconds:
                valid_data[symbol] = info
                # Calculate time delta for display (e.g. "Hôm qua", "2 giờ trước")
                # For simplicity, we just use the display_time stored or format relative text in handler?
                # User asked for: "Báo: 14:30 hôm nay", "Báo: Hôm qua"
                # Let's return the raw info + relative logic here or in handler.
                # Let's assume we return list of dicts.
                
                # Relative time logic
                dt_entry = datetime.fromtimestamp(entry_time)
                dt_now = datetime.fromtimestamp(now)
                diff = dt_now - dt_entry
                
                if diff.days == 0:
                    time_str = f"{dt_entry.strftime('%H:%M')} hôm nay"
                elif diff.days == 1:
                    time_str = "Hôm qua"
                else:
                    time_str = f"{diff.days} ngày trước"
                
                sorted_items.append({
                    "symbol": symbol,
                    "time_str": time_str,
                    "entry_time": entry_time
                })
            else:
                is_modified = True
                
        if is_modified or len(valid_data) != len(data):
            self._save_data(valid_data)
            
        # Sort by newest first
        sorted_items.sort(key=lambda x: x['entry_time'], reverse=True)
        return sorted_items
