from telebot import types

def create_main_menu():
    """Tạo bàn phím menu chính (Level 1)"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    markup.add(
        types.KeyboardButton("🌟 Giá Vàng Thế Giới"),
        types.KeyboardButton("🇻🇳 Cổ Phiếu Việt Nam")
    )
    markup.add(
        types.KeyboardButton("ℹ️ Hướng dẫn / Help"),
        types.KeyboardButton("📞 Liên hệ Admin")
    )
    # Row 3
    markup.add(types.KeyboardButton("🦈 Săn Cá Mập"))
    return markup

def create_shark_menu():
    """Tạo bàn phím menu Cá Mập (Level 2)"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    markup.add(
        types.KeyboardButton("✅ Bật Cảnh Báo"),
        types.KeyboardButton("📊 Thống Kê Hôm Nay")
    )
    markup.add(types.KeyboardButton("🔙 Quay lại"))
    
    return markup

def create_stock_menu():
    """Tạo bàn phím menu Cổ Phiếu (Level 2)"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    # Row 1
    markup.add(types.KeyboardButton("📊 Tổng quan thị trường"))
    # Row 2
    markup.add(
        types.KeyboardButton("🔎 Tra cứu Cổ phiếu"),
        types.KeyboardButton("⭐ Watchlist")
    )
    # Row 3 - New Volatility button
    markup.add(types.KeyboardButton("📊 Biến Động Mạnh"))
    # Row 4 (Back)
    markup.add(types.KeyboardButton("🔙 Quay lại"))
    
    return markup

def send_welcome(bot, message):
    """Xử lý lệnh /start"""
    user_name = message.from_user.first_name
    welcome_msg = f"👋 Xin chào {user_name}!\nChào mừng bạn đến với **Super Bot Trading**.\nHãy chọn chức năng bên dưới 👇"
    
    bot.send_message(
        message.chat.id, 
        welcome_msg, 
        reply_markup=create_main_menu(), 
        parse_mode="Markdown"
    )

def handle_help(bot, message):
    help_text = (
        "🤖 **HƯỚNG DẪN SỬ DỤNG SUPER BOT**\n\n"
        "1. Nhấn '🌟 Giá Vàng Thế Giới' để xem giá vàng Real-time.\n"
        "2. Nhấn '🇻🇳 Cổ Phiếu Việt Nam' để xem tin tức thị trường.\n"
        "3. Nhấn '🦈 Săn Cá Mập' để theo dõi dòng tiền lớn (>1 Tỷ).\n"
        "4. Nhấn '📞 Liên hệ Admin' nếu cần hỗ trợ."
    )
    bot.reply_to(message, help_text, parse_mode="Markdown")

def handle_contact(bot, message):
    contact_text = "📞 **Liên hệ Admin:**\n\nNếu bạn cần hỗ trợ, vui lòng nhắn tin trực tiếp cho Admin."
    bot.reply_to(message, contact_text, parse_mode="Markdown")

def handle_vn_stock(bot, message):
    """Chuyển sang Menu Cổ Phiếu"""
    bot.send_message(
        message.chat.id,
        "📉 **Thị Trường Chứng Khoán Việt Nam**\nChọn chức năng bên dưới:",
        reply_markup=create_stock_menu(),
        parse_mode="Markdown"
    )

def handle_shark_menu(bot, message):
    """Chuyển sang Menu Cá Mập"""
    bot.send_message(
        message.chat.id,
        "🦈 **Săn Cá Mập (Big Shark)**\nChọn chức năng bên dưới:",
        reply_markup=create_shark_menu(),
        parse_mode="Markdown"
    )

def handle_back_main(bot, message):
    """Quay lại Menu Chính"""
    bot.send_message(
        message.chat.id,
        "🔙 Đã quay lại Menu Chính.",
        reply_markup=create_main_menu()
    )
