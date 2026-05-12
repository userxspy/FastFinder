import asyncio
import json
import logging
import os
import random
from hydrogram import Client, filters
from hydrogram.errors import FloodWait, SessionPasswordNeeded
from info import API_ID, API_HASH, ADMINS

# Files for saving data locally
CONFIG_FILE = "transfer_config.json"
STATE_FILE = "transfer_state.json"
LOG_FILE = "transfer_errors.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding='utf-8'), logging.StreamHandler()]
)
logger = logging.getLogger("TransferPlugin")

is_transferring = False

# ----------------- HELPER FUNCTIONS -----------------
def load_data(filename, default_data):
    if os.path.exists(filename):
        with open(filename, "r") as f:
            return json.load(f)
    return default_data

def save_data(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=4)

# ----------------- BACKGROUND TRANSFER LOGIC -----------------
async def run_transfer(bot, message, config):
    global is_transferring
    is_transferring = True
    
    session_str = config["session_string"]
    src_chat = config["source_chat"]
    tgt_chat = config["target_chat"]
    
    status_msg = await message.reply("🚀 **Transfer Process Started!**\nConnecting to User Session...")

    user_app = Client("transfer_user", session_string=session_str, api_id=API_ID, api_hash=API_HASH, in_memory=True)
    
    try:
        await user_app.start()
        state = load_data(STATE_FILE, {"last_id": 0, "scanned": 0, "copied": 0, "skipped": 0})
        last_id = state["last_id"]
        
        max_id = 0
        async for msg in user_app.get_chat_history(src_chat, limit=1):
            max_id = msg.id
            break
            
        if max_id == 0 or last_id >= max_id:
            await status_msg.edit("✅ **No new messages to transfer.** Everything is up to date!")
            await user_app.stop()
            is_transferring = False
            return

        await status_msg.edit(f"🔄 **Resuming Transfer**\n📍 Last Processed ID: {last_id}\n🎯 Target Max ID: {max_id}")

        chunk_size = 200
        for chunk_start in range(last_id + 1, max_id + 1, chunk_size):
            if not is_transferring: break
            
            chunk_end = min(chunk_start + chunk_size, max_id + 1)
            chunk_ids = list(range(chunk_start, chunk_end))
            
            messages = await user_app.get_messages(src_chat, chunk_ids)
            
            for msg in messages:
                if not is_transferring: break
                
                state["scanned"] += 1
                msg_id = msg.id

                if not msg or msg.empty:
                    state["skipped"] += 1
                elif getattr(msg, "photo", None) or getattr(msg, "video", None) or getattr(msg, "document", None):
                    try:
                        await msg.copy(tgt_chat)
                        state["copied"] += 1
                        await asyncio.sleep(random.uniform(2.0, 4.0))
                    except FloodWait as e:
                        await asyncio.sleep(e.value + 2)
                        await msg.copy(tgt_chat)
                        state["copied"] += 1
                        await asyncio.sleep(random.uniform(2.0, 4.0))
                    except Exception as e:
                        logger.error(f"Error copying msg {msg_id}: {e}")
                        state["skipped"] += 1
                else:
                    state["skipped"] += 1

                state["last_id"] = msg_id
            
            save_data(STATE_FILE, state)
            
            # Update Live Status every 5 chunks (1000 messages)
            if (chunk_start // chunk_size) % 5 == 0:
                try: await status_msg.edit(f"⏳ **Transferring...**\n\n📊 Scanned: {state['scanned']}\n✅ Copied: {state['copied']}\n⏭ Skipped: {state['skipped']}\n\n📍 Last Processed ID: {state['last_id']}")
                except: pass

        await user_app.stop()
        if is_transferring:
            await message.reply(f"🎉 **Transfer Complete!**\n\n📊 Final Stats:\nScanned: {state['scanned']}\nCopied: {state['copied']}\nSkipped: {state['skipped']}")
            
    except Exception as e:
        logger.error(f"Transfer Error: {e}")
        await message.reply(f"❌ **Error occurred:** `{e}`")
    finally:
        is_transferring = False


# ----------------- INTERACTIVE WIZARD COMMAND -----------------
@Client.on_message(filters.command("transfer") & filters.user(ADMINS) & filters.private)
async def interactive_transfer_wizard(client, message):
    global is_transferring
    if is_transferring:
        return await message.reply("⚠️ **Transfer is already running!** Send `/stop_transfer` first.")
    
    if not API_ID or not API_HASH:
        return await message.reply("❌ `API_ID` और `API_HASH` info.py में सेट नहीं है!")

    config = load_data(CONFIG_FILE, {"session_string": "", "source_chat": 0, "target_chat": 0})

    try:
        # STEP 1: SESSION STRING CHECK / GENERATION
        generate_new = True
        if config.get("session_string"):
            ask_msg = await message.reply("✅ आपके पास पहले से एक **Saved Session** मौजूद है।\nक्या आप नया Session बनाना चाहते हैं? \n\n(रिप्लाई करें: `yes` या `no`)")
            ans_msg = await client.listen(message.chat.id, timeout=60)
            if ans_msg.text.lower().strip() == "no":
                generate_new = False
        
        if generate_new:
            await message.reply("📱 **अपना मोबाइल नंबर भेजें**\n(कंट्री कोड के साथ, जैसे: `+919876543210`)")
            phone_msg = await client.listen(message.chat.id, timeout=60)
            phone_number = phone_msg.text.strip().replace(" ", "")
            
            temp_app = Client("temp_gen", api_id=API_ID, api_hash=API_HASH, in_memory=True)
            await temp_app.connect()
            
            try:
                code_info = await temp_app.send_code(phone_number)
            except Exception as e:
                await temp_app.disconnect()
                return await message.reply(f"❌ OTP भेजने में एरर: `{e}`")
                
            await message.reply("💬 **OTP भेजा गया!**\n\nकृपया अपने Telegram ऐप में आया हुआ OTP यहाँ भेजें।\n⚠️ **जरूरी:** OTP के बीच में स्पेस लगा कर भेजें (जैसे: `1 2 3 4 5`)")
            otp_msg = await client.listen(message.chat.id, timeout=120)
            otp = otp_msg.text.replace(" ", "")
            
            try:
                await temp_app.sign_in(phone_number, code_info.phone_code_hash, otp)
            except SessionPasswordNeeded:
                await message.reply("🔐 आपके अकाउंट में **2-Step Verification** लगा है।\nकृपया अपना पासवर्ड भेजें:")
                pwd_msg = await client.listen(message.chat.id, timeout=60)
                await temp_app.check_password(pwd_msg.text)
            except Exception as e:
                await temp_app.disconnect()
                return await message.reply(f"❌ गलत OTP या एरर: `{e}`")
            
            # Save new session internally
            config["session_string"] = await temp_app.export_session_string()
            save_data(CONFIG_FILE, config)
            await temp_app.disconnect()
            await message.reply("✅ **Session Successfully Generated & Saved Internally!** 🔐")

        # STEP 2: SOURCE CHAT ID
        await message.reply("📥 **Source Chat ID भेजें**\nजहाँ से मैसेज कॉपी करने हैं (e.g. `-1001234567890`):")
        src_msg = await client.listen(message.chat.id, timeout=60)
        config["source_chat"] = int(src_msg.text.strip())

        # STEP 3: TARGET CHAT ID
        await message.reply("📤 **Target Chat ID भेजें**\nजहाँ मैसेज भेजने हैं (e.g. `-1009876543210`):")
        tgt_msg = await client.listen(message.chat.id, timeout=60)
        config["target_chat"] = int(tgt_msg.text.strip())

        # Save Final Config
        save_data(CONFIG_FILE, config)
        await message.reply(f"✅ **Setup Complete!**\n\n📥 Source: `{config['source_chat']}`\n📤 Target: `{config['target_chat']}`\n\n⏳ बैकग्राउंड में ट्रांसफर शुरू किया जा रहा है...")

        # STEP 4: START TRANSFER IN BACKGROUND
        asyncio.create_task(run_transfer(client, message, config))

    except asyncio.TimeoutError:
        await message.reply("⏱️ **टाइमआउट!** आपने जवाब देने में बहुत देर कर दी। कृपया दोबारा `/transfer` भेजें।")
    except ValueError:
        await message.reply("❌ **गलत ID!** ID में सिर्फ नंबर होने चाहिए। कृपया दोबारा `/transfer` भेजें।")
    except Exception as e:
        await message.reply(f"❌ **अप्रत्याशित एरर:** `{e}`")

@Client.on_message(filters.command("stop_transfer") & filters.user(ADMINS))
async def stop_transfer_cmd(client, message):
    global is_transferring
    if is_transferring:
        is_transferring = False
        await message.reply("🛑 **Stopping transfer...** State save करके प्रोसेस को रोका जा रहा है।")
    else:
        await message.reply("⚠️ **कोई ट्रांसफर चालू नहीं है!**")
