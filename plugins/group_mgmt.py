import asyncio
from datetime import datetime, timedelta
from hydrogram import Client, filters, enums
from hydrogram.types import ChatPermissions as CP
from database.users_chats_db import db

# =========================
# ⚙️ CONFIG & HELPERS
# =========================
MAX_WARNS, AUTO_MUTE_TIME = 3, 600

async def is_admin(c, cid, uid):
    try: return (await c.get_chat_member(cid, uid)).status in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER)
    except: return False

async def warn_user(uid, cid):
    d = await db.get_warn(uid, cid) or {"count": 0}
    d["count"] += 1; await db.set_warn(uid, cid, d)
    return d["count"]

# =========================
# 👮 ADMIN MODERATION (MERGED)
# =========================
@Client.on_message(filters.group & filters.reply & filters.command(["mute", "unmute", "ban", "warn", "resetwarn"]))
async def mod_cmds(c, m):
    if not await is_admin(c, m.chat.id, m.from_user.id): return
    cmd, u, cid = m.command[0], m.reply_to_message.from_user, m.chat.id

    if cmd == "mute":
        await c.restrict_chat_member(cid, u.id, CP(), until_date=datetime.utcnow() + timedelta(seconds=AUTO_MUTE_TIME))
        await m.reply(f"🔇 {u.mention} has been muted")
    elif cmd == "unmute":
        await c.restrict_chat_member(cid, u.id, CP(can_send_messages=True))
        await m.reply(f"🔊 {u.mention} has been unmuted")
    elif cmd == "ban":
        await c.ban_chat_member(cid, u.id)
        await m.reply(f"🚫 {u.mention} has been banned")
    elif cmd == "warn":
        await m.reply(f"⚠️ {u.mention} warned ({await warn_user(u.id, cid)}/{MAX_WARNS})")
    elif cmd == "resetwarn":
        await db.clear_warn(u.id, cid)
        await m.reply(f"♻️ Warnings reset for {u.mention}")

# =========================
# 🚫 BLACKLIST & DLINK CONFIG (MERGED)
# =========================
@Client.on_message(filters.group & filters.command(["addblacklist", "removeblacklist", "blacklist", "blacklistwarn", "dlink", "removedlink", "dlinklist"]))
async def bl_dl_cmds(c, m):
    if not await is_admin(c, m.chat.id, m.from_user.id): return
    cmd, cid = m.command[0], m.chat.id
    data = await db.get_settings(cid) or {}

    # Read-only commands
    if cmd == "blacklist": return await m.reply("\n".join(f"• `{w}`" for w in data.get("blacklist", [])) or "📭 Blacklist is empty")
    if cmd == "dlinklist": return await m.reply("\n".join(f"• `{k}` → {v//60}m" for k, v in data.get("dlink", {}).items()) or "📭 Dlink list is empty")
    
    if len(m.command) < 2: return
    txt_arg = m.text.split(None, 1)[1].lower()

    # Write commands
    if cmd == "addblacklist":
        data.setdefault("blacklist", []).append(txt_arg)
        data["blacklist"] = list(set(data["blacklist"]))
        data.setdefault("blacklist_warn", True)
    elif cmd == "removeblacklist":
        if txt_arg in data.get("blacklist", []): data["blacklist"].remove(txt_arg)
    elif cmd == "blacklistwarn":
        data["blacklist_warn"] = (m.command[1].lower() == "on")
    elif cmd == "dlink":
        args, d, idx = m.command[1:], 300, 0
        if len(args) > 1 and args[0][-1] in ("m", "h") and args[0][:-1].isdigit():
            d, idx = int(args[0][:-1]) * (60 if args[0][-1] == "m" else 3600), 1
        data.setdefault("dlink", {})[" ".join(args[idx:]).lower()] = d
    elif cmd == "removedlink":
        data.get("dlink", {}).pop(txt_arg, None)

    await db.update_settings(cid, data)
    await m.reply(f"✅ Settings updated for `{cmd}`")

# =========================
# ⏱️ BACKGROUND DELAYED DELETE
# =========================
async def delayed_delete(msg, delay):
    await asyncio.sleep(delay)
    try: await msg.delete()
    except: pass

# =========================
# 🛡️ UNIFIED TEXT FILTER (MASSIVE PERF BOOST)
# =========================
@Client.on_message(filters.group & filters.text, group=15)
async def unified_text_filter(c, m):
    if not m.from_user or await is_admin(c, m.chat.id, m.from_user.id): return

    data = await db.get_settings(m.chat.id) or {}
    bl, dl = data.get("blacklist", []), data.get("dlink", {})
    if not bl and not dl: return

    txt = m.text.lower()

    # Check Blacklist
    for w in bl:
        if (w.endswith("*") and txt.startswith(w[:-1])) or (w in txt):
            await m.delete()
            if data.get("blacklist_warn", True): await warn_user(m.from_user.id, m.chat.id)
            return

    # Check Delayed Delete (Dlink) - Non-blocking
    for w, delay in dl.items():
        if (w.endswith("*") and txt.startswith(w[:-1])) or (w in txt):
            asyncio.create_task(delayed_delete(m, delay))
            return

# =========================
# 🤖 ANTI BOT PROTECTION
# =========================
@Client.on_message(filters.new_chat_members)
async def anti_bot(c, m):
    for u in m.new_chat_members:
        if u.is_bot and not await is_admin(c, m.chat.id, m.from_user.id):
            await c.ban_chat_member(m.chat.id, u.id)

# =========================
# 👨‍🚒 HELP COMMAND
# =========================
@Client.on_message(filters.group & filters.command("help"))
async def help_command(c, m):
    if not await is_admin(c, m.chat.id, m.from_user.id): return
    await m.reply(
        "🛠️ **Admin Help Menu**\n━━━━━━━━━━━━━━━━━━\n\n"
        "👮 **Moderation (Reply):**\n🔇 `/mute` (10m) | 🔊 `/unmute`\n🚫 `/ban` | ⚠️ `/warn` | ♻️ `/resetwarn`\n\n"
        "🚫 **Blacklist:**\n➕ `/addblacklist <word>` | ➖ `/removeblacklist <word>`\n📃 `/blacklist` | ⚙️ `/blacklistwarn on|off`\n\n"
        "⏱️ **Delayed Delete (DLINK):**\n🕒 `/dlink <word>` (5m)\n🕒 `/dlink 10m <word>`\n🗑️ `/removedlink <word>`\n📃 `/dlinklist`\n\n"
        "🤖 **Auto Protection:** Anti-bot is enabled (Admins only)."
    )
