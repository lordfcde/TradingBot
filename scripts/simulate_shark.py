import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import time
from services.shark_hunter_service import SharkHunterService

# Mock Bot
class MockBot:
    def send_message(self, chat_id, text, parse_mode=None):
        print(f"\n[📣 TELEGRAM ALERT to {chat_id}]\n{text}\n")

def main():
    print("🦈 SIMULATING SHARK CLUSTER DETECTOR...")
    
    # 1. Init Service
    bot = MockBot()
    service = SharkHunterService(bot)
    service.set_alert_chat_id("TEST_CHANNEL")
    
    symbol = "HPG"
    price = 30000 
    
    # Shark Order: > 1 Billion
    # 35,000 shares * 30,000 = 1.05 Billion
    vol_per_hit = 35000 
    
    print(f"🔹 Simulating Cluster for {symbol} (Threshold: 1B/order, Min Hits: 3)...")
    
    # Hit 1
    print("👊 HIT 1: Sending Order (1.05 Billion)...")
    service.process_tick({
        "symbol": symbol,
        "matchPrice": price,
        "matchVolume": vol_per_hit,
        "totalVolumeTraded": 1000000,
        "changedRatio": 2.0
    })
    time.sleep(1) # Simulate delay
    
    # Hit 2
    print("� HIT 2: Sending Order (1.05 Billion)...")
    service.process_tick({
        "symbol": symbol,
        "matchPrice": price,
        "matchVolume": vol_per_hit,
        "totalVolumeTraded": 1035000,
        "changedRatio": 2.1
    })
    time.sleep(1)
    
    # Hit 3 (Trigger)
    print("👊 HIT 3: Sending Order (1.05 Billion)...")
    service.process_tick({
        "symbol": symbol,
        "matchPrice": price,
        "matchVolume": vol_per_hit, # Trigger!
        "totalVolumeTraded": 1070000,
        "changedRatio": 2.2
    })
    
    print("✅ Simulation Finished. (Check for Alert above)")

if __name__ == "__main__":
    main()
