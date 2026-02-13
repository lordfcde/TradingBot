# config.py
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ==========================================
# CẤU HÌNH BOT (CONFIGURATION)
# ==========================================

# Token API của Bot (Lấy từ @BotFather)
API_TOKEN = os.getenv("API_TOKEN")
if not API_TOKEN:
    raise ValueError("❌ API_TOKEN not found in .env file")

# ID Chat Admin (Để gửi thông báo lỗi hoặc debug)
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
if not ADMIN_CHAT_ID:
    raise ValueError("❌ ADMIN_CHAT_ID not found in .env file")

# Cấu hình Webhook (Nếu dùng sau này)
WEBHOOK_URL = ""

# Các hằng số khác
DEFAULT_TIMEOUT = 60

# Cấu hình Shark Hunter
SHARK_MIN_VALUE = int(os.getenv("SHARK_MIN_VALUE", 1_000_000_000))
