import time
from services.dnse_service import DNSEService

def run():
    dnse = DNSEService()
    
    def on_tick(payload):
        symbol = payload.get("symbol")
        if not symbol or len(symbol) > 3: return
        price = float(payload.get("lastPrice", 0) or payload.get("matchPrice", 0) or payload.get("price", 0))
        vol = float(payload.get("lastVol", 0) or payload.get("matchVol", 0) or payload.get("vol", 0) or payload.get("matchQuantity", 0))
        real_price = price if price > 1000 else price * 1000
        val = real_price * vol
        if val >= 500_000_000:
            print(f"LARGE ORDER: {symbol} - Vol: {vol}, Price: {real_price}, Value: {val:,.0f} VND")

    dnse.register_shark_streams(ohlc_cb=lambda x: None, tick_cb=on_tick)
    print("Connecting...")
    dnse.connect()
    dnse.subscribe_all_markets()
    print("Listening for 60 seconds...")
    time.sleep(60)
    dnse.client.disconnect()
    print("Done")

if __name__ == "__main__":
    run()
