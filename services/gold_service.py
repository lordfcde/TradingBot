import yfinance as yf
import datetime

class GoldService:
    def get_gold_price(self):
        """
        Fetches real-time Gold data (GC=F) from yfinance.
        Returns a dictionary or None if error.
        """
        try:
            ticker = yf.Ticker("GC=F")
            data = ticker.history(period="1d")
            
            if data.empty:
                return None

            # Get important metrics
            current_price = data['Close'].iloc[-1]
            open_price = data['Open'].iloc[-1]
            high_price = data['High'].iloc[-1]
            low_price = data['Low'].iloc[-1]
            
            # Calculate % Change (need 5d history to be safe for prev close)
            data_5d = ticker.history(period="5d")
            if len(data_5d) >= 2:
                prev_close = data_5d['Close'].iloc[-2]
                change_percent = ((current_price - prev_close) / prev_close) * 100
            else:
                change_percent = 0.0
                
            return {
                "price": current_price,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "change_percent": change_percent,
                "timestamp": datetime.datetime.now().strftime("%H:%M:%S %d/%m/%Y")
            }
            
        except Exception as e:
            print(f"❌ Gold Service Error: {e}")
            return None
