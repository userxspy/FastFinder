from info import BIN_CHANNEL, URL
from utils import temp
import urllib.parse, html as _html


# ======================================================
# 🎬 FAST FINDER — WATCH TEMPLATE
#   • Dark / Light mode toggle (localStorage)
#   • Tap left/right → ±5 sec skip
#   • Mute button only (no volume slider)
#   • Blue accent, auto badge detection
# ======================================================

WATCH_HTML = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.plyr.io/3.7.8/plyr.css">

<style>
[data-theme="dark"]{{
  --bg:#0c0c0f;--surface:#16161a;--surface2:#1e1e24;
  --border:rgba(255,255,255,0.07);--text:#eeeae0;--muted:#6b6870;
  --card:#131317;--accent:#3b82f6;--red:#ff6b4a;--shadow:rgba(0,0,0,0.6);
}}
[data-theme="light"]{{
  --bg:#f2f0ec;--surface:#ffffff;--surface2:#e8e6e2;
  --border:rgba(0,0,0,0.08);--text:#1a1814;--muted:#8a8580;
  --card:#ffffff;--accent:#2563eb;--red:#d93a1e;--shadow:rgba(0,0,0,0.1);
}}

*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html{{scroll-behavior:smooth}}
body{{
  background:var(--bg);color:var(--text);
  font-family:'DM Sans',sans-serif;
  min-height:100vh;overflow-x:hidden;
  transition:background .3s,color .3s;
}}
body::after{{
  content:'';position:fixed;inset:0;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='200' height='200' filter='url(%23n)' opacity='0.035'/%3E%3C/svg%3E");
  pointer-events:none;z-index:9999;opacity:.45;transition:opacity .3s;
}}
[data-theme="light"] body::after{{opacity:.12}}

header{{
  padding:13px 20px;display:flex;align-items:center;justify-content:space-between;
  border-bottom:1px solid var(--border);position:sticky;top:0;
  background:color-mix(in srgb,var(--bg) 85%,transparent);
  backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
  z-index:100;animation:hdrIn .4s ease;
}}
@keyframes hdrIn{{from{{transform:translateY(-100%);opacity:0}}to{{transform:translateY(0);opacity:1}}}}
.logo{{
  font-family:'Syne',sans-serif;font-weight:800;font-size:18px;
  letter-spacing:.5px;color:var(--accent);display:flex;align-items:center;gap:9px;
}}
.dot{{
  width:7px;height:7px;background:var(--red);
  border-radius:50%;box-shadow:0 0 6px var(--red);animation:blink 2s infinite;
}}
@keyframes blink{{0%,100%{{opacity:1;transform:scale(1)}}50%{{opacity:.3;transform:scale(.7)}}}}
.hdr-r{{display:flex;align-items:center;gap:8px}}
.tag-free{{
  font-size:10px;font-weight:500;padding:3px 9px;
  border:1px solid var(--border);border-radius:100px;
  color:var(--muted);letter-spacing:.4px;
}}
.theme-btn{{
  width:36px;height:36px;border-radius:9px;border:1px solid var(--border);
  background:var(--surface);color:var(--text);
  cursor:pointer;display:flex;align-items:center;justify-content:center;
  transition:background .2s,border-color .2s,transform .15s;
}}
.theme-btn:hover{{background:var(--surface2);border-color:var(--accent);transform:scale(1.06)}}
.theme-btn svg{{width:16px;height:16px}}
.i-moon{{display:block}}.i-sun{{display:none}}
[data-theme="light"] .i-moon{{display:none}}[data-theme="light"] .i-sun{{display:block}}

.page{{
  max-width:920px;margin:0 auto;padding:22px 16px 60px;
  animation:pgIn .5s ease .05s both;
}}
@keyframes pgIn{{from{{opacity:0;transform:translateY(16px)}}to{{opacity:1;transform:translateY(0)}}}}

/* PLAYER */
.player-wrap{{
  border-radius:14px;overflow:hidden;background:#000;position:relative;
  box-shadow:0 0 0 1px var(--border),0 24px 60px var(--shadow);
  transition:box-shadow .3s;
}}
video{{width:100%;display:block}}

/* TAP ZONES */
.tap-zone{{
  position:absolute;top:0;bottom:0;width:35%;z-index:10;
  cursor:pointer;-webkit-tap-highlight-color:transparent;user-select:none;
  display:flex;align-items:center;
}}
.tap-zone.left{{left:0;justify-content:flex-start;padding-left:12px}}
.tap-zone.right{{right:0;justify-content:flex-end;padding-right:12px}}
.tap-zone::before{{
  content:'';position:absolute;inset:0;
  background:rgba(255,255,255,0);transition:background .15s;
}}
.tap-zone.left::before{{border-radius:0 50% 50% 0/0 80% 80% 0}}
.tap-zone.right::before{{border-radius:50% 0 0 50%/80% 0 0 80%}}
.tap-zone.flash::before{{background:rgba(255,255,255,0.12)}}
.skip-indicator{{
  display:flex;flex-direction:column;align-items:center;gap:4px;
  opacity:0;transform:scale(0.7);
  transition:opacity .15s,transform .15s;pointer-events:none;
}}
.tap-zone.show-indicator .skip-indicator{{opacity:1;transform:scale(1)}}
.skip-arrows{{display:flex;align-items:center;gap:1px}}
.skip-arrows svg{{
  width:22px;height:22px;fill:rgba(255,255,255,0.9);
  filter:drop-shadow(0 1px 4px rgba(0,0,0,0.5));
}}
.skip-label{{
  font-family:'Syne',sans-serif;font-size:11px;font-weight:700;
  color:rgba(255,255,255,0.9);letter-spacing:.5px;
  text-shadow:0 1px 4px rgba(0,0,0,0.6);white-space:nowrap;
}}

/* PLYR */
.plyr--video .plyr__controls{{
  background:linear-gradient(transparent,rgba(0,0,0,0.8)) !important;
  padding:18px 12px 10px !important;
}}
.plyr__control--overlaid{{
  background:var(--accent) !important;color:#fff !important;
  box-shadow:0 4px 14px rgba(59,130,246,.4) !important;
}}
.plyr__control:hover,.plyr__control[aria-pressed=true]{{
  background:var(--accent) !important;color:#fff !important;
}}
.plyr--full-ui input[type=range]{{color:var(--accent) !important}}

/* FILE CARD */
.file-card{{
  margin-top:16px;background:var(--card);border:1px solid var(--border);
  border-radius:13px;padding:16px;
  display:flex;align-items:flex-start;justify-content:space-between;gap:14px;
  transition:background .3s,border-color .3s;
}}
.file-info{{flex:1;min-width:0}}
.file-title{{
  font-family:'Syne',sans-serif;font-size:17px;font-weight:700;
  line-height:1.35;color:var(--text);margin-bottom:10px;
  word-break:break-word;transition:color .3s;
}}
.badge-row{{display:flex;flex-wrap:wrap;gap:5px}}
.badge{{
  font-size:10px;font-weight:600;letter-spacing:.6px;
  text-transform:uppercase;padding:3px 8px;border-radius:5px;
}}
.b-blue{{background:rgba(59,130,246,.13);color:var(--accent);border:1px solid rgba(59,130,246,.22)}}
.b-red{{background:rgba(255,107,74,.11);color:var(--red);border:1px solid rgba(255,107,74,.2)}}
.b-dim{{background:var(--surface2);color:var(--muted);border:1px solid var(--border)}}

.dl-area{{display:flex;flex-direction:column;align-items:flex-end;gap:7px;flex-shrink:0}}
.btn-dl{{
  display:inline-flex;align-items:center;gap:7px;padding:11px 17px;
  background:var(--accent);color:#fff;
  font-family:'Syne',sans-serif;font-weight:700;font-size:13px;
  border-radius:9px;text-decoration:none;white-space:nowrap;
  transition:filter .2s,transform .15s,box-shadow .2s;
  box-shadow:0 4px 16px rgba(59,130,246,.3);
}}
.btn-dl:hover{{filter:brightness(1.12);transform:translateY(-2px);box-shadow:0 7px 22px rgba(59,130,246,.45)}}
.btn-dl:active{{transform:translateY(0);filter:brightness(.95)}}
.btn-dl svg{{width:14px;height:14px}}
.dl-size{{font-size:11px;color:var(--muted);font-style:italic}}
.btn-copy{{
  display:inline-flex;align-items:center;gap:6px;padding:7px 13px;
  background:var(--surface2);color:var(--muted);
  font-size:11px;font-weight:500;
  border-radius:7px;border:1px solid var(--border);
  cursor:pointer;white-space:nowrap;
  transition:background .2s,color .2s,border-color .2s;
}}
.btn-copy:hover{{background:var(--surface);color:var(--text);border-color:var(--accent)}}
.btn-copy svg{{width:12px;height:12px}}
.btn-copy.ok{{color:#4caf50;border-color:#4caf50}}

.notice{{
  margin-top:12px;padding:10px 14px;
  background:var(--surface);border:1px solid var(--border);
  border-radius:9px;font-size:11.5px;color:var(--muted);
  display:flex;align-items:center;gap:8px;transition:background .3s;
}}
.notice svg{{flex-shrink:0;color:var(--accent);width:14px;height:14px}}

footer{{
  margin-top:34px;padding-top:16px;border-top:1px solid var(--border);
  text-align:center;font-size:11px;color:var(--muted);line-height:1.9;
  transition:border-color .3s;
}}
footer strong{{color:var(--accent);font-family:'Syne',sans-serif}}

@media(max-width:540px){{
  .file-card{{flex-direction:column}}
  .dl-area{{flex-direction:row;align-items:center;width:100%;justify-content:space-between}}
  .file-title{{font-size:15px}}
}}
</style>
</head>

<body>

<header>
  <div class="logo"><div class="dot"></div>FAST FINDER</div>
  <div class="hdr-r">
    <span class="tag-free">NO ADS • FREE</span>
    <button class="theme-btn" id="themeToggle" title="Toggle theme">
      <svg class="i-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
        <path d="M21 12.79A9 9 0 1111.21 3a7 7 0 009.79 9.79z"/>
      </svg>
      <svg class="i-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
        <circle cx="12" cy="12" r="5"/>
        <line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/>
        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
        <line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/>
        <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
      </svg>
    </button>
  </div>
</header>

<div class="page">

  <div class="player-wrap">

    <div class="tap-zone left" id="tapLeft">
      <div class="skip-indicator">
        <div class="skip-arrows">
          <svg viewBox="0 0 24 24"><path d="M15 18l-6-6 6-6"/></svg>
          <svg viewBox="0 0 24 24"><path d="M11 18l-6-6 6-6"/></svg>
        </div>
        <div class="skip-label">5 seconds</div>
      </div>
    </div>

    <div class="tap-zone right" id="tapRight">
      <div class="skip-indicator">
        <div class="skip-arrows">
          <svg viewBox="0 0 24 24"><path d="M9 18l6-6-6-6"/></svg>
          <svg viewBox="0 0 24 24"><path d="M13 18l6-6-6-6"/></svg>
        </div>
        <div class="skip-label">5 seconds</div>
      </div>
    </div>

    <video class="plyr-player" controls playsinline src="{src}"></video>
  </div>

  <div class="file-card">
    <div class="file-info">
      <div class="file-title">{file_name}</div>
      <div class="badge-row">{badges}</div>
    </div>
    <div class="dl-area">
      <a class="btn-dl" href="{src}" download>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
          <path d="M12 3v13M5 14l7 7 7-7"/><path d="M3 21h18"/>
        </svg>
        Download
      </a>
      <span class="dl-size">{file_size}</span>
      <button class="btn-copy" id="copyBtn">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <rect x="9" y="9" width="13" height="13" rx="2"/>
          <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
        </svg>
        Copy Link
      </button>
    </div>
  </div>

  <div class="notice">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <circle cx="12" cy="12" r="10"/>
      <line x1="12" y1="8" x2="12" y2="12"/>
      <circle cx="12" cy="16" r=".8" fill="currentColor"/>
    </svg>
    Video ke left/right side tap karo — 5 sec back/forward. Link temporary hai, download kar lein.
  </div>

  <footer>
    <strong>FAST FINDER</strong> — Telegram Bot powered streaming<br>
    © 2025 Fast Finder Bot
  </footer>
</div>

<script src="https://cdn.plyr.io/3.7.8/plyr.js"></script>
<script>
/* Telegram theme sync */
(function(){{
  if(!window.Telegram||!Telegram.WebApp)return;
  const t=Telegram.WebApp.themeParams;
  if(t.bg_color){{
    const dark=parseInt(t.bg_color.replace('#',''),16)<0x888888;
    document.documentElement.setAttribute('data-theme',dark?'dark':'light');
  }}
  if(t.button_color)document.documentElement.style.setProperty('--accent',t.button_color);
}})();

/* Restore saved theme */
const saved=localStorage.getItem('ff-theme');
if(saved)document.documentElement.setAttribute('data-theme',saved);

/* Theme toggle */
document.getElementById('themeToggle').addEventListener('click',()=>{{
  const d=document.documentElement;
  const now=d.getAttribute('data-theme')==='dark'?'light':'dark';
  d.setAttribute('data-theme',now);
  localStorage.setItem('ff-theme',now);
}});

/* Copy link */
document.getElementById('copyBtn').addEventListener('click',function(){{
  navigator.clipboard.writeText(location.href).then(()=>{{
    this.innerHTML='✓ Copied!';this.classList.add('ok');
    setTimeout(()=>{{
      this.innerHTML=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>Copy Link`;
      this.classList.remove('ok');
    }},2000);
  }});
}});

/* Plyr — mute only, no volume slider */
const player=new Plyr('.plyr-player',{{
  controls:['play','mute','progress','current-time','settings','fullscreen'],
  settings:['speed'],
  ratio:'16:9',
  speed:{{selected:1,options:[0.5,0.75,1,1.25,1.5,2]}},
  keyboard:{{focused:true,global:true}},
}});

/* Tap-to-skip ±5 seconds */
(function(){{
  const SKIP=5;
  const left=document.getElementById('tapLeft');
  const right=document.getElementById('tapRight');

  function skip(zone,sec){{
    const vid=document.querySelector('.plyr-player');
    if(vid)vid.currentTime=Math.max(0,vid.currentTime+sec);
    zone.classList.add('flash');
    setTimeout(()=>zone.classList.remove('flash'),200);
    zone.classList.add('show-indicator');
    clearTimeout(zone._t);
    zone._t=setTimeout(()=>zone.classList.remove('show-indicator'),700);
  }}

  left.addEventListener('click', ()=>skip(left,-SKIP));
  right.addEventListener('click',()=>skip(right,+SKIP));
  left.addEventListener('touchend', e=>{{e.preventDefault();skip(left,-SKIP);}});
  right.addEventListener('touchend',e=>{{e.preventDefault();skip(right,+SKIP);}});
}})();
</script>

</body>
</html>
"""


# ======================================================
# 🔧 HELPERS
# ======================================================

def _format_size(size_bytes: int) -> str:
    if not size_bytes:
        return "Unknown size"
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _make_badges(file_name: str) -> str:
    name = file_name.upper()
    badges = []

    # Quality
    for q, label in [("2160P","4K UHD"),("4K","4K UHD"),("1080P","1080p"),
                     ("720P","720p"),("480P","480p"),("360P","360p")]:
        if q in name:
            badges.append((label, "blue"))
            break

    # Source
    for s, label in [("BLURAY","BluRay"),("BLU-RAY","BluRay"),("BDRIP","BDRip"),
                     ("WEBRIP","WEBRip"),("WEB-DL","WEB-DL"),
                     ("HDTV","HDTV"),("DVDRIP","DVDRip"),("CAM","CAM")]:
        if s in name:
            badges.append((label, "red"))
            break

    # Codec
    for c in ["X265","X264","HEVC","AVC","H265","H264","AV1"]:
        if c in name:
            badges.append((c.lower(), "dim"))
            break

    # Language
    for lang in ["HINDI","ENGLISH","TAMIL","TELUGU","KOREAN","JAPANESE","DUAL AUDIO","MULTI"]:
        if lang.replace(" ","") in name.replace(" ",""):
            cls = "blue" if "DUAL" in lang or "MULTI" in lang else "dim"
            badges.append((lang.title(), cls))

    if not badges:
        badges.append(("VIDEO", "dim"))

    return "".join(
        f'<span class="badge b-{cls}">{_html.escape(text)}</span>'
        for text, cls in badges
    )


# ======================================================
# 🎬 WATCH HANDLER
# ======================================================

async def media_watch(message_id: int):
    msg   = await temp.BOT.get_messages(BIN_CHANNEL, message_id)
    media = getattr(msg, msg.media.value, None)

    if not media:
        return "<h3 style='font-family:sans-serif;padding:40px;color:#f00'>File not found.</h3>"

    src       = urllib.parse.urljoin(URL, f"download/{message_id}")
    file_name = getattr(media, "file_name", None) or f"file_{message_id}"
    file_size = _format_size(getattr(media, "file_size", 0))

    return WATCH_HTML.format(
        title     = _html.escape(f"Watch – {file_name}"),
        file_name = _html.escape(file_name),
        src       = src,
        file_size = file_size,
        badges    = _make_badges(file_name),
    )
