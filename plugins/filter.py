import asyncio, hashlib, re, traceback
from math import ceil
from time import time
from collections import defaultdict

from hydrogram import Client, filters, enums
from hydrogram.types import InlineKeyboardMarkup as IKM, InlineKeyboardButton as IKB

from info import ADMINS
from database.users_chats_db import db
from database.ia_filterdb import get_search_results
from utils import get_size, is_premium, temp, learn_keywords, suggest_query

# =====================================================
# ⚙️ CONFIGURATION & MEMORY SETUP
# =====================================================
RES_PM, RES_GRP = 12, 10
EXP_TIME, DEL_DELAY = 300, 60
RL_LIMIT, RL_WIN = 5, 60

user_search_times = defaultdict(list)
if not hasattr(temp, 'callback_data'): temp.callback_data = {}
if not hasattr(temp, 'message_activity'): temp.message_activity = {}

# =====================================================
# 🧠 SMART HELPERS (MINIFIED)
# =====================================================
async def is_admin(c, cid, uid):
    try: return (await c.get_chat_member(cid, uid)).status in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER)
    except: return False

def is_rate_limited(uid):
    t = time()
    user_search_times[uid] = [x for x in user_search_times[uid] if t - x < RL_WIN]
    if len(user_search_times[uid]) >= RL_LIMIT: return True
    user_search_times[uid].append(t)
    return False

def make_key(s, o, c_id, u, is_pm):
    k = hashlib.md5(f"{s}:{o}:{c_id}:{u}:{time()}".encode()).hexdigest()[:12]
    temp.callback_data[k] = {'s': s, 'o': o, 'c': c_id, 'u': u, 'pm': is_pm, 't': time()}
    temp.callback_data = {k: v for k, v in temp.callback_data.items() if time() - v['t'] < 600}
    return k

def sanitize(txt): return re.sub(r"[<>\"'&]", "", " ".join(txt.split())).strip()
def update_act(mid): temp.message_activity[mid] = time()

# =====================================================
# 🔄 SEARCH TOGGLE (GROUP ADMINS)
# =====================================================
@Client.on_message(filters.group & filters.command("search"))
async def search_toggle(c, m):
    if not await is_admin(c, m.chat.id, m.from_user.id): return await m.reply("❌ Admins only.")
    
    stg = await db.get_settings(m.chat.id) or {}
    args = m.text.lower().split()
    
    if len(args) < 2 or args[1] not in ["on", "off"]:
        return await m.reply(f"🔍 <b>Status:</b> {'✅ Enabled' if stg.get('search', True) else '❌ Disabled'}\n💡 <b>Usage:</b> <code>/search on|off</code>")
    
    stg["search"] = (args[1] == "on")
    await db.update_settings(m.chat.id, stg)
    await m.reply(f"{'✅ <b>Enabled</b>' if stg['search'] else '❌ <b>Disabled</b>'} file search for this group.")

# =====================================================
# 📩 MAIN MESSAGE HANDLER (CORE FILTER)
# =====================================================
@Client.on_message(filters.text & filters.incoming & (filters.group | filters.private))
async def filter_handler(c, m):
    if m.text.startswith("/") or len(m.text.strip()) < 2: return
    uid, cid, is_grp = m.from_user.id, m.chat.id, m.chat.type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP)
    
    try: prem = await is_premium(uid, c)
    except: prem = False

    # Check Permissions & Rate Limits
    if not is_grp:
        if uid not in ADMINS and not prem:
            return await m.reply("🔒 <b>Premium Required</b>\nPM search is for premium users only.", reply_markup=IKM([[IKB("💰 Buy Premium", "buy_premium")]]))
        src_cid, is_pm = 0, True
    else:
        if (await db.get_settings(cid) or {}).get("search") is False: return
        if uid not in ADMINS and not prem and is_rate_limited(uid):
            return await m.reply("⚠️ <b>Too many searches!</b> Wait a moment.\n💡 Premium users get unlimited searches.")
        src_cid, is_pm = cid, False

    try: learn_keywords(m.text.lower())
    except: pass

    q = sanitize(m.text.lower())
    if not q: return
    await send_results(c, cid, uid, q, 0, src_cid, is_pm)

# =====================================================
# 🔎 SEND & EDIT RESULTS ENGINE
# =====================================================
async def send_results(c, cid, uid, q, off, src_cid, is_pm, msg=None, fallback=False):
    try:
        limit = RES_PM if is_pm else RES_GRP
        files, nxt, tot = await get_search_results(q, offset=off, max_results=limit)

        if not files and not fallback and (alt := suggest_query(q)) and alt != q:
            return await send_results(c, cid, uid, alt, 0, src_cid, is_pm, msg, True)

        if not files:
            txt = f"❌ <b>No results found for:</b> <code>{q}</code>"
            return await (msg.edit(txt) if msg else c.send_message(cid, txt))

        try: crown = "👑 " if await is_premium(uid, c) else ""
        except: crown = ""

        txt = f"{crown}🔎 <b>Search:</b> <code>{q}</code>\n🎬 <b>Files:</b> <code>{tot}</code>\n📄 <b>Page:</b> <code>{(off // limit) + 1}/{ceil(tot / limit)}</code>\n\n"
        
        for f in files:
            txt += f"📁 <a href='https://t.me/{temp.U_NAME}?start=file_{src_cid}_{f.get('_id')}'>[{get_size(f.get('file_size', 0))}] {f.get('file_name', 'Unknown')}</a>\n\n"

        nav = []
        if off > 0: nav.append(IKB("◀️ Prev", f"page#{make_key(q, off - limit, src_cid, uid, is_pm)}"))
        if nxt: nav.append(IKB("Next ▶️", f"page#{make_key(q, off + limit, src_cid, uid, is_pm)}"))
        markup = IKM([nav]) if nav else None

        if msg:
            await msg.edit(txt, reply_markup=markup, disable_web_page_preview=True)
            update_act(msg.id)
        else:
            sent = await c.send_message(cid, txt, reply_markup=markup, disable_web_page_preview=True)
            update_act(sent.id)
            asyncio.create_task(auto_expire(sent))
            
    except Exception as e:
        print(f"Send results err: {e}")
        try: await (msg.edit("❌ Error fetching results.") if msg else c.send_message(cid, "❌ Error fetching results."))
        except: pass

# =====================================================
# 🔁 PAGINATION CALLBACK
# =====================================================
@Client.on_callback_query(filters.regex("^page#"))
async def pagination_handler(c, q):
    data = temp.callback_data.get(q.data.split("#", 1)[1])
    if not data: return await q.answer("⌛ Result expired. Please search again.", show_alert=True)
    
    if q.from_user.id != data['u'] and q.from_user.id not in ADMINS:
        return await q.answer("❌ Not your result", show_alert=True)

    await q.answer()
    update_act(q.message.id)
    await send_results(c, q.message.chat.id, data['u'], data['s'], data['o'], data['c'], data['pm'], q.message)

# =====================================================
# ⏱ AUTO EXPIRE (SMART MEMORY DELETE)
# =====================================================
async def auto_expire(m):
    mid = m.id
    try:
        while True:
            await asyncio.sleep(EXP_TIME)
            if time() - temp.message_activity.get(mid, time()) < EXP_TIME: continue
            break
            
        try: await m.edit("⌛ <i>This result has expired.</i>", reply_markup=None)
        except: return temp.message_activity.pop(mid, None)

        await asyncio.sleep(DEL_DELAY)
        try: await m.delete()
        except: pass
        
    except: pass
    finally: temp.message_activity.pop(mid, None)
