from aiohttp import web
from .search_api import search_routes
from .stream_routes import stream_routes
from .admin_routes import admin_routes # अगर आप एडमिन पैनल बना रहे हैं

# Main web application
web_app = web.Application()

# Registering all routes from different files
web_app.add_routes(search_routes)
web_app.add_routes(stream_routes)
web_app.add_routes(admin_routes)
