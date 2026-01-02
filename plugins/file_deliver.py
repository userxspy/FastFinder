import asyncio
import time
import logging
from datetime import datetime, timedelta

from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from info import IS_STREAM, PM_FILE_DELETE_TIME, PROTECT_CONTENT, ADMINS
from database.ia_filterdb import get_file_details
from database.users_chats_db import db
from utils import get_settings, get_size, temp, is_premium

# ======================================================
# 📝 LOGGING SETUP
# ======================================================
logger = logging.getLogger(__name__)

# ======================================================
# CONFIG
# ======================================================
GRACE_PERIOD = timedelta(minutes=30)
RESEND_EXPIRE_TIME = 60  # seconds

# Track active deletion tasks to prevent memory leaks
# Key: task_id, Value: asyncio.Task
active_tasks = {}

# ======================================================
# HELPER: PREMIUM CHECK
# ======================================================
async def has_premium_or_grace(user_id: int) -> bool:
    """Check if user is admin or has premium (with grace)"""
    # 1. Check Admins
    if user_id in ADMINS:
        return True
    
    # 2. Check Plan via DB
    try:
        plan = await db.get_plan(user_id)
        if not plan or not plan.get("premium"):
            return False

        expire = plan.get("expire")
        
        # Handle different date formats
        if isinstance(expire, (int, float)):
            expire = datetime.utcfromtimestamp(expire)
        elif not isinstance(expire, datetime):
            return False

        # Check expiry with grace period
        return datetime.utcnow() <= expire + GRACE_PERIOD
        
    except Exception as e:
        logger.error(f"Premium check error for {user_id}: {e}")
        return False

# ======================================================
# 📂 FILE BUTTON HANDLER (GROUP)
# ======================================================
@Client.on_callback_query(filters.regex(r"^file#"))
async def file_button_handler(client: Client, query: CallbackQuery):
    try:
        _, file_id = query.data.split("#", 1)
        uid = query.from_user.id
        group_id = query.message.chat.id
        
        # 1. Check File
        file = await get_file_details(file_id)
        if not file:
            return await query.answer("❌ File Not Found", show_alert=True)
            
        # 2. Check Premium
        is_prem = await has_premium_or_grace(uid)
        
        # 3. IF PREMIUM -> Direct Link
        if is_prem:
            await query.answer(
                url=f"https://t.me/{temp.U_NAME}?start=file_{group_id}_{file_id}"
            )
            return

        # 4. IF NOT PREMIUM -> Alert & Upsell
        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("💰 Buy Premium", callback_data="buy_premium")],
            [InlineKeyboardButton("❌ Close", callback_data="close_data")]
        ])
        
        await query.message.reply_text(
            "🔒 **Premium Required**\n\nDirect file access is a Premium feature.\nBuy Premium to unlock instant access!",
            reply_markup=btn,
            quote=True
        )
        await query.answer("🔒 Premium Required", show_alert=True)
        
    except Exception as e:
        logger.error(f"File button error: {e}")
        await query.answer("❌ Error occurred", show_alert=True)

# ======================================================
# 🚀 START FILE DELIVERY (PM)
# ======================================================
@Client.on_message(filters.private & filters.command("start") & filters.regex(r"file_"))
async def start_file_delivery(client: Client, message):
    try:
        _, grp_id, file_id = message.text.split("_", 2)
        grp_id = int(grp_id)
    except:
        return

    uid = message.from_user.id
    
    # 1. Check Premium Access
    is_prem = await has_premium_or_grace(uid)
    
    if not is_prem:
        # Upsell Message
        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("💰 Buy Premium", callback_data="buy_premium")],
            [InlineKeyboardButton("❌ Close", callback_data="close_data")]
        ])
        await message.reply_text(
            "🔒 **Premium Required**\n\nOnly Premium users can access files directly.\n\n💎 **Benefits:**\n• Instant Access\n• No Ads\n• High Speed\n\nUpgrade now!",
            reply_markup=btn
        )
        try: await message.delete()
        except: pass
        return

    # 2. Manage Tasks
    task_key = f"dl_{uid}"
    if task_key in active_tasks:
        active_tasks[task_key].cancel()
        
    # 3. Start Delivery
    task = asyncio.create_task(deliver_file(client, uid, grp_id, file_id))
    active_tasks[task_key] = task
    
    # Cleanup task when done
    def cleanup(t):
        active_tasks.pop(task_key, None)
    task.add_done_callback(cleanup)
    
    try: await message.delete()
    except: pass

# ======================================================
# 🚚 DELIVERY LOGIC
# ======================================================
async def deliver_file(client, uid, grp_id, file_id):
    try:
        # Get File
        file = await get_file_details(file_id)
        if not file: return

        # Verify Premium Again (Security)
        if not await has_premium_or_grace(uid):
            return

        # Prepare Caption
        fname = file.get("file_name", "")
        fcap = file.get("caption", "")
        caption = f"{fname}\n\n{fcap}" if fcap and fcap != fname else fname
        
        # Buttons
        btns = []
        if IS_STREAM:
            btns.append([InlineKeyboardButton("▶️ Stream / Download", callback_data=f"stream#{file_id}")])
        btns.append([InlineKeyboardButton("❌ Close", callback_data="close_data")])
        
        # Send File
        sent = await client.send_cached_media(
            chat_id=uid,
            file_id=file_id,
            caption=caption,
            protect_content=PROTECT_CONTENT,
            reply_markup=InlineKeyboardMarkup(btns)
        )
        
        # Schedule Deletion
        del_task = asyncio.create_task(schedule_deletion(client, sent, uid, file_id))
        
        # Track Deletion Task
        dt_key = f"del_{sent.id}"
        active_tasks[dt_key] = del_task
        def cleanup_del(t):
            active_tasks.pop(dt_key, None)
        del_task.add_done_callback(cleanup_del)
        
    except Exception as e:
        logger.error(f"Delivery Error: {e}")

# ======================================================
# 🗑 SCHEDULE DELETION & RESEND
# ======================================================
async def schedule_deletion(client, msg, uid, file_id):
    try:
        # Register in Temp
        if not hasattr(temp, 'FILES'): temp.FILES = {}
        temp.FILES[msg.id] = {
            "owner": uid, 
            "file": file_id, 
            "expire": int(time.time()) + PM_FILE_DELETE_TIME
        }
        
        # Wait
        await asyncio.sleep(PM_FILE_DELETE_TIME)
        
        # Remove from Temp
        if msg.id in temp.FILES:
            del temp.FILES[msg.id]
            
        # Delete File
        try: await msg.delete()
        except: pass
        
        # Send Resend Option
        rs_btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Resend File", callback_data=f"resend#{file_id}")]])
        resend_msg = await client.send_message(uid, "⌛ **File Expired**", reply_markup=rs_btn)
        
        # Delete Resend Button
        await asyncio.sleep(RESEND_EXPIRE_TIME)
        try: await resend_msg.delete()
        except: pass
        
    except asyncio.CancelledError:
        # Clean up if cancelled
        temp.FILES.pop(msg.id, None)

# ======================================================
# 🔁 RESEND HANDLER
# ======================================================
@Client.on_callback_query(filters.regex(r"^resend#"))
async def resend_handler(client, query):
    file_id = query.data.split("#")[1]
    uid = query.from_user.id
    
    if not await has_premium_or_grace(uid):
        return await query.answer("🔒 Premium Required", show_alert=True)
        
    await query.answer()
    try: await query.message.delete()
    except: pass
    
    # Resend
    asyncio.create_task(deliver_file(client, uid, 0, file_id))

