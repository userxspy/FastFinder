import asyncio
import hashlib
from math import ceil
from time import time
from collections import defaultdict

from hydrogram import Client, filters, enums
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from info import ADMINS, UPI_ID, UPI_NAME
from database.users_chats_db import db
from database.ia_filterdb import get_search_results
from utils import (
    get_size,
    is_premium,
    temp,
    learn_keywords,
    suggest_query
)

# =====================================================
# ⚙️ CONFIGURATION
# =====================================================
RESULTS_PER_PAGE_PM = 10      # PM में 10 results
RESULTS_PER_PAGE_GROUP = 8    # Group में 8 results (cleaner look)
RESULT_EXPIRE_TIME = 300      # 5 minutes (Results validity)
EXPIRE_DELETE_DELAY = 60      # Delete 1 min after expiry
RATE_LIMIT = 5                # Searches per minute
RATE_LIMIT_WINDOW = 60        # Window size

# RAM Storage for Rate Limiting
user_search_times = defaultdict(list)

# RAM Storage for Callback Data (Fix 64-byte limit)
if not hasattr(temp, 'CALLBACK_DATA'):
    temp.CALLBACK_DATA = {}

# Track message activity
if not hasattr(temp, 'MSG_ACTIVITY'):
    temp.MSG_ACTIVITY = {}


# =====================================================
# 🔧 ADMIN CHECK HELPER
# =====================================================
async def is_group_admin(client, chat_id, user_id):
    """Check if user is admin in the group"""
    try:
        if user_id in ADMINS: return True
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (
            enums.ChatMemberStatus.ADMINISTRATOR,
            enums.ChatMemberStatus.OWNER
        )
    except:
        return False


# =====================================================
# 🔄 SEARCH TOGGLE COMMANDS (ADMIN ONLY)
# =====================================================
@Client.on_message(filters.group & filters.command("search"))
async def search_toggle(client, message):
    try:
        if not await is_group_admin(client, message.chat.id, message.from_user.id):
            return await message.reply("❌ Only Admins can use this.", quote=True)
        
        args = message.text.split()
        stg = await db.get_settings(message.chat.id)
        
        if len(args) < 2:
            status = "✅ Enabled" if stg.get("search", True) else "❌ Disabled"
            return await message.reply(f"🔎 **Search Status:** {status}\n\nUse `/search on` or `/search off`")
        
        action = args[1].lower()
        if action == "on":
            stg["search"] = True
            await db.update_settings(message.chat.id, stg)
            await message.reply("✅ **Search Enabled!**")
        elif action == "off":
            stg["search"] = False
            await db.update_settings(message.chat.id, stg)
            await message.reply("❌ **Search Disabled!**")
        else:
            await message.reply("❌ Use `/search on` or `/search off`")
            
    except Exception as e:
        print(f"Toggle Error: {e}")


# =====================================================
# 🛡️ RATE LIMITER
# =====================================================
def is_rate_limited(user_id):
    now = time()
    history = user_search_times[user_id]
    # Clean old records
    user_search_times[user_id] = [t for t in history if now - t < RATE_LIMIT_WINDOW]
    
    if len(user_search_times[user_id]) >= RATE_LIMIT:
        return True
    
    user_search_times[user_id].append(now)
    return False


# =====================================================
# 🔑 CALLBACK KEY MANAGER (HASHING)
# =====================================================
def make_callback_key(search, offset, source_chat_id, owner, is_pm):
    """Generate short key and store data in RAM"""
    try:
        # Create Hash
        raw = f"{search}_{offset}_{source_chat_id}_{owner}_{time()}"
        key = hashlib.md5(raw.encode()).hexdigest()[:10] # 10 chars key
        
        # Store Data
        temp.CALLBACK_DATA[key] = {
            'search': search,
            'offset': offset,
            'chat': source_chat_id,
            'owner': owner,
            'is_pm': is_pm,
            't': time()
        }
        
        # Cleanup Old Keys (Older than 10 mins)
        now = time()
        if len(temp.CALLBACK_DATA) > 1000:
            keys = list(temp.CALLBACK_DATA.keys())
            for k in keys:
                if now - temp.CALLBACK_DATA[k]['t'] > 600:
                    del temp.CALLBACK_DATA[k]
                    
        return key
    except:
        return "expired"

def get_callback_data(key):
    return temp.CALLBACK_DATA.get(key)


# =====================================================
# 📩 MESSAGE HANDLER
# =====================================================
@Client.on_message(filters.text & filters.incoming & (filters.group | filters.private))
async def filter_handler(client, message):
    try:
        if message.text.startswith("/"): return # Ignore commands
        
        txt = message.text.strip()
        if len(txt) < 2: return # Too short

        user_id = message.from_user.id
        chat_id = message.chat.id
        is_pm = message.chat.type == enums.ChatType.PRIVATE
        
        # ==============================
        # 🔒 PM: CHECK PREMIUM
        # ==============================
        if is_pm:
            if user_id not in ADMINS:
                is_prem = await is_premium(user_id, client)
                if not is_prem:
                    btn = InlineKeyboardMarkup([[InlineKeyboardButton("💎 Buy Premium", callback_data="buy_premium")]])
                    return await message.reply(
                        "🔒 **Premium Required**\n\nPM Search is only for Premium users.\nBuy Premium to unlock.",
                        reply_markup=btn,
                        quote=True
                    )
            source_chat = user_id
        
        # ==============================
        # 👥 GROUP: CHECK SETTINGS & SPAM
        # ==============================
        else:
            stg = await db.get_settings(chat_id)
            if stg.get("search") is False: return # Search disabled

            # Rate Limit (Skip for Admins/Premium)
            if user_id not in ADMINS:
                is_prem = await is_premium(user_id) # Silent check
                if not is_prem and is_rate_limited(user_id):
                    return await message.reply("⚠️ **Slow Down!**\n\nWait 1 minute or buy Premium.", quote=True)
            
            source_chat = chat_id

        # Auto Learn Keywords
        learn_keywords(txt)
        
        # Sanitize
        search = txt.replace('"', '').replace("'", "").strip()
        
        await send_results(client, chat_id, user_id, search, 0, source_chat, is_pm)
        
    except Exception as e:
        print(f"Filter Error: {e}")


# =====================================================
# 🔎 SEND RESULTS
# =====================================================
async def send_results(client, chat_id, owner, search, offset, source_chat, is_pm, msg=None, retry=False):
    try:
        limit = RESULTS_PER_PAGE_PM if is_pm else RESULTS_PER_PAGE_GROUP
        files, next_offset, total = await get_search_results(search, offset=offset, limit=limit)
        
        # Smart Fallback (Fuzzy)
        if not files and not retry:
            alt = suggest_query(search)
            if alt:
                return await send_results(client, chat_id, owner, alt, 0, source_chat, is_pm, msg, True)

        if not files:
            txt = f"❌ **No Results Found:** `{search}`"
            if msg: await msg.edit(txt)
            else: 
                m = await client.send_message(chat_id, txt)
                asyncio.create_task(auto_delete(m, 10)) # Delete 'No results' fast
            return

        # Formatting
        page = (offset // limit) + 1
        total_pages = ceil(total / limit)
        is_prem = await is_premium(owner)
        crown = "💎" if is_prem else "👤"
        
        text = f"{crown} **Search:** `{search}`\n**Found:** `{total}` | **Page:** `{page}/{total_pages}`\n\n"
        
        bot_username = temp.U_NAME or "YourBot" # Safety fallback
        
        for f in files:
            f_id = f.get('_id')
            f_name = f.get('file_name', 'Unknown')
            f_size = get_size(f.get('file_size', 0))
            
            # Deep Link
            link = f"https://t.me/{bot_username}?start=file_{source_chat}_{f_id}"
            text += f"📁 [{f_size}] [{f_name}]({link})\n\n"

        # Buttons
        btns = []
        if offset > 0:
            key = make_callback_key(search, offset - limit, source_chat, owner, is_pm)
            btns.append(InlineKeyboardButton("◀️ Prev", callback_data=f"pg#{key}"))
            
        if next_offset:
            key = make_callback_key(search, offset + limit, source_chat, owner, is_pm)
            btns.append(InlineKeyboardButton("Next ▶️", callback_data=f"pg#{key}"))

        markup = InlineKeyboardMarkup([btns]) if btns else None

        if msg:
            await msg.edit(text, reply_markup=markup, disable_web_page_preview=True)
            temp.MSG_ACTIVITY[msg.id] = time() # Update activity
        else:
            m = await client.send_message(chat_id, text, reply_markup=markup, disable_web_page_preview=True)
            temp.MSG_ACTIVITY[m.id] = time()
            asyncio.create_task(auto_expire(m))

    except Exception as e:
        print(f"Send Results Error: {e}")


# =====================================================
# 🔁 PAGINATION HANDLER
# =====================================================
@Client.on_callback_query(filters.regex("^pg#"))
async def pagination(client, query):
    try:
        _, key = query.data.split("#")
        data = get_callback_data(key)
        
        if not data:
            return await query.answer("⌛ Result Expired", show_alert=True)
        
        if query.from_user.id != data['owner'] and query.from_user.id not in ADMINS:
            return await query.answer("❌ Not your search!", show_alert=True)
            
        await send_results(
            client, 
            query.message.chat.id, 
            data['owner'], 
            data['search'], 
            data['offset'], 
            data['chat'], 
            data['is_pm'], 
            query.message
        )
        
    except Exception as e:
        print(f"Pagination Error: {e}")


# =====================================================
# ⏱ AUTO EXPIRE
# =====================================================
async def auto_expire(msg):
    try:
        msg_id = msg.id
        while True:
            await asyncio.sleep(RESULT_EXPIRE_TIME)
            
            # Check last activity
            last_act = temp.MSG_ACTIVITY.get(msg_id, 0)
            if time() - last_act < RESULT_EXPIRE_TIME:
                continue # Was active recently
            break
            
        await msg.edit("⌛ **Results Expired**", reply_markup=None)
        await asyncio.sleep(EXPIRE_DELETE_DELAY)
        await msg.delete()
        
        # Cleanup
        temp.MSG_ACTIVITY.pop(msg_id, None)
        
    except:
        pass

async def auto_delete(msg, delay):
    await asyncio.sleep(delay)
    try: await msg.delete()
    except: pass

