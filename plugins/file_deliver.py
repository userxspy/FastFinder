import asyncio, time, logging
from datetime import datetime, timedelta

from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardMarkup as IKM, InlineKeyboardButton as IKB, CallbackQuery

from info import IS_STREAM, PM_FILE_DELETE_TIME, PROTECT_CONTENT, ADMINS
from database.ia_filterdb import get_file_details
from database.users_chats_db import db
from utils import get_size, temp, is_premium

# ======================================================
# ⚙️ CONFIG & GLOBAL VARIABLES
# ======================================================
active_tasks = {}

PREM_TXT = (
    "🔒 <b>Premium Required</b>\n\n"
    "PM file access is only available for premium users.\n\n"
    "💎 Get unlimited search access\n"
    "⚡ Faster responses\n"
    "🎯 Priority support\n\n"
    "Upgrade now to unlock this feature!"
)

prem_btn = lambda: IKM([[IKB("💰 Buy / Renew Premium", "buy_premium")], [IKB("❌ Close", "close_data")]])

# ======================================================
# 🧠 PREMIUM CHECKER (WITH GRACE PERIOD)
# ======================================================
async def has_premium_or_grace(uid: int) -> bool:
    if uid in ADMINS: return True
    p = await db.get_plan(uid)
    if not p or not p.get("premium"): return False
    
    e = p.get("expire")
    e_dt = datetime.utcfromtimestamp(e) if isinstance(e, (int, float)) else e
    return bool(e_dt and datetime.utcnow() <= e_dt + timedelta(minutes=30))

# ======================================================
# 📁 FILE BUTTON HANDLER (GROUP)
# ======================================================
@Client.on_callback_query(filters.regex(r"^file#"))
async def file_button_handler(c: Client, q: CallbackQuery):
    file_id = q.data.split("#", 1)[1]
    
    if not await get_file_details(file_id):
        return await q.answer("❌ File not found", show_alert=True)

    if await has_premium_or_grace(q.from_user.id):
        await q.answer(url=f"https://t.me/{temp.U_NAME}?start=file_{q.message.chat.id}_{file_id}")
    else:
        await q.message.reply_text(PREM_TXT, reply_markup=prem_btn(), quote=True)
        await q.answer("🔒 Premium required", show_alert=True)

# ======================================================
# 🚀 START FILE DELIVERY (PM)
# ======================================================
@Client.on_message(filters.private & filters.command("start") & filters.regex(r"file_"), group=1)
async def start_file_delivery(c: Client, m):
    try: _, grp_id, file_id = m.text.split("_", 2)
    except: return

    uid = m.from_user.id
    if not await has_premium_or_grace(uid):
        await m.reply_text(PREM_TXT, reply_markup=prem_btn())
        try: await m.delete()
        except: pass
        return

    ukey = f"user_{uid}"
    if ukey in active_tasks: active_tasks[ukey].cancel()

    t = asyncio.create_task(deliver_file(c, uid, int(grp_id), file_id))
    active_tasks[ukey] = t
    t.add_done_callback(lambda _: active_tasks.pop(ukey, None))

    try: await m.delete()
    except: pass

# ======================================================
# 🗑 AUTO DELETION SCHEDULER
# ======================================================
async def schedule_file_deletion(c, sent_msg, uid, file_id):
    mid = sent_msg.id
    if not hasattr(temp, 'FILES'): temp.FILES = {}
    
    temp.FILES[mid] = {"owner": uid, "file_id": file_id, "expire": int(time.time()) + PM_FILE_DELETE_TIME}
    
    try:
        await asyncio.sleep(PM_FILE_DELETE_TIME)
        if not temp.FILES.pop(mid, None): return
        
        try: await sent_msg.delete()
        except: pass
        
        resend = await c.send_message(uid, "⌛ <b>File expired</b>", reply_markup=IKM([[IKB("🔁 Resend File", f"resend#{file_id}")]]))
        await asyncio.sleep(60) # RESEND_EXPIRE_TIME
        try: await resend.delete()
        except: pass
            
    except asyncio.CancelledError:
        temp.FILES.pop(mid, None)
        raise

# ======================================================
# 📥 CORE FILE DELIVERY
# ======================================================
async def deliver_file(c, uid, grp_id, file_id):
    try:
        file = await get_file_details(file_id)
        if not file: return

        if not await has_premium_or_grace(uid):
            return await c.send_message(uid, PREM_TXT, reply_markup=prem_btn())

        fn, fc = (file.get("file_name") or "").strip(), (file.get("caption") or "").strip()
        cap = f"{fn}\n\n{fc}" if fc and fc != fn else fn

        btns = [[IKB("▶️ Watch / Download", f"stream#{file_id}")]] if IS_STREAM else []
        btns.append([IKB("❌ Close", "close_data")])

        sent = await c.send_cached_media(chat_id=uid, file_id=file_id, caption=cap, protect_content=PROTECT_CONTENT, reply_markup=IKM(btns))

        tkey = f"del_{sent.id}"
        t = asyncio.create_task(schedule_file_deletion(c, sent, uid, file_id))
        active_tasks[tkey] = t
        t.add_done_callback(lambda _: active_tasks.pop(tkey, None))
        
    except Exception as e:
        logging.error(f"Error delivering file: {e}")

# ======================================================
# 🔁 RESEND HANDLER
# ======================================================
@Client.on_callback_query(filters.regex(r"^resend#"))
async def resend_handler(c, q: CallbackQuery):
    uid = q.from_user.id
    if not await has_premium_or_grace(uid): return await q.answer("🔒 Premium required", show_alert=True)

    await q.answer()
    try: await q.message.delete()
    except: pass

    asyncio.create_task(deliver_file(c, uid, 0, q.data.split("#", 1)[1]))
