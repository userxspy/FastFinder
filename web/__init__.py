# Credit - adarsh-goel

from aiohttp import web
from web.stream_routes import routes

# ⬇️ यहाँ हमने अपनी नई फाइल्स को इम्पोर्ट किया है ⬇️
from web.admin_routes import admin_routes
from web.search_api import search_routes

# 🌟 नया पब्लिक लॉगिन और OTP वाला राउट इम्पोर्ट किया है 
from web.public_routes import public_routes 

# =========================================
# 🚀 WEB APP INITIALIZATION
# =========================================

# client_max_size=100MB set kiya hai taaki 'Payload Too Large' error na aaye
web_app = web.Application(client_max_size=100 * 1024 * 1024)

# Routes load karna
web_app.add_routes(routes)

# ⬇️ यहाँ हमने नए राउट्स को वेब ऐप से जोड़ दिया है ⬇️
web_app.add_routes(admin_routes)
web_app.add_routes(search_routes)

# 🌟 नया पब्लिक राउट ऐप में जोड़ दिया है
web_app.add_routes(public_routes)
