import random
from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardMarkup as IKM, InlineKeyboardButton as IKB
from info import PICS, script

# ======================================================
# 🔘 START BUTTON (MINIMAL)
# ======================================================
start_btn = lambda: IKM([[IKB("👨‍🚒 Help", "help")]])

# ======================================================
# 🚀 /start COMMAND (NORMAL - NOT FILE DELIVERY)
# ======================================================
@Client.on_message(filters.command("start") & filters.private & ~filters.regex(r"file_"))
async def start_cmd(c, m):
    """Handle /start command for normal users"""
    txt = script.START_TXT.format(m.from_user.mention, (await c.get_me()).mention)
    
    try:
        await m.reply_photo(random.choice(PICS) if PICS else None, caption=txt, reply_markup=start_btn())
    except:
        # Fallback if photo fails or PICS list is empty
        await m.reply_text(txt, reply_markup=start_btn())
