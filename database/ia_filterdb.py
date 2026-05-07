import logging
import re
import base64
import time
import asyncio
from struct import pack
from datetime import datetime
from collections import OrderedDict
from typing import List, Tuple, Optional, Dict, Any

from hydrogram.file_id import FileId
from motor.motor_asyncio import AsyncIOMotorClient  # ✅ FIX #1: Async MongoDB driver
from pymongo import TEXT, ASCENDING
from pymongo.errors import DuplicateKeyError, OperationFailure

from info import (
    DATA_DATABASE_URL,
    DATABASE_NAME,
    COLLECTION_NAME,
    MAX_BTN,
    USE_CAPTION_FILTER
)

logger = logging.getLogger(__name__)

# =====================================================
# 📦 DATABASE CONNECTION (Async Motor Client)
# =====================================================
# ✅ FIX #1: Use Motor (async) instead of PyMongo (sync)
# PyMongo blocks the event loop — Motor is non-blocking
try:
    client = AsyncIOMotorClient(
        DATA_DATABASE_URL,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        socketTimeoutMS=10000,
        maxPoolSize=50,          # ✅ PERF: Connection pooling
        minPoolSize=5,
        waitQueueTimeoutMS=5000,
    )
    db = client[DATABASE_NAME]
    collection = db[COLLECTION_NAME]
    logger.info("✅ Async Motor client initialized")
except Exception as e:
    logger.error(f"❌ Database connection failed: {e}")
    raise


# =====================================================
# 🚀 SAFE INDEX SETUP (Run once at startup)
# =====================================================
_indexes_created = False  # ✅ FIX #10: Only create indexes once

async def ensure_indexes() -> None:
    """Create necessary indexes if they don't exist (async, runs once)"""
    global _indexes_created
    if _indexes_created:
        return

    try:
        existing = await collection.index_information()

        # Text search index
        if "file_text_index" not in existing:
            try:
                await collection.create_index(
                    [("file_name", TEXT), ("caption", TEXT)],
                    name="file_text_index",
                    default_language="english",
                    background=True,  # ✅ PERF: Non-blocking index build
                )
                logger.info("✅ Text index created")
            except OperationFailure as e:
                logger.warning(f"⚠️ Text index skipped: {e}")

        # Quality index
        if "quality_idx" not in existing:
            await collection.create_index(
                [("quality", ASCENDING)],
                name="quality_idx",
                background=True,
            )
            logger.info("✅ Quality index created")

        # Updated_at index
        if "updated_at_idx" not in existing:
            await collection.create_index(
                [("updated_at", ASCENDING)],
                name="updated_at_idx",
                background=True,
            )
            logger.info("✅ Updated_at index created")

        _indexes_created = True

    except Exception as e:
        logger.error(f"❌ Index creation error: {e}")


# =====================================================
# 📊 DOCUMENT COUNT (Async)
# =====================================================
async def db_count_documents() -> int:
    """Get approximate document count (non-blocking)"""
    try:
        return await collection.estimated_document_count()
    except Exception as e:
        logger.error(f"Count error: {e}")
        return 0


# =====================================================
# ⚡ THREAD-SAFE LRU CACHE
# =====================================================
# ✅ FIX #2 & #7: Thread-safe LRU with proper eviction using OrderedDict
class LRUCache:
    """Thread-safe LRU cache with TTL support"""

    def __init__(self, maxsize: int = 1000, ttl: int = 30):
        self._cache: OrderedDict[str, Tuple[Any, float]] = OrderedDict()
        self._maxsize = maxsize
        self._ttl = ttl
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            if key not in self._cache:
                return None
            data, ts = self._cache[key]
            if time.monotonic() - ts > self._ttl:
                del self._cache[key]
                return None
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            return data

    async def set(self, key: str, value: Any) -> None:
        async with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = (value, time.monotonic())
            # Evict LRU entries until within size limit
            while len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()

    async def invalidate_prefix(self, prefix: str) -> None:
        """Invalidate only keys matching prefix (targeted invalidation)"""
        async with self._lock:
            keys_to_del = [k for k in self._cache if k.startswith(prefix)]
            for k in keys_to_del:
                del self._cache[k]

    @property
    def size(self) -> int:
        return len(self._cache)


_search_cache = LRUCache(maxsize=1000, ttl=30)


# =====================================================
# 🧠 QUALITY DETECTOR
# =====================================================
# ✅ PERF: Pre-compile patterns once at module load
QUALITY_PATTERNS = [
    (re.compile(r'\b(2160p?|4k|uhd)\b', re.IGNORECASE), "2160p"),
    (re.compile(r'\b1440p?\b', re.IGNORECASE), "1440p"),
    (re.compile(r'\b1080p?\b', re.IGNORECASE), "1080p"),
    (re.compile(r'\b720p?\b', re.IGNORECASE), "720p"),
    (re.compile(r'\b480p?\b', re.IGNORECASE), "480p"),
    (re.compile(r'\b360p?\b', re.IGNORECASE), "360p"),
    (re.compile(r'\b240p?\b', re.IGNORECASE), "240p"),
]

def detect_quality(name: str) -> str:
    """Detect video quality from filename"""
    if not name:
        return "unknown"
    for pattern, quality in QUALITY_PATTERNS:
        if pattern.search(name):
            return quality
    return "unknown"


# =====================================================
# 🧹 TEXT CLEANER
# =====================================================
# ✅ FIX #3: Pre-compiled regexes, fixed edge cases
_RE_USERNAME  = re.compile(r'@\w+')
_RE_URL       = re.compile(r'https?://\S+|www\.\S+')
_RE_SEPARATORS = re.compile(r'[_\-\.+|]+')
_RE_SPACES    = re.compile(r'\s{2,}')
_RE_NON_WORD  = re.compile(r'[^\w\s]')

def clean_text(text: str) -> str:
    """Remove special characters, usernames, URLs and extra spaces"""
    if not text or not text.strip():
        return ""
    t = _RE_USERNAME.sub('', text)
    t = _RE_URL.sub('', t)
    t = _RE_SEPARATORS.sub(' ', t)
    t = _RE_NON_WORD.sub('', t)
    t = _RE_SPACES.sub(' ', t)
    return t.strip()


# =====================================================
# 🔎 SMART SEARCH ENGINE (Fully Async)
# =====================================================
# ✅ FIX #1, #6, #9: Async cursor, complete projection, correct count logic
async def get_search_results(
    query: str,
    offset: int = 0,
    max_results: int = MAX_BTN,
) -> Tuple[List[Dict], str, int]:
    """
    Search files with text search + regex fallback.
    Returns: (files, next_offset, total_count)
    """
    q = query.strip()
    if len(q) < 2:
        return [], "", 0

    q_lower = q.lower()
    cache_key = f"{q_lower}:{offset}"

    # Check cache
    cached = await _search_cache.get(cache_key)
    if cached is not None:
        return cached

    files: List[Dict] = []
    total: int = 0

    # ─── PROJECTION: include all needed fields ─────────────────────────────
    # ✅ FIX #6: Added caption & file_id to projection so callers have full data
    PROJECTION = {
        "file_name": 1,
        "file_size": 1,
        "caption": 1,
        "quality": 1,
    }

    # ─── METHOD 1: TEXT SEARCH (FAST) ─────────────────────────────────────
    text_filter = {"$text": {"$search": q}}
    text_projection = {**PROJECTION, "score": {"$meta": "textScore"}}

    try:
        # ✅ PERF: Run find + count concurrently
        cursor = collection.find(text_filter, text_projection)\
            .sort([("score", {"$meta": "textScore"})])\
            .skip(offset)\
            .limit(max_results)

        # Run count and fetch concurrently
        fetch_task = asyncio.ensure_future(_cursor_to_list(cursor))
        count_task = asyncio.ensure_future(
            collection.count_documents(text_filter, limit=10000)
        )
        files, total = await asyncio.gather(fetch_task, count_task)

    except Exception as e:
        logger.error(f"Text search error: {e}")
        files, total = [], 0

    # ─── METHOD 2: REGEX FALLBACK (ACCURATE) ──────────────────────────────
    if not files:
        try:
            escaped = re.escape(q)
            regex = re.compile(escaped, re.IGNORECASE)

            if USE_CAPTION_FILTER:
                rg_filter: Dict = {"$or": [{"file_name": regex}, {"caption": regex}]}
            else:
                rg_filter = {"file_name": regex}

            cursor = collection.find(rg_filter, PROJECTION)\
                .skip(offset)\
                .limit(max_results)

            fetch_task = asyncio.ensure_future(_cursor_to_list(cursor))
            count_task = asyncio.ensure_future(
                collection.count_documents(rg_filter, limit=5000)
            )
            files, raw_count = await asyncio.gather(fetch_task, count_task)
            # ✅ FIX #9: Consistent capping
            total = min(raw_count, 5000)

        except Exception as e:
            logger.error(f"Regex search error: {e}")

    # ─── Calculate next offset ────────────────────────────────────────────
    fetched_end = offset + len(files)
    next_offset = str(fetched_end) if total > fetched_end else ""

    result = (files, next_offset, total)
    await _search_cache.set(cache_key, result)
    return result


async def _cursor_to_list(cursor) -> List[Dict]:
    """Helper: drain an async Motor cursor into a list"""
    results = []
    async for doc in cursor:
        results.append(doc)
    return results


# =====================================================
# 🗑 DELETE FILES BY QUERY
# =====================================================
async def delete_files(query: str) -> int:
    """Delete files matching query by file_name regex"""
    if not query or len(query.strip()) < 2:
        return 0
    try:
        escaped = re.escape(query.strip())
        regex = re.compile(escaped, re.IGNORECASE)
        res = await collection.delete_many({"file_name": regex})
        # ✅ FIX #8: Targeted cache invalidation instead of full clear
        await _search_cache.invalidate_prefix(query.strip().lower()[:10])
        return res.deleted_count
    except Exception as e:
        logger.error(f"Delete error: {e}")
        return 0


# =====================================================
# 🗑 DELETE ALL FILES
# =====================================================
async def delete_all_files() -> int:
    """
    Delete ALL files from database.
    ⚠️ WARNING: Irreversible!
    """
    try:
        res = await collection.delete_many({})
        await _search_cache.clear()
        deleted = res.deleted_count
        logger.warning(f"⚠️ DELETED ALL FILES: {deleted} files removed!")
        return deleted
    except Exception as e:
        logger.error(f"❌ Delete all files error: {e}")
        return 0


# =====================================================
# 🗑 DELETE FILE BY ID
# =====================================================
async def delete_file_by_id(file_id: str) -> bool:
    """Delete single file by its _id"""
    if not file_id:
        return False
    try:
        res = await collection.delete_one({"_id": file_id})
        if res.deleted_count > 0:
            await _search_cache.clear()
            logger.info(f"✅ File deleted: {file_id}")
            return True
        return False
    except Exception as e:
        logger.error(f"❌ Delete file by ID error: {e}")
        return False


# =====================================================
# 🗑 DELETE BY QUALITY
# =====================================================
async def delete_by_quality(quality: str) -> int:
    """Delete all files of specific quality (e.g. '480p')"""
    if not quality or not quality.strip():
        return 0
    try:
        res = await collection.delete_many({"quality": quality.strip()})
        await _search_cache.clear()
        deleted = res.deleted_count
        logger.info(f"✅ Deleted {deleted} files with quality: {quality}")
        return deleted
    except Exception as e:
        logger.error(f"❌ Delete by quality error: {e}")
        return 0


# =====================================================
# 📄 GET FILE DETAILS
# =====================================================
async def get_file_details(file_id: str) -> Optional[Dict]:
    """Get single file details by _id"""
    if not file_id:
        return None
    try:
        return await collection.find_one({"_id": file_id})
    except Exception as e:
        logger.error(f"Get file error: {e}")
        return None


# =====================================================
# 💾 SAVE / UPDATE FILE
# =====================================================
async def save_file(media) -> str:
    """
    Save or update file in database.
    Returns: 'suc' (new), 'dup' (updated), 'err' (failed)
    """
    try:
        if not media or not hasattr(media, 'file_id'):
            return "err"

        # ✅ FIX #4: Validate file_id before saving to prevent corrupt _id
        file_id = unpack_new_file_id(media.file_id)
        if not file_id:
            logger.error("❌ unpack_new_file_id returned empty string — skipping save")
            return "err"

        file_name = clean_text(getattr(media, 'file_name', None) or "Untitled")
        caption   = clean_text(getattr(media, 'caption',   None) or "")
        file_size = getattr(media, 'file_size', 0) or 0
        quality   = detect_quality(file_name)

        now = datetime.utcnow()
        doc = {
            "_id":        file_id,
            "file_name":  file_name,
            "file_size":  file_size,
            "caption":    caption,
            "quality":    quality,
            "updated_at": now,
        }

        try:
            await collection.insert_one(doc)
            return "suc"

        except DuplicateKeyError:
            await collection.update_one(
                {"_id": file_id},
                {"$set": {
                    "caption":    caption,
                    "quality":    quality,
                    "file_size":  file_size,
                    "updated_at": now,
                }},
            )
            return "dup"

    except Exception as e:
        logger.error(f"Save file error: {e}")
        return "err"


# =====================================================
# 🔄 UPDATE CAPTION
# =====================================================
async def update_file_caption(file_id: str, new_caption: str) -> bool:
    """Update file caption by _id"""
    if not file_id or not new_caption or not new_caption.strip():
        return False
    try:
        cleaned = clean_text(new_caption)
        res = await collection.update_one(
            {"_id": file_id},
            {"$set": {"caption": cleaned, "updated_at": datetime.utcnow()}},
        )
        await _search_cache.clear()
        return res.modified_count > 0
    except Exception as e:
        logger.error(f"Update caption error: {e}")
        return False


# =====================================================
# 🔄 UPDATE QUALITY
# =====================================================
async def update_file_quality(file_id: str, new_name: str) -> bool:
    """Re-detect and update file quality based on new filename"""
    if not file_id or not new_name or not new_name.strip():
        return False
    try:
        quality = detect_quality(new_name)
        res = await collection.update_one(
            {"_id": file_id},
            {"$set": {"quality": quality, "updated_at": datetime.utcnow()}},
        )
        return res.modified_count > 0
    except Exception as e:
        logger.error(f"Update quality error: {e}")
        return False


# =====================================================
# 🔐 FILE ID ENCODING UTILITIES
# =====================================================
def encode_file_id(s: bytes) -> str:
    """Encode raw bytes to Telegram-compatible base64 file ID"""
    try:
        r = b""
        n = 0
        for i in s + bytes([22]) + bytes([4]):
            if i == 0:
                n += 1
            else:
                if n:
                    r += b"\x00" + bytes([n])
                    n = 0
                r += bytes([i])
        return base64.urlsafe_b64encode(r).decode().rstrip("=")
    except Exception as e:
        logger.error(f"Encode error: {e}")
        return ""


def unpack_new_file_id(new_file_id: str) -> str:
    """
    Decode and unpack Telegram file ID.
    ✅ FIX #4: Returns "" on failure — caller MUST check before using as _id
    """
    if not new_file_id or not isinstance(new_file_id, str):
        return ""
    try:
        decoded = FileId.decode(new_file_id)
        return encode_file_id(
            pack(
                "<iiqq",
                int(decoded.file_type),
                decoded.dc_id,
                decoded.media_id,
                decoded.access_hash,
            )
        )
    except Exception as e:
        logger.error(f"Unpack error for file_id '{new_file_id[:20]}...': {e}")
        return ""


# =====================================================
# 🧪 HEALTH CHECK (Async)
# =====================================================
async def database_health_check() -> Dict[str, Any]:
    """Check database health and stats"""
    try:
        count_task = asyncio.ensure_future(db_count_documents())
        ping_task  = asyncio.ensure_future(db.command("ping"))
        total, _   = await asyncio.gather(count_task, ping_task)

        return {
            "status":      "healthy",
            "total_files": total,
            "cache_size":  _search_cache.size,
            "connected":   True,
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status":    "unhealthy",
            "error":     str(e),
            "connected": False,
        }
