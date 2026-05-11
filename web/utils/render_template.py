from info import BIN_CHANNEL, URL
from utils import temp
import urllib.parse, html


# ======================================================
# 🎬 CINEMATIC WATCH TEMPLATE — Fast Finder Bot
# ======================================================

WATCH_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:ital,wght@0,300;0,400;0,500;1,300&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.plyr.io/3.7.8/plyr.css">

<style>
:root {{
  --gold:    #f5c842;
  --bg:      #0a0a0a;
  --surface: #141414;
  --surface2:#1c1c1c;
  --border:  rgba(245,200,66,0.12);
  --text:    #f0ece0;
  --muted:   #7a7570;
  --red:     #e53935;
}}

*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html{{scroll-behavior:smooth}}
body{{
  background:var(--bg);
  color:var(--text);
  font-family:'DM Sans',sans-serif;
  min-height:100vh;
  overflow-x:hidden;
}}

/* Grain */
body::before{{
  content:'';
  position:fixed;
  inset:0;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='300'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='300' height='300' filter='url(%23n)' opacity='0.04'/%3E%3C/svg%3E");
  pointer-events:none;
  z-index:1000;
  opacity:0.5;
}}

/* Header */
header{{
  padding:16px 24px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  border-bottom:1px solid var(--border);
  position:sticky;top:0;
  background:rgba(10,10,10,0.92);
  backdrop-filter:blur(12px);
  z-index:100;
  animation:slideDown 0.5s ease;
}}
@keyframes slideDown{{
  from{{transform:translateY(-100%);opacity:0}}
  to  {{transform:translateY(0);opacity:1}}
}}
.logo{{
  font-family:'Syne',sans-serif;
  font-weight:800;font-size:20px;
  letter-spacing:-0.5px;
  color:var(--gold);
  display:flex;align-items:center;gap:8px;
}}
.logo-dot{{
  width:8px;height:8px;
  background:var(--red);
  border-radius:50%;
  animation:pulse 2s infinite;
}}
@keyframes pulse{{
  0%,100%{{opacity:1;transform:scale(1)}}
  50%     {{opacity:0.5;transform:scale(0.8)}}
}}
.header-badge{{
  font-size:11px;font-weight:500;
  padding:4px 10px;
  border:1px solid var(--border);
  border-radius:100px;
  color:var(--muted);
  letter-spacing:0.5px;
}}

/* Page */
.page{{
  max-width:960px;
  margin:0 auto;
  padding:28px 20px 60px;
  animation:fadeUp 0.6s ease 0.1s both;
}}
@keyframes fadeUp{{
  from{{opacity:0;transform:translateY(20px)}}
  to  {{opacity:1;transform:translateY(0)}}
}}

/* Player */
.player-wrap{{
  position:relative;
  border-radius:16px;
  overflow:hidden;
  background:#000;
  box-shadow:
    0 0 0 1px var(--border),
    0 32px 80px rgba(0,0,0,0.7),
    0 0 60px rgba(245,200,66,0.04);
}}
.player-wrap::before{{
  content:'';
  position:absolute;inset:0;
  background:linear-gradient(135deg,rgba(245,200,66,0.03) 0%,transparent 60%);
  pointer-events:none;z-index:1;
  border-radius:16px;
}}
video{{width:100%;display:block}}

/* Plyr overrides */
.plyr--video .plyr__controls{{
  background:linear-gradient(transparent,rgba(0,0,0,0.85)) !important;
}}
.plyr__control--overlaid{{background:var(--gold) !important;color:#000 !important}}
.plyr__control:hover,
.plyr__control[aria-pressed=true]{{background:var(--gold) !important;color:#000 !important}}
.plyr--full-ui input[type=range]{{color:var(--gold) !important}}

/* Meta */
.meta{{
  margin-top:22px;
  display:grid;
  grid-template-columns:1fr auto;
  gap:16px;align-items:start;
}}
.file-title{{
  font-family:'Syne',sans-serif;
  font-size:22px;font-weight:700;
  line-height:1.3;color:var(--text);
  margin-bottom:10px;letter-spacing:-0.3px;
}}
.badge-row{{display:flex;flex-wrap:wrap;gap:6px}}
.badge{{
  font-size:11px;font-weight:600;
  letter-spacing:0.8px;text-transform:uppercase;
  padding:4px 10px;border-radius:6px;
}}
.badge-gold{{
  background:rgba(245,200,66,0.12);
  color:var(--gold);
  border:1px solid rgba(245,200,66,0.2);
}}
.badge-red{{
  background:rgba(229,57,53,0.12);
  color:#ff6b6b;
  border:1px solid rgba(229,57,53,0.2);
}}
.badge-dim{{
  background:var(--surface2);
  color:var(--muted);
  border:1px solid rgba(255,255,255,0.06);
}}

/* Download */
.dl-block{{display:flex;flex-direction:column;gap:8px;min-width:170px}}
.btn-download{{
  display:flex;align-items:center;
  justify-content:center;gap:8px;
  padding:12px 20px;
  background:var(--gold);
  color:#0a0a0a;
  font-family:'Syne',sans-serif;
  font-weight:700;font-size:14px;
  border-radius:10px;text-decoration:none;
  transition:background 0.2s,transform 0.15s,box-shadow 0.2s;
  box-shadow:0 4px 20px rgba(245,200,66,0.2);
}}
.btn-download:hover{{
  background:#ffd54f;
  transform:translateY(-1px);
  box-shadow:0 6px 28px rgba(245,200,66,0.35);
}}
.btn-download:active{{transform:translateY(0)}}
.btn-download svg{{width:16px;height:16px;flex-shrink:0}}
.file-size{{text-align:center;font-size:12px;color:var(--muted);font-style:italic}}

/* Divider */
.divider{{height:1px;background:var(--border);margin:24px 0}}

/* Info Strip */
.info-strip{{display:flex;flex-wrap:wrap;gap:0}}
.info-item{{
  flex:1;min-width:120px;
  padding:14px 16px;
  border-right:1px solid var(--border);
}}
.info-item:last-child{{border-right:none}}
.info-label{{
  font-size:10px;text-transform:uppercase;
  letter-spacing:1px;color:var(--muted);margin-bottom:4px;
}}
.info-value{{
  font-family:'Syne',sans-serif;
  font-size:15px;font-weight:600;color:var(--text);
}}
.info-value.gold{{color:var(--gold)}}

/* Notice */
.notice{{
  margin-top:20px;padding:12px 16px;
  background:var(--surface);
  border:1px solid var(--border);
  border-radius:10px;
  font-size:12px;color:var(--muted);
  display:flex;align-items:center;gap:8px;
}}
.notice svg{{flex-shrink:0;color:var(--gold)}}

/* Footer */
footer{{
  margin-top:40px;padding-top:20px;
  border-top:1px solid var(--border);
  text-align:center;font-size:12px;
  color:var(--muted);line-height:1.8;
}}
footer strong{{color:var(--gold);font-family:'Syne',sans-serif}}

/* Responsive */
@media(max-width:600px){{
  .meta{{grid-template-columns:1fr}}
  .dl-block{{flex-direction:row;align-items:center}}
  .file-size{{white-space:nowrap}}
  .file-title{{font-size:18px}}
  .info-item{{min-width:100px}}
}}
</style>
</head>

<body>

<header>
  <div class="logo">
    <div class="logo-dot"></div>
    FAST FINDER
  </div>
  <div class="header-badge">NO ADS • FREE</div>
</header>

<div class="page">

  <!-- Player -->
  <div class="player-wrap">
    <video
      class="plyr-player"
      controls playsinline
      src="{src}">
    </video>
  </div>

  <!-- Meta -->
  <div class="meta">
    <div class="meta-left">
      <div class="file-title">{file_name}</div>
      <div class="badge-row">
        {badges}
      </div>
    </div>

    <div class="dl-block">
      <a class="btn-download" href="{src}" download>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
          <path d="M12 3v13M5 14l7 7 7-7"/>
          <path d="M3 21h18"/>
        </svg>
        Download
      </a>
      <div class="file-size">{file_size}</div>
    </div>
  </div>

  <div class="divider"></div>

  <!-- Info Strip -->
  <div class="info-strip">
    <div class="info-item">
      <div class="info-label">Type</div>
      <div class="info-value">{media_type}</div>
    </div>
    <div class="info-item">
      <div class="info-label">Size</div>
      <div class="info-value">{file_size}</div>
    </div>
    <div class="info-item">
      <div class="info-label">Format</div>
      <div class="info-value">{mime_type}</div>
    </div>
    <div class="info-item">
      <div class="info-label">Stream</div>
      <div class="info-value gold">Ready ✓</div>
    </div>
  </div>

  <!-- Notice -->
  <div class="notice">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <circle cx="12" cy="12" r="10"/>
      <line x1="12" y1="8" x2="12" y2="12"/>
      <circle cx="12" cy="16" r="0.5" fill="currentColor"/>
    </svg>
    Link temporary hai — expire hone se pehle download kar lein. Stream seedha browser mein chalti hai.
  </div>

  <footer>
    <strong>FAST FINDER</strong> — Telegram Bot powered streaming<br>
    © 2025 Fast Finder Bot
  </footer>

</div>

<script src="https://cdn.plyr.io/3.7.8/plyr.js"></script>
<script>
(function () {{
  if (!window.Telegram || !Telegram.WebApp) return;
  const t = Telegram.WebApp.themeParams;
  const r = document.documentElement;
  if (t.button_color) r.style.setProperty('--gold', t.button_color);
  if (t.bg_color)     r.style.setProperty('--bg',   t.bg_color);
  if (t.text_color)   r.style.setProperty('--text',  t.text_color);
}})();

new Plyr('.plyr-player', {{
  controls: ['play','progress','current-time','mute','volume','fullscreen'],
  ratio: '16:9',
  speed: {{ selected: 1, options: [0.5, 0.75, 1, 1.25, 1.5, 2] }}
}});
</script>

</body>
</html>
"""


# ======================================================
# 🔧 HELPERS
# ======================================================

def _format_size(size_bytes: int) -> str:
    """Bytes → human readable (KB / MB / GB)"""
    if not size_bytes:
        return "Unknown"
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _detect_badges(file_name: str) -> str:
    """File name se quality/language badges auto-detect karo."""
    name = file_name.upper()
    badges = []

    # Quality
    for q, cls in [("4K", "gold"), ("2160P", "gold"), ("1080P", "gold"),
                   ("720P", "dim"), ("480P", "dim"), ("360P", "dim")]:
        if q in name:
            badges.append((q.replace("2160P","4K UHD").replace("1080P","1080p")
                            .replace("720P","720p").replace("480P","480p")
                            .replace("360P","360p"), cls))
            break

    # Source
    for s, cls in [("BLURAY","red"),("BLU-RAY","red"),("BDRIP","red"),
                   ("WEBRIP","dim"),("WEB-DL","dim"),("HDTV","dim"),
                   ("DVDRIP","dim"),("CAM","dim")]:
        if s in name:
            badges.append((s.replace("BLURAY","BluRay").replace("BLU-RAY","BluRay")
                            .replace("BDRIP","BDRip").replace("WEBRIP","WEBRip")
                            .replace("WEB-DL","WEB-DL").replace("HDTV","HDTV")
                            .replace("DVDRIP","DVDRip"), cls))
            break

    # Codec
    for c in ["X265","X264","HEVC","AVC","H265","H264","AV1"]:
        if c in name:
            badges.append((c.lower(), "dim"))
            break

    # Language (simple detection)
    for lang in [("HINDI","dim"),("ENGLISH","dim"),("TAMIL","dim"),
                 ("TELUGU","dim"),("KOREAN","dim"),("DUAL AUDIO","gold")]:
        if lang[0].replace(" ","") in name.replace(" ",""):
            badges.append((lang[0].title(), lang[1]))

    badge_html = ""
    for text, cls in badges:
        badge_html += f'<span class="badge badge-{cls}">{html.escape(text)}</span>\n'

    return badge_html or '<span class="badge badge-dim">VIDEO</span>'


# ======================================================
# 🎬 WATCH HANDLER
# ======================================================

async def media_watch(message_id: int):
    msg = await temp.BOT.get_messages(BIN_CHANNEL, message_id)
    media = getattr(msg, msg.media.value, None)

    if not media:
        return "<h3 style='font-family:sans-serif;padding:40px;color:#f00'>File not found.</h3>"

    src        = urllib.parse.urljoin(URL, f"download/{message_id}")
    file_name  = getattr(media, "file_name", None) or f"file_{message_id}"
    file_size  = _format_size(getattr(media, "file_size", 0))
    mime       = getattr(media, "mime_type", "video/mp4").split("/")[-1].upper()
    media_type = type(media).__name__.replace("Video","Video").replace("Document","File")

    badges = _detect_badges(file_name)

    return WATCH_HTML.format(
        title      = html.escape(f"Watch – {file_name}"),
        file_name  = html.escape(file_name),
        src        = src,
        file_size  = file_size,
        mime_type  = mime,
        media_type = media_type,
        badges     = badges,
    )
