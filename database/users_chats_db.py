import time
import logging
from typing import List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorClient

from info import DATA_DATABASE_URL, DATABASE_NAME

logger = logging.getLogger(__name__)

# =========================
# 🔗 ASYNC MongoDB Connection
# =========================
try:
    client = AsyncIOMotorClient(
        DATA_DATABASE_URL,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=10000,
        maxPoolSize=50,
        retryWrites=True
    )
    dbase = client[DATABASE_NAME]
    logger.info("✅ Users/Chats Database connected successfully")
except Exception as e:
    logger.error(f"❌ Database connection failed: {e}")
    dbase = None


class Database:
    # =========================
    # DEFAULT STRUCTURES
    # =========================
    default_settings = {"pm_search": True, "group_search": True, "auto_delete": False, "anti_link": False}
    default_verify = {"is_verified": False, "verified_time": 0, "verify_token": "", "expire_time": 0}
    default_plan = {"premium": False, "plan": "free", "expire": None, "invoices": [], "last_reminder": None, "activated_at": None}

    def __init__(self):
        if dbase is None:
            raise Exception("Database not connected")

        self.users = dbase.users
        self.groups = dbase.groups
        self.premium = dbase.premium
        self.reminders = dbase.reminders
        self.bans = dbase.bans
        self.warns = dbase.warns

    # 🚀 SAFE ASYNC INDEX SETUP (Call this on bot start)
    async def setup_indexes(self) -> None:
        """Create necessary indexes efficiently"""
        try:
            await self.users.create_index("id", unique=True)
            await self.groups.create_index("id", unique=True)
            await self.bans.create_index("id", unique=True)
            await self.bans.create_index("until")
            await self.warns.create_index([("user_id", 1), ("chat_id", 1)])
            await self.premium.create_index("id", unique=True)
            await self.reminders.create_index([("sent", 1), ("remind_at", 1)])
            logger.info("✅ Users/Chats Indexes created successfully")
        except Exception as e:
            logger.warning(f"⚠️ Index creation skipped/error: {e}")

    # =========================
    # 👤 USERS
    # =========================
    async def is_user_exist(self, user_id: int) -> bool:
        return bool(await self.users.find_one({"id": user_id}, {"_id": 1}))

    async def add_user(self, user_id: int, name: str) -> bool:
        if await self.is_user_exist(user_id): 
            return False
        await self.users.insert_one({"id": user_id, "name": name, "created_at": time.time(), "verify": self.default_verify.copy()})
        return True

    async def total_users_count(self) -> int:
        return await self.users.estimated_document_count()

    async def get_all_users(self) -> List[Dict]:
        return await self.users.find({}).to_list(length=None)

    # =========================
    # 🚫 BANS
    # =========================
    async def get_banned_users(self) -> List[Dict]:
        return await self.bans.find({"until": {"$gt": time.time()}}).to_list(length=None)

    async def ban_user(self, user_id: int, until: float, reason: str = "") -> bool:
        await self.bans.update_one({"id": user_id}, {"$set": {"until": until, "reason": reason, "banned_at": time.time()}}, upsert=True)
        return True

    async def unban_user(self, user_id: int) -> bool:
        await self.bans.delete_one({"id": user_id})
        return True

    async def get_ban_status(self, user_id: int) -> Dict[str, Any]:
        ban = await self.bans.find_one({"id": user_id})
        if not ban: return {"status": False}
        
        if ban.get("until", 0) <= time.time():
            await self.unban_user(user_id)
            return {"status": False}
        return {"status": True, "reason": ban.get("reason", ""), "until": ban.get("until")}

    # =========================
    # 👥 GROUPS
    # =========================
    async def add_group(self, chat_id: int, title: str) -> bool:
        if await self.groups.find_one({"id": chat_id}, {"_id": 1}): 
            return False
        await self.groups.insert_one({"id": chat_id, "title": title, "settings": self.default_settings.copy(), "joined_at": time.time()})
        return True

    async def get_settings(self, chat_id: int) -> Dict[str, Any]:
        group = await self.groups.find_one({"id": chat_id}, {"settings": 1})
        # Fast dictionary merging using kwargs expansion
        return {**self.default_settings, **(group.get("settings", {}) if group else {})}

    async def update_settings(self, chat_id: int, settings: dict) -> bool:
        await self.groups.update_one({"id": chat_id}, {"$set": {"settings": settings}}, upsert=True)
        return True

    # =========================
    # 💎 PREMIUM
    # =========================
    async def get_plan(self, user_id: int) -> Dict[str, Any]:
        data = await self.premium.find_one({"id": user_id}, {"plan": 1})
        return data.get("plan", self.default_plan.copy()) if data else self.default_plan.copy()

    async def update_plan(self, user_id: int, plan_data: dict) -> bool:
        await self.premium.update_one({"id": user_id}, {"$set": {"plan": plan_data}}, upsert=True)
        return True

    async def get_premium_users(self) -> List[Dict]:
        return await self.premium.find({"plan.premium": True}).to_list(length=None)

# =========================
# EXPORT
# =========================
db = Database()

