import time, sys, platform
from hydrogram import Client, filters, enums
from utils import temp
from info import IS_PREMIUM

# ======================================================
# 🆔 ID COMMAND (PM + GROUP | USER + STICKER | ADMIN BADGE)
# ======================================================
@Client.on_message(filters.command("id"))
async def get_id(c, m):
    r = m.reply_to_message
    u = r.from_user if r and r.from_user else m.from_user
    chat_type = m.chat.type

    # ---------- ADMIN BADGE ----------
    badge = "👤 Member"
    if chat_type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
        try:
            stat = (await m.chat.get_member(u.id)).status
            badge = "👑 Owner" if stat == enums.ChatMemberStatus.OWNER else "🛡 Admin" if stat in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.ADMIN) else badge
        except: pass

    # ---------- USER & CHAT INFO ----------
    txt = (
        f"🆔 <b>ID INFORMATION</b>\n\n👤 <b>Name:</b> {u.first_name or ''} {u.last_name or ''}\n"
        f"🦹 <b>User ID:</b> <code>{u.id}</code>\n🏷 <b>Username:</b> @{u.username or 'N/A'}\n"
        f"🌐 <b>DC ID:</b> <code>{u.dc_id or 'Unknown'}</code>\n🤖 <b>Bot:</b> {'Yes' if u.is_bot else 'No'}\n"
        f"{badge}\n🔗 <b>Profile:</b> <a href='tg://user?id={u.id}'>Open</a>\n\n"
        f"💬 <b>CHAT & MESSAGE INFO</b>\n\n🆔 <b>Chat ID:</b> <code>{m.chat.id}</code>\n"
        f"🏷 <b>Chat Type:</b> <code>{chat_type.name}</code>\n📩 <b>Message ID:</b> <code>{m.id}</code>\n"
    )

    # ---------- GROUP INFO ----------
    if chat_type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
        txt += f"\n👥 <b>GROUP INFORMATION</b>\n\n📛 <b>Title:</b> {m.chat.title}\n🆔 <b>Group ID:</b> <code>{m.chat.id}</code>\n🔗 <b>Username:</b> @{m.chat.username or 'N/A'}\n"

    # ---------- STICKER INFO ----------
    if r and r.sticker:
        s = r.sticker
        txt += f"\n🎭 <b>STICKER INFORMATION</b>\n\n🆔 <b>File ID:</b> <code>{s.file_id}</code>\n📦 <b>Set:</b> <code>{s.set_name or 'N/A'}</code>\n🔖 <b>Emoji:</b> {s.emoji or 'N/A'}\n📐 <b>Size:</b> {s.width}×{s.height}\n🎞 <b>Animated:</b> {'Yes' if s.is_animated else 'No'}\n🧩 <b>Video:</b> {'Yes' if s.is_video else 'No'}\n"

    await m.reply_text(txt, disable_web_page_preview=True)

# ======================================================
# 🏓 PING
# ======================================================
@Client.on_message(filters.command("ping"))
async def ping_cmd(c, m):
    s = time.time()
    msg = await m.reply_text("🏓 Pinging…")
    await msg.edit_text(f"🏓 <b>Pong!</b>\n\n⚡ <code>{int((time.time() - s) * 1000)} ms</code>")

# ======================================================
# 🤖 BOT INFO
# ======================================================
@Client.on_message(filters.command("botinfo"))
async def bot_info(c, m):
    up = int(time.time() - temp.START_TIME)
    await m.reply_text(
        f"🤖 <b>BOT INFO</b>\n\n"
        f"⏱️ Uptime: <code>{up//3600}h {(up%3600)//60}m</code>\n"
        f"🐍 Python: <code>{sys.version.split()[0]}</code>\n"
        f"⚙️ Platform: <code>{platform.system()}</code>\n"
        f"📦 Library: <code>Hydrogram</code>\n"
        f"💎 Premium System: <code>{'ON' if IS_PREMIUM else 'OFF'}</code>\n"
        f"🚀 Mode: <code>Ultra-Pro</code>"
    )

# ======================================================
# 🕒 LAST ONLINE HELPER (MINIFIED)
# ======================================================
def last_online(u):
    if u.is_bot: return "🤖 Bot"
    if u.status == enums.UserStatus.OFFLINE and u.last_online_date: return u.last_online_date.strftime("%d %b %Y, %I:%M %p")
    
    return {
        enums.UserStatus.ONLINE: "🟢 Online",
        enums.UserStatus.RECENTLY: "Recently",
        enums.UserStatus.LAST_WEEK: "Within last week",
        enums.UserStatus.LAST_MONTH: "Within last month",
        enums.UserStatus.LONG_AGO: "Long time ago"
    }.get(u.status, "Unknown")
