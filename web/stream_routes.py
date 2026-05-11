import re
import math
from aiohttp import web
from utils import temp

stream_routes = web.RouteTableDef()

@stream_routes.get('/stream/{file_id}')
async def stream_handler(request: web.Request):
    try:
        file_id = request.match_info['file_id']
        bot = temp.BOT 
        
        # यहाँ आपको file_id को डिकोड करके Telegram message/file fetch करना होगा
        # उदाहरण के लिए (आपको अपने फाइल सिस्टम के हिसाब से इसे एडजस्ट करना होगा):
        # message = await bot.get_messages(LOG_CHANNEL, int(file_id))
        # file_size = message.video.file_size
        
        # डमी साइज़ (रियल में Telegram से आएगा)
        file_size = 1024 * 1024 * 500 # 500 MB 
        
        # Range Header Parsing for seeking forward/backward
        range_header = request.headers.get('Range', 0)
        start = 0
        end = file_size - 1
        
        if range_header:
            match = re.search(r'bytes=(\d+)-(\d*)', range_header)
            if match:
                start = int(match.group(1))
                if match.group(2):
                    end = int(match.group(2))

        chunk_size = (end - start) + 1

        headers = {
            'Content-Type': 'video/mp4',
            'Accept-Ranges': 'bytes',
            'Content-Range': f'bytes {start}-{end}/{file_size}',
            'Content-Length': str(chunk_size),
        }

        response = web.StreamResponse(
            status=206 if range_header else 200,
            headers=headers
        )
        await response.prepare(request)

        # ⚠️ Telegram से असली स्ट्रीमिंग लॉजिक यहाँ आएगा:
        # async for chunk in bot.stream_media(message, offset=start, limit=chunk_size):
        #     await response.write(chunk)
        
        await response.write_eof()
        return response

    except Exception as e:
        return web.Response(text=f"Streaming Error: {e}", status=500)
