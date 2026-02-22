import sys
import os
from unittest.mock import MagicMock

# Mock modules
sys.modules["telebot"] = MagicMock()
sys.modules["telebot.types"] = MagicMock()
sys.modules["pandas_ta"] = MagicMock()

# Mock Analyer
class MockAnalyzer:
    def __init__(self):
        pass
    
    def check_signal(self, symbol):
        # Default Valid Signal
        return {
            'adx': 30,
            'is_bullish': True,
            'rsi': 60,
            'vol_avg': 1000000,
            'vol_dry': False,
            'rating': 'MUA MẠNH 🚀',
            'trend': 'UPTREND',
            'error': None
        }

    def get_market_context(self):
        return {'status': 'SAFE', 'reason': 'Market OK', 'current': 1250, 'trend': 'UP'}

    def judge_signal(self, symbol, shark_payload):
        # Copied logic for testing without full env
        # In real test, we import the actual class. 
        # But here we want to verify the LOGIC FLOW we just wrote.
        # Let's import the actual file!
        pass

# Setup Environment to import actual code
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.append(project_root)

try:
    from services.analyzer import TrinityAnalyzer
    print("✅ Imported TrinityAnalyzer")
except ImportError as e:
    print(f"❌ Import Error: {e}")
    sys.exit(1)

# Mock Internal methods of Analyzer to test Judge logic specifically
def test_judge():
    analyzer = TrinityAnalyzer(None)
    
    # 1. Mock Check Signal
    analyzer.check_signal = MagicMock()
    # 2. Mock Market Context
    analyzer.get_market_context = MagicMock()
    
    # Test Case 1: Market Danger
    print("\n--- CASE 1: MARKET DANGER ---")
    analyzer.check_signal.return_value = {'rating': 'MUA MẠNH', 'adx': 30, 'is_bullish': True}
    analyzer.get_market_context.return_value = {'status': 'DANGER', 'reason': 'Gãy MA20'}
    
    res = analyzer.judge_signal("CASE1", {})
    print(f"Result: {res['approved']} - Reason: {res['reason']}")
    
    # Test Case 2: ADX Weak
    print("\n--- CASE 2: ADX WEAK (<20) ---")
    analyzer.get_market_context.return_value = {'status': 'SAFE', 'reason': 'OK'} # Reset Market
    analyzer.check_signal.return_value = {'rating': 'MUA MẠNH', 'adx': 15, 'is_bullish': True}
    
    res = analyzer.judge_signal("CASE2", {})
    print(f"Result: {res['approved']} - Reason: {res['reason']}")

    # Test Case 3: RSI Overbought
    print("\n--- CASE 3: RSI > 75 ---")
    analyzer.check_signal.return_value = {'rating': 'MUA MẠNH', 'adx': 30, 'is_bullish': True, 'rsi': 80}
    
    res = analyzer.judge_signal("CASE3", {})
    print(f"Result: {res['approved']} - Reason: {res['reason']}")

    # Test Case 4: Perfect Setup
    print("\n--- CASE 4: PERFECT SETUP ---")
    analyzer.check_signal.return_value = {
        'rating': 'MUA MẠNH 🚀', 
        'adx': 40, 'is_bullish': True, 
        'rsi': 60, 'vol_avg': 1000000, 
        'vol_dry': False,
        'trend': 'UPTREND'
    }
    shark_payload = {'price': 50000, 'change_pc': 6.5, 'total_vol': 2000000} # 2x Vol
    
    res = analyzer.judge_signal("VIC", shark_payload)
    print(f"Result: {res['approved']}")
    if res['approved']:
        print("Message:")
        print(res['message'])

test_judge()
