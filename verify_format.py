import sys
import os
from datetime import datetime

# Mock objects
import sys
from unittest.mock import MagicMock

# Mock telebot
sys.modules["telebot"] = MagicMock()
sys.modules["telebot.types"] = MagicMock()

class MockSharkService:
    def get_shark_stats(self, symbol):
        return 5000000000, 2000000000 # 5B Buy, 2B Sell

# Dummy Data
stock_data = {
    "symbol": "VIC",
    "matchPrice": 45000,
    "changedRatio": 2.5,
    "totalVolumeTraded": 1500000, # 1.5M -> x10 -> 15M
    "avg_vol_5d": 10000000,
    "industry": "Real Estate",
    "rsi": 65.5
}

# Trinity Data Samples
trinity_strong_buy = {
    'trend': 'UPTREND ✅',
    'adx_status': 'MẠNH TĂNG 🟢',
    'signal': 'DIAMOND', # Diamond
    'structure': 'Trên EMA50 (Tăng)',
    'support': 42000,
    'resistance': 48000,
    'vol_avg': 10000000,
    'cmf': 0.15,
    'cmf_status': 'VÀO MẠNH 🔥',
    'rating': 'MUA MẠNH 🚀',
    'rsi': 65.5
}

trinity_downtrend = {
    'trend': 'DOWNTREND ❌',
    'adx_status': 'MẠNH GIẢM 🔴',
    'signal': 'SELL',
    'structure': 'Chạm Kháng cự (Hộp Đỏ)',
    'support': 40000,
    'resistance': 44000,
    'vol_avg': 10000000,
    'cmf': -0.05,
    'cmf_status': 'RA NGOÀI ❌',
    'rating': 'WATCH',
    'rsi': 35.0
}

# Import the handler
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.append(project_root)

try:
    from handlers.stock_handler import format_stock_reply
except ImportError as e:
    print(f"CRITICAL ERROR: Could not import handler: {e}")
    sys.exit(1)

print("--- CASE 1: STRONG BUY (DIAMOND) ---")
try:
    # Creating a dummy SharkService class that mimics the get_shark_stats method
    class DummySharkService:
        def get_shark_stats(self, symbol):
            return 5000000000, 2000000000

    msg = format_stock_reply(stock_data, DummySharkService(), trinity_strong_buy)
    print(msg)
except Exception as e:
    print(f"Error executing format_stock_reply: {e}")
    import traceback
    traceback.print_exc()

print("\n--- CASE 2: DOWNTREND (SELL) ---")
try:
    msg = format_stock_reply(stock_data, MockSharkService(), trinity_downtrend)
    print(msg)
except Exception as e:
    print(f"Error executing format_stock_reply: {e}")
