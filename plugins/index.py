import time
import asyncio
from pymongo import MongoClient

from hydrogram import Client, filters, enums
from hydrogram.errors import FloodWait, MessageNotModified
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from info import ADMINS, DATA_DATABASE_URL, DATABASE_NAME, INDEX_LOG_CHANNEL
from database.ia_filterdb import save_file
from utils import get_readable_time

# =====================================================
# GLOBALS
# =====================================================
LOCK = asyncio.Lock()
CANCEL = False
WAITING_SKIP = {} 

# =====================================================
# RESUME DB
# =====================================================
mongo = MongoClient(DATA_DATABASE_URL)
db = mongo[DATABASE_NAME]
resume_col = db["index_resume"]

def get_resume(chat_id):
    d = resume_col.find_one({"_id": chat_id})
    return d["last_id"] if d else None

def set_resume(chat_id, msg_id):
    resume_col.update_one(
        {"_id": chat_id},
        {"$set": {"last_id": msg_id}},
        upsert=True
    )

# =====================================================
# HELPERS
# =====================================================
async def auto_delete(bot, chat_id, msg_id, delay=120):
    await asyncio.sleep(delay)
    try:
        await bot.delete_messages(chat_id, msg_id)
    except:
        pass

async def send_log(bot, text):
    if not INDEX_LOG_CHANNEL:
        return
    try:
        await bot.send_message(INDEX_LOG_CHANNEL, text)
    except:
        pass

# =====================================================
# ENTRY POINT
# forward / link → index
# =====================================================
@Client.on_message(filters.private & filters.user(ADMINS) & filters.incoming)
async def start_index(bot, message):
    global CANCEL

    # अगर skip wait चल रहा है तो ignore
    if message.from_user.id in WAITING_SKIP:
        return

    if LOCK.locked():
        return await message.reply("⏳ Indexing already running")

    try:
        # ---- LINK ----
        if message.text and message.text.startswith("https://t.me"):
            parts = message.text.split("/")
            last_msg_id = int(parts[-1])
            raw = parts[-2]
            chat_id = int("-100" + raw) if raw.isdigit() else raw

        # ---- FORWARD ----
        elif message.forward_from_chat and message.forward_from_chat.type == enums.ChatType.CHANNEL:
            last_msg_id = message.forward_from_message_id
            chat_id = message.forward_from_chat.id

        else:
            return

        chat = await bot.get_chat(chat_id)
        if chat.type != enums.ChatType.CHANNEL:
            return await message.reply("❌ Only channels supported")

    except Exception as e:
        return await message.reply(f"❌ Error: `{e}`")

    # ---- ASK SKIP (STATE SET) ----
    ask = await message.reply("⏩ Send skip message number (0 for none)")
    WAITING_SKIP[message.from_user.id] = {
        "chat_id": chat_id,
        "last_msg_id": last_msg_id,
        "title": chat.title,
        "ask_id": ask.id
    }
    return

# =====================================================
# HANDLE SKIP INPUT
# =====================================================
@Client.on_message(filters.private & filters.user(ADMINS) & filters.text)
async def handle_skip(bot, message):
    uid = message.from_user.id
    if uid not in WAITING_SKIP:
        return

    try:
        skip = int(message.text)
    except:
        err = await message.reply("❌ Skip must be a number")
        await asyncio.sleep(2)
        await err.delete()
        return

    data = WAITING_SKIP.pop(uid)

    try:
        await bot.delete_messages(message.chat.id, data["ask_id"])
    except:
        pass

    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "✅ START",
            callback_data=f"idx#start#{data['chat_id']}#{data['last_msg_id']}#{skip}"
        )],
        [InlineKeyboardButton("❌ CANCEL", callback_data="idx#close")]
    ])

    await message.reply(
        f"📢 **Channel:** `{data['title']}`\n"
        f"🆔 **ID:** `{data['chat_id']}`\n"
        f"📊 **Last Message:** `{data['last_msg_id']}`",
        reply_markup=btn
    )

# =====================================================
# CALLBACK
# =====================================================
@Client.on_callback_query(filters.regex("^idx#"))
async def index_callback(bot, query):
    global CANCEL
    data = query.data.split("#")

    if data[1] == "close":
        return await query.message.edit("❌ Cancelled")

    _, _, chat_id, last_id, skip = data
    chat = await bot.get_chat(int(chat_id))

    await query.message.edit("⚡ Indexing started…")

    async with LOCK:
        CANCEL = False
        await index_worker(
            bot,
            query.message,
            int(chat_id),
            int(last_id),
            int(skip),
            chat.title
        )

# =====================================================
# CORE INDEX LOOP (FIXED & OPTIMIZED)
# =====================================================
async def index_worker(bot, status, chat_id, last_msg_id, skip, channel_title):
    global CANCEL

    start_time = time.time()
    saved = dup = err = nomedia = 0
    processed = 0

    # 🔥 FIX 1: पुराने Resume ID को "STOP POINT" बनाओ
    old_resume_id = get_resume(chat_id)
    stop_id = old_resume_id if old_resume_id else 0
    
    # 🔥 FIX 2: स्कैनिंग हमेशा लेटेस्ट मैसेज से शुरू करो
    current_id = last_msg_id - skip

    try:
        # 🔥 FIX 3: लूप तब तक चलाओ जब तक पुराने स्टॉप पॉइंट तक न पहुंच जाओ
        while current_id > stop_id:
            if CANCEL:
                break

            try:
                msg = await bot.get_messages(chat_id, current_id)
            except FloodWait as e:
                await asyncio.sleep(e.value)
                continue
            except Exception:
                # अगर मैसेज डिलीटेड है तो स्किप
                current_id -= 1
                continue

            processed += 1

            # Status update (हर 50 msg पर)
            if processed % 50 == 0:
                elapsed = time.time() - start_time
                speed = processed / elapsed if elapsed else 0
                eta = (current_id - stop_id) / speed if speed else 0

                try:
                    btn = InlineKeyboardMarkup(
                        [[InlineKeyboardButton("🛑 STOP", callback_data="idx#cancel")]]
                    )
                    await status.edit(
                        f"📊 `{processed}` scanned\n"
                        f"✅ `{saved}` | ♻️ `{dup}` | ❌ `{err}`\n"
                        f"⚡ `{speed:.2f}/s`\n"
                        f"⏳ `{get_readable_time(eta)}`",
                        reply_markup=btn
                    )
                except MessageNotModified:
                    pass

            # Media Validation
            if not msg or not msg.media:
                nomedia += 1
                current_id -= 1
                continue

            if msg.media not in (
                enums.MessageMediaType.VIDEO,
                enums.MessageMediaType.DOCUMENT
            ):
                nomedia += 1
                current_id -= 1
                continue

            media = getattr(msg, msg.media.value, None)
            if not media:
                current_id -= 1
                continue

            media.caption = msg.caption
            res = await save_file(media)

            if res == "suc":
                saved += 1
            elif res == "dup":
                dup += 1
            else:
                err += 1

            # अगला मैसेज चेक करो (Descending Order)
            current_id -= 1
        
        # 🔥 FIX 4: जब पूरा हो जाए, तो Resume ID को सबसे हाईएस्ट ID (last_msg_id) पर सेट करो
        # ताकि अगली बार बोट को पता हो कि यहाँ तक स्कैन हो चुका है।
        if not CANCEL:
            set_resume(chat_id, last_msg_id)

    except Exception as e:
        await status.edit(f"❌ Failed: `{e}`")
        return

    total_time = get_readable_time(time.time() - start_time)

    # ---- ADMIN CHAT (AUTO DELETE) ----
    final_msg = await status.edit(
        f"✅ **Index Completed**\n\n"
        f"📢 `{channel_title}`\n"
        f"🆔 `{chat_id}`\n\n"
        f"✅ `{saved}` | ♻️ `{dup}` | ❌ `{err}` | 🚫 `{nomedia}`\n"
        f"⏱ `{total_time}`"
    )
    asyncio.create_task(auto_delete(bot, final_msg.chat.id, final_msg.id, 120))

    # ---- PERMANENT LOG CHANNEL ----
    await send_log(
        bot,
        "📊 **Index Report**\n\n"
        f"📢 **Channel:** `{channel_title}`\n"
        f"🆔 **Channel ID:** `{chat_id}`\n\n"
        f"✅ **Saved:** `{saved}`\n"
        f"♻️ **Duplicate:** `{dup}`\n"
        f"❌ **Errors:** `{err}`\n"
        f"🚫 **Non-media:** `{nomedia}`\n"
        f"⏱ **Time:** `{total_time}`"
    )

# =====================================================
# STOP
# =====================================================
@Client.on_callback_query(filters.regex("^idx#cancel"))
async def stop_index(bot, query):
    global CANCEL
    CANCEL = True
    await query.answer("Stopping…", show_alert=True)

