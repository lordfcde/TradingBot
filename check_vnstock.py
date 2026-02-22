import sys
import os
import json

# Ensure we can import services
sys.path.append(os.getcwd())

try:
    from services.vnstock_service import VnstockService
except ImportError as e:
    print(f"❌ Import Error: {e}")
    sys.exit(1)

def print_section(title, data):
    print(f"\n{'='*20} {title} {'='*20}")
    if data is None:
        print("❌ No Data")
        return
        
    if hasattr(data, 'head'): # DataFrame
        print(data.head().to_markdown())
        print(f"\nColumns: {list(data.columns)}")
    elif isinstance(data, dict):
        print(json.dumps(data, indent=4, ensure_ascii=False))
    else:
        print(data)

def main():
    symbol = "FOX"
    print(f"🚀 Exploring Vnstock Data for {symbol}...")
    
    service = VnstockService()
    
    # 1. Stock Info (Real-time Price + Basic Info)
    info = service.get_stock_info(symbol)
    print_section("1. Stock Info (Real-time)", info)
    
    # 2. Historical Data (OHLC)
    hist = service.get_history(symbol, start='2024-01-01', end='2024-02-14', interval='1D')
    print_section("2. Historical Price (Lịch sử)", hist)
    
    # 3. Direct Access to underlying library for more info
    # We try to access the `stock_source` attribute if public
    try:
        stock = service.stock_source.stock(symbol=symbol, source='VCI')
        
        # Profile
        profile = stock.company.profile()
        print_section("3. Company Profile", profile)
        
        # Financial Ratio
        ratio = stock.finance.ratio(period='year', lang='vi')
        print_section("4. Financial Ratios", ratio)
        
    except Exception as e:
        print(f"⚠️ Advanced features error: {e}")

if __name__ == "__main__":
    main()
