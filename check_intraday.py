import sys
import os
import json

sys.path.append(os.getcwd())

# Mock pandas if missing
try:
    import pandas as pd
except ImportError:
    from unittest.mock import MagicMock
    sys.modules["pandas"] = MagicMock()
    print("⚠️ Mocked pandas")

# Mock vnstock keys
try:
    import vnstock
except ImportError:
    # If vnstock is missing, we rely on VnstockService which might wrap it or mock it
    # But VnstockService imports vnstock. 
    # Let's import the local service, assuming the user environment HAS vnstock 
    # (since the bot is running).
    # The previous error "No module named 'vnstock'" suggests the script environment 
    # lacks it even though bot has it? Or path issue.
    # Let's try to mock it if we just want to see structure, 
    # BUT we need real data.
    pass

try:
    from services.vnstock_service import VnstockService
except ImportError as e:
    print(f"❌ Import Error: {e}")
    sys.exit(1)

def main():
    symbol = "FOX"
    print(f"🚀 Checking Intraday Quote for {symbol} (Active Buy/Sell Source)...")
    
    service = VnstockService()
    try:
        # Try to get intraday quotes which usually contain side or can be inferred
        # We access the raw stock object from vnstock
        stock = service.stock_source.stock(symbol=symbol, source='VCI')
        
        # Check 'quote.intraday' or similar
        # This usually returns recent matches: time, price, volume, side (sometimes)
        intraday = stock.quote.intraday(symbol=symbol, page_size=10)
        
        if intraday is not None and not intraday.empty:
            print("\n✅ Intraday Data Found:")
            # print(intraday.head().to_markdown()) # Requires tabulate
            print(intraday.head().to_dict('records'))
            print(f"\nColumns: {list(intraday.columns)}")
        else:
            print("❌ No Intraday Data")
            
    except Exception as e:
        print(f"❌ Error checking intraday: {e}")

if __name__ == "__main__":
    main()
