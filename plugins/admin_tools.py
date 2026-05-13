import os, sys, time, asyncio
from datetime import datetime, timedelta
from collections import defaultdict

from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardButton as IKB, InlineKeyboardMarkup as IKM, CallbackQuery
from hydrogram.errors import MessageNotModified, MessageIdInvalid, BadRequest, ListenerTimeout

from info import ADMINS, LOG_CHANNEL
from database.users_chats_db import db
from database.ia_filterdb import db_count_documents, delete_files, delete_all_files, delete_file_by_id, delete_by_quality
from utils import get_size, get_readable_time, temp

# ======================================================
# 🧠 CONFIG & SAFE INIT
# ======================================================
DASH_REFRESH, DASH_CACHE, DASH_LOCKS = 45, {}, defaultdict(asyncio.Lock)

if not hasattr(temp, "INDEX_STATS"): temp.INDEX_STATS = {"running": False, "start": 0, "saved": 0}
if not hasattr(temp, "START_TIME"): temp.START_TIME = time.time()

# ======================================================
# 🛡 SAFE HELPERS & UI BUILDERS
# ======================================================
async def safe_edit(msg, text, **kwargs):
    if msg.text == text: return True
    try: await msg.edit(text, **kwargs); return True
    except (MessageNotModified, MessageIdInvalid, BadRequest, Exception): return False

async def safe_answer(q, text="", alert=False):
    try: await q.answer(text, show_alert=alert)
    except: pass

fmt = lambda dt: (datetime.utcfromtimestamp(dt) if isinstance(dt, (int, float)) else dt).strftime("%d %b %Y, %I:%M %p")

# BUTTONS (Minified)
admin_btns = lambda: IKM([[IKB("💎 Premium", "admin_premium"), IKB("🗑 Delete Files", "admin_delete")], [IKB("🔄 Refresh", "admin_refresh"), IKB("🔄 Restart Bot", "admin_restart")], [IKB("❌ Close", "close_data")]])
prm_btns = lambda: IKM([[IKB("➕ Add", "prm_add"), IKB("➖ Remove", "prm_remove"), IKB("⏳ Extend", "prm_extend")], [IKB("🔍 Check User", "prm_check")], [IKB("⏰ 3d", "prm_exp_3"), IKB("⏰ 7d", "prm_exp_7"), IKB("⏰ 30d", "prm_exp_30")], [IKB("📊 Expiry Chart", "prm_chart")], [IKB("🔙 Back", "admin_back")]])
del_btns = lambda: IKM([[IKB("🔍 By Keyword", "del_keyword"), IKB("📹 By Quality", "del_quality")], [IKB("🗑 Delete ALL", "del_all_confirm")], [IKB("🔙 Back", "admin_back")]])
delq_btns = lambda: IKM([[IKB(q, f"delq_{q}") for q in ["360p", "480p", "720p"]], [IKB(q, f"delq_{q}") for q in ["1080p", "1440p", "2160p"]], [IKB("🔙 Back", "admin_delete")]])

async def build_dashboard():
    s = {"users": 0, "chats": 0, "files": 0, "premium": 0, "data": 0}
    try: s["users"] = await db.total_users_count()
    except: pass
    try: s["chats"] = await asyncio.to_thread(db.groups.count_documents, {})
    except: pass
    try: s["files"] = await asyncio.to_thread(db_count_documents)
    except: pass
    try: s["premium"] = await asyncio.to_thread(db.premium.count_documents, {"plan.premium": True})
    except: pass
    try: s["data"] = (await asyncio.to_thread(db.users.database.command, "dbstats")).get("dataSize", 0)
    except: pass

    idx = temp.INDEX_STATS
    speed = f"🚀 {idx['saved']/max(1, time.time()-idx['start']):.2f} files/sec" if idx.get("running") else "❌ Not running"
    
    return (f"📊 <b>ADMIN CONTROL PANEL</b>\n\n👤 <b>Users</b>: <code>{s['users']}</code>\n👥 <b>Groups</b>: <code>{s['chats']}</code>\n"
            f"📦 <b>Indexed</b>: <code>{s['files']}</code>\n💎 <b>Premium</b>: <code>{s['premium']}</code>\n\n"
            f"⚡ <b>Index Speed</b>: <code>{speed}</code>\n🗃 <b>DB Size</b>: <code>{get_size(s['data'])}</code>\n\n"
            f"⏱ <b>Uptime</b>: <code>{get_readable_time(time.time() - temp.START_TIME)}</code>\n🔄 <b>Updated</b>: <code>{fmt(time.time())}</code>")

# ======================================================
# 🚀 ADMIN PANEL & CORE ROUTER
# ======================================================
@Client.on_message(filters.command(["admin", "dashboard"]) & filters.user(ADMINS))
async def open_admin_panel(bot, m):
    msg = await m.reply("⏳ Loading admin panel...")
    await safe_edit(msg, await build_dashboard(), reply_markup=admin_btns())

@Client.on_callback_query(filters.regex("^(admin_|close_data$)"))
async def admin_callbacks(bot, q: CallbackQuery):
    if q.from_user.id not in ADMINS: return await safe_answer(q, "Admins only", True)
    
    d = q.data
    if d == "close_data": return await q.message.delete()
    elif d in ["admin_refresh", "admin_back"]:
        async with DASH_LOCKS[q.from_user.id]: await safe_edit(q.message, await build_dashboard(), reply_markup=admin_btns())
    elif d == "admin_premium":
        await safe_edit(q.message, f"💎 <b>Premium Management</b>\n\n👤 Active: <code>{await asyncio.to_thread(db.premium.count_documents, {'plan.premium': True})}</code>\n🕒 {fmt(datetime.utcnow())}", reply_markup=prm_btns())
    elif d == "admin_delete":
        await safe_edit(q.message, f"🗑 <b>Delete Files</b>\n\n📦 Total: <code>{await asyncio.to_thread(db_count_documents)}</code>\nChoose method:", reply_markup=del_btns())
    elif d == "admin_restart":
        await safe_edit(q.message, "⏳ Restarting..."); os.execl(sys.executable, sys.executable, "bot.py")
    await safe_answer(q, "✅ Action Completed" if "refresh" in d else "")

# ======================================================
# 🗑 DELETE MANAGEMENT (Merged Handlers)
# ======================================================
@Client.on_callback_query(filters.regex("^(del_|delq_)"))
async def delete_callbacks(bot, q: CallbackQuery):
    if q.from_user.id not in ADMINS: return await safe_answer(q, "Admins only", True)
    
    d = q.data
    if d == "del_keyword": await safe_edit(q.message, "🔍 <b>Delete by Keyword</b>\nUse: <code>/delete movie_name</code>", reply_markup=IKM([[IKB("🔙 Back", "admin_delete")]]))
    elif d == "del_quality": await safe_edit(q.message, "📹 <b>Delete by Quality</b>\nSelect quality:", reply_markup=delq_btns())
    elif d == "del_all_confirm": await safe_edit(q.message, f"⚠️ <b>WARNING</b>\n❗ This permanently deletes ALL <code>{await asyncio.to_thread(db_count_documents)}</code> files. Sure?", reply_markup=IKM([[IKB("✅ Yes, Delete", "del_all_execute"), IKB("❌ Cancel", "admin_delete")]]))
    elif d == "del_all_execute" or d.startswith("delq_"):
        qual = d.split("_")[1] if d.startswith("delq_") else None
        msg = await q.message.edit(f"⏳ Deleting {'all '+qual if qual else 'ALL'} files...")
        try:
            count = await delete_by_quality(qual) if qual else await delete_all_files()
            txt = f"✅ <b>Deleted {'Quality: '+qual if qual else 'ALL'} Files</b>\n🗑 Count: <code>{count}</code>\n🕒 {fmt(datetime.utcnow())}"
            await msg.edit(txt, reply_markup=IKM([[IKB("🔙 Back", "admin_delete")]]))
            try: await bot.send_message(LOG_CHANNEL, f"🗑 <b>Admin Deletion</b>\n👤 {q.from_user.mention}\n{txt}")
            except: pass
        except Exception as e: await msg.edit(f"❌ Error: {e}")
    await safe_answer(q)

# ======================================================
# 💎 PREMIUM MANAGEMENT (Merged Handlers)
# ======================================================
@Client.on_callback_query(filters.regex("^prm_"))
async def premium_callbacks(bot, q: CallbackQuery):
    if q.from_user.id not in ADMINS: return await safe_answer(q, "Admins only", True)
    d = q.data; now = datetime.utcnow()
    
    cmds = {
        "prm_add": ("➕ Add Premium", "/addpremium user_id days"),
        "prm_remove": ("➖ Remove Premium", "/removepremium user_id"),
        "prm_extend": ("⏳ Extend Premium", "/extendpremium user_id days"),
        "prm_check": ("🔍 Check Premium", "Reply with user ID")
    }
    
    if d in cmds:
        t, c = cmds[d]
        await safe_edit(q.message, f"{t}\nUse:\n<code>{c}</code>", reply_markup=IKM([[IKB("🔙 Back", "admin_premium")]]))
        
    elif d.startswith("prm_exp_") or d == "prm_chart":
        users = await db.get_premium_users()
        valid = [(u["id"], datetime.utcfromtimestamp(e) if isinstance(e, (int, float)) else e) for u in users if u["id"] not in ADMINS and (e := u.get("plan", {}).get("expire")) and ((isinstance(e, (int, float)) and e > 0) or isinstance(e, datetime))]
        valid = [(uid, edt) for uid, edt in valid if edt > now]
        
        if d.startswith("prm_exp_"):
            limit = now + timedelta(days=int(d.split("_")[-1]))
            res = [f"👤 <code>{uid}</code> → ⏳ {get_readable_time(int((edt - now).total_seconds()))}" for uid, edt in valid if edt <= limit][:20]
            await safe_edit(q.message, f"⏰ <b>Expiring Soon</b>\n\n" + ("\n".join(res) if res else "✅ None found."), reply_markup=IKM([[IKB("🔙 Back", "admin_premium")]]))
            
        elif d == "prm_chart":
            days = [(edt - now).days for _, edt in valid]
            await safe_edit(q.message, f"📊 <b>Expiry Chart</b>\n\n🟥 0-3d: <code>{sum(1 for x in days if x<=3)}</code>\n🟧 4-7d: <code>{sum(1 for x in days if 3<x<=7)}</code>\n🟨 8-30d: <code>{sum(1 for x in days if 7<x<=30)}</code>\n🟩 30d+: <code>{sum(1 for x in days if x>30)}</code>", reply_markup=IKM([[IKB("🔙 Back", "admin_premium")]]))
    await safe_answer(q)

# ======================================================
# 🗑 DELETE COMMANDS (Optimized)
# ======================================================
@Client.on_message(filters.command("delete") & filters.user(ADMINS))
async def delete_cmd(bot, m):
    if len(m.command) < 2: return await m.reply("❌ <b>Usage:</b> <code>/delete keyword</code>")
    key = m.text.split(" ", 1)[1].strip()
    msg = await m.reply(f"⏳ Deleting `{key}`...")
    try:
        c = await delete_files(key)
        txt = f"✅ <b>Files Deleted</b>\n🔍 <code>{key}</code>\n🗑 Count: <code>{c}</code>\n🕒 {fmt(datetime.utcnow())}"
        await msg.edit(txt)
        try: await bot.send_message(LOG_CHANNEL, f"🗑 <b>Admin Deletion</b>\n👤 {m.from_user.mention}\n{txt}")
        except: pass
    except Exception as e: await msg.edit(f"❌ Error: {e}")

@Client.on_message(filters.command("deleteall") & filters.user(ADMINS))
async def delete_all_cmd(bot, m):
    msg = await m.reply(f"⚠️ <b>Delete ALL Files</b>\n❗ Irreversible! Reply `CONFIRM DELETE ALL`.", reply_markup=IKM([[IKB("❌ Cancel", "close_data")]]))
    try:
        res = await bot.listen(m.chat.id, filters=filters.text, timeout=30)
        if res.text.strip().upper() == "CONFIRM DELETE ALL":
            await res.delete(); await msg.edit("⏳ Deleting...")
            c = await delete_all_files()
            txt = f"✅ <b>ALL Files Deleted</b>\n🗑 Count: <code>{c}</code>\n🕒 {fmt(datetime.utcnow())}"
            await msg.edit(txt)
            try: await bot.send_message(LOG_CHANNEL, f"🗑 <b>Admin Purge</b>\n👤 {m.from_user.mention}\n{txt}")
            except: pass
        else: await msg.edit("❌ Cancelled - incorrect confirmation.")
    except ListenerTimeout: await msg.edit("❌ Cancelled - timeout.")

# ======================================================
# 🛠️ PREMIUM EXPIRY BUG FIX COMMAND (V2 - Bulletproof)
# ======================================================
@Client.on_message(filters.command("fix_premium") & filters.user(ADMINS))
async def fix_premium_bug(client, message):
    from bson.objectid import ObjectId
    msg = await message.reply("⏳ एक्सपायरी बग फिक्स कर रहा हूँ (Take 2)...")
    
    try:
        # ObjectId और String दोनों फॉर्मेट डाल दिए ताकि बचने का कोई चांस न रहे!
        buggy_ids = [
            ObjectId("6948e2eb0fcb2bcfc0b9c3a7"), 
            ObjectId("694cd3f30fcb2bcfc0bb100a"),
            "6948e2eb0fcb2bcfc0b9c3a7",
            "694cd3f30fcb2bcfc0bb100a"
        ]
        
        # 1. Premium कलेक्शन से हमेशा के लिए डिलीट करना
        res_prem = await db.premium.delete_many({"_id": {"$in": buggy_ids}})
        
        # 2. Users कलेक्शन में भी चेक करके अपडेट कर देना
        res_user = await db.users.update_many(
            {"_id": {"$in": buggy_ids}},
            {"$set": {"premium": False, "plan": None, "expire": None}}
        )
        
        await msg.edit(
            f"✅ **बग पक्का फिक्स हो गया!** 😎\n\n"
            f"🗑 Premium से डिलीट हुए: {res_prem.deleted_count}\n"
            f"🔄 Users में अपडेट हुए: {res_user.modified_count}\n\n"
            f"अब आप बॉट रीस्टार्ट करेंगे तो वो फालतू मैसेज 100% नहीं आएगा।"
        )
    except Exception as e:
        await msg.edit(f"❌ Error: {e}")
