import sys, time, asyncio
from datetime import datetime

from hydrogram import Client, filters
from hydrogram.errors import ListenerTimeout

from info import ADMINS, LOG_CHANNEL
from database.users_chats_db import db
from database.ia_filterdb import db_count_documents, delete_files, delete_all_files
from utils import get_size, get_readable_time, temp

if not hasattr(temp, "START_TIME"): temp.START_TIME = time.time()

# ======================================================
# 📊 SIMPLE ADMIN STATS (NO BUTTONS)
# ======================================================
@Client.on_message(filters.command(["admin", "dashboard", "stats"]) & filters.user(ADMINS))
async def simple_admin_stats(bot, m):
    msg = await m.reply("⏳ Fetching stats...")
    
    # 🚀 Perfectly Awaited DB Calls
    try: u_count = await db.total_users_count()
    except: u_count = 0
    
    try: c_count = await db.groups.count_documents({})
    except: c_count = 0
    
    try: f_count = await db_count_documents()
    except: f_count = 0
    
    try: p_count = await db.premium.count_documents({"plan.premium": True})
    except: p_count = 0
    
    try: d_size = get_size((await db.users.database.command("dbstats")).get("dataSize", 0))
    except: d_size = "0 B"
    
    idx = getattr(temp, "INDEX_STATS", {})
    speed = f"🚀 {idx.get('saved', 0)/max(1, time.time()-idx.get('start', time.time())):.2f} files/sec" if idx.get("running") else "❌ Not running"
    
    text = (
        f"📊 **ADMIN CONTROL PANEL**\n\n"
        f"👤 Users: `{u_count}`\n"
        f"👥 Groups: `{c_count}`\n"
        f"📦 Indexed Files: `{f_count}`\n"
        f"💎 Premium Users: `{p_count}`\n\n"
        f"⚡ Index Speed: {speed}\n"
        f"🗃 DB Size: `{d_size}`\n\n"
        f"⏱ Uptime: `{get_readable_time(time.time() - temp.START_TIME)}`\n"
        f"🔄 Updated: `{datetime.now().strftime('%d %b %Y, %I:%M %p')}`"
    )
    
    await msg.edit(text)

# ======================================================
# 🗑 MANUAL DELETE COMMANDS
# ======================================================
@Client.on_message(filters.command("delete") & filters.user(ADMINS))
async def delete_cmd(bot, m):
    if len(m.command) < 2: return await m.reply("❌ **Usage:** `/delete keyword`")
    key = m.text.split(" ", 1)[1].strip()
    msg = await m.reply(f"⏳ Deleting `{key}`...")
    try:
        c = await delete_files(key)
        await msg.edit(f"✅ **Files Deleted**\n🔍 `{key}`\n🗑 Count: `{c}`")
    except Exception as e: 
        await msg.edit(f"❌ Error: {e}")

@Client.on_message(filters.command("deleteall") & filters.user(ADMINS))
async def delete_all_cmd(bot, m):
    msg = await m.reply(f"⚠️ **Delete ALL Files**\n❗ Irreversible! Reply `CONFIRM DELETE ALL`.")
    try:
        res = await bot.listen(m.chat.id, filters=filters.text, timeout=30)
        if res.text.strip().upper() == "CONFIRM DELETE ALL":
            await res.delete()
            await msg.edit("⏳ Deleting...")
            c = await delete_all_files()
            await msg.edit(f"✅ **ALL Files Deleted**\n🗑 Count: `{c}`")
        else: 
            await msg.edit("❌ Cancelled - incorrect confirmation.")
    except ListenerTimeout: 
        await msg.edit("❌ Cancelled - timeout.")
