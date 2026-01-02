import logging
import re
import base64
import time
from struct import pack
from typing import List, Tuple, Dict, Any

from hydrogram.file_id import FileId
from pymongo import MongoClient, TEXT
from pymongo.errors import DuplicateKeyError

from info import (
    DATA_DATABASE_URL,
    DATABASE_NAME,
    COLLECTION_NAME,
    MAX_BTN,
    USE_CAPTION_FILTER
)

logger = logging.getLogger(__name__)

# =====================================================
# 🔌 FAST DB CONNECTION
# =====================================================
client = MongoClient(DATA_DATABASE_URL, connect=False)
db = client[DATABASE_NAME]
col = db[COLLECTION_NAME]

# Indexing (Run once quietly)
try:
    if "file_name_text_caption_text" not in col.index_information():
        col.create_index([("file_name", TEXT), ("caption", TEXT)], name="text_idx", default_language="english")
except:
    pass

# =====================================================
# ⚡ SUPER FAST CACHE (RAM BASED)
# =====================================================
SEARCH_CACHE = {}
CACHE_TTL = 60  # Cache for 1 minute
MAX_CACHE = 500

def get_cached(key):
    if key in SEARCH_CACHE:
        data, timestamp = SEARCH_CACHE[key]
        if time.time() - timestamp < CACHE_TTL:
            return data
        del SEARCH_CACHE[key]
    return None

def set_cache(key, data):
    if len(SEARCH_CACHE) > MAX_CACHE:
        SEARCH_CACHE.pop(next(iter(SEARCH_CACHE)))  # Remove oldest
    SEARCH_CACHE[key] = (data, time.time())

# =====================================================
# 🛠 UTILS (Optimized)
# =====================================================
# Pre-compile regex for speed
QUALITY_REGEX = {
    "2160p": re.compile(r'\b(2160p?|4k|uhd)\b', re.IGNORECASE),
    "1440p": re.compile(r'\b1440p?\b', re.IGNORECASE),
    "1080p": re.compile(r'\b1080p?\b', re.IGNORECASE),
    "720p": re.compile(r'\b720p?\b', re.IGNORECASE),
    "480p": re.compile(r'\b480p?\b', re.IGNORECASE),
    "360p": re.compile(r'\b360p?\b', re.IGNORECASE)
}

def detect_quality(text: str) -> str:
    if not text: return "unknown"
    for quality, pattern in QUALITY_REGEX.items():
        if pattern.search(text):
            return quality
    return "unknown"

def clean_text(text: str) -> str:
    """Removes garbage for better indexing"""
    if not text: return ""
    # Chain replacements for speed
    text = re.sub(r'(@\w+|https?://\S+|[_\-\.]+)', ' ', text)
    return " ".join(text.split())

# =====================================================
# 🔍 SEARCH ENGINE (The Core)
# =====================================================
async def get_search_results(query: str, offset: int = 0, limit: int = MAX_BTN) -> Tuple[List, str, int]:
    """
    Returns: (files_list, next_offset, total_count)
    """
    if not query: return [], "", 0
    
    # 1. Check Cache
    cache_key = f"{query.lower()}|{offset}"
    cached = get_cached(cache_key)
    if cached: return cached

    # 2. Text Search (Primary & Fast)
    search_filter = {"$text": {"$search": query}}
    
    # Use projection to fetch ONLY needed fields (Saves Bandwidth)
    projection = {"file_name": 1, "caption": 1, "file_size": 1, "quality": 1}
    
    cursor = col.find(search_filter, projection).sort([("score", {"$meta": "textScore"})])
    
    # 3. Regex Fallback (If text search fails)
    # Only run regex if text search yields 0 results to save CPU
    count = col.count_documents(search_filter)
    
    if count == 0:
        # Regex is slow, so we escape and limit strictness
        reg = re.compile(re.escape(query), re.IGNORECASE)
        search_filter = {"$or": [{"file_name": reg}, {"caption": reg}]} if USE_CAPTION_FILTER else {"file_name": reg}
        cursor = col.find(search_filter, projection)
        count = col.count_documents(search_filter)

    # 4. Pagination
    files = list(cursor.skip(offset).limit(limit))
    next_offset = str(offset + limit) if count > offset + limit else ""
    
    result = (files, next_offset, count)
    set_cache(cache_key, result)
    return result

# =====================================================
# 💾 SAVE FILE
# =====================================================
async def save_file(media):
    """Saves file to DB. Returns: 'suc', 'dup', or 'err'"""
    try:
        if not media: return "err"

        # Unique ID Generation
        file_id = media.file_id
        try:
            # Custom packing (Legacy support)
            decoded = FileId.decode(file_id)
            packed = pack("<iiqq", int(decoded.file_type), decoded.dc_id, decoded.media_id, decoded.access_hash)
            file_id = base64.urlsafe_b64encode(b"" + packed).decode().rstrip("=")
        except:
            return "err"

        name = clean_text(getattr(media, 'file_name', "Untitled"))
        caption = getattr(media, 'caption', "")
        
        doc = {
            "_id": file_id,
            "file_name": name,
            "file_size": getattr(media, 'file_size', 0),
            "caption": caption,
            "quality": detect_quality(name)
        }

        col.insert_one(doc)
        return "suc"

    except DuplicateKeyError:
        # Fast update without re-fetching
        col.update_one(
            {"_id": doc["_id"]}, 
            {"$set": {"caption": doc["caption"], "quality": doc["quality"]}}
        )
        return "dup"
    except Exception as e:
        logger.error(f"Save Error: {e}")
        return "err"

# =====================================================
# 🗑 DELETE UTILS
# =====================================================
async def delete_files(query: str):
    try:
        reg = re.compile(re.escape(query), re.IGNORECASE)
        res = col.delete_many({"file_name": reg})
        SEARCH_CACHE.clear()
        return res.deleted_count
    except:
        return 0

async def delete_all_files():
    try:
        res = col.delete_many({})
        SEARCH_CACHE.clear()
        return res.deleted_count
    except:
        return 0

# =====================================================
# 🩺 HEALTH CHECK
# =====================================================
async def db_stats():
    try:
        return {
            "total": col.estimated_document_count(),
            "cache": len(SEARCH_CACHE)
        }
    except:
        return {"total": 0, "cache": 0}

