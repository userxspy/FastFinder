from aiohttp import web
from database.ia_filterdb import get_search_results

search_routes = web.RouteTableDef()

@search_routes.get('/api/search')
async def web_search(request: web.Request):
    query = request.query.get('q', '')
    offset = int(request.query.get('offset', 0))
    
    if len(query) < 2:
        return web.json_response({"results": [], "next_offset": 0})

    # Fetching ultra-fast results from your optimized database
    files, next_offset, total = await get_search_results(query, offset=offset, max_results=10)
    
    results = [{"id": f['_id'], "name": f['file_name'], "size": f['file_size']} for f in files]
        
    return web.json_response({
        "results": results,
        "next_offset": next_offset,
        "total": total
    })
