
# test_simulation.py
# Simulating Shark Hunter Logic (REA ALERT MODE)
# Senior QA Automation Engineer Approach

import time
import json
import telebot # Real Lib
import config  # Real Config
from services.shark_hunter_service import SharkHunterService

# ==========================================
# 1. MOCK OBJECTS
# ==========================================

class MockWatchlistService:
    """Giả lập Watchlist Service"""
    def add_to_watchlist(self, symbol):
        print(f"[📝 MOCK WATCHLIST] Added {symbol}")

# ==========================================
# 2. SETUP ENVIRONMENT
# ==========================================

print("⚙️  Setting up Test Environment (REAL ALERT MODE)...")

# CHÚ Ý: Sử dụng Bot Thật!
try:
    real_bot = telebot.TeleBot(config.API_TOKEN)
    print("✅ Connected to Real Telegram Bot API.")
except Exception as e:
    print(f"❌ Failed to connect to Telegram: {e}")
    exit()

# Khởi tạo Shark Service với Real Bot
service = SharkHunterService(real_bot)

# Mock Watchlist Service trả về dummy (Không cần add thật vào DB)
service.watchlist_service = MockWatchlistService()

# Cấu hình lại để dễ test
service.min_value = 1_000_000_000  # 1 Tỷ
service.cooldown = 60              # 1 Phút (Theo yêu cầu mới)

# Load Chat ID thật từ Config
if not service.alert_chat_id:
    # Fallback nếu chưa lưu
    service.alert_chat_id = "1622117094" # Hardcoded from logs just in case

print(f"✅ Environment Ready! Target Chat ID: {service.alert_chat_id}\n")


# ==========================================
# 3. TEST CASES
# ==========================================

from datetime import datetime, timedelta

def run_test(case_name, payload_dict, expected_desc):
    print(f"🔹 RUNNING: {case_name}")
    print(f"   Input: {payload_dict}")
    print(f"   Expect: {expected_desc}")
    service.process_tick(payload_dict)
    print(f"   Completed.\n{'-'*50}\n")


# CASE 1: BURST TEST (SHK) - Should Add on 3rd Hit
payload_shark = {
    "symbol": "SHK", "matchPrice": 50.0, "matchQuantity": 10000, 
    "totalVolumeTraded": 500000, "changedRatio": 2.5, "side": 1
}

# Hit 1
run_test("SHK Hit 1", payload_shark, "Alert YES, Watchlist NO (Count=1)")

# Case 2: SPLIT COOLDOWN TEST (SHK)
# Prior: Hit 1 (Buy) triggered at 10:00.
# Now: Trigger Sell immediately.
payload_sell = {
    "symbol": "SHK", "matchPrice": 49.0, "matchQuantity": 10000, 
    "totalVolumeTraded": 500000, "changedRatio": -1.0, "side": 2 # Sell
}

run_test("SHK Sell (Immediate)", payload_sell, "Alert YES (Separate Key), Watchlist NO")

# Now Trigger Sell Again
run_test("SHK Sell 2 (Immediate)", payload_sell, "Alert NO (Sell Cooldown Active)")


# CASE 2: TIME WINDOW TEST (OLD) - Should FAIL
# Inject Old History
print("🧪 Injecting OLD history for symbol 'OLD' (1 hour ago)...")
old_time = (datetime.now() - timedelta(seconds=4000)).strftime("%H:%M:%S")
service.trade_history.append({'time': old_time, 'symbol': 'OLD', 'value': 5e9, 'change': 1.0, 'side': 'Buy'})
service.trade_history.append({'time': old_time, 'symbol': 'OLD', 'value': 5e9, 'change': 1.0, 'side': 'Buy'})
# Stats need update too for consistency? Watchlist logic checks trade_history mainly.
# But it also relies on loop.

payload_old = {
    "symbol": "OLD", "matchPrice": 50.0, "matchQuantity": 10000, 
    "totalVolumeTraded": 500000, "changedRatio": 1.0, "side": 1
}

# Hit 3 (New)
run_test("OLD Hit 3 (New)", payload_old, "Watchlist NO (Count=1 valid in 30m window). The other 2 are too old.")


# CASE 4: Verification of Stats
print("🔹 RUNNING: Final Stats Verification")
report = service.get_stats_report()
print(report)
print(f"{'-'*50}\n")

