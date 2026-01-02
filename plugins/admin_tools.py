import os
import sys
import time
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict

from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from hydrogram.errors import MessageNotModified, MessageIdInvalid, BadRequest

from info import ADMINS, LOG_CHANNEL
from database.users_chats_db import db
from database.ia_filterdb import db_count_documents, delete_files, delete_all_files, delete_by_quality
from utils import get_size, get_readable_time, temp

# ======================================================
# 🧠 CONFIG & INIT
# ======================================================

DASH_LOCKS = defaultdict(asyncio.Lock)

if not hasattr(temp, "INDEX_STATS"):
    temp.INDEX_STATS = {"running": False, "start": 0, "saved": 0}

if not hasattr(temp, "START_TIME"):
    temp.START_TIME = time.time()

# ======================================================
# 🛡 HELPERS
# ======================================================

async def safe_edit(msg, text, reply_markup=None):
    try:
        if msg.text == text: return True # Ignore same edit
        await msg.edit(text, reply_markup=reply_markup)
        return True
    except (MessageNotModified, MessageIdInvalid): return True
    except Exception as e:
        print(f"Edit Error: {e}")
        return False

def fmt(dt):
    if isinstance(dt, (int, float)):
        dt = datetime.utcfromtimestamp(dt)
    return dt.strftime("%d %b %Y, %I:%M %p")

# ======================================================
# 📊 DASHBOARD BUILDER
# ======================================================

async def build_dashboard():
    # Fetch Stats Asynchronously
    users_coro = db.total_users_count()
    chats_coro = asyncio.to_thread(db.groups.count_documents, {})
    files_coro = asyncio.to_thread(db_count_documents)
    prem_coro = db.premium.count_documents({"plan.premium": True})
    
    # Run in parallel
    users, chats, files, premium = await asyncio.gather(
        users_coro, chats_coro, files_coro, prem_coro
    )
    
    # DB Size (Requires DB Command)
    try:
        info = await db.db.command("dbstats")
        db_size = get_size(info.get("dataSize", 0))
    except:
        db_size = "N/A"

    uptime = get_readable_time(time.time() - temp.START_TIME)

    # Index Stats
    idx_txt = "💤 Idle"
    if temp.INDEX_STATS.get("running"):
        elapsed = time.time() - temp.INDEX_STATS['start']
        speed = temp.INDEX_STATS['saved'] / elapsed if elapsed > 0 else 0
        idx_txt = f"🚀 {speed:.1f} f/s"

    return (
        "📊 <b>ADMIN CONTROL PANEL</b>\n\n"
        f"👤 <b>Users:</b> `{users}`\n"
        f"👥 <b>Groups:</b> `{chats}`\n"
        f"📦 <b>Files:</b> `{files}`\n"
        f"💎 <b>Premium:</b> `{premium}`\n\n"
        f"⚡ <b>Index:</b> {idx_txt}\n"
        f"🗃 <b>DB Size:</b> `{db_size}`\n"
        f"⏱ <b>Uptime:</b> `{uptime}`"
    )

# ======================================================
# 🎛 BUTTONS
# ======================================================

def main_btns():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 Premium", callback_data="adm_prem"),
         InlineKeyboardButton("🗑 Delete", callback_data="adm_del")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="adm_ref"),
         InlineKeyboardButton("🔴 Restart", callback_data="adm_rst")],
        [InlineKeyboardButton("❌ Close", callback_data="close_data")]
    ])

def prem_btns():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add", callback_data="prm_add"),
         InlineKeyboardButton("➖ Rem", callback_data="prm_rem")],
        [InlineKeyboardButton("🔍 Check User", callback_data="prm_check"),
         InlineKeyboardButton("📊 Chart", callback_data="prm_chart")],
        [InlineKeyboardButton("🔙 Back", callback_data="adm_back")]
    ])

def del_btns():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 By Keyword", callback_data="del_key"),
         InlineKeyboardButton("📹 By Quality", callback_data="del_qual")],
        [InlineKeyboardButton("🗑 DELETE ALL", callback_data="del_all_ask")],
        [InlineKeyboardButton("🔙 Back", callback_data="adm_back")]
    ])

# ======================================================
# 🚀 /admin COMMAND
# ======================================================

@Client.on_message(filters.command(["admin", "dashboard"]) & filters.user(ADMINS))
async def admin_panel(bot, message):
    m = await message.reply("⏳ Loading...")
    txt = await build_dashboard()
    await safe_edit(m, txt, main_btns())

# ======================================================
# 🔁 CALLBACKS
# ======================================================

@Client.on_callback_query(filters.regex("^adm_"))
async def adm_cb(bot, query: CallbackQuery):
    if query.from_user.id not in ADMINS:
        return await query.answer("🔒 Admins Only", show_alert=True)

    act = query.data
    
    if act == "adm_ref":
        async with DASH_LOCKS[query.from_user.id]:
            txt = await build_dashboard()
            await safe_edit(query.message, txt, main_btns())
            await query.answer("✅ Refreshed")

    elif act == "adm_prem":
        await safe_edit(query.message, "💎 **Premium Manager**", prem_btns())

    elif act == "adm_del":
        await safe_edit(query.message, "🗑 **Delete Manager**", del_btns())

    elif act == "adm_back":
        txt = await build_dashboard()
        await safe_edit(query.message, txt, main_btns())

    elif act == "adm_rst":
        await query.answer("🔄 Restarting...", show_alert=True)
        await query.message.edit("🔄 Restarting Bot...")
        os.execl(sys.executable, sys.executable, "bot.py")

# ======================================================
# 🗑 DELETE CALLBACKS
# ======================================================

@Client.on_callback_query(filters.regex("^del_"))
async def del_cb(bot, query: CallbackQuery):
    if query.from_user.id not in ADMINS:
        return

    act = query.data

    if act == "del_key":
        await query.message.edit(
            "🔍 **Delete by Keyword**\n\nSend: `/delete keyword`\nExample: `/delete spiderman`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="adm_del")]])
        )

    elif act == "del_qual":
        btns = [
            [InlineKeyboardButton("480p", callback_data="dq_480p"),
             InlineKeyboardButton("720p", callback_data="dq_720p")],
            [InlineKeyboardButton("1080p", callback_data="dq_1080p"),
             InlineKeyboardButton("🔙 Back", callback_data="adm_del")]
        ]
        await query.message.edit("📹 **Select Quality to Delete:**", reply_markup=InlineKeyboardMarkup(btns))

    elif act == "del_all_ask":
        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ YES, DELETE ALL", callback_data="del_all_confirm")],
            [InlineKeyboardButton("❌ CANCEL", callback_data="adm_del")]
        ])
        await query.message.edit("⚠️ **WARNING**\n\nAre you sure you want to delete **ALL FILES**?", reply_markup=btn)

    elif act == "del_all_confirm":
        await query.message.edit("⏳ Deleting all files... This may take time.")
        c = await delete_all_files()
        await query.message.edit(f"✅ Deleted **{c}** files.", reply_markup=main_btns())
        
        try: await bot.send_message(LOG_CHANNEL, f"🗑 **ALL FILES DELETED** by {query.from_user.mention}")
        except: pass

@Client.on_callback_query(filters.regex("^dq_"))
async def del_qual_cb(bot, query):
    qual = query.data.split("_")[1]
    await query.message.edit(f"⏳ Deleting {qual} files...")
    c = await delete_by_quality(qual)
    await query.message.edit(f"✅ Deleted **{c}** files ({qual})", reply_markup=del_btns())

# ======================================================
# 💎 PREMIUM CALLBACKS (Shortened)
# ======================================================

@Client.on_callback_query(filters.regex("^prm_"))
async def prm_cb(bot, query):
    act = query.data
    
    if act == "prm_add":
        await query.message.edit(
            "➕ **Add Premium**\n\nCmd: `/addpremium ID DAYS`\nEx: `/addpremium 12345 30`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="adm_prem")]])
        )
        
    elif act == "prm_chart":
        # Simple stats
        c = await db.premium.count_documents({"plan.premium": True})
        await query.message.edit(f"📊 **Premium Users:** {c}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="adm_prem")]]))

# ======================================================
# 🗑 DELETE COMMAND
# ======================================================

@Client.on_message(filters.command("delete") & filters.user(ADMINS))
async def delete_cmd(bot, message):
    if len(message.command) < 2:
        return await message.reply("❌ Usage: `/delete keyword`")
    
    key = message.text.split(None, 1)[1]
    m = await message.reply(f"⏳ Deleting `{key}`...")
    
    c = await delete_files(key)
    await m.edit(f"✅ Deleted **{c}** files matching `{key}`")
    
    try: await bot.send_message(LOG_CHANNEL, f"🗑 Deleted `{key}` ({c} files) by {message.from_user.mention}")
    except: pass

