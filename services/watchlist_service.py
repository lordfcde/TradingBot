import json
import os
import time
from datetime import datetime, timedelta, timezone
from services.database_service import DatabaseService

EXPIRY_HOURS = 72

class WatchlistService:
    def __init__(self):
        # Database initialization runs inside DatabaseService.get_pool() if DATABASE_URL is set.
        pass

    def add_to_watchlist(self, symbol):
        """
        Adds symbol with current timestamp. Updates time if exists.
        """
        symbol = symbol.upper()
        vn_time = datetime.now(timezone.utc) + timedelta(hours=7)
        now = time.time()
        display_time = vn_time.strftime("%H:%M %d/%m")
        
        query = """
            INSERT INTO watchlist (symbol, entry_time, display_time)
            VALUES (%s, %s, %s)
            ON CONFLICT (symbol) DO UPDATE SET
                signal_count = CASE WHEN RIGHT(watchlist.display_time, 5) = RIGHT(EXCLUDED.display_time, 5) THEN watchlist.signal_count + 1 ELSE 1 END,
                entry_time = EXCLUDED.entry_time,
                display_time = EXCLUDED.display_time;
        """
        DatabaseService.execute_query(query, (symbol, now, display_time))
        # print(f"⭐ Added {symbol} to Watchlist.")

    def add_enriched(self, symbol, shark_data=None, trinity_data=None):
        """
        Add symbol with enriched Shark + Trinity data.
        """
        symbol = symbol.upper()
        vn_time = datetime.now(timezone.utc) + timedelta(hours=7)
        now = time.time()
        display_time = vn_time.strftime("%H:%M %d/%m")

        shark_json = None
        if shark_data:
            shark_info = {
                "price": shark_data.get("price", 0),
                "change_pc": shark_data.get("change_pc", 0),
                "order_value": shark_data.get("order_value", 0),
                "vol": shark_data.get("vol", 0),
                "side": shark_data.get("side", "Unknown"),
            }
            shark_json = json.dumps(shark_info)

        trinity_json = None
        if trinity_data:
            trinity_info = {
                "rating": trinity_data.get("rating", "N/A"),
                "trend": trinity_data.get("trend", "N/A"),
                "cmf": trinity_data.get("cmf", 0),
                "rsi": trinity_data.get("rsi", 0),
                "adx": trinity_data.get("adx", 0),
                "error": trinity_data.get("error"),
            }
            trinity_json = json.dumps(trinity_info)

        query = """
            INSERT INTO watchlist (symbol, entry_time, display_time, shark_data, trinity_data)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (symbol) DO UPDATE SET
                signal_count = CASE WHEN RIGHT(watchlist.display_time, 5) = RIGHT(EXCLUDED.display_time, 5) THEN watchlist.signal_count + 1 ELSE 1 END,
                entry_time = EXCLUDED.entry_time,
                display_time = EXCLUDED.display_time,
                shark_data = EXCLUDED.shark_data,
                trinity_data = EXCLUDED.trinity_data;
        """
        DatabaseService.execute_query(query, (symbol, now, display_time, shark_json, trinity_json))

    def get_active_watchlist(self):
        """Get watchlist items that are valid for today, and delete expired items."""
        now = time.time()
        expiry_seconds = EXPIRY_HOURS * 3600
        
        # Auto-delete items older than 72 hours
        del_query = "DELETE FROM watchlist WHERE (%s - entry_time) >= %s"
        DatabaseService.execute_query(del_query, (now, expiry_seconds))
        
        # Read surviving items
        sel_query = "SELECT symbol, entry_time FROM watchlist ORDER BY entry_time DESC"
        rows = DatabaseService.execute_query(sel_query, fetch=True)
        
        sorted_items = []
        if rows:
            for row in rows:
                symbol = row['symbol']
                entry_time = row['entry_time']
                
                # Convert timestamp to UTC+7 datetime
                dt_entry = datetime.fromtimestamp(entry_time, tz=timezone.utc) + timedelta(hours=7)
                dt_now = datetime.fromtimestamp(now, tz=timezone.utc) + timedelta(hours=7)
                
                # Calculate days difference correctly based on actual day shift 
                # (not total hours, since "hôm qua" means previous calendar day)
                diff_days = dt_now.date() - dt_entry.date()
                
                if diff_days.days == 0:
                    time_str = f"{dt_entry.strftime('%H:%M')} hôm nay"
                elif diff_days.days == 1:
                    time_str = f"Báo lúc {dt_entry.strftime('%H:%M')} hôm qua"
                else:
                    time_str = f"Báo lúc {dt_entry.strftime('%H:%M')} {diff_days.days} ngày trước"
                
                sorted_items.append({
                    "symbol": symbol,
                    "time_str": time_str,
                    "entry_time": entry_time
                })
                
        return sorted_items

    def filter_by_liquidity(self, vnstock_service, min_avg_volume=250000):
        """
        Filter watchlist by liquidity (5-day average volume).
        Remove symbols with avg volume < min_avg_volume.
        """
        sel_query = "SELECT symbol FROM watchlist"
        rows = DatabaseService.execute_query(sel_query, fetch=True)
        if not rows:
            print("📊 Watchlist empty - no filtering needed")
            return
            
        print(f"🔍 Filtering watchlist by liquidity (min 5d avg: {min_avg_volume:,})...")
        
        symbols_to_remove = []
        symbols_kept = []
        from datetime import datetime, timedelta
        
        for row in rows:
            symbol = row['symbol']
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
            format_strings = ','.join(['%s'] * len(symbols_to_remove))
            del_query = f"DELETE FROM watchlist WHERE symbol IN ({format_strings})"
            DatabaseService.execute_query(del_query, tuple(symbols_to_remove))
            print(f"🧹 Removed {len(symbols_to_remove)} illiquid stock(s)")
            print(f"✅ Kept {len(symbols_kept)} liquid stock(s)")
        else:
            print(f"✅ All {len(symbols_kept)} stock(s) passed liquidity filter")

    def clear_watchlist(self):
        """Clears all entries from watchlist."""
        DatabaseService.execute_query("DELETE FROM watchlist")
        print("🧹 Watchlist cleared.")
