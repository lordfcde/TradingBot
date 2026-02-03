import time
from services.shark_hunter_service import SharkHunterService
from data.stock_lists import VN100

# Mock Bot
class MockBot:
    def send_message(self, chat_id, text, parse_mode=None):
        print(f"\n[📣 TELEGRAM ALERT to {chat_id}]\n{text}\n")

def main():
    print("🦈 SIMULATING SHARK DETECTION...")
    
    # 1. Init Service
    bot = MockBot()
    service = SharkHunterService(bot)
    service.set_alert_chat_id("TEST_CHANNEL")
    
    # 2. Select a VN100 Symbol (Must be in VN100 to pass filter)
    symbol = "HPG" 
    if symbol not in VN100:
        print(f"❌ {symbol} not in VN100. Updating test data...")
        # Since we use the imported set, we can't easily modify the module's set if it's imported inside service?
        # Actually validation happens inside service using `from data.stock_lists import VN100`.
        # So we must use a valid one. HPG is in VN100.
    
    # 3. Inject Baseline (Healthy)
    # Avg 3M > 50k, Avg 5D > 100k
    print(f"🔹 Injecting Baseline for {symbol}...")
    with service.lock:
        service.market_state[symbol] = {
            'avg_3m': 20_000_000,   # 20M
            'avg_5d': 10_000_000,   # 10M
            'trend_ok': True,
            'last_update': time.time()
        }
        
    # 4. Inject Breakout Tick
    # Condition: TotalVol > Avg5D * 1.3
    # Target Vol: 10M * 1.3 = 13M. Let's send 15M (150%)
    
    tick_payload = {
        "symbol": symbol,
        "totalVolumeTraded": 15_000_000, # 15M
        "matchPrice": 28000,
        "changedRatio": 2.5, # +2.5%
        "matchVolume": 500_000 # Last tick volume
    }
    
    print(f"🔹 Sending Tick: Vol=15M (Avg=10M)...")
    service.process_tick(tick_payload)
    
    print("✅ Simulation Validated.")

if __name__ == "__main__":
    main()
