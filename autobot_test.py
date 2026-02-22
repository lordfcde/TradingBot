import sys
import os
from unittest.mock import MagicMock

# Mock modules
try:
    import pandas as pd
    import pandas_ta as ta
    sys.modules["pandas"] = pd
    sys.modules["pandas_ta"] = ta
except ImportError:
    from unittest.mock import MagicMock
    sys.modules["pandas"] = MagicMock()
    sys.modules["pandas_ta"] = MagicMock()
    print("⚠️ Mocked pandas/ta")

sys.modules["telebot"] = MagicMock()
sys.modules["telebot.types"] = MagicMock()

# Setup Environment to import actual code
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.append(project_root)

try:
    from services.analyzer import TrinityAnalyzer
except ImportError as e:
    print(f"❌ Import Error: {e}")
    sys.exit(1)

def test_autobot_perfect_buy():
    print("🚀 TESTING AUTOBOT: PERFECT BUY SCENARIO")
    
    analyzer = TrinityAnalyzer(None)
    
    # 1. Mock Check Signal (Technical Data)
    analyzer.check_signal = MagicMock(return_value={
        'rating': 'MUA MẠNH 🚀',
        'adx': 35,             # > 25 (Good)
        'is_bullish': True,    # Bullish Trend
        'rsi': 60,             # < 75 (Safe)
        'vol_avg': 1_000_000,
        'vol_dry': False,
        'trend': 'UPTREND',
        'error': None
    })
    
    # 2. Mock Market Context (Safe)
    analyzer.get_market_context = MagicMock(return_value={
        'status': 'SAFE',
        'reason': 'Market OK',
        'current': 1250,
        'trend': 'UP'
    })
    
    # 3. Shark Payload (Breakout Data)
    shark_payload = {
        'price': 50000, 
        'change_pc': 6.5,       # Strong Increase
        'total_vol': 3_000_000, # 3x Avg Vol
        'order_value': 5_000_000_000,
        'vol': 50000,
        'side': 'Buy'
    }
    
    # 4. Run Judge
    print("\n⚖️ JUDGING SIGNAL...")
    result = analyzer.judge_signal("TEST_STOCK", shark_payload)
    
    print(f"✅ Approved: {result['approved']}")
    print(f"📝 Reason: {result['reason']}")
    
    if result['approved']:
        print("\n📢 GENERATED ALERT MESSAGE:")
        print("-" * 40)
        print(result['message'])
        print("-" * 40)
        print("✅ AUTOBOT TEST PASSED!")
    else:
        print("❌ AUTOBOT TEST FAILED (Should be Approved)")

if __name__ == "__main__":
    test_autobot_perfect_buy()
