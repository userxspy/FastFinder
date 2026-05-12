import qrcode, secrets, asyncio
from io import BytesIO
from datetime import datetime, timedelta

from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardMarkup as IKM, InlineKeyboardButton as IKB, CallbackQuery

from info import ADMINS, IS_PREMIUM, PRE_DAY_AMOUNT, UPI_ID, UPI_NAME, RECEIPT_SEND_USERNAME
from database.users_chats_db import db
from utils import is_premium

# ======================================================
# ⚙️ CONFIG & CORE HELPERS
# ======================================================
LISTEN_SHORT, LISTEN_LONG, active_sessions = 180, 300, {}

def fmt(dt): return (datetime.utcfromtimestamp(dt) if isinstance(dt, (int, float)) else dt).strftime("%d %b %Y, %I:%M %p")
def gen_invoice_id(): return "PRM-" + secrets.token_hex(3).upper()

def parse_duration(txt: str):
    n = int("".join(filter(str.isdigit, txt or "")) or 0)
    if n <= 0: return None
    t = txt.lower()
    return timedelta(days=n*365) if "year" in t else timedelta(days=n*30) if "month" in t else timedelta(hours=n) if "hour" in t else timedelta(days=n)

async def get_plan_data(uid):
    if uid in ADMINS: return None, "admin"
    plan = await db.get_plan(uid)
    if not plan or not plan.get("premium"): return None, "none"
    
    exp_dt = datetime.utcfromtimestamp(plan["expire"]) if isinstance(plan["expire"], (int, float)) else plan["expire"]
    rem = exp_dt - datetime.utcnow()
    
    if rem.total_seconds() <= 0:
        await db.update_plan(uid, {"premium": False, "plan": None, "expire": None})
        return None, "expired"
    return {"plan": plan, "exp_dt": exp_dt, "days": max(0, rem.days), "hours": rem.seconds // 3600}, "active"

# ======================================================
# 🎨 UI BUTTONS & TEXT COMPRESSORS
# ======================================================
buy_btn = lambda: IKM([[IKB("💰 Buy / Renew Premium", callback_data="buy_premium")]])
cancel_btn = lambda: IKM([[IKB("❌ Cancel", callback_data="cancel_payment")]])
back_btn = lambda: IKM([[IKB("🔙 Back", callback_data="back_to_myplan")]])
myplan_btns = lambda: IKM([[IKB("🔄 Renew", callback_data="buy_premium"), IKB("🧾 Invoices", callback_data="show_invoices")]])

def duration_buttons(n):
    return IKM([
        [IKB(f"⏰ {n} Hours (₹{max(1, n//24)*PRE_DAY_AMOUNT})", callback_data=f"dur#{n}#hour")],
        [IKB(f"📅 {n} Days (₹{n*PRE_DAY_AMOUNT})", callback_data=f"dur#{n}#day")],
        [IKB(f"📆 {n} Months (₹{n*30*PRE_DAY_AMOUNT})", callback_data=f"dur#{n}#month")],
        [IKB(f"🗓️ {n} Years (₹{n*365*PRE_DAY_AMOUNT})", callback_data=f"dur#{n}#year")],
        [IKB("🔄 Re-enter Number", callback_data="buy_premium")], [IKB("❌ Cancel", callback_data="cancel_payment")]
    ])

def myplan_text(d): return f"🎉 **Premium Active**\n\n💎 Plan: {d['plan'].get('plan')}\n⏰ Expires: {fmt(d['exp_dt'])}\n⏳ Remaining: {d['days']} days {d['hours']} hours"

async def end_session(uid, msg_obj, text, markup=buy_btn()):
    """Helper to pop session and send error/cancel message"""
    active_sessions.pop(uid, None)
    try: await (msg_obj.edit if hasattr(msg_obj, 'edit') else msg_obj.reply)(text, reply_markup=markup)
    except: pass

# ======================================================
# 👤 USER COMMANDS
# ======================================================
@Client.on_message(filters.command("plan") & filters.private)
async def plan_cmd(c, m):
    if not IS_PREMIUM: return await m.reply("⚠️ Premium system disabled")
    if m.from_user.id in ADMINS: return await m.reply("👑 You are Admin = Lifetime Premium Access")
    
    txt = f"💎 **Premium Benefits**\n\n🚀 Faster search & downloads\n📩 PM Search access\n🔕 No ads\n🎯 Priority support\n\n💰 **Pricing:** ₹{PRE_DAY_AMOUNT}/day\n\n📌 **Example Plans:**\n• 7 days = ₹{7 * PRE_DAY_AMOUNT}\n• 30 days = ₹{30 * PRE_DAY_AMOUNT}"
    if await is_premium(m.from_user.id, c): txt += "\n\n✅ **You already have Premium!**\nYou can renew or extend your current plan."
    await m.reply(txt, reply_markup=buy_btn())

@Client.on_message(filters.command("myplan") & filters.private)
async def myplan_cmd(c, m):
    d, s = await get_plan_data(m.from_user.id)
    if s == "admin": return await m.reply("👑 You are Admin = Lifetime Access")
    if s in ["none", "expired"]: return await m.reply("❌ Plan expired!" if s=="expired" else "❌ No active plan", reply_markup=buy_btn())
    await m.reply(myplan_text(d), reply_markup=myplan_btns())

@Client.on_message(filters.command("invoice") & filters.private)
async def invoice_cmd(c, m):
    p = await db.get_plan(m.from_user.id)
    invs = p.get("invoices", []) if p else []
    if not invs: return await m.reply("❌ No invoices found")
    i = invs[-1]
    await m.reply(f"🧾 **Latest Invoice**\n\n🆔 `{i.get('id')}`\n💎 Plan: {i.get('plan')}\n💰 ₹{i.get('amount')}\n📅 Activated: {i.get('activated')}\n⏰ Expires: {i.get('expire')}", reply_markup=IKM([[IKB("📜 All Invoices", callback_data="show_invoices")]]))

@Client.on_callback_query(filters.regex("^show_invoices$"))
async def show_invoice_cb(c, q):
    invs = (await db.get_plan(q.from_user.id) or {}).get("invoices", [])
    if not invs: return await q.answer("❌ No invoices found", show_alert=True)
    txt = "🧾 **Invoice History**\n\n" + "\n\n".join([f"• `{i.get('id')}` | ₹{i.get('amount')} | {i.get('plan')}\n  📅 {i.get('activated')} → {i.get('expire')}" for i in invs[-10:][::-1]])
    await q.message.edit(txt, reply_markup=back_btn())

@Client.on_callback_query(filters.regex("^back_to_myplan$"))
async def back_to_myplan_cb(c, q):
    d, s = await get_plan_data(q.from_user.id)
    if s == "admin": return await q.message.edit("👑 You are Admin = Lifetime Access")
    if s in ["none", "expired"]: return await q.message.edit("❌ Plan expired!" if s=="expired" else "❌ No active plan", reply_markup=buy_btn())
    await q.message.edit(myplan_text(d), reply_markup=myplan_btns())

# ======================================================
# 💰 BUY FLOW
# ======================================================
@Client.on_callback_query(filters.regex("^buy_premium$"))
async def buy_premium(c, q):
    uid = q.from_user.id
    if uid in active_sessions: return await q.answer("⚠️ Active payment session exists", show_alert=True)
    
    active_sessions[uid] = {"step": "waiting_number"}
    await q.message.edit("🔢 **Enter a Number**\n\nSend a number (e.g., 7, 30, 365)\nThen choose Hours/Days/Months/Years.", reply_markup=cancel_btn())
    
    try:
        msg = await c.listen(q.message.chat.id, timeout=LISTEN_SHORT)
        if msg.from_user.id != uid or not msg.text: return await end_session(uid, q.message, "❌ Invalid response. Please try again.")
        
        num = int("".join(filter(str.isdigit, msg.text)) or 0)
        if not (0 < num < 10000): return await end_session(uid, q.message, "❌ Invalid number. Send between 1-9999.")
        
        active_sessions[uid] = {"step": "waiting_duration", "number": num}
        await q.message.edit(f"✅ Number: **{num}**\n\nNow select your duration:", reply_markup=duration_buttons(num))
        
    except asyncio.TimeoutError: await end_session(uid, q.message, "⏱️ Timeout! Cancelled.")
    except Exception as e: await end_session(uid, q.message, f"❌ Error: {e}")

@Client.on_callback_query(filters.regex("^dur#"))
async def duration_selected(c, q):
    uid = q.from_user.id
    if uid not in active_sessions: return await q.answer("⚠️ Session expired.", show_alert=True)
    
    try: _, n_str, unit = q.data.split("#"); num = int(n_str)
    except: return await q.answer("❌ Invalid data", show_alert=True)
    
    umap = {"hour": ("Hours", max(1, num//24)), "day": ("Days", num), "month": ("Months", num*30), "year": ("Years", num*365)}
    if unit not in umap: return await q.answer("❌ Invalid unit", show_alert=True)
    
    disp, days = umap[unit]
    amt = days * PRE_DAY_AMOUNT
    p_txt = f"{num} {disp}"
    active_sessions[uid] = {"step": "screenshot", "plan_text": p_txt, "amount": amt, "days": days}
    
    bio = BytesIO(); qrcode.make(f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&am={amt}&cu=INR").save(bio, "PNG"); bio.seek(0); bio.name = "qr.png"
    await q.message.reply_photo(bio, caption=f"💰 **Payment Details**\n\n📦 Plan: {p_txt}\n💵 Amount: ₹{amt}\n📱 UPI ID: `{UPI_ID}`\n\n📸 **Send payment screenshot now**", reply_markup=cancel_btn())
    try: await q.message.delete()
    except: pass
    
    try:
        rcpt = await c.listen(q.message.chat.id, timeout=LISTEN_LONG)
        if rcpt.from_user.id != uid or not rcpt.photo: return await end_session(uid, rcpt, "❌ Screenshot not received. Send a photo.")
        
        btns = IKM([[IKB("✅ Approve", callback_data=f"pay_ok#{uid}#{p_txt}#{amt}"), IKB("❌ Reject", callback_data=f"pay_no#{uid}")]])
        await c.send_photo(RECEIPT_SEND_USERNAME, rcpt.photo.file_id, caption=f"🔔 **#PremiumPayment**\n👤 ID: `{uid}`\n👤 @{rcpt.from_user.username or 'N/A'}\n📦 {p_txt} | ₹{amt}\n⏰ {fmt(datetime.utcnow())}", reply_markup=btns)
        await end_session(uid, rcpt, "✅ **Screenshot received!**\nAdmin will review your payment shortly.", markup=None)
        
    except asyncio.TimeoutError: await end_session(uid, q.message, "⏱️ Timeout! Payment cancelled.")
    except Exception as e: await end_session(uid, q.message, f"❌ Error: {e}")

@Client.on_callback_query(filters.regex("^cancel_payment$"))
async def cancel_payment(c, q): await end_session(q.from_user.id, q.message, "❌ Payment cancelled."); await q.answer()

# ======================================================
# 🛂 ADMIN APPROVAL (Combined Handlers)
# ======================================================
@Client.on_callback_query(filters.regex("^(pay_ok|pay_no)#"))
async def admin_payment_cb(c, q):
    if q.from_user.id not in ADMINS: return await q.answer("⛔ Not authorized", show_alert=True)
    
    data = q.data.split("#")
    action, uid = data[0], int(data[1])
    
    if action == "pay_no":
        try: await c.send_message(uid, "❌ **Payment Rejected**\nYour screenshot was rejected by admin.")
        except: pass
        await q.message.edit_caption(f"{q.message.caption}\n\n❌ **REJECTED** by @{q.from_user.username}\n⏰ {fmt(datetime.utcnow())}")
        return await q.answer("Rejected", show_alert=True)
        
    amt, p_txt = int(data[3]), data[2]
    dur = parse_duration(p_txt)
    if not dur: return await q.message.edit_caption(f"{q.message.caption}\n\n❌ FAILED - Invalid duration")
    
    now = datetime.utcnow()
    dur = timedelta(days=max(1, (dur.seconds//3600)//24+1)) if dur.days == 0 and dur.seconds > 0 else dur
    
    old = await db.get_plan(uid) or {}
    exp = old.get("expire")
    exp_dt = (datetime.utcfromtimestamp(exp) if isinstance(exp, (int, float)) else exp) if exp else now
    exp_dt = exp_dt + dur if exp_dt > now else now + dur
    
    inv = {"id": gen_invoice_id(), "plan": p_txt, "amount": amt, "activated": fmt(now), "expire": fmt(exp_dt), "created_at": now.timestamp()}
    invs = old.get("invoices", []) + [inv]
    
    await db.update_plan(uid, {"premium": True, "plan": p_txt, "expire": exp_dt.timestamp(), "activated_at": now.timestamp(), "invoices": invs})
    
    try: await c.send_message(uid, f"🎉 **Premium Activated!**\n\n💎 Plan: {p_txt}\n⏰ Till: {fmt(exp_dt)}\n🧾 Invoice: `{inv['id']}`")
    except: pass
    
    await q.message.edit_caption(f"{q.message.caption}\n\n✅ **APPROVED** by @{q.from_user.username}\n⏰ {fmt(datetime.utcnow())}")
    await q.answer("Approved!", show_alert=True)
