import random, time, asyncio
from datetime import timedelta

from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardMarkup as IKM, InlineKeyboardButton as IKB, CallbackQuery, InputMediaPhoto
from hydrogram.errors import MessageNotModified, MessageIdInvalid, MessageDeleteForbidden, QueryIdInvalid, BadRequest

from info import ADMINS, PICS, URL, BIN_CHANNEL, QUALITY, script
from utils import is_premium, temp
from database.users_chats_db import db
from database.ia_filterdb import db_count_documents

# ======================================================
# 🛡 SAFE EDIT HELPERS (UNIVERSAL & MINIFIED)
# ======================================================
async def safe_action(action_coro, max_retries=3):
    """Universally handles safe edits and answers with retries"""
    for _ in range(max_retries):
        try: return await action_coro()
        except MessageNotModified: return True
        except (MessageIdInvalid, BadRequest, QueryIdInvalid): await asyncio.sleep(0.3)
        except Exception: return False
    return False

async def safe_delete(msg, delay=0):
    """Safely delete a message with optional delay"""
    try:
        if delay: await asyncio.sleep(delay)
        await msg.delete()
    except: pass

# ======================================================
# 🔁 CALLBACK HANDLER (OPTIMIZED)
# ======================================================
@Client.on_callback_query()
async def cb_handler(c: Client, q: CallbackQuery):
    d, uid = q.data, q.from_user.id

    # Lambda to quickly answer queries safely
    ans = lambda txt="", alert=False: asyncio.create_task(safe_action(lambda: q.answer(txt, show_alert=alert)))
    
    if d.startswith("page#") or d == "pages": return await ans()

    # ==================================================
    # ❌ CLOSE FILE
    # ==================================================
    if d == "close_data":
        ans("Closed")
        tk = next((k for k, v in getattr(temp, 'FILES', {}).items() if v.get("owner") == uid), None)
        
        if tk and (mem := temp.FILES.pop(tk, None)):
            if "task" in mem and not mem["task"].done(): mem["task"].cancel()
            if "file" in mem: await safe_delete(mem["file"])
            if "notice" in mem: await safe_delete(mem["notice"])

        await safe_delete(q.message)
        if q.message.reply_to_message: await safe_delete(q.message.reply_to_message)
        return

    # ==================================================
    # ▶️ STREAM
    # ==================================================
    if d.startswith("stream#"):
        fid = d.split("#", 1)[1] if len(d.split("#")) > 1 else None
        if not fid: return await ans("❌ Invalid data", True)

        if not any(v.get("owner") == uid and v.get("file_id") == fid for v in getattr(temp, 'FILES', {}).values()):
            return await ans("❌ This file is not for you", True)

        if not await is_premium(uid, c):
            return await ans("🔒 Premium only feature.\nUse /plan to upgrade.", True)

        try:
            msg = await c.send_cached_media(BIN_CHANNEL, fid)
            markup = IKM([[IKB("▶️ Watch Online", url=f"{URL}watch/{msg.id}"), IKB("⬇️ Fast Download", url=f"{URL}download/{msg.id}")], [IKB("❌ Close", "close_data")]])
            success = await safe_action(lambda: q.message.edit_reply_markup(markup))
            await ans("✅ Links ready" if success else "⚠️ Failed to update message", not success)
        except:
            await ans("❌ Failed to generate stream links", True)
        return

    # ==================================================
    # 🆘 HELP & CMDS
    # ==================================================
    nav_btns = lambda: IKM([[IKB("🔙 Back", "help")], [IKB("❌ Close", "close_data")]])
    
    if d == "help":
        pic = random.choice(PICS) if PICS else None
        markup = IKM([[IKB("👤 User Commands", "user_cmds"), IKB("🛡️ Admin Commands", "admin_cmds")], [IKB("❌ Close", "close_data")]])
        txt = script.HELP_TXT.format(q.from_user.mention)
        success = await safe_action(lambda: q.message.edit_media(InputMediaPhoto(pic, caption=txt), reply_markup=markup) if pic else q.message.edit_caption(txt, reply_markup=markup))
        return await ans("" if success else "⚠️ Failed to load help", not success)

    cmds_map = {"user_cmds": (script.USER_COMMAND_TXT, True), "admin_cmds": (script.ADMIN_COMMAND_TXT, uid in ADMINS)}
    
    if d in cmds_map:
        txt, allowed = cmds_map[d]
        if not allowed: return await ans("⚠️ Admins only", True)
        success = await safe_action(lambda: q.message.edit_caption(txt, reply_markup=nav_btns()))
        return await ans("" if success else "⚠️ Failed to load commands", not success)

    # ==================================================
    # 📊 STATS
    # ==================================================
    if d == "stats_callback":
        if uid not in ADMINS: return await ans("⚠️ Admins only", True)
        
        try: files = db_count_documents()
        except: files = "N/A"
        try: users = await db.total_users_count()
        except: users = "N/A"
        try: up = str(timedelta(seconds=int(time.time() - getattr(temp, 'START_TIME', time.time()))))
        except: up = "N/A"
        
        return await ans(f"📊 <b>Bot Statistics</b>\n\n📁 Files: <code>{files}</code>\n👥 Users: <code>{users}</code>\n⏱ Uptime: <code>{up}</code>", True)

    await ans("⚠️ Unknown action")
