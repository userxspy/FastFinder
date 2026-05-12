import asyncio
from hydrogram import Client, filters
from hydrogram.errors import FloodWait

from info import INDEX_CHANNELS, LOG_CHANNEL
from database.ia_filterdb import save_file, update_file_caption, detect_quality
from utils import get_size  # 🔥 Imported existing size formatter

try: from plugins.index import CANCEL_INDEX
except: CANCEL_INDEX = {}

# ======================================================
# 🛡️ SAFE HELPERS (MINIFIED)
# ======================================================
async def safe_react(m, emoji: str):
    try: await m.react(emoji)
    except FloodWait as e: await asyncio.sleep(e.value); await safe_react(m, emoji)
    except: pass

async def safe_log(c, txt: str):
    if not LOG_CHANNEL: return
    try: await c.send_message(LOG_CHANNEL, txt)
    except FloodWait as e: await asyncio.sleep(e.value); await safe_log(c, txt)
    except: pass

# ======================================================
# 📥 AUTO INDEX (LIVE POSTS ONLY)
# ======================================================
@Client.on_message(filters.chat(INDEX_CHANNELS) & (filters.video | filters.document), group=10)
async def index_new_file(bot, m):
    if CANCEL_INDEX.get(m.chat.id) is False: return
    
    # 🧠 Smart media extraction using Walrus Operator (:=)
    if not (media := m.document or m.video) or not getattr(media, "file_id", None): return

    try:
        q = detect_quality(media.file_name, m.caption or "")
        status = await save_file(media, quality=q)
        
        await safe_react(m, {"suc": "✅", "dup": "♻️", "err": "❌", "skip": "⏭"}.get(status, "❓"))
        await safe_log(bot, f"📥 **Auto Index**\n\n📄 `{media.file_name}`\n📊 `{get_size(getattr(media, 'file_size', 0))}`\n🎞 `{q}`\n✅ `{status}`\n💬 `{m.chat.title}`")

    except FloodWait as e: await asyncio.sleep(e.value)
    except: await safe_react(m, "❌")

# ======================================================
# ✏️ CAPTION EDIT UPDATER
# ======================================================
@Client.on_edited_message(filters.chat(INDEX_CHANNELS) & (filters.video | filters.document), group=11)
async def update_caption(bot, m):
    if not (media := m.document or m.video) or not getattr(media, "file_id", None): return

    try:
        cap = m.caption or ""
        updated = await update_file_caption(media.file_id, cap, detect_quality(media.file_name, cap))
        await safe_react(m, "✏️" if updated else "⚠️")

    except FloodWait as e: await asyncio.sleep(e.value)
    except: await safe_react(m, "❌")

# ======================================================
# 🗑️ DELETE LOG
# ======================================================
@Client.on_deleted_messages(filters.chat(INDEX_CHANNELS), group=12)
async def handle_deleted_files(bot, msgs):
    await safe_log(bot, f"🗑️ **Deleted Messages**\nCount: `{len(msgs)}`")
