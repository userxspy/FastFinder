import asyncio, time
from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardButton as IKB, InlineKeyboardMarkup as IKM

from database.users_chats_db import db
from utils import broadcast_messages, groups_broadcast_messages, temp, get_readable_time
from info import ADMINS

lock = asyncio.Lock()

# ======================================================
# 🛑 CANCEL CALLBACK
# ======================================================
@Client.on_callback_query(filters.regex(r'^broadcast_cancel'))
async def broadcast_cancel(c, q):
    tgt = q.data.split("#")[1]
    if tgt == "users": temp.USERS_CANCEL = True
    elif tgt == "groups": temp.GROUPS_CANCEL = True
    await q.message.edit(f"🛑 Cancelling {tgt[:-1]} broadcast…")

# ======================================================
# 📢 USER BROADCAST (SEGMENTED)
# ======================================================
@Client.on_message(filters.command(["broadcast_all", "broadcast_premium", "broadcast_free", "pin_broadcast"]) & filters.user(ADMINS) & filters.reply)
async def user_broadcast(bot, m):
    if lock.locked(): return await m.reply("⚠️ Another broadcast is already running.")
    
    cmd, pin = m.command[0], m.command[0] == "pin_broadcast"
    all_u = await db.get_all_users()
    
    # 🧠 Smart Segmentation
    users = [u for u in all_u if u.get("status", {}).get("premium")] if cmd == "broadcast_premium" else [u for u in all_u if not u.get("status", {}).get("premium")] if cmd == "broadcast_free" else all_u
    tot = len(users)
    
    if not tot: return await m.reply("❌ No users found for this broadcast.")
    
    sts = await m.reply("🚀 Broadcasting started…")
    b_msg, st_time, done, suc, fail = m.reply_to_message, time.time(), 0, 0, 0

    async with lock:
        for i in range(0, tot, 25):
            if temp.USERS_CANCEL: temp.USERS_CANCEL = False; break
            batch = users[i:i+25]
            res = await asyncio.gather(*[broadcast_messages(int(u["id"]), b_msg, pin) for u in batch], return_exceptions=True)

            for u, r in zip(batch, res):
                done += 1
                if r == "Success": suc += 1
                else: fail += 1; await db.delete_user(int(u["id"])) # 🧹 Remove inactive

            if done % 100 == 0:
                await sts.edit(f"📣 <b>Broadcasting…</b>\n\n👥 Total: <code>{tot}</code>\n✅ Success: <code>{suc}</code>\n❌ Failed/Removed: <code>{fail}</code>\n📊 Progress: <code>{done}/{tot}</code>\n⏱ Time: {get_readable_time(time.time() - st_time)}", reply_markup=IKM([[IKB("❌ CANCEL", "broadcast_cancel#users")]]))
            await asyncio.sleep(0.4)

    await sts.edit(f"✅ <b>Broadcast Completed</b>\n\n👥 Target users: <code>{tot}</code>\n✅ Success: <code>{suc}</code>\n❌ Failed/Removed: <code>{fail}</code>\n⏱ Duration: {get_readable_time(time.time() - st_time)}")

# ======================================================
# 📡 GROUP BROADCAST
# ======================================================
@Client.on_message(filters.command(["grp_broadcast", "pin_grp_broadcast"]) & filters.user(ADMINS) & filters.reply)
async def group_broadcast(bot, m):
    if lock.locked(): return await m.reply("⚠️ Another broadcast is running.")
    
    pin, grps = m.command[0] == "pin_grp_broadcast", await db.get_all_chats()
    tot = len(grps)
    
    if not tot: return await m.reply("❌ No groups found.")
    
    sts = await m.reply("🚀 Group broadcast started…")
    b_msg, st_time, done, suc, fail = m.reply_to_message, time.time(), 0, 0, 0

    async with lock:
        for i in range(0, tot, 15):
            if temp.GROUPS_CANCEL: temp.GROUPS_CANCEL = False; break
            batch = grps[i:i+15]
            res = await asyncio.gather(*[groups_broadcast_messages(int(g["id"]), b_msg, pin) for g in batch], return_exceptions=True)

            for r in res:
                done += 1
                if r == "Success": suc += 1
                else: fail += 1

            if done % 30 == 0:
                await sts.edit(f"📡 <b>Group Broadcast…</b>\n\n💬 Total: <code>{tot}</code>\n✅ Success: <code>{suc}</code>\n❌ Failed: <code>{fail}</code>\n📊 Progress: <code>{done}/{tot}</code>\n⏱ Time: {get_readable_time(time.time() - st_time)}", reply_markup=IKM([[IKB("❌ CANCEL", "broadcast_cancel#groups")]]))
            await asyncio.sleep(1)

    await sts.edit(f"✅ <b>Group Broadcast Completed</b>\n\n💬 Total groups: <code>{tot}</code>\n✅ Success: <code>{suc}</code>\n❌ Failed: <code>{fail}</code>\n⏱ Duration: {get_readable_time(time.time() - st_time)}")
