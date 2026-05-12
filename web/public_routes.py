import time, uuid, hashlib, random
from aiohttp import web
from utils import temp, is_premium
from database.users_chats_db import db

public_routes = web.RouteTableDef()

# ==========================================
# 🛠️ HELPER FUNCTIONS
# ==========================================
def hash_pass(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

async def get_user_by_email(email: str):
    return await db.users.find_one({"web_email": email})

if not hasattr(temp, 'PUBLIC_SESSIONS'): temp.PUBLIC_SESSIONS = {}
if not hasattr(temp, 'OTPS'): temp.OTPS = {}
if not hasattr(temp, 'SIGNUPS'): temp.SIGNUPS = {} # New: Sign Up Verification

CSS = "*{box-sizing:border-box;margin:0;padding:0}body{font-family:'DM Sans',sans-serif;background:#141414;color:#fff;display:flex;justify-content:center;align-items:center;min-height:100vh}.bg{position:fixed;inset:0;background:linear-gradient(rgba(0,0,0,.7),rgba(0,0,0,.9)),url('https://assets.nflxext.com/ffe/siteui/vlv3/f841d4c7-10e1-40af-bcae-07a3f8dc141a/f6d7434e-d6de-4185-a6d4-c77a2d08737b/IN-en-20220502-popsignuptwoweeks-perspective_alpha_website_medium.jpg') center/cover;z-index:-1}.card{background:rgba(0,0,0,.75);padding:50px;border-radius:8px;width:100%;max-width:450px}.card h2{font-size:32px;margin-bottom:25px}.input-group{margin-bottom:15px}.input-group input{width:100%;background:#333;border:0;padding:15px;color:#fff;border-radius:4px;outline:0}.btn{width:100%;background:#e50914;color:#fff;border:0;padding:15px;font-size:16px;font-weight:700;border-radius:4px;cursor:pointer;margin-top:10px}.btn:hover{background:#b30710}.link{color:#b3b3b3;text-decoration:none;font-size:14px;margin-top:15px;display:block;text-align:center}.link:hover{text-decoration:underline}.err{background:#e87c03;color:#fff;padding:10px;border-radius:4px;margin-bottom:15px;font-size:14px}.success{background:#2b9eb3;color:#fff;padding:10px;border-radius:4px;margin-bottom:15px;font-size:14px}"

def render_page(title, body):
    return web.Response(text=f"<!DOCTYPE html><html><head><title>{title}</title><style>{CSS}</style></head><body><div class='bg'></div>{body}</body></html>", content_type='text/html')

# ==========================================
# 🏠 1. LOGIN PAGE
# ==========================================
# 🚀 FIX: URL changed to /login
@public_routes.get('/login')
async def login_page(req):
    if req.cookies.get('user_session') in temp.PUBLIC_SESSIONS:
        return web.HTTPFound('/dashboard')
    err = req.query.get('err', '')
    msg = req.query.get('msg', '')
    b = f"<div class='success'>{msg}</div>" if msg else (f"<div class='err'>{err}</div>" if err else "")
    html = f"<div class='card'><h2>Sign In</h2>{b}<form action='/login_user' method='post'><div class='input-group'><input type='email' name='email' placeholder='Email address' required></div><div class='input-group'><input type='password' name='password' placeholder='Password' required></div><button class='btn'>Sign In</button></form><a href='/forgot' class='link'>Forgot Password?</a><a href='/signup' class='link'>New here? Sign up now.</a></div>"
    return render_page("Login - Fast Finder", html)

@public_routes.post('/login_user')
async def login_user(req):
    data = await req.post()
    email, pwd = data.get('email'), data.get('password')
    user = await get_user_by_email(email)
    
    if user and user.get('web_pass') == hash_pass(pwd):
        if not await is_premium(user['id'], temp.BOT):
            return web.HTTPFound('/login?err=Active Premium Subscription Required! Message the bot to upgrade.')
            
        sid = str(uuid.uuid4())
        temp.PUBLIC_SESSIONS[sid] = {"id": user['id'], "expire": time.time() + 86400 * 7}
        res = web.HTTPFound('/dashboard')
        res.set_cookie('user_session', sid, max_age=86400 * 7)
        return res
    return web.HTTPFound('/login?err=Invalid Email or Password')

# ==========================================
# 📝 2. SIGN UP (WITH OTP VERIFICATION)
# ==========================================
@public_routes.get('/signup')
async def signup_page(req):
    err = req.query.get('err', '')
    err_box = f"<div class='err'>{err}</div>" if err else ""
    html = f"<div class='card'><h2>Sign Up</h2>{err_box}<p style='color:#808080; font-size:13px; margin-bottom:15px'>*Start the Telegram bot before signing up</p><form action='/register_user' method='post'><div class='input-group'><input type='number' name='tg_id' placeholder='Your Telegram ID (from @userinfobot)' required></div><div class='input-group'><input type='email' name='email' placeholder='Email address' required></div><div class='input-group'><input type='password' name='password' placeholder='Password' required></div><button class='btn'>Verify Telegram ID</button></form><a href='/login' class='link'>Already have an account? Sign In.</a></div>"
    return render_page("Sign Up - Fast Finder", html)

@public_routes.post('/register_user')
async def register_user(req):
    data = await req.post()
    try: tg_id = int(data.get('tg_id'))
    except: return web.HTTPFound('/signup?err=Invalid Telegram ID Format')
    
    email, pwd = data.get('email'), data.get('password')
    
    # 1. Check Email
    if await get_user_by_email(email):
        return web.HTTPFound('/signup?err=Email already registered!')
        
    # 2. Check if Telegram ID already has a web account
    existing_user = await db.users.find_one({"id": tg_id})
    if existing_user and existing_user.get("web_email"):
        return web.HTTPFound('/signup?err=This Telegram ID is already linked to another account.')

    # 3. Generate Sign Up OTP
    otp = str(random.randint(100000, 999999))
    temp.SIGNUPS[email] = {"tg_id": tg_id, "pwd": pwd, "otp": otp, "exp": time.time() + 300}
    
    try:
        await temp.BOT.send_message(tg_id, f"🔐 **Web Registration Verification**\n\nSomeone is trying to link your Telegram ID to this email: `{email}`\n\nYour OTP is: `{otp}`\n\n_Valid for 5 mins. If this wasn't you, just ignore this message._")
        return web.HTTPFound(f'/verify_signup_page?email={email}')
    except Exception:
        return web.HTTPFound('/signup?err=Failed to send OTP! Have you started the bot on Telegram?')

@public_routes.get('/verify_signup_page')
async def verify_signup_page(req):
    email = req.query.get('email', '')
    err = req.query.get('err', '')
    err_box = f"<div class='err'>{err}</div>" if err else ""
    html = f"<div class='card'><h2>Verify Ownership</h2><p style='color:#808080; margin-bottom:15px'>OTP sent to your Telegram PM to verify ID.</p>{err_box}<form action='/confirm_signup' method='post'><input type='hidden' name='email' value='{email}'><div class='input-group'><input type='text' name='otp' placeholder='6-Digit OTP' required></div><button class='btn'>Create Account</button></form></div>"
    return render_page("Verify Sign Up", html)

@public_routes.post('/confirm_signup')
async def confirm_signup(req):
    data = await req.post()
    email, otp = data.get('email'), data.get('otp')
    
    saved = temp.SIGNUPS.get(email)
    if not saved or time.time() > saved['exp'] or saved['otp'] != otp:
        return web.HTTPFound(f'/verify_signup_page?email={email}&err=Invalid or Expired OTP')
        
    # Security Passed! Create Account
    await db.users.update_one({"id": saved['tg_id']}, {"$set": {"web_email": email, "web_pass": hash_pass(saved['pwd'])}}, upsert=True)
    del temp.SIGNUPS[email]
    
    try: await temp.BOT.send_message(saved['tg_id'], "✅ **Web Account Successfully Created!**\nYou can now log in to the website.")
    except: pass
    
    return web.HTTPFound('/login?msg=Account Created Successfully! Please Sign In.')

# ==========================================
# 🔐 3. FORGOT PASSWORD (OTP VIA BOT)
# ==========================================
@public_routes.get('/forgot')
async def forgot_page(req):
    err = req.query.get('err', '')
    b = f"<div class='err'>{err}</div>" if err else ""
    html = f"<div class='card'><h2>Reset Password</h2>{b}<form action='/send_otp' method='post'><div class='input-group'><input type='email' name='email' placeholder='Enter your registered email' required></div><button class='btn'>Send OTP to Telegram</button></form><a href='/login' class='link'>Back to Sign In</a></div>"
    return render_page("Forgot Password", html)

@public_routes.post('/send_otp')
async def send_otp(req):
    email = (await req.post()).get('email')
    user = await get_user_by_email(email)
    
    if not user: return web.HTTPFound('/forgot?err=Email not found in database')
    
    otp = str(random.randint(100000, 999999))
    temp.OTPS[email] = {"otp": otp, "id": user['id'], "exp": time.time() + 300}
    
    try:
        await temp.BOT.send_message(user['id'], f"🔐 **Password Reset OTP**\n\nYour OTP is: `{otp}`\n\n_Valid for 5 minutes. Do not share it._")
        return web.HTTPFound(f'/verify_otp_page?email={email}')
    except:
        return web.HTTPFound('/forgot?err=Failed to send OTP. Have you blocked the bot?')

@public_routes.get('/verify_otp_page')
async def verify_otp_page(req):
    email = req.query.get('email', '')
    err = req.query.get('err', '')
    err_box = f"<div class='err'>{err}</div>" if err else ""
    html = f"<div class='card'><h2>Enter OTP</h2><p style='color:#808080; margin-bottom:15px'>OTP sent to your Telegram PM.</p>{err_box}<form action='/reset_password' method='post'><input type='hidden' name='email' value='{email}'><div class='input-group'><input type='text' name='otp' placeholder='6-Digit OTP' required></div><div class='input-group'><input type='password' name='new_pass' placeholder='New Password' required></div><button class='btn'>Reset Password</button></form></div>"
    return render_page("Verify OTP", html)

@public_routes.post('/reset_password')
async def reset_password(req):
    data = await req.post()
    email, otp, new_pass = data.get('email'), data.get('otp'), data.get('new_pass')
    
    saved_otp = temp.OTPS.get(email)
    if not saved_otp or time.time() > saved_otp['exp'] or saved_otp['otp'] != otp:
        return web.HTTPFound(f'/verify_otp_page?email={email}&err=Invalid or Expired OTP')
        
    await db.users.update_one({"id": saved_otp['id']}, {"$set": {"web_pass": hash_pass(new_pass)}})
    del temp.OTPS[email] 
    return web.HTTPFound('/login?msg=Password Reset Successful! Please Login.')

# ==========================================
# 🚪 4. LOGOUT ROUTE
# ==========================================
@public_routes.get('/user_logout')
async def user_logout(req):
    s = req.cookies.get('user_session')
    if s in temp.PUBLIC_SESSIONS: del temp.PUBLIC_SESSIONS[s]
    res = web.HTTPFound('/') # Redirects to main landing page (stream_routes.py)
    res.del_cookie('user_session')
    return res
