# main.py
import telebot
from telebot import types
import config
import logging

# ==========================================
# 1. KHỞI TẠO BOT
# ==========================================
# Khởi tạo logging để theo dõi lỗi
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    bot = telebot.TeleBot(config.API_TOKEN)
    print("✅ Bot đang khởi động...")
except Exception as e:
    print(f"❌ Lỗi khởi tạo Bot: {e}")
    exit(1)

# ==========================================
# 2. MENU GIAO DIỆN (UI/UX)
# ==========================================
def create_main_menu():
    """Tạo bàn phím menu chính (ReplyKeyboardMarkup)"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    # Định nghĩa các nút bấm với Emoji
    btn_gold = types.KeyboardButton("🌟 Giá Vàng Thế Giới")
    btn_stock = types.KeyboardButton("🇻🇳 Cổ Phiếu Việt Nam")
    btn_help = types.KeyboardButton("ℹ️ Hướng dẫn / Help")
    btn_contact = types.KeyboardButton("📞 Liên hệ Admin")
    
    # Sắp xếp bố cục (Layout)
    # Dòng 1: Vàng | Chứng khoán
    markup.add(btn_gold, btn_stock)
    # Dòng 2: Hướng dẫn | Liên hệ
    markup.add(btn_help, btn_contact)
    
    return markup

# ==========================================
# 3. LOGIC XỬ LÝ (MODULAR FUNCTIONS)
# ==========================================
def handle_gold_price(message):
    """Xử lý khi bấm nút Giá Vàng"""
    # Placeholder: Sau này sẽ thêm logic lấy giá vàng thực tế (API yfinance, v.v.)
    bot.reply_to(message, "⏳ Đang lấy dữ liệu giá Vàng thế giới...\n(Chức năng đang phát triển 🛠)")

def handle_vn_stock(message):
    """Xử lý khi bấm nút Cổ Phiếu VN"""
    # Placeholder: Sau này sẽ thêm logic lấy giá chứng khoán VN (API vnstock)
    bot.reply_to(message, "⏳ Đang lấy dữ liệu Cổ phiếu Việt Nam...\n(Chức năng đang phát triển 🛠)")

def handle_help(message):
    """Xử lý khi bấm nút Hướng dẫn"""
    help_text = (
        "🤖 **HƯỚNG DẪN SỬ DỤNG SUPER BOT**\n\n"
        "1. Nhấn '🌟 Giá Vàng Thế Giới' để xem giá vàng Real-time.\n"
        "2. Nhấn '🇻🇳 Cổ Phiếu Việt Nam' để xem tin tức thị trường.\n"
        "3. Nhấn '📞 Liên hệ Admin' nếu cần hỗ trợ."
    )
    bot.reply_to(message, help_text, parse_mode="Markdown")

def handle_contact(message):
    """Xử lý khi bấm nút Liên hệ"""
    contact_text = "📞 **Liên hệ Admin:**\n\nNếu bạn cần hỗ trợ, vui lòng nhắn tin trực tiếp cho Admin."
    bot.reply_to(message, contact_text, parse_mode="Markdown")

# ==========================================
# 4. HANDLERS (ĐIỀU HƯỚNG)
# ==========================================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    """Xử lý lệnh /start"""
    user_name = message.from_user.first_name
    welcome_msg = f"👋 Xin chào {user_name}!\nChào mừng bạn đến với **Super Bot Trading**.\nHãy chọn chức năng bên dưới 👇"
    
    bot.send_message(
        message.chat.id, 
        welcome_msg, 
        reply_markup=create_main_menu(), 
        parse_mode="Markdown"
    )

# Điều hướng tin nhắn văn bản (Text Filters)
@bot.message_handler(func=lambda message: True)
def echo_all(message):
    """Router điều hướng dựa trên nội dung tin nhắn"""
    text = message.text
    
    if text == "🌟 Giá Vàng Thế Giới":
        handle_gold_price(message)
    elif text == "🇻🇳 Cổ Phiếu Việt Nam":
        handle_vn_stock(message)
    elif text == "ℹ️ Hướng dẫn / Help":
        handle_help(message)
    elif text == "📞 Liên hệ Admin":
        handle_contact(message)
    else:
        # Phản hồi mặc định nếu không hiểu lệnh
        bot.reply_to(message, "Tôi chưa hiểu lệnh này. Vui lòng chọn menu bên dưới. 👇", reply_markup=create_main_menu())

# ==========================================
# 5. MAIN LOOP
# ==========================================
if __name__ == "__main__":
    print("🚀 Super Bot đang chạy... (Nhấn Ctrl+C để dừng)")
    try:
        bot.infinity_polling()
    except KeyboardInterrupt:
        print("\n🛑 Bot đã dừng.")
    except Exception as e:
        print(f"❌ Lỗi Runtime: {e}")
