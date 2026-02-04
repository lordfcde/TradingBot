
import sys
import os
import json
import time

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from services.dnse_service import DNSEService

count = 0

def on_fox_tick(payload):
    global count
    symbol = payload.get("symbol")
    vol = payload.get("matchQuantity", 0)
    price = payload.get("matchPrice", 0)
    print(f"🦊 FOX TICK: {symbol} | Price: {price} | Vol: {vol}")
    print(f"RAW: {payload}")
    
    count += 1
    if count >= 3:
        print("✅ Captured 3 Ticks. Exiting.")
        os._exit(0)

def main():
    print("🚀 Starting FOX Test...")
    service = DNSEService()
    if service.connect():
        # Subscribe explicitly
        topic = "plaintext/quotes/krx/mdds/stockinfo/v1/roundlot/symbol/FOX"
        service.client.subscribe(topic)
        service.client.message_callback_add(topic, lambda c, u, m: on_fox_tick(json.loads(m.payload.decode())))
        print(f"📡 Subscribed to: {topic}")
        print("⏳ Waiting for data (Ctrl+C to stop)...")
        
        while True:
            time.sleep(1)
    else:
        print("❌ Failed to connect.")

if __name__ == "__main__":
    main()
