import qrcode
import secrets
import asyncio
from io import BytesIO
from datetime import datetime, timedelta

from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from info import (
    ADMINS, 
    IS_PREMIUM, 
    PRE_DAY_AMOUNT, 
    UPI_ID, 
    UPI_NAME, 
    RECEIPT_SEND_USERNAME
)
from database.users_chats_db import db
from utils import is_premium, get_readable_time

# ======================================================
# ⚙️ CONFIG
# ======================================================

LISTEN_SHORT = 60   # 1 Minute to enter number
LISTEN_LONG = 300   # 5 Minutes to send screenshot
active_sessions = {}

# ======================================================
# 🧠 HELPERS
# ======================================================

def fmt(dt):
    """Format datetime to readable string"""
    if isinstance(dt, (int, float)):
        dt = datetime.utcfromtimestamp(dt)
    return dt.strftime("%d %b %Y, %I:%M %p")

def gen_invoice_id():
    """Generate unique invoice ID"""
    return "PRM-" + secrets.token_hex(3).upper()

def get_expiry_datetime(expire):
    if isinstance(expire, (int, float)):
        return datetime.utcfromtimestamp(expire)
    return expire

async def get_plan_data(uid):
    """Get user plan details"""
    if uid in ADMINS:
        return None, "admin"
    
    plan = await db.get_plan(uid)
    if not plan or not plan.get("premium"):
        return None, "none"
    
    expire = plan.get("expire")
    exp_dt = get_expiry_datetime(expire)
    now = datetime.utcnow()
    
    if exp_dt <= now:
        await db.update_plan(uid, {"premium": False, "plan": None, "expire": None})
        return None, "expired"
    
    remaining = exp_dt - now
    
    return {
        "plan": plan,
        "exp_dt": exp_dt,
        "remaining": remaining,
        "days": remaining.days,
        "hours": remaining.seconds // 3600
    }, "active"

# ======================================================
# 🎨 UI HELPERS
# ======================================================

def buy_btn():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("💰 Buy / Renew Premium", callback_data="buy_premium")
    ]])

def cancel_btn():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("❌ Cancel", callback_data="cancel_payment")
    ]])

def duration_buttons(num):
    # Pricing Logic
    hours_price = max(10, (num * 2)) if num < 24 else (num * PRE_DAY_AMOUNT) # Placeholder logic
    days_price = num * PRE_DAY_AMOUNT
    months_price = num * 30 * PRE_DAY_AMOUNT
    
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⏰ {num} Hours (₹{hours_price})", callback_data=f"dur#{num}#hour")],
        [InlineKeyboardButton(f"📅 {num} Days (₹{days_price})", callback_data=f"dur#{num}#day")],
        [InlineKeyboardButton(f"📆 {num} Months (₹{months_price})", callback_data=f"dur#{num}#month")],
        [InlineKeyboardButton(f"🔄 Re-enter Number", callback_data="buy_premium")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_payment")]
    ])

def myplan_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Renew / Extend", callback_data="buy_premium")],
        [InlineKeyboardButton("🧾 Invoices", callback_data="show_invoices"),
         InlineKeyboardButton("✖️ Close", callback_data="close_data")]
    ])

def back_btn():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_myplan")]])

# ======================================================
# 👤 USER COMMANDS
# ======================================================

@Client.on_message(filters.command("plan") & filters.private)
async def plan_cmd(client, message):
    if not IS_PREMIUM:
        return await message.reply("⚠️ Premium system is currently disabled.")

    uid = message.from_user.id
    if uid in ADMINS:
        return await message.reply("👑 You are an Admin (Lifetime Premium).")

    is_prem = await is_premium(uid)
    
    text = f"""
💎 **Premium Benefits**

🚀 **High Speed:** Priority processing
📥 **Direct Links:** Fast download links
🔕 **Ad-Free:** No promotional messages
⚡ **Batch:** Bulk link support
🔐 **PM Search:** Search directly in bot

💰 **Pricing:** ₹{PRE_DAY_AMOUNT} / Day

📌 **Popular Plans:**
• 7 Days : ₹{7 * PRE_DAY_AMOUNT}
• 1 Month : ₹{30 * PRE_DAY_AMOUNT}
"""
    if is_prem:
        text += "\n✅ **Status:** Premium Active"
    
    await message.reply(text, reply_markup=buy_btn())

@Client.on_message(filters.command("myplan") & filters.private)
async def myplan_cmd(client, message):
    data, status = await get_plan_data(message.from_user.id)
    
    if status == "admin":
        return await message.reply("👑 You are Admin.")
    
    if status in ["none", "expired"]:
        msg = "❌ Plan Expired" if status == "expired" else "❌ No Active Plan"
        return await message.reply(msg, reply_markup=buy_btn())
    
    text = f"""
🎉 **Premium Active**

💎 **Plan:** {data['plan'].get("plan")}
📅 **Expires:** {fmt(data['exp_dt'])}
⏳ **Remaining:** {data['days']}d {data['hours']}h
"""
    await message.reply(text, reply_markup=myplan_buttons())

@Client.on_message(filters.command("invoice") & filters.private)
async def invoice_cmd(client, message):
    plan = await db.get_plan(message.from_user.id)
    invoices = plan.get("invoices", []) if plan else []
    
    if not invoices:
        return await message.reply("❌ No invoice history found.")
    
    inv = invoices[-1]
    await message.reply(
        f"""
🧾 **Last Invoice**

🆔 **ID:** `{inv.get('id')}`
💰 **Amount:** ₹{inv.get('amount')}
📅 **Date:** {inv.get('activated')}
""",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📜 History", callback_data="show_invoices")]])
    )

# ======================================================
# 💰 BUY FLOW
# ======================================================

@Client.on_callback_query(filters.regex("^buy_premium$"))
async def buy_premium(client, query: CallbackQuery):
    uid = query.from_user.id
    if uid in active_sessions:
        return await query.answer("⚠️ Finish current payment process first!", show_alert=True)
    
    active_sessions[uid] = True
    
    try:
        await query.message.edit(
            "🔢 **Enter Number**\n\nExample: `7` for 7 days or `30` for 30 days.\n\n👇 Send the number below:",
            reply_markup=cancel_btn()
        )
        
        # 1. Wait for Number
        try:
            msg = await client.listen(query.message.chat.id, timeout=LISTEN_SHORT)
            if not msg.text or not msg.text.isdigit():
                del active_sessions[uid]
                return await query.message.reply("❌ Invalid number. Try again.", reply_markup=buy_btn())
            
            num = int(msg.text)
            if num <= 0 or num > 1000:
                del active_sessions[uid]
                return await query.message.reply("❌ Number must be between 1-1000.", reply_markup=buy_btn())
                
        except asyncio.TimeoutError:
            del active_sessions[uid]
            return await query.message.edit("⏱️ Timeout.", reply_markup=buy_btn())

        # 2. Select Unit
        await query.message.reply(
            f"✅ **Selected:** {num}\n\nChoose duration unit:",
            reply_markup=duration_buttons(num)
        )
        
    except Exception as e:
        del active_sessions[uid]
        await query.message.edit(f"❌ Error: {e}")

@Client.on_callback_query(filters.regex("^dur#"))
async def duration_selected(client, query: CallbackQuery):
    uid = query.from_user.id
    if uid not in active_sessions:
        return await query.answer("⚠️ Session expired.", show_alert=True)
    
    _, num, unit = query.data.split("#")
    num = int(num)
    
    # Calc Price
    if unit == "hour":
        amount = max(10, (num * 2)) if num < 24 else (num * PRE_DAY_AMOUNT)
        days = num / 24
        plan_txt = f"{num} Hours"
    elif unit == "day":
        amount = num * PRE_DAY_AMOUNT
        days = num
        plan_txt = f"{num} Days"
    elif unit == "month":
        amount = num * 30 * PRE_DAY_AMOUNT
        days = num * 30
        plan_txt = f"{num} Months"
    else:
        return
    
    try:
        # ⚡ Generate QR in Thread (Non-blocking)
        def make_qr():
            upi_url = f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&am={amount}&cu=INR"
            qr = qrcode.make(upi_url)
            bio = BytesIO()
            qr.save(bio, "PNG")
            bio.seek(0)
            bio.name = "pay.png"
            return bio

        qr_file = await asyncio.to_thread(make_qr)
        
        await query.message.reply_photo(
            qr_file,
            caption=f"""
💰 **Payment Request**

📦 **Plan:** {plan_txt}
💵 **Amount:** ₹{amount}
📱 **UPI:** `{UPI_ID}`

📸 **Send Screenshot:** Please pay and send the screenshot of payment below within 5 minutes.
""",
            reply_markup=cancel_btn()
        )
        await query.message.delete()
        
        # 3. Wait for Screenshot
        try:
            receipt = await client.listen(query.message.chat.id, filters=filters.photo, timeout=LISTEN_LONG)
        except asyncio.TimeoutError:
            del active_sessions[uid]
            return await query.message.reply("⏱️ Timeout. Payment cancelled.", reply_markup=buy_btn())

        # 4. Forward to Admin
        admin_btns = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Approve", callback_data=f"pay_ok#{uid}#{amount}#{days}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"pay_no#{uid}")
        ]])
        
        caption = f"""
🔔 **New Payment**

👤 **User:** {receipt.from_user.mention} (`{uid}`)
📦 **Plan:** {plan_txt}
💰 **Amount:** ₹{amount}
"""
        try:
            await client.send_photo(
                RECEIPT_SEND_USERNAME,
                receipt.photo.file_id,
                caption=caption,
                reply_markup=admin_btns
            )
            await receipt.reply("✅ **Screenshot Sent!**\nWait for admin approval.", reply_markup=myplan_buttons())
        except Exception as e:
            await receipt.reply(f"❌ Error sending to admin: {e}")
            
    except Exception as e:
        await query.message.reply(f"❌ Error: {e}")
    
    finally:
        del active_sessions[uid]

@Client.on_callback_query(filters.regex("^cancel_payment$"))
async def cancel_payment(_, query):
    uid = query.from_user.id
    if uid in active_sessions:
        del active_sessions[uid]
    await query.message.edit("❌ Cancelled.", reply_markup=buy_btn())

# ======================================================
# 🛂 ADMIN ACTIONS
# ======================================================

@Client.on_callback_query(filters.regex("^pay_ok#"))
async def pay_ok(client, query):
    if query.from_user.id not in ADMINS:
        return await query.answer("⛔ Admins Only", show_alert=True)
    
    _, uid, amount, days = query.data.split("#")
    uid = int(uid)
    amount = int(amount)
    days = float(days)
    
    # Calculate Expiry
    now = datetime.utcnow()
    old_plan = await db.get_plan(uid)
    
    # If already premium, extend it
    if old_plan and old_plan.get("premium") and old_plan.get("expire"):
        current_exp = get_expiry_datetime(old_plan["expire"])
        if current_exp > now:
            new_exp = current_exp + timedelta(days=days)
        else:
            new_exp = now + timedelta(days=days)
    else:
        new_exp = now + timedelta(days=days)
        
    plan_name = f"{int(days)} Days Premium"
    
    # Save to DB
    inv_id = gen_invoice_id()
    invoice = {
        "id": inv_id,
        "amount": amount,
        "plan": plan_name,
        "activated": fmt(now),
        "expire": fmt(new_exp)
    }
    
    invoices = old_plan.get("invoices", []) if old_plan else []
    invoices.append(invoice)
    
    await db.update_plan(uid, {
        "premium": True,
        "plan": plan_name,
        "expire": new_exp.timestamp(),
        "invoices": invoices
    })
    
    # Notify User
    try:
        await client.send_message(
            uid,
            f"🎉 **Payment Approved!**\n\n💎 **Plan:** {plan_name}\n📅 **Expires:** {fmt(new_exp)}"
        )
    except:
        pass
        
    await query.message.edit_caption(
        query.message.caption + f"\n\n✅ **APPROVED** by {query.from_user.first_name}"
    )

@Client.on_callback_query(filters.regex("^pay_no#"))
async def pay_no(client, query):
    if query.from_user.id not in ADMINS:
        return await query.answer("⛔ Admins Only", show_alert=True)
    
    uid = int(query.data.split("#")[1])
    
    try:
        await client.send_message(uid, "❌ **Payment Rejected**\nContact admin for details.")
    except:
        pass
        
    await query.message.edit_caption(
        query.message.caption + f"\n\n❌ **REJECTED** by {query.from_user.first_name}"
    )

@Client.on_callback_query(filters.regex("^show_invoices$"))
async def show_invoices(_, query):
    plan = await db.get_plan(query.from_user.id)
    invoices = plan.get("invoices", []) if plan else []
    
    if not invoices:
        return await query.answer("No invoices", show_alert=True)
        
    txt = "🧾 **Your Invoices**\n\n"
    for i in invoices[-5:][::-1]:
        txt += f"🆔 `{i['id']}`\n💰 ₹{i['amount']}\n📅 {i['activated']}\n\n"
        
    await query.message.edit(txt, reply_markup=back_btn())

@Client.on_callback_query(filters.regex("^back_to_myplan$"))
async def back_to_myplan(client, query):
    await myplan_cmd(client, query.message)
    await query.message.delete()

