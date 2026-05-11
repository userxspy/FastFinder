from aiohttp import web
import time
from utils import temp, get_size
from info import BIN_CHANNEL

# 🚀 IMPORT NEW FAST DB
from database.ia_filterdb import get_search_results

search_routes = web.RouteTableDef()

def is_auth(req):
    s = req.cookies.get('admin_session')
    return bool(s and hasattr(temp, 'ADMIN_SESSIONS') and temp.ADMIN_SESSIONS.get(s, 0) > time.time())

@search_routes.get('/api/search')
async def api_search(req):
    if not is_auth(req): 
        return web.json_response({"error": "Unauthorized Access"}, status=403)

    q = req.query.get('q', '').strip()
    off = req.query.get('offset', '0')
    
    if not q: return web.json_response({"results": [], "total": 0, "next_offset": ""})
    
    off = int(off) if off.isdigit() else 0
    
    # 🚀 USE ULTRA-FAST DB SEARCH (Replaced old slow regex loop)
    files, next_offset, tot = await get_search_results(q, offset=off, max_results=20)
    
    res = []
    for d in files:
        fid = d.get("_id") # New DB uses _id directly
        res.append({
            "name": d.get("file_name", "Unknown File"),
            "size": get_size(d.get("file_size", 0)),
            "type": "DOCUMENT", 
            "source": "Primary", 
            "watch": f"/setup_stream?file_id={fid}&mode=watch",
            "download": f"/setup_stream?file_id={fid}&mode=download"
        })

    return web.json_response({
        "results": res, 
        "total": tot, 
        "next_offset": int(next_offset) if next_offset else ""
    })

@search_routes.get('/setup_stream')
async def setup_stream(req):
    if not is_auth(req): return web.Response(text="❌ Unauthorized Access!", status=403)
    
    fid, mode = req.query.get('file_id'), req.query.get('mode', 'watch')
    if not fid: return web.Response(text="Invalid Request", status=400)
    
    try:
        # Send to BIN_CHANNEL to generate valid message_id for streaming
        msg = await temp.BOT.send_cached_media(chat_id=BIN_CHANNEL, file_id=fid)
        return web.HTTPFound(f"/{'download' if mode == 'download' else 'watch'}/{msg.id}")
    except Exception as e: 
        return web.Response(text=f"❌ Error: {e}", status=500)
