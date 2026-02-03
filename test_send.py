import telebot
import sys

# Values from user file
API_TOKEN = "8288173761:AAEhh0Km0LVNZIel15flHEGGh3ixY-4v0Nw"
CHAT_ID = "1622117094"

bot = telebot.TeleBot(API_TOKEN)

print(f"Testing connection with Token: {API_TOKEN[:10]}... and Chat ID: {CHAT_ID}")

try:
    msg = "#TEST | Hello from Gold Bot! | 🚀\nIf you see this, the bot is working!"
    bot.send_message(CHAT_ID, msg)
    print("✅ SUCCESS: Message sent successfully!")
except Exception as e:
    print(f"❌ ERROR: Failed to send message.")
    print(f"Details: {e}")
    
    if "chat not found" in str(e).lower() or "bad request" in str(e).lower():
        print("\n⚠️  TIP: 'vinh' is likely not a valid Chat ID.")
        print("   - If it's a private chat, you need your numeric ID (e.g. 123456789).")
        print("   - You can get it by messaging @userinfobot on Telegram.")
        print("   - If it's a channel, use '@channelname' (bot must be admin).")
