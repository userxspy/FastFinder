from aiohttp import web
from info import ADMIN_USERNAME, ADMIN_PASSWORD
from database.ia_filterdb import get_search_results

search_routes = web.RouteTableDef()

# ==========================================
# 🔑 CUSTOM LOGIN VERIFICATION ROUTE
# ==========================================
@search_routes.post('/api/login')  # इसे POST कर दिया है ताकि पासवर्ड सुरक्षित रहे
async def web_login(request: web.Request):
    data = await request.post()
    username = data.get('username')
    password = data.get('password')
    
    # Check credentials from info.py
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        # लॉगिन सक्सेस! कुकी सेट करें और /search पर भेजें
        response = web.HTTPFound('/search')
        response.set_cookie('admin_auth', 'true', max_age=86400 * 30) # 30 दिन के लिए लॉगिन
        return response
        
    return web.Response(text="Login Failed! Incorrect Username or Password.", status=401)

# ==========================================
# 🔎 SEARCH API ROUTE
# ==========================================
@search_routes.get('/api/search')
async def web_search(request: web.Request):
    query = request.query.get('q', '')
    offset = int(request.query.get('offset', 0))
    
    if len(query) < 2: return web.json_response({"results": []})

    files, next_offset, total = await get_search_results(query, offset=offset, max_results=15)
    results = [{"id": f['_id'], "name": f['file_name'], "size": f['file_size']} for f in files]
        
    return web.json_response({"results": results, "next_offset": next_offset})
