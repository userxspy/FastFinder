import asyncio
from datetime import datetime, timedelta
from hydrogram import Client, filters, enums
from hydrogram.types import ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from database.users_chats_db import db
from info import ADMINS
from utils import temp

# =========================
# CONFIG
# =========================
MAX_WARNS = 3
AUTO_MUTE_TIME = 600  # 10 minutes

# =========================
# HELPERS
# =========================

async def is_admin(client, chat_id, user_id):
    try:
        if user_id in ADMINS: return True
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (
            enums.ChatMemberStatus.ADMINISTRATOR,
            enums.ChatMemberStatus.OWNER
        )
    except:
        return False

# =========================
# MODERATION (REPLY)
# =========================

@Client.on_message(filters.group & filters.reply & filters.command("mute"))
async def mute_user(client, message):
    if not await is_admin(client, message.chat.id, message.from_user.id): return
    user = message.reply_to_message.from_user
    until = datetime.utcnow() + timedelta(seconds=AUTO_MUTE_TIME)
    try:
        await client.restrict_chat_member(message.chat.id, user.id, ChatPermissions(), until_date=until)
        await message.reply(f"🔇 {user.mention} muted for 10m.")
    except Exception as e:
        await message.reply(f"❌ Error: {e}")

@Client.on_message(filters.group & filters.reply & filters.command("unmute"))
async def unmute_user(client, message):
    if not await is_admin(client, message.chat.id, message.from_user.id): return
    user = message.reply_to_message.from_user
    try:
        await client.restrict_chat_member(message.chat.id, user.id, ChatPermissions(can_send_messages=True))
        await message.reply(f"🔊 {user.mention} unmuted.")
    except Exception as e:
        await message.reply(f"❌ Error: {e}")

@Client.on_message(filters.group & filters.reply & filters.command("ban"))
async def ban_user(client, message):
    if not await is_admin(client, message.chat.id, message.from_user.id): return
    user = message.reply_to_message.from_user
    try:
        await client.ban_chat_member(message.chat.id, user.id)
        await message.reply(f"🚫 {user.mention} banned.")
    except Exception as e:
        await message.reply(f"❌ Error: {e}")

# =========================
# BLACKLIST SYSTEM
# =========================

@Client.on_message(filters.group & filters.command("addblacklist"))
async def add_bl(client, message):
    if not await is_admin(client, message.chat.id, message.from_user.id): return
    if len(message.command) < 2: return await message.reply("❌ Usage: `/addblacklist word`")
    
    word = message.text.split(None, 1)[1].lower()
    data = await db.get_settings(message.chat.id)
    bl = data.get("blacklist", [])
    
    if word not in bl:
        bl.append(word)
        data["blacklist"] = bl
        await db.update_settings(message.chat.id, data)
        await message.reply(f"✅ Added `{word}` to blacklist.")
    else:
        await message.reply("⚠️ Already in blacklist.")

@Client.on_message(filters.group & filters.command("removeblacklist"))
async def rem_bl(client, message):
    if not await is_admin(client, message.chat.id, message.from_user.id): return
    word = message.text.split(None, 1)[1].lower()
    data = await db.get_settings(message.chat.id)
    bl = data.get("blacklist", [])
    
    if word in bl:
        bl.remove(word)
        data["blacklist"] = bl
        await db.update_settings(message.chat.id, data)
        await message.reply(f"✅ Removed `{word}` from blacklist.")
    else:
        await message.reply("⚠️ Not found in blacklist.")

# =========================
# DLINK (DELAYED DELETE) - UPDATED
# =========================

@Client.on_message(filters.group & filters.command("dlink"))
async def add_dlink(client, message):
    if not await is_admin(client, message.chat.id, message.from_user.id): return
    
    args = message.text.split()
    if len(args) < 2: return await message.reply("❌ Usage: `/dlink word` or `/dlink 10m word`")
    
    delay = 300 # Default 5m
    idx = 1
    
    # Check if time provided
    if args[1][-1] in ['m', 'h'] and args[1][:-1].isdigit():
        val = int(args[1][:-1])
        delay = val * 60 if args[1][-1] == 'm' else val * 3600
        idx = 2
        
    word = " ".join(args[idx:]).lower()
    if not word: return await message.reply("❌ Word required")
    
    data = await db.get_settings(message.chat.id)
    dl = data.get("dlink", {})
    dl[word] = delay
    data["dlink"] = dl
    
    await db.update_settings(message.chat.id, data)
    await message.reply(f"✅ DLink added for `{word}` ({delay}s)")

@Client.on_message(filters.group & filters.command("dlinklist"))
async def list_dlink(client, message):
    if not await is_admin(client, message.chat.id, message.from_user.id): return
    data = await db.get_settings(message.chat.id)
    dl = data.get("dlink", {})
    
    if not dl: return await message.reply("📭 Empty")
    
    txt = "📝 **DLink List:**\n\n"
    for k, v in dl.items():
        txt += f"• `{k}` ➔ {v}s\n"
        
    await message.reply(txt)

# =========================
# FILTER HANDLER (BL + DLINK)
# =========================

@Client.on_message(filters.group & filters.text)
async def group_filters(client, message):
    chat_id = message.chat.id
    txt = message.text.lower()
    
    # Get Settings (Cached)
    if chat_id in temp.SETTINGS:
        data = temp.SETTINGS[chat_id]
    else:
        data = await db.get_settings(chat_id)
        temp.SETTINGS[chat_id] = data

    # 1. Blacklist Check (Skip Admins)
    if not await is_admin(client, chat_id, message.from_user.id):
        bl = data.get("blacklist", [])
        for w in bl:
            if w in txt:
                try: await message.delete()
                except: pass
                return # Stop further processing

    # 2. DLink Check (DELETE FOR EVERYONE)
    dl = data.get("dlink", {})
    for w, delay in dl.items():
        if w in txt:
            # Schedule Delete
            asyncio.create_task(delayed_delete(message, delay))
            return

async def delayed_delete(msg, delay):
    await asyncio.sleep(delay)
    try: await msg.delete()
    except: pass

# =========================
# CACHE CLEAR & BUTTONS
# =========================

@Client.on_message(filters.command("clearcache") & filters.user(ADMINS))
async def clear_cache_cmd(bot, message):
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🧹 Clear Cache", callback_data="cls_cache"),
         InlineKeyboardButton("❌ Close", callback_data="close_data")]
    ])
    await message.reply("⚙️ **System Maintenance**\n\nClick below to clear RAM cache.", reply_markup=btn)

@Client.on_callback_query(filters.regex("^cls_cache$"))
async def clear_cache_cb(bot, query):
    if query.from_user.id not in ADMINS:
        return await query.answer("🔒 Admins Only", show_alert=True)
        
    # Clear RAM
    temp.SETTINGS.clear()
    temp.FILES.clear()
    temp.PREMIUM.clear()
    temp.KEYWORDS.clear()
    
    await query.answer("✅ Cache Cleared!", show_alert=True)
    await query.message.edit("✅ **System Cache Cleared Successfully!**")

# =========================
# PREMIUM APPROVAL BUTTONS
# =========================

@Client.on_message(filters.command("approve") & filters.reply & filters.user(ADMINS))
async def approve_user_cmd(bot, message):
    user = message.reply_to_message.from_user
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Approve", callback_data=f"ap_ok_{user.id}"),
         InlineKeyboardButton("❌ Reject", callback_data=f"ap_no_{user.id}")]
    ])
    await message.reply(f"👤 **User:** {user.mention}\n\nApprove access?", reply_markup=btn)

@Client.on_callback_query(filters.regex("^ap_ok_"))
async def approve_cb(bot, query):
    uid = int(query.data.split("_")[2])
    # Logic to approve (e.g., add to premium DB) is handled in premium.py mostly
    # Here we just show a placeholder
    await query.answer("✅ Approved")
    await query.message.edit(f"✅ User `{uid}` Approved!")

@Client.on_callback_query(filters.regex("^ap_no_"))
async def reject_cb(bot, query):
    uid = int(query.data.split("_")[2])
    await query.answer("❌ Rejected")
    await query.message.edit(f"❌ User `{uid}` Rejected!")

