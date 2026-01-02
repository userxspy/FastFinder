import logging
import time
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

from info import (
    DATABASE_NAME,
    DATA_DATABASE_URL
)

# =========================
# 📝 LOGGING SETUP
# =========================
logger = logging.getLogger(__name__)

class Database:
    
    # =========================
    # DEFAULTS
    # =========================
    default_settings = {
        "pm_search": True,
        "group_search": True,
        "auto_delete": False,
        "anti_link": False,
    }

    default_verify = {
        "is_verified": False,
        "verified_time": 0,
        "verify_token": "",
        "expire_time": 0,
    }

    default_plan = {
        "premium": False,
        "plan": "free",
        "expire": None,
        "invoices": [],
        "last_reminder": None,
        "activated_at": None,
    }

    # =========================
    # INIT & CONNECTION
    # =========================
    def __init__(self):
        try:
            self.client = AsyncIOMotorClient(
                DATA_DATABASE_URL,
                serverSelectionTimeoutMS=5000,
                maxPoolSize=10
            )
            self.db = self.client[DATABASE_NAME]
            
            # Collections
            self.users = self.db.users
            self.groups = self.db.groups
            self.premium = self.db.premium
            self.reminders = self.db.reminders
            self.bans = self.db.bans
            self.warns = self.db.warns
            
            # Local RAM Cache (Ultra Speed)
            self._premium_cache = {} 
            self._ban_cache = {}

            logger.info("✅ Database (Motor) Connected Successfully")
            
        except Exception as e:
            logger.error(f"❌ Database Connection Failed: {e}")
            raise e

    # =========================
    # 👥 USERS
    # =========================
    async def is_user_exist(self, user_id: int):
        user = await self.users.find_one({"id": user_id}, {"_id": 1})
        return bool(user)

    async def add_user(self, user_id: int, name: str):
        if await self.is_user_exist(user_id):
            return False
        
        try:
            await self.users.insert_one({
                "id": user_id,
                "name": name,
                "created_at": time.time(),
                "verify": self.default_verify.copy()
            })
            return True
        except DuplicateKeyError:
            return False

    async def total_users_count(self):
        return await self.users.count_documents({})

    async def get_all_users(self):
        """Returns a cursor instead of a list to save RAM"""
        return self.users.find({})

    async def delete_user(self, user_id: int):
        await self.users.delete_one({"id": user_id})
        await self.premium.delete_one({"id": user_id})

    # =========================
    # 🚫 BANS (With Caching)
    # =========================
    async def ban_user(self, user_id: int, until: float, reason: str = ""):
        await self.bans.update_one(
            {"id": user_id},
            {"$set": {
                "until": until,
                "reason": reason,
                "banned_at": time.time()
            }},
            upsert=True
        )
        self._ban_cache[user_id] = {"status": True, "until": until} # Update Cache
        return True

    async def unban_user(self, user_id: int):
        await self.bans.delete_one({"id": user_id})
        if user_id in self._ban_cache:
            del self._ban_cache[user_id] # Clear Cache
        return True

    async def get_ban_status(self, user_id: int):
        # 1. Check RAM Cache
        if user_id in self._ban_cache:
            cached = self._ban_cache[user_id]
            if cached["until"] > time.time():
                return cached
            else:
                del self._ban_cache[user_id] # Expired

        # 2. Check Database
        ban = await self.bans.find_one({"id": user_id})
        
        if not ban:
            return {"status": False}

        if ban.get("until", 0) <= time.time():
            await self.unban_user(user_id)
            return {"status": False}

        # 3. Update Cache
        data = {
            "status": True,
            "reason": ban.get("reason", ""),
            "until": ban.get("until")
        }
        self._ban_cache[user_id] = data
        return data

    # =========================
    # 📢 GROUPS
    # =========================
    async def add_group(self, chat_id: int, title: str):
        try:
            await self.groups.insert_one({
                "id": chat_id,
                "title": title,
                "settings": self.default_settings.copy(),
                "joined_at": time.time()
            })
            return True
        except DuplicateKeyError:
            return False

    async def get_settings(self, chat_id: int):
        group = await self.groups.find_one({"id": chat_id}, {"settings": 1})
        if group:
            return group.get("settings", self.default_settings.copy())
        return self.default_settings.copy()

    async def update_settings(self, chat_id: int, settings: dict):
        await self.groups.update_one(
            {"id": chat_id},
            {"$set": {"settings": settings}},
            upsert=True
        )
        return True

    # =========================
    # 💎 PREMIUM (With Caching)
    # =========================
    async def get_plan(self, user_id: int):
        # 1. Check Cache
        if user_id in self._premium_cache:
            return self._premium_cache[user_id]

        # 2. DB Query
        data = await self.premium.find_one({"id": user_id})
        
        if not data:
            plan = self.default_plan.copy()
        else:
            plan = data.get("plan", self.default_plan.copy())

        # 3. Save to Cache (Only if premium is True to save RAM)
        if plan.get("premium"):
            self._premium_cache[user_id] = plan
            
        return plan

    async def update_plan(self, user_id: int, plan_data: dict):
        await self.premium.update_one(
            {"id": user_id},
            {"$set": {"plan": plan_data}},
            upsert=True
        )
        # Update Cache
        self._premium_cache[user_id] = plan_data
        return True

    async def remove_premium(self, user_id: int):
        # Reset to default plan in DB
        await self.update_plan(user_id, self.default_plan.copy())
        # Remove from Cache
        if user_id in self._premium_cache:
            del self._premium_cache[user_id]

    async def get_premium_users(self):
        """Returns cursor of all premium users"""
        return self.premium.find({"plan.premium": True})

# =========================
# EXPORT
# =========================
db = Database()

