import asyncio, time
from datetime import datetime, timedelta, timezone
from hydrogram.errors import FloodWait, UserIsBlocked, PeerIdInvalid
from info import ADMINS, IS_PREMIUM
from database.users_chats_db import db

# ======================================================
# GLOBAL RUNTIME STATE
# ======================================================
class temp:
    START_TIME = 0; BOT = ME = U_NAME = B_NAME = None
    SETTINGS, FILES, PREMIUM, KEYWORDS, BANNED_USERS = {}, {}, {}, {}, set()
    INDEX_STATS = {"running": False, "start": 0, "scanned": 0, "saved": 0, "dup": 0, "err": 0}
    _cleanup_running = _reminder_running = False

# ======================================================
# DATETIME HELPERS
# ======================================================
def get_expiry_datetime(exp):
    if isinstance(exp, (int, float)): return datetime.fromtimestamp(exp, timezone.utc)
    return exp.replace(tzinfo=timezone.utc) if isinstance(exp, datetime) and exp.tzinfo is None else exp

def fmt(dt):
    return get_expiry_datetime(dt).strftime("%d %b %Y, %I:%M %p") if dt else "N/A"

# ======================================================
# ULTRA FAST PREMIUM CHECK
# ======================================================
async def is_premium(user_id, bot=None) -> bool:
    if user_id in ADMINS or not IS_PREMIUM: return True
    now, cached = time.time(), temp.PREMIUM.get(user_id)
    is_valid = lambda c: bool(c and c.get("expire") and datetime.now(timezone.utc) <= c["expire"] + timedelta(minutes=30))
    
    if cached and now - cached["checked_at"] < 600: return is_valid(cached)
    
    try: plan = await db.get_plan(user_id)
    except: return is_valid(cached)
    
    exp = get_expiry_datetime(plan.get("expire")) if plan and plan.get("premium") else None
    valid = bool(exp and datetime.now(timezone.utc) <= exp + timedelta(minutes=30))
    temp.PREMIUM[user_id] = {"expire": exp if valid else None, "checked_at": now}
    return valid

# ======================================================
# PREMIUM EXPIRY REMINDER
# ======================================================
async def premium_expiry_reminder(bot):
    if temp._reminder_running: return
    temp._reminder_running = True
    steps = [("1 day", timedelta(days=1)), ("6 hours", timedelta(hours=6)), ("1 hour", timedelta(hours=1))]
    
    while True:
        try:
            now = datetime.now(timezone.utc)
            for u in (await db.get_premium_users() or []):
                uid, plan = u.get("_id") or u.get("id"), u.get("plan", {})
                if not uid or uid in ADMINS: continue
                
                exp = get_expiry_datetime(plan.get("expire"))
                if not exp: continue
                
                for tag, delta in steps:
                    if plan.get("last_reminder") == tag: continue
                    if exp - delta <= now < exp:
                        try:
                            await bot.send_message(uid, f"⏰ **Premium Expiry Alert**\n\nYour premium will expire in **{tag}**.\n\nUse /plan to renew!")
                            plan["last_reminder"] = tag; await db.update_plan(uid, plan)
                        except FloodWait as e: await asyncio.sleep(e.value)
                        except (UserIsBlocked, PeerIdInvalid, Exception): pass
                        break
                await asyncio.sleep(0.2)
        except: pass
        await asyncio.sleep(1800)

# ======================================================
# SEARCH LEARNING + SUGGESTIONS
# ======================================================
def learn_keywords(text: str):
    for w in text.lower().split():
        if 3 <= len(w) <= 50: temp.KEYWORDS[w] = temp.KEYWORDS.get(w, 0) + 1

def fast_similarity(a: str, b: str) -> int:
    if a == b: return 100
    sa, sb = set(a.split()), set(b.split())
    return int((len(sa & sb) / max(len(sa), len(sb))) * 100) if sa & sb else 0

def suggest_query(query: str):
    try:
        ql, best, max_s = query.lower(), None, 0
        for k, _ in sorted(temp.KEYWORDS.items(), key=lambda x: x[1], reverse=True)[:500]:
            if (s := fast_similarity(ql, k)) > max_s: best, max_s = k, s
        return best if max_s >= 60 else None
    except: return None

# ======================================================
# FILE MEMORY CLEANER
# ======================================================
async def cleanup_files_memory():
    if temp._cleanup_running: return
    temp._cleanup_running = True
    
    while True:
        try:
            now = int(time.time())
            [temp.FILES.pop(k, None) for k in [k for k, v in temp.FILES.items() if v.get("expire", 0) <= now]]
            if len(temp.PREMIUM) > 1000: [temp.PREMIUM.pop(k, None) for k in list(temp.PREMIUM.keys())[:500]]
            if len(temp.KEYWORDS) > 10000: temp.KEYWORDS = dict(sorted(temp.KEYWORDS.items(), key=lambda x: x[1], reverse=True)[:5000])
        except: pass
        await asyncio.sleep(120)

# ======================================================
# BROADCAST HELPERS
# ======================================================
async def _bcast(uid, msg, pin, is_grp):
    try:
        m = await msg.copy(chat_id=uid)
        if pin: 
            try: await m.pin(both_sides=not is_grp) if not is_grp else await m.pin()
            except: pass
        return "Success"
    except FloodWait as e:
        if e.value > 300: return "Error"
        await asyncio.sleep(e.value); return await _bcast(uid, msg, pin, is_grp)
    except:
        try: await db.delete_chat(uid) if is_grp else await db.delete_user(int(uid))
        except: pass
        return "Error"

async def broadcast_messages(uid, msg, pin=False): return await _bcast(uid, msg, pin, False)
async def groups_broadcast_messages(cid, msg, pin=False): return await _bcast(cid, msg, pin, True)

# ======================================================
# UTILITIES
# ======================================================
def get_size(size):
    try:
        size = float(size)
        for u in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024: return f"{size:.2f} {u}"
            size /= 1024
        return f"{size:.2f} PB"
    except: return "0 B"

def get_readable_time(sec):
    try:
        out = ""
        for n, s in [("d", 86400), ("h", 3600), ("m", 60), ("s", 1)]:
            if sec >= s: v, sec = divmod(sec, s); out += f"{int(v)}{n} "
        return out.strip() or "0s"
    except: return "0s"

async def get_settings(gid):
    try:
        if gid not in temp.SETTINGS: temp.SETTINGS[gid] = await db.get_settings(gid) or {}
        return temp.SETTINGS[gid]
    except: return {}
