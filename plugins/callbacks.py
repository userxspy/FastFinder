import random
import time
import asyncio
from datetime import timedelta

from hydrogram import Client, filters
from hydrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    InputMediaPhoto
)
from hydrogram.errors import (
    MessageNotModified,
    MessageIdInvalid,
    MessageDeleteForbidden,
    QueryIdInvalid,
    BadRequest
)

from info import (
    ADMINS,
    PICS,
    URL,
    BIN_CHANNEL,
    script
)

from utils import is_premium, temp
from database.users_chats_db import db
from database.ia_filterdb import db_count_documents

# ======================================================
# 🛡 SAFE EDIT HELPERS
# ======================================================

async def safe_edit_caption(msg, caption, reply_markup=None):
    try:
        await msg.edit_caption(caption=caption, reply_markup=reply_markup)
        return True
    except MessageNotModified:
        return True
    except (MessageIdInvalid, BadRequest):
        return False
    except Exception as e:
        print(f"Edit Caption Error: {e}")
        return False

async def safe_edit_media(msg, media, reply_markup=None):
    try:
        await msg.edit_media(media=media, reply_markup=reply_markup)
        return True
    except MessageNotModified:
        return True
    except (MessageIdInvalid, BadRequest):
        return False
    except Exception as e:
        print(f"Edit Media Error: {e}")
        return False

async def safe_delete_message(msg):
    try:
        await msg.delete()
    except:
        pass

# ======================================================
# 🔁 CALLBACK HANDLER
# ======================================================

@Client.on_callback_query()
async def cb_handler(client: Client, query: CallbackQuery):
    try:
        data = query.data
        uid = query.from_user.id
        
        # --------------------------------------------------
        # ❗ PAGINATION (Handled in filter.py)
        # --------------------------------------------------
        if data.startswith("pg#") or data.startswith("page#"):
            return # Let filter.py handle it

        # ==================================================
        # ❌ CLOSE
        # ==================================================
        if data == "close_data":
            await query.answer("Closed")
            await safe_delete_message(query.message)
            return

        # ==================================================
        # ▶️ STREAM
        # ==================================================
        if data.startswith("stream#"):
            _, file_id = data.split("#")
            
            # 1. Premium Check
            if uid not in ADMINS:
                if not await is_premium(uid):
                    return await query.answer("🔒 Premium Only!\n/plan to buy.", show_alert=True)

            # 2. Generate Links
            try:
                # Forward to BIN to get public link
                log_msg = await client.send_cached_media(
                    chat_id=BIN_CHANNEL,
                    file_id=file_id
                )
                
                stream_link = f"{URL}watch/{log_msg.id}"
                dl_link = f"{URL}download/{log_msg.id}"
                
                btn = InlineKeyboardMarkup([
                    [InlineKeyboardButton("▶️ Watch", url=stream_link),
                     InlineKeyboardButton("⬇️ Download", url=dl_link)],
                    [InlineKeyboardButton("❌ Close", callback_data="close_data")]
                ])
                
                await query.message.edit_reply_markup(reply_markup=btn)
                await query.answer("✅ Links Generated!")
                
            except Exception as e:
                print(f"Stream Error: {e}")
                await query.answer("❌ Error Generating Link", show_alert=True)
            return

        # ==================================================
        # 🆘 HELP
        # ==================================================
        if data == "help":
            pic = random.choice(PICS) if PICS else None
            txt = script.HELP_TXT
            
            btn = InlineKeyboardMarkup([
                [InlineKeyboardButton("👤 User Commands", callback_data="user_cmds"),
                 InlineKeyboardButton("🛡️ Admin Commands", callback_data="admin_cmds")],
                [InlineKeyboardButton("🔙 Back", callback_data="start")]
            ])
            
            if pic:
                await safe_edit_media(query.message, InputMediaPhoto(pic, caption=txt), reply_markup=btn)
            else:
                await safe_edit_caption(query.message, txt, reply_markup=btn)
            return

        if data == "start":
            pic = random.choice(PICS) if PICS else None
            txt = script.START_TXT.format(query.from_user.mention, temp.B_NAME)
            
            btn = InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Add Me To Your Group ➕", url=f"http://t.me/{temp.U_NAME}?startgroup=true")],
                [InlineKeyboardButton("🆘 Help", callback_data="help"),
                 InlineKeyboardButton("💎 Premium", callback_data="myplan")],
                [InlineKeyboardButton("📊 Stats", callback_data="stats_callback")]
            ])
            
            if pic:
                await safe_edit_media(query.message, InputMediaPhoto(pic, caption=txt), reply_markup=btn)
            else:
                await safe_edit_caption(query.message, txt, reply_markup=btn)
            return

        # ==================================================
        # 📜 COMMANDS
        # ==================================================
        if data == "user_cmds":
            await safe_edit_caption(
                query.message, 
                script.USER_COMMAND_TXT,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="help")]])
            )
            return

        if data == "admin_cmds":
            if uid not in ADMINS:
                return await query.answer("🔒 Admins Only", show_alert=True)
                
            await safe_edit_caption(
                query.message, 
                script.ADMIN_COMMAND_TXT,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="help")]])
            )
            return

        # ==================================================
        # 📊 STATS
        # ==================================================
        if data == "stats_callback":
            if uid not in ADMINS:
                return await query.answer("🔒 Admins Only", show_alert=True)
            
            files = db_count_documents()
            users = await db.total_users_count()
            uptime = timedelta(seconds=int(time.time() - temp.START_TIME))
            
            txt = script.STATUS_TXT.format(users, "Active", "N/A", files, "N/A", uptime)
            await query.answer(txt, show_alert=True)
            return
            
    except Exception as e:
        print(f"Callback Error: {e}")

