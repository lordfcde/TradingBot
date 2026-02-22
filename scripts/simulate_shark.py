import os
import sys
import argparse
import telebot
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

# Adjust path to find 'services'
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from services.shark_hunter_service import SharkHunterService

def main():
    parser = argparse.ArgumentParser(description="Simulate a Shark Hunter Alert")
    parser.add_argument("--symbol", type=str, default="TST", help="Stock Symbol (3 chars)")
    parser.add_argument("--price", type=float, default=50.0, help="Price in thousands (e.g. 50.0)")
    parser.add_argument("--vol", type=int, default=20000, help="Volume (shares)")
    args = parser.parse_args()

    # Load Env
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    load_dotenv(env_path)

    API_KEY = os.getenv("API_TOKEN") 
    ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
    
    if not API_KEY:
        print("❌ Error: API_TOKEN not found in .env")
        return

    print("🚀 Starting Shark Simulation...")
    print(f"   Symbol: {args.symbol}")
    print(f"   Price:  {args.price}")
    print(f"   Vol:    {args.vol}")
    
    # Init Bot
    bot = telebot.TeleBot(API_KEY)
    service = SharkHunterService(bot)
    # Force threshold lower if needed, or ensure payload exceeds it
    # 50.0 * 1000 * 20000 = 1,000,000,000 (1B) -> Fits exactly
    
    # Mock Time (10:00 AM UTC+7)
    # UTC = 03:00
    mock_utc = datetime(2024, 1, 1, 3, 0, 0, tzinfo=timezone.utc)
    
    print("🕑 Mocking Time: 10:00 (Trading Session)")

    # Patch datetime in the service module
    with patch('services.shark_hunter_service.datetime') as mock_dt:
        mock_dt.now.side_effect = lambda tz=None: mock_utc
        mock_dt.strptime = datetime.strptime
        
        # Construct Payload
        payload = {
            "symbol": args.symbol,
            "matchPrice": args.price,
            "matchVol": args.vol,
            "totalVolumeTraded": 500000,
            "changedRatio": 1.5,
            "time": "10:00:00",
            "side": 1
        }
        
        service.process_tick(payload)
        
    print("✅ Simulation sent to system.")

if __name__ == "__main__":
    main()
