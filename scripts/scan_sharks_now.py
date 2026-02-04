import sys
import os
import time
import json
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from services.dnse_service import DNSEService

start_time = time.time()
DURATION = 60 # 1 Minute scan

def on_data(payload):
    try:
        ts = datetime.now().strftime("%H:%M:%S")
        symbol = payload.get("symbol")
        price = float(payload.get("matchPrice", 0))
        qty = int(payload.get("matchQuantity", 0) or payload.get("matchVolume", 0) or 0)
        
        # Calculate Value
        # Assuming price is raw or x1000
        real_price = price if price > 1000 else price * 1000
        val = real_price * qty
        
        val_billion = val / 1_000_000_000
        
        # Show anything > 100 Million for visibility, highlight Sharks > 1B
        if val > 100_000_000:
            tag = "🐟 Small"
            if val > 500_000_000: tag = "🦈 MEDIUM"
            if val > 1_000_000_000: tag = "🐳 **WHALE**"
            
            print(f"[{ts}] {tag} #{symbol}: {val_billion:.3f} Tỷ (Vol: {qty})")
            
    except Exception as e:
        pass

try:
    print(f"🔹 Scanning Market for Big Orders (>100M) for {DURATION}s...")
    service = DNSEService()
    
    # Subscribe to Firehose
    # We must replicate the 'subscribe_all' logic manually or call the method
    # Since we imported DNSEService, we can use it.
    
    # We need to register a callback. DNSEService doesn't expose a 'global' callback directly 
    # except via register_shark_streams.
    
    # Let's use that.
    def dummy_ohlc(p): pass
    
    service.register_shark_streams(dummy_ohlc, on_data)
    
    # Service calls subscribe_all_markets automatically now? 
    # If using my fixed version: Yes, register_shark_streams sets is_shark_active=True.
    # So when it connects, it subscribes.
    
    # Just need to keep script alive
    while time.time() - start_time < DURATION:
        time.sleep(1)
        
    print("\n✅ Scan Complete.")

except KeyboardInterrupt:
    print("\n🛑 Stopped.")
except Exception as e:
    print(f"Error: {e}")
