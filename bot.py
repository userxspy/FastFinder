import os, time, asyncio, logging, pytz
import uvloop
from datetime import datetime, timezone
from aiohttp import web

from hydrogram import Client, filters
from info import API_ID, API_HASH, BOT_TOKEN, PORT, LOG_CHANNEL, ADMINS
from web import web_app
from utils import temp, cleanup_files_memory, premium_expiry_reminder
from database.users_chats_db import db

# ==========================
# 🔥 LOGGING CONFIG
# ==========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logging.getLogger("hydrogram").setLevel(logging.ERROR)
logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
logging.getLogger("aiohttp.server").setLevel(logging.WARNING)

logger = logging.getLogger("XFILER")

# ==========================
# 🕒 TIME UTILS
# ==========================
def ist_time():
    return datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%d %b %Y, %I:%M %p")

# ==========================
# ⭐ PREMIUM AUTO-REMOVE TASK
# ==========================
async def check_and_remove_expired_premium(client):
    logger.info("✅ Premium expiry checker started")
    while True:
        try:
            now = datetime.now(timezone.utc)
            users = await db.get_premium_users() or []
            removed = 0
            
            for u in users:
                uid, plan = u.get("_id") or u.get("id"), u.get("plan", {})
                exp = plan.get("expire")
                if not exp: continue
                
                # Convert to UTC aware datetime
                if isinstance(exp, (int, float)):
                    exp = datetime.fromtimestamp(exp, timezone.utc)
                elif isinstance(exp, datetime) and exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                
                if exp <= now:
                    await db.update_plan(uid, {"premium": False, "plan": None, "expire": None})
                    removed += 1
                    logger.info(f"✅ Removed expired premium for user {uid}")
                    try:
                        await client.send_message(uid, "⚠️ **Premium Expired**\n\nYour premium subscription has ended.\nUse /plan to renew!")
                    except: pass
            
            if removed: logger.info(f"✅ Removed {removed} expired premium users")
            await asyncio.sleep(3600) # Check every hour
            
        except Exception as e:
            logger.error(f"❌ Premium checker error: {e}")
            await asyncio.sleep(600)

# ==========================
# 🧪 GLOBAL DEBUG: /START LOGGER (Fixed Block Bug)
# ==========================
@Client.on_message(filters.private & filters.command("start"), group=-1)
async def debug_start_logger(client, message):
    logger.warning(f"/START HIT | user={message.from_user.id} | text='{message.text}'")

# ==========================
# 🤖 BOT CLASS
# ==========================
class Bot(Client):
    def __init__(self):
        super().__init__(
            name="Auto_Filter_Bot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            plugins={"root": "plugins"}
        )

    async def start(self):
        await super().start()
        
        # 🚀 SETUP ASYNC DATABASE INDEXES (Crucial for Speed)
        await db.setup_indexes()

        # ---- Runtime Globals ----
        temp.START_TIME, temp.BOT = time.time(), self
        me = await self.get_me()
        temp.ME, temp.U_NAME, temp.B_NAME = me.id, me.username, me.first_name

        # ---- Restart Notify ----
        if os.path.exists("restart.txt"):
            try:
                with open("restart.txt") as f:
                    cid, mid = map(int, f.read().split())
                    await self.edit_message_text(cid, mid, "✅ Bot Restarted Successfully!")
            except: pass
            os.remove("restart.txt")

        # ---- Web Server ----
        runner = web.AppRunner(web_app)
        await runner.setup()
        await web.TCPSite(runner, host="0.0.0.0", port=PORT).start()

        # ==========================
        # 🔁 BACKGROUND TASKS
        # ==========================
        asyncio.create_task(cleanup_files_memory())
        asyncio.create_task(premium_expiry_reminder(self))
        asyncio.create_task(check_and_remove_expired_premium(self))

        # ---- Notifications ----
        start_msg = f"♻️ **Bot Restarted**\n🕒 Time: {ist_time()}\n🤖 Status: Online & Stable\n⭐ Premium System: Active"
        for admin in ADMINS:
            try: await self.send_message(admin, start_msg)
            except: pass

        try: await self.send_message(LOG_CHANNEL, f"🤖 <b>@{temp.U_NAME} started</b>\n🕒 {ist_time()}")
        except: pass

        logger.info(f"✅ Bot @{temp.U_NAME} started successfully")

    async def stop(self, *args):
        await super().stop()
        logger.info("✅ Bot stopped cleanly")

# ==========================
# 🚀 ENTRYPOINT
# ==========================
async def main():
    uvloop.install()
    bot = Bot()
    try:
        await bot.start()
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        await bot.stop()

if __name__ == "__main__":
    asyncio.run(main())
