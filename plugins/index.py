import time, asyncio
from pymongo import MongoClient
from hydrogram import Client, filters, enums
from hydrogram.errors import FloodWait, MessageNotModified
from hydrogram.types import InlineKeyboardMarkup as IKM, InlineKeyboardButton as IKB

from info import ADMINS, DATA_DATABASE_URL, DATABASE_NAME, INDEX_LOG_CHANNEL
from database.ia_filterdb import save_file
from utils import get_readable_time

# =====================================================
# ⚙️ GLOBALS & DB SETUP
# =====================================================
LOCK, CANCEL = asyncio.Lock(), False
resume_col = MongoClient(DATA_DATABASE_URL)[DATABASE_NAME]["index_resume"]

def get_resume(cid): return (resume_col.find_one({"_id": cid}) or {}).get("last_id", 0)
def set_resume(cid, mid): resume_col.update_one({"_id": cid}, {"$set": {"last_id": mid}}, upsert=True)

# =====================================================
# 🛡️ SAFE HELPERS
# =====================================================
async def auto_delete(c, cid, mid, delay=120):
    await asyncio.sleep(delay)
    try: await c.delete_messages(cid, mid)
    except: pass

async def send_log(c, txt):
    if INDEX_LOG_CHANNEL:
        try: await c.send_message(INDEX_LOG_CHANNEL, txt)
        except: pass

# =====================================================
# 🚀 ENTRY POINT (LINK / FORWARD)
# =====================================================
@Client.on_message(filters.private & filters.user(ADMINS) & filters.incoming)
async def start_index(c, m):
    if LOCK.locked(): return await m.reply("⏳ Indexing already running")

    try:
        txt = m.text or ""
        if txt.startswith("https://t.me"):
            p = txt.split("/"); lid, raw = int(p[-1]), p[-2]
            cid = int(f"-100{raw}") if raw.isdigit() else raw
        elif m.forward_from_chat and m.forward_from_chat.type == enums.ChatType.CHANNEL:
            lid, cid = m.forward_from_message_id, m.forward_from_chat.id
        else: return

        chat = await c.get_chat(cid)
        if chat.type != enums.ChatType.CHANNEL: return await m.reply("❌ Only channels supported")
    except Exception as e: return await m.reply(f"❌ Error: `{e}`")

    await m.reply(
        f"📢 **Channel:** `{chat.title}`\n🆔 **ID:** `{cid}`\n📊 **Last Message:** `{lid}`",
        reply_markup=IKM([[IKB("✅ START", f"idx#start#{cid}#{lid}")], [IKB("❌ CANCEL", "idx#close")]])
    )

# =====================================================
# 🔄 CALLBACK ROUTER
# =====================================================
@Client.on_callback_query(filters.regex("^idx#"))
async def index_callback(c, q):
    global CANCEL
    d = q.data.split("#")

    if d[1] == "close": return await q.message.edit("❌ Cancelled")
    elif d[1] == "cancel": CANCEL = True; return await q.answer("Stopping…", show_alert=True)

    await q.message.edit("⚡ Indexing started…")
    async with LOCK:
        CANCEL = False
        await index_worker(c, q.message, int(d[2]), int(d[3]), (await c.get_chat(int(d[2]))).title)

# =====================================================
# ⚙️ CORE INDEX WORKER
# =====================================================
async def index_worker(c, status, cid, lid, c_title):
    global CANCEL
    st_time, stats, curr_id, stop_id = time.time(), {"suc": 0, "dup": 0, "err": 0, "nom": 0, "proc": 0}, lid, get_resume(cid)

    try:
        while curr_id > stop_id:
            if CANCEL: break
            try: msg = await c.get_messages(cid, curr_id)
            except FloodWait as e: await asyncio.sleep(e.value); continue
            except: curr_id -= 1; continue

            stats["proc"] += 1
            if stats["proc"] % 50 == 0:
                el = time.time() - st_time
                spd = stats["proc"] / el if el else 0
                eta = (curr_id - stop_id) / spd if spd else 0
                try: await status.edit(f"📊 `{stats['proc']}` scanned\n✅ `{stats['suc']}` | ♻️ `{stats['dup']}` | ❌ `{stats['err']}`\n⚡ `{spd:.2f}/s`\n⏳ `{get_readable_time(eta)}`", reply_markup=IKM([[IKB("🛑 STOP", "idx#cancel")]]))
                except MessageNotModified: pass

            curr_id -= 1
            if not msg or not msg.media or msg.media not in (enums.MessageMediaType.VIDEO, enums.MessageMediaType.DOCUMENT):
                stats["nom"] += 1; continue

            if not (media := getattr(msg, msg.media.value, None)): continue
            media.caption = msg.caption

            res = await save_file(media)
            if res in stats: stats[res] += 1
            else: stats["err"] += 1

        if not CANCEL: set_resume(cid, lid)
    except Exception as e: return await status.edit(f"❌ Failed: `{e}`")

    tot_time = get_readable_time(time.time() - st_time)
    rep = f"📢 `{c_title}`\n🆔 `{cid}`\n\n✅ `{stats['suc']}` | ♻️ `{stats['dup']}` | ❌ `{stats['err']}` | 🚫 `{stats['nom']}`\n⏱ `{tot_time}`"

    final_msg = await status.edit(f"✅ **Index Completed**\n\n{rep}")
    asyncio.create_task(auto_delete(c, final_msg.chat.id, final_msg.id, 120))
    await send_log(c, f"📊 **Index Report**\n\n{rep}")
