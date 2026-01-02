import logging
import asyncio
import time
from datetime import datetime, timedelta

from hydrogram.errors import FloodWait

from info import ADMINS, IS_PREMIUM
from database.users_chats_db import db

# ======================================================
# 📝 LOGGING SETUP
# ======================================================
logger = logging.getLogger(__name__)

# ======================================================
# 🧠 GLOBAL RUNTIME STATE (Koyeb Optimized)
# ======================================================

class temp(object):
    START_TIME = 0
    BOT = None
    ME = None
    U_NAME = None
    B_NAME = None

    SETTINGS = {}       # chat_id -> settings dict
    FILES = {}          # msg_id -> delivery data
    PREMIUM = {}        # RAM premium cache (user_id -> dict)
    KEYWORDS = {}       # learned keywords (RAM)
    
    # Cache Locks
    LOCKS = {}

    INDEX_STATS = {
        "running": False,
        "start": 0,
        "scanned": 0,
        "saved": 0,
        "dup": 0,
        "err": 0
    }
    
    # Task Flags
    _cleanup_running = False
    _reminder_running = False


# ======================================================
# 👑 PREMIUM CONFIG
# ======================================================

GRACE_PERIOD = timedelta(minutes=30)
PREMIUM_CACHE_TTL = 600  # 10 Minutes

# ======================================================
# ⚡ ULTRA FAST PREMIUM CHECK
# ======================================================

async def is_premium(user_id, bot=None) -> bool:
    """
    Checks if a user is premium efficiently.
    1. Checks Admins
    2. Checks Global Flag
    3. Checks RAM Cache
    4. Checks Database
    """
    # 1. Admins are always premium
    if user_id in ADMINS:
        return True
    
    # 2. If Premium System is Disabled
    if not IS_PREMIUM:
        return True

    now_ts = time.time()
    cached = temp.PREMIUM.get(user_id)

    # 3. Check RAM Cache (Fastest)
    if cached and (now_ts - cached["checked_at"] < PREMIUM_CACHE_TTL):
        expire = cached["expire"]
        if expire:
            # Check expiry + grace period
            return datetime.utcnow() <= expire + GRACE_PERIOD
        return False

    # 4. Check Database (If cache miss)
    try:
        plan = await db.get_plan(user_id)
        
        # Helper to update cache
        def update_cache(is_prem, exp_date=None):
            temp.PREMIUM[user_id] = {
                "expire": exp_date,
                "checked_at": now_ts
            }
            return is_prem

        if not plan or not plan.get("premium"):
            return update_cache(False)

        expire = plan.get("expire")
        
        # Convert to datetime object
        if isinstance(expire, (int, float)):
            expire = datetime.utcfromtimestamp(expire)
        elif not isinstance(expire, datetime):
            return update_cache(False)

        # Validate Expiry
        if datetime.utcnow() > expire + GRACE_PERIOD:
            # Expired
            return update_cache(False)
        
        # Valid Premium
        return update_cache(True, expire)

    except Exception as e:
        logger.error(f"DB Error in is_premium: {e}")
        # Fallback to cache if DB fails
        if cached:
            return bool(cached["expire"] and datetime.utcnow() <= cached["expire"] + GRACE_PERIOD)
        return False


# ======================================================
# 📅 DATETIME HELPERS
# ======================================================

def get_expiry_datetime(expire):
    if isinstance(expire, (int, float)):
        return datetime.utcfromtimestamp(expire)
    return expire

def fmt(dt):
    if isinstance(dt, (int, float)):
        dt = datetime.utcfromtimestamp(dt)
    return dt.strftime("%d %b %Y, %I:%M %p")

def get_readable_time(seconds):
    try:
        result = ""
        count = 0
        timestamps = {
            "d": 86400, "h": 3600, "m": 60, "s": 1
        }
        for name, count_secs in timestamps.items():
            if seconds >= count_secs:
                count_units = int(seconds // count_secs)
                seconds %= count_secs
                result += f"{count_units}{name} "
                count += 1
                if count >= 2: # Max 2 units (e.g. 1d 2h)
                    break
        return result.strip() or "0s"
    except:
        return "0s"

def get_size(size):
    try:
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(size)
        i = 0
        while size >= 1024.0 and i < len(units) - 1:
            size /= 1024.0
            i += 1
        return f"{size:.2f} {units[i]}"
    except:
        return "0 B"

# ======================================================
# 🔔 PREMIUM EXPIRY REMINDER (Motor Fixed)
# ======================================================

REMINDER_STEPS = [
    ("1 day", timedelta(days=1)),
    ("6 hours", timedelta(hours=6)),
    ("1 hour", timedelta(hours=1))
]

async def premium_expiry_reminder(bot):
    if temp._reminder_running:
        return
    temp._reminder_running = True
    logger.info("✅ Premium Reminder Task Started")
    
    while True:
        try:
            # Run every 30 minutes
            await asyncio.sleep(1800)
            
            now = datetime.utcnow()
            users_cursor = await db.get_premium_users()
            
            # 🔥 CRITICAL FIX: Use 'async for' for Motor Cursor
            async for user in users_cursor:
                try:
                    uid = user.get("id")
                    if not uid or uid in ADMINS:
                        continue

                    plan = user.get("plan", {})
                    expire = plan.get("expire")
                    last_remind = plan.get("last_reminder")

                    if not expire:
                        continue
                        
                    # Normalize expiry
                    if isinstance(expire, (int, float)):
                        expire = datetime.utcfromtimestamp(expire)
                    
                    # Check reminders
                    for tag, delta in REMINDER_STEPS:
                        if last_remind == tag:
                            continue
                            
                        # If time matches (within a window)
                        if expire - delta <= now < expire:
                            try:
                                await bot.send_message(
                                    uid,
                                    "⏰ **Premium Expiry Alert**\n\n"
                                    f"Your premium expires in **{tag}**.\n"
                                    "Use /plan to renew!"
                                )
                                # Update DB
                                await db.update_plan(uid, {**plan, "last_reminder": tag})
                                logger.info(f"Sent {tag} reminder to {uid}")
                            except Exception as e:
                                logger.warning(f"Failed reminder for {uid}: {e}")
                            break # Send only one type of reminder at a time
                            
                except Exception as e:
                    logger.error(f"Error in reminder loop: {e}")
                    continue

        except Exception as e:
            logger.error(f"Critical Reminder Task Error: {e}")
            await asyncio.sleep(300)

# ======================================================
# 🧠 SEARCH LEARNING (Memory Safe)
# ======================================================

def learn_keywords(text: str):
    try:
        # Strict Memory Cap
        if len(temp.KEYWORDS) > 5000:
            # Keep top 2500 only
            sorted_kw = sorted(temp.KEYWORDS.items(), key=lambda x: x[1], reverse=True)
            temp.KEYWORDS = dict(sorted_kw[:2500])
        
        # Learn
        for w in text.lower().split():
            if 4 <= len(w) <= 30: # Ignore very short/long words
                temp.KEYWORDS[w] = temp.KEYWORDS.get(w, 0) + 1
    except:
        pass

def suggest_query(query: str):
    if not query: return None
    try:
        query = query.lower()
        best_match = None
        best_score = 0
        
        # Search only top 300 keywords for speed
        check_limit = 0
        for kw in temp.KEYWORDS:
            if check_limit > 300: break
            
            # Simple substring/overlap match (Faster than fuzzy)
            if query in kw or kw in query:
                return kw
                
            check_limit += 1
            
        return None
    except:
        return None

# ======================================================
# 🔁 CLEANUP TASK
# ======================================================

async def cleanup_files_memory():
    if temp._cleanup_running: return
    temp._cleanup_running = True
    logger.info("✅ Memory Cleanup Task Started")
    
    while True:
        try:
            await asyncio.sleep(300) # Run every 5 mins
            now = int(time.time())
            
            # Clean FILES
            keys_to_del = [k for k, v in temp.FILES.items() if v.get("expire", 0) <= now]
            for k in keys_to_del:
                temp.FILES.pop(k, None)
            
            # Clean Premium Cache
            if len(temp.PREMIUM) > 2000:
                temp.PREMIUM.clear() # Full clear is safer/faster than partial
                logger.info("Cleared Premium Cache")
                
        except Exception as e:
            logger.error(f"Cleanup Error: {e}")

# ======================================================
# 📢 BROADCAST HELPERS
# ======================================================

async def broadcast_messages(user_id, message, pin=False):
    try:
        msg = await message.copy(chat_id=user_id)
        if pin:
            try: await msg.pin(both_sides=True)
            except: pass
        return "Success"
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await broadcast_messages(user_id, message, pin)
    except Exception:
        # If user blocked bot, delete from DB to save future resources
        try: await db.delete_user(int(user_id))
        except: pass
        return "Error"

async def groups_broadcast_messages(chat_id, message, pin=False):
    try:
        msg = await message.copy(chat_id=chat_id)
        if pin:
            try: await msg.pin()
            except: pass
        return "Success"
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await groups_broadcast_messages(chat_id, message, pin)
    except Exception:
        return "Error"

async def get_settings(group_id):
    if group_id in temp.SETTINGS:
        return temp.SETTINGS[group_id]
    
    st = await db.get_settings(group_id)
    temp.SETTINGS[group_id] = st
    return st

