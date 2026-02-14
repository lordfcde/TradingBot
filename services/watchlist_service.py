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
        # Fix: Use UTC+7 for display
        vn_time = datetime.now(timezone.utc) + timedelta(hours=7)
        data[symbol] = {
            "entry_time": time.time(),
            "display_time": vn_time.strftime("%H:%M %d/%m")
        }
        
        self._save_data(data)
        # print(f"⭐ Added {symbol} to Watchlist.")

    def add_enriched(self, symbol, shark_data=None, trinity_data=None):
        """
        Add symbol with enriched Shark + Trinity data.
        
        Args:
            symbol: Stock symbol
            shark_data: dict with price, change_pc, order_value, vol, side
            trinity_data: dict from TrinityAnalyzer.check_signal() 
        """
        data = self._load_data()
        symbol = symbol.upper()

        entry = {
            "entry_time": time.time(),
            "display_time": datetime.now().strftime("%H:%M %d/%m"),
        }

        if shark_data:
            entry["shark"] = {
                "price": shark_data.get("price", 0),
                "change_pc": shark_data.get("change_pc", 0),
                "order_value": shark_data.get("order_value", 0),
                "vol": shark_data.get("vol", 0),
                "side": shark_data.get("side", "Unknown"),
            }

        if trinity_data:
            entry["trinity"] = {
                "rating": trinity_data.get("rating", "N/A"),
                "trend": trinity_data.get("trend", "N/A"),
                "cmf": trinity_data.get("cmf", 0),
                "rsi": trinity_data.get("rsi", 0),
                "error": trinity_data.get("error"),
            }

        data[symbol] = entry
        self._save_data(data)

    def get_active_watchlist(self):
        """Get watchlist items that are valid for today"""
        # Fix: Use UTC+7
        vn_time = datetime.now(timezone.utc) + timedelta(hours=7)
        today_str = vn_time.strftime("%Y-%m-%d")
        
        active_items = []
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

    def filter_by_liquidity(self, vnstock_service, min_avg_volume=250000):
        """
        Filter watchlist by liquidity (5-day average volume).
        Remove symbols with avg volume < min_avg_volume.
        """
        data = self._load_data()
        if not data:
            print("📊 Watchlist empty - no filtering needed")
            return
        
        from datetime import datetime, timedelta
        from datetime import datetime, timedelta
        
        symbols_to_remove = []
        symbols_kept = []
        
        print(f"🔍 Filtering watchlist by liquidity (min 5d avg: {min_avg_volume:,})...")
        
        for symbol in list(data.keys()):
            try:
                # Get last 10 days of data to calculate 5-day avg
                end_date = datetime.now()
                start_date = end_date - timedelta(days=10)
                
                df = vnstock_service.get_history(
                    symbol=symbol,
                    start=start_date.strftime('%Y-%m-%d'),
                    end=end_date.strftime('%Y-%m-%d'),
                    interval='1D',
                    source='KBS'
                )
                
                if df is not None and not df.empty and len(df) >= 5:
                    # Calculate 5-day average volume
                    avg_volume = df['volume'].tail(5).mean()
                    
                    if avg_volume < min_avg_volume:
                        symbols_to_remove.append(symbol)
                        print(f"  ❌ {symbol}: {avg_volume:,.0f} < {min_avg_volume:,} (removed)")
                    else:
                        symbols_kept.append(symbol)
                        print(f"  ✅ {symbol}: {avg_volume:,.0f} >= {min_avg_volume:,} (kept)")
                else:
                    print(f"  ⚠️ {symbol}: Insufficient data - keeping")
                    
            except Exception as e:
                print(f"  ⚠️ {symbol}: Error checking liquidity ({e}) - keeping")
        
        # Remove illiquid stocks
        if symbols_to_remove:
            for symbol in symbols_to_remove:
                del data[symbol]
            self._save_data(data)
            print(f"🧹 Removed {len(symbols_to_remove)} illiquid stock(s)")
            print(f"✅ Kept {len(symbols_kept)} liquid stock(s)")
        else:
            print(f"✅ All {len(symbols_kept)} stock(s) passed liquidity filter")

    def clear_watchlist(self):
        """Clears all entries from watchlist."""
        self._save_data({})
        print("🧹 Watchlist cleared.")
