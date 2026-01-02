import logging
import os
import time
import asyncio
import uvloop
from datetime import datetime
import pytz

from hydrogram import Client
from aiohttp import web

from web import web_app
from info import API_ID, API_HASH, BOT_TOKEN, PORT, LOG_CHANNEL, ADMINS

from utils import (
    temp,
    cleanup_files_memory,
    premium_expiry_reminder
)

from database.users_chats_db import db

# ==========================
# 🔥 LOGGING CONFIG (OPTIMIZED)
# ==========================
# Only log critical info to keep Koyeb logs clean
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%d-%b %H:%M",
    handlers=[logging.StreamHandler()]
)

# Silence noisy libraries
logging.getLogger("hydrogram").setLevel(logging.ERROR)
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logging.getLogger("motor").setLevel(logging.WARNING)

logger = logging.getLogger("BOT")

# ==========================
# 🕒 TIME UTILS
# ==========================
IST = pytz.timezone("Asia/Kolkata")

def ist_time():
    return datetime.now(IST).strftime("%d %b %Y, %I:%M %p")

# ==========================
# ⭐ PREMIUM AUTO-REMOVE (ASYNC FIX)
# ==========================
async def check_and_remove_expired_premium(client):
    """
    Background task to automatically remove expired premium users
    Fixed for Motor (Async DB)
    """
    logger.info("⏳ Premium expiry checker started...")
    
    while True:
        try:
            # Wait 1 hour between checks
            await asyncio.sleep(3600)
            
            # Get Cursor
            users_cursor = await db.get_premium_users()
            now = datetime.utcnow()
            removed_count = 0
            
            # 🔥 IMPORTANT: Use 'async for' with Motor Cursor
            async for user in users_cursor:
                try:
                    plan = user.get("plan", {})
                    expire = plan.get("expire")
                    
                    if not expire:
                        continue
                    
                    # Handle both Timestamp and Datetime objects
                    if isinstance(expire, (int, float)):
                        exp_dt = datetime.utcfromtimestamp(expire)
                    else:
                        exp_dt = expire
                    
                    # Check validity
                    if exp_dt <= now:
                        uid = user.get("id")
                        
                        # Remove from DB & Cache
                        await db.remove_premium(uid)
                        
                        removed_count += 1
                        
                        # Notify User (Fail-safe)
                        try:
                            await client.send_message(
                                uid,
                                "⚠️ **Premium Expired**\n\n"
                                "Your premium subscription has ended.\n"
                                "Use /plan to renew and continue enjoying premium benefits!"
                            )
                        except:
                            pass
                            
                except Exception as e:
                    logger.error(f"Error checking user {user.get('id')}: {e}")
                    continue
            
            if removed_count > 0:
                logger.info(f"✅ Removed {removed_count} expired premium users")
            
        except Exception as e:
            logger.error(f"❌ Error in premium background task: {e}")
            await asyncio.sleep(300) # Wait 5 mins on crash

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
            plugins={"root": "plugins"},
            workers=50, # Optimized for Koyeb
            sleep_threshold=10
        )

    async def start(self):
        # 1. Start Hydrogram Client
        await super().start()
        me = await self.get_me()

        # 2. Set Globals
        temp.START_TIME = time.time()
        temp.BOT = self
        temp.ME = me.id
        temp.U_NAME = me.username
        temp.B_NAME = me.first_name

        # 3. Handle Restart Notification
        if os.path.exists("restart.txt"):
            try:
                with open("restart.txt") as f:
                    cid, mid = map(int, f.read().split())
                    await self.edit_message_text(
                        cid, mid, "✅ **Bot Restarted Successfully!**"
                    )
            except Exception as e:
                logger.warning(f"Restart message error: {e}")
            os.remove("restart.txt")

        # 4. Start Web Server (Non-blocking)
        app = web.AppRunner(web_app)
        await app.setup()
        await web.TCPSite(app, "0.0.0.0", PORT).start()
        logger.info(f"🌍 Web Server running on Port {PORT}")

        # 5. Start Background Tasks
        # Using create_task ensures they run in background without blocking start
        asyncio.create_task(cleanup_files_memory())
        asyncio.create_task(premium_expiry_reminder(self))
        asyncio.create_task(check_and_remove_expired_premium(self))

        # 6. Admin Notifications
        start_msg = (
            "♻️ **Bot Restarted Successfully**\n\n"
            f"🕒 Time: `{ist_time()}`\n"
            f"🐍 Python: `{os.sys.version.split()[0]}`\n"
            "⚡ Status: **Online & Fast**"
        )
        
        # Send to Log Channel
        if LOG_CHANNEL:
            try:
                await self.send_message(LOG_CHANNEL, start_msg)
            except:
                pass

        # Send to Admins
        for admin in ADMINS:
            try:
                await self.send_message(admin, start_msg)
            except:
                pass

        logger.info(f"✅ @{me.username} Started Successfully!")

    async def stop(self, *args):
        await super().stop()
        logger.info("❌ Bot Stopped Cleanly")

# ==========================
# 🚀 ENTRY POINT
# ==========================
if __name__ == "__main__":
    # Install uvloop for maximum speed
    uvloop.install()
    
    bot = Bot()
    
    try:
        bot.run()
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as e:
        logger.error(f"Critical Error: {e}")

