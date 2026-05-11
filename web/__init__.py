from aiohttp import web
from .search_api import search_routes
from .stream_routes import stream_routes

web_app = web.Application()

# ==========================================
# 1️⃣ LOGIN PAGE (Username/Password Form)
# ==========================================
async def login_page(request):
    if 'admin_auth' in request.cookies:
        raise web.HTTPFound('/search')

    html = """
    <html>
    <body style="background:#121212; color:white; text-align:center; padding-top:100px; font-family:sans-serif;">
        <h1>🍿 Admin Login</h1>
        <p style="color:gray;">Enter your info.py credentials</p><br>
        
        <form action="/api/login" method="post" style="display:inline-block; background:#222; padding:30px; border-radius:10px;">
            <input type="text" name="username" placeholder="Username" required style="padding:10px; width:250px; margin-bottom:15px; border-radius:5px; border:none; outline:none;"><br>
            
            <input type="password" name="password" placeholder="Password" required style="padding:10px; width:250px; margin-bottom:15px; border-radius:5px; border:none; outline:none;"><br>
            
            <button type="submit" style="padding:10px 20px; width:250px; background:#0088cc; color:white; border:none; border-radius:5px; cursor:pointer;">Login</button>
        </form>
    </body>
    </html>
    """
    return web.Response(text=html, content_type='text/html')

# ==========================================
# 2️⃣ SEARCH PAGE (Protected Route)
# ==========================================
async def search_page(request):
    if 'admin_auth' not in request.cookies:
        raise web.HTTPFound('/')
    
    html = """
    <html>
    <body style="background:#121212; color:white; text-align:center; padding:50px; font-family:sans-serif;">
        <h2>🍿 Movie Search & Stream (Admin Panel)</h2>
        
        <input type="text" id="query" placeholder="Search movies..." style="padding:12px; width:300px; border-radius:5px; border:none; outline:none;">
        <button onclick="searchFiles()" style="padding:12px 20px; background:#0088cc; color:white; border:none; border-radius:5px; cursor:pointer;">Search</button>
        
        <div id="results" style="margin-top:30px; text-align:left; max-width:600px; margin-left:auto; margin-right:auto;"></div>
        <br><br><a href="/logout" style="color:#ff4444; text-decoration:none;">Logout</a>

        <script>
            async function searchFiles() {
                let q = document.getElementById('query').value;
                document.getElementById('results').innerHTML = '<p style="text-align:center;">Searching...</p>';
                
                let res = await fetch(`/api/search?q=${q}`);
                let data = await res.json();
                
                let html = '';
                if(data.results.length === 0) html = '<p style="text-align:center;">No files found.</p>';
                
                for(let f of data.results) {
                    html += `<div style="background:#222; padding:15px; margin-bottom:10px; border-radius:8px;">
                                <b style="color:#ddd;">${f.name}</b><br>
                                <a href="/stream/${f.id}" target="_blank" style="display:inline-block; margin-top:10px; color:#0088cc; text-decoration:none;">▶ Play Stream</a>
                             </div>`;
                }
                document.getElementById('results').innerHTML = html;
            }
        </script>
    </body>
    </html>
    """
    return web.Response(text=html, content_type='text/html')

# ==========================================
# 3️⃣ LOGOUT ROUTE
# ==========================================
async def logout(request):
    response = web.HTTPFound('/')
    response.del_cookie('admin_auth')
    return response

# Routes रजिस्टर करें
web_app.router.add_get('/', login_page)
web_app.router.add_get('/search', search_page)
web_app.router.add_get('/logout', logout)

web_app.add_routes(search_routes)
web_app.add_routes(stream_routes)
