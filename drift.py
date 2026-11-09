"""
Social Media Downloader API (modified)
Developer / Owner : S Kanhaiya (@S_kanhaiya)

Endpoints
  /            -> health + endpoint list
  /facebook    -> Facebook video (HD/SD)
  /instagram   -> Instagram reel/post/story/profile   (/Instagram also works)
  /snap        -> Snapchat video/image
  /pinterest   -> Pinterest video/photo               (/Pinterest also works)
  /youtube     -> YouTube video formats (yt-dlp)
  /audio       -> YouTube/other audio-only links (yt-dlp)          [NEW]
  /universal   -> TikTok, Twitter/X, Reddit, Vimeo ... (yt-dlp)    [NEW]

Env variables (all optional)
  API_KEYS        comma separated keys. If set, every endpoint except "/" needs
                  ?key=KEY  or header  X-API-Key: KEY
  RATE_LIMIT      requests per minute per client (default 30, 0 = off)
  ALLOWED_ORIGIN  CORS origin (default "*")
  DEV_NAME / DEV_HANDLE / DEV_LINK   credit shown in every response
  PORT            local port (default 5310)
"""
import os
import re
import time
import socket
import random
import ipaddress
from functools import wraps
from threading import Lock
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify

# ----------------------------------------------------------------------------
# Config / branding
# ----------------------------------------------------------------------------
DEV_NAME = os.getenv("DEV_NAME", "S Kanhaiya")
DEV_HANDLE = os.getenv("DEV_HANDLE", "@S_kanhaiya")
DEV_LINK = os.getenv("DEV_LINK", "t.me/S_kanhaiya")

API_KEYS = {k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()}
RATE_LIMIT = int(os.getenv("RATE_LIMIT", "30"))
ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "*")

app = Flask(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
]


def ua():
    return random.choice(USER_AGENTS)


# ----------------------------------------------------------------------------
# Helpers: response, validation, auth, rate limit, CORS
# ----------------------------------------------------------------------------
def credit(payload):
    """Attach developer credit to a dict (or each dict of a list)."""
    if isinstance(payload, list):
        return [credit(p) for p in payload]
    payload = dict(payload)
    payload["Developer"] = DEV_LINK
    payload["Owner"] = DEV_HANDLE
    return payload


def ok(**kw):
    return {"status": "success", **kw}


def err(msg):
    return {"status": "error", "message": msg}


PLATFORM_HOSTS = {
    "facebook": ("facebook.com", "fb.watch", "fb.com"),
    "instagram": ("instagram.com", "instagr.am"),
    "snapchat": ("snapchat.com",),
    "pinterest": ("pinterest.com", "pin.it", "pinterest.co.uk", "pinterest.ca"),
    "youtube": ("youtube.com", "youtu.be", "music.youtube.com"),
}


def host_matches(host, domains):
    host = (host or "").lower().split(":")[0]
    return any(host == d or host.endswith("." + d) for d in domains)


def is_public_host(host):
    """Reject localhost / private / link-local targets (SSRF protection)."""
    try:
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local
                    or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
                return False
        return True
    except Exception:
        return False


def validate_url(url, platform=None):
    """Return (clean_url, error_message)."""
    url = (url or "").strip()
    if not url:
        return None, "Missing 'video' parameter (pass the link as ?video=URL)"
    if len(url) > 2000:
        return None, "URL too long"
    if not re.match(r"^https?://", url, re.I):
        return None, "URL must start with http:// or https://"
    host = urlparse(url).hostname
    if not host:
        return None, "Invalid URL"
    if platform and not host_matches(host, PLATFORM_HOSTS[platform]):
        return None, f"This endpoint only accepts {platform} links"
    if platform is None and not is_public_host(host):
        return None, "This host is not allowed"
    return url, None


_hits = {}
_lock = Lock()


def rate_limited(client_id):
    if RATE_LIMIT <= 0:
        return False
    now = time.time()
    with _lock:
        stamps = [t for t in _hits.get(client_id, []) if now - t < 60]
        if len(stamps) >= RATE_LIMIT:
            _hits[client_id] = stamps
            return True
        stamps.append(now)
        _hits[client_id] = stamps
        # keep memory bounded
        if len(_hits) > 5000:
            for k in list(_hits)[:1000]:
                _hits.pop(k, None)
    return False


def client_ip():
    fwd = request.headers.get("X-Forwarded-For", "")
    return fwd.split(",")[0].strip() if fwd else (request.remote_addr or "unknown")


def endpoint(platform=None):
    """Decorator: auth + rate limit + URL validation + credit + safe errors."""
    def deco(fn):
        @wraps(fn)
        def wrapper():
            key = request.values.get("key") or request.headers.get("X-API-Key", "")
            if API_KEYS and key not in API_KEYS:
                return jsonify(credit(err("Invalid or missing API key"))), 401
            if rate_limited(key or client_ip()):
                return jsonify(credit(err("Too many requests, slow down"))), 429
            url, problem = validate_url(request.values.get("video"), platform)
            if problem:
                return jsonify(credit(err(problem))), 400
            try:
                result = fn(url)
            except requests.Timeout:
                result = err("The upstream service timed out, try again")
            except requests.RequestException as e:
                result = err(f"Upstream request failed: {type(e).__name__}")
            except Exception as e:  # last resort, never leak a traceback
                result = err(f"Unexpected error: {type(e).__name__}: {e}")
            code = 200
            if isinstance(result, dict) and result.get("status") == "error":
                code = 502
            return jsonify(credit(result)), code
        return wrapper
    return deco


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


# ----------------------------------------------------------------------------
# Platform scrapers
# ----------------------------------------------------------------------------
def get_fb_video(url):
    headers = {
        "User-Agent": ua(),
        "Origin": "https://fbdown.blog",
        "Referer": "https://fbdown.blog/",
    }
    r = requests.post("https://fbdown.blog/get.php", headers=headers,
                      data={"url": url}, timeout=15)
    try:
        data = r.json()["data"]
    except Exception:
        return err("Facebook video not found")

    duration_sec = data.get("duration", 0) or 0
    hd = sd = "Not available"
    for m in data.get("medias", []):
        if m.get("quality") == "HD":
            hd = m["url"]
        elif m.get("quality") == "SD" and sd == "Not available":
            sd = m["url"]
    return ok(video={
        "title": data.get("title", "Unknown Title"),
        "author": data.get("author", "Unknown Author"),
        "duration": f"{int(duration_sec // 60):02d}:{int(duration_sec % 60):02d}",
        "thumbnail": data.get("thumbnail", ""),
        "hd": hd,
        "sd": sd,
    })


def download_insta_reel(url):
    session = requests.Session()
    agent = ua()
    page_url = "https://snapdownloader.com/tools/instagram-reels-downloader/download"
    r_get = session.get(page_url, headers={
        "User-Agent": agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }, timeout=20)
    if r_get.status_code != 200:
        return err(f"Initial page fetch failed: {r_get.status_code}")

    soup = BeautifulSoup(r_get.text, "html.parser")
    csrf_meta = soup.find("meta", attrs={"name": "csrf-token"})
    if not csrf_meta:
        return err("CSRF token not found")
    api_meta = soup.find("meta", attrs={"name": "api-fetch-url"})
    api_url = api_meta.get("content") if api_meta else "https://grabgram.io/api/fetch/instagram"

    m = re.search(r"instagram\.com/([^/?#]+)", url)
    tool = "reels"
    if m and m.group(1) not in ("p", "reel", "reels", "stories", "tv", "developer", "about", "explore"):
        tool = "profile"

    r_post = session.post(api_url, headers={
        "User-Agent": agent,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-CSRF-TOKEN": csrf_meta.get("content"),
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://grabgram.io",
        "Referer": "https://grabgram.io/en/instagram-reels-downloader",
    }, json={"url": url, "tool": tool}, timeout=20)

    if r_post.status_code != 200:
        try:
            return err(r_post.json().get("error", "API request failed"))
        except Exception:
            return err(f"API request failed with code {r_post.status_code}")

    res = r_post.json()
    if not res.get("ok"):
        return err(res.get("error", "Failed to fetch media"))

    data = res.get("data", {}) or {}
    items = data.get("items", [])
    if not items:
        return err("No media found in API response")

    caption = data.get("caption")
    user = data.get("user", {}) or {}
    username = user.get("username", "Unknown")
    full_name = user.get("full_name", "Unknown")

    results = []
    for idx, item in enumerate(items):
        downloads = item.get("downloads", [])
        if not downloads:
            continue
        best = downloads[0]
        results.append({
            "Download Link": best.get("url"),
            "Quality": best.get("label") or best.get("ext") or "Original",
            "Title": caption or f"Instagram {item.get('kind', 'media')} #{idx + 1} by {username} ({full_name})",
        })
    if not results:
        return err("No download links found")
    return results[0] if len(results) == 1 else results


def download_snapchat(url):
    headers = {
        "authority": "www.expertstool.com",
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "content-type": "application/x-www-form-urlencoded",
        "origin": "https://www.expertstool.com",
        "referer": "https://www.expertstool.com/snapchat-video-downloader/",
        "user-agent": ua(),
    }
    html = requests.post("https://www.expertstool.com/converter.php",
                         headers=headers, data={"url": url}, timeout=20).text

    def clean(link):
        if not link:
            return None
        link = link.replace("\\u0026", "&").replace("&quot;", "").strip()
        return link.split(",mediaPreviewUrl:")[0].rstrip("&")

    videos = [c for c in (clean(v) for v in re.findall(r'<source[^>]+src="(https?://[^"]+)"', html)) if c]
    images = [c for c in (clean(i[1]) for i in re.findall(r'(poster|src)="(https?://[^"]+)"', html)) if c]
    images = list(dict.fromkeys(images))  # de-duplicate, keep order
    if not videos and not images:
        return err("Invalid Snapchat URL")
    return ok(video=videos[0] if videos else None, image=images[0] if images else None)


def get_pinterest_download_links(url):
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "origin": "https://www.expertstool.com",
        "referer": "https://www.expertstool.com/pinterest-video-download/",
        "user-agent": ua(),
    }
    html = requests.post("https://www.expertstool.com/pinterest-video-download/",
                         headers=headers, data={"url": url}, timeout=20).text
    if "API Not Work" in html or "Invalid" in html:
        return err("Invalid Pinterest URL")

    soup = BeautifulSoup(html, "html.parser")
    for btn in soup.find_all("a", class_=re.compile(r"btn.*primary")):
        href = btn.get("href", "")
        if href.startswith("https://v") and ".mp4" in href:
            return ok(video=href)
    for img in soup.find_all("a", href=re.compile(r"pinimg\.com.*originals")):
        return ok(photo=img["href"])
    return err("No media found")


# ----------------------------------------------------------------------------
# yt-dlp based: YouTube, audio, universal
# ----------------------------------------------------------------------------
def _extract(url):
    import yt_dlp  # imported lazily so the app still starts if it is missing
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": 20,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def _meta(info):
    return {
        "title": info.get("title", "Unknown Title"),
        "author": info.get("uploader", "Unknown"),
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
    }


def _video_formats(info):
    out, seen = [], set()
    for f in info.get("formats", []):
        u = f.get("url")
        if not u or u in seen or f.get("vcodec") == "none":
            continue
        seen.add(u)
        out.append({
            "quality": f.get("format_note") or f.get("resolution") or "Original",
            "ext": f.get("ext") or "mp4",
            "has_audio": f.get("acodec") not in (None, "none"),
            "url": u,
        })
    return out


def _audio_formats(info):
    out, seen = [], set()
    for f in info.get("formats", []):
        u = f.get("url")
        if not u or u in seen:
            continue
        if f.get("vcodec") not in (None, "none") or f.get("acodec") in (None, "none"):
            continue
        seen.add(u)
        out.append({
            "bitrate_kbps": round(f["abr"]) if f.get("abr") else None,
            "ext": f.get("ext") or "m4a",
            "url": u,
        })
    out.sort(key=lambda x: x["bitrate_kbps"] or 0, reverse=True)
    return out


def download_youtube(url):
    info = _extract(url)
    return ok(**_meta(info), video=_video_formats(info))


def download_audio(url):
    info = _extract(url)
    audio = _audio_formats(info)
    if not audio:
        return err("No audio-only stream found")
    return ok(**_meta(info), audio=audio)


def download_universal(url):
    """TikTok, Twitter/X, Reddit, Vimeo, Dailymotion ... anything yt-dlp supports."""
    info = _extract(url)
    videos = _video_formats(info)
    if not videos and info.get("url"):
        videos = [{"quality": "Original", "ext": info.get("ext", "mp4"),
                   "has_audio": True, "url": info["url"]}]
    if not videos:
        return err("No downloadable media found")
    return ok(**_meta(info), platform=info.get("extractor_key"), video=videos)


# ----------------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    return jsonify(credit({
        "status": "running",
        "Developer Name": DEV_NAME,
        "auth_required": bool(API_KEYS),
        "Endpoints": {
            "Facebook": "/facebook?video=URL",
            "Instagram": "/instagram?video=URL",
            "Pinterest": "/pinterest?video=URL",
            "Snapchat": "/snap?video=URL",
            "YouTube": "/youtube?video=URL",
            "Audio": "/audio?video=URL",
            "Universal (TikTok, Twitter/X, Reddit...)": "/universal?video=URL",
        },
    }))


def route(rule, platform, fn):
    # register both original and lowercase paths, so /Instagram and /instagram work
    for r in {rule, rule.lower()}:
        app.add_url_rule(r, endpoint=f"{fn.__name__}_{r}", methods=["GET", "POST"],
                         view_func=endpoint(platform)(fn))


route("/facebook", "facebook", get_fb_video)
route("/Instagram", "instagram", download_insta_reel)
route("/snap", "snapchat", download_snapchat)
route("/Pinterest", "pinterest", get_pinterest_download_links)
route("/youtube", "youtube", download_youtube)
route("/audio", None, download_audio)
route("/universal", None, download_universal)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5310")))
