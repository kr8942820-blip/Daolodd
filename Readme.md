# 📥 Social Media Downloader API

Flask-based API that returns direct media links for Facebook, Instagram, Snapchat, Pinterest, YouTube, and (via yt-dlp) TikTok, Twitter/X, Reddit, Vimeo and more.

Developer: **S Kanhaiya** — [@S_kanhaiya](https://t.me/S_kanhaiya)

## Endpoints

All endpoints take the link in the `video` parameter (query string or form-data; JSON body is not supported). Both `GET` and `POST` work.

| Endpoint | Description |
|----------|-------------|
| `/` | Health check + endpoint list (no API key needed) |
| `/facebook?video=URL` | Facebook video (HD / SD) |
| `/instagram?video=URL` | Reel / Post / Story / Profile (`/Instagram` also works) |
| `/snap?video=URL` | Snapchat video / image |
| `/pinterest?video=URL` | Pinterest video / photo (`/Pinterest` also works) |
| `/youtube?video=URL` | YouTube video formats |
| `/audio?video=URL` | Audio-only streams (sorted by bitrate) — **new** |
| `/universal?video=URL` | TikTok, Twitter/X, Reddit, Vimeo… (anything yt-dlp supports) — **new** |

### Example

```
GET /youtube?video=https://youtu.be/xxxx&key=MYKEY
```

```json
{
  "status": "success",
  "title": "...",
  "author": "...",
  "duration": 213,
  "thumbnail": "https://...",
  "video": [{"quality": "720p", "ext": "mp4", "has_audio": true, "url": "https://..."}],
  "Developer": "t.me/S_kanhaiya",
  "Owner": "@S_kanhaiya"
}
```

Errors always look like `{"status": "error", "message": "..."}` with HTTP 400 (bad input), 401 (bad key), 429 (rate limit) or 502 (upstream failed).

## Security options (environment variables)

| Variable | Meaning | Default |
|----------|---------|---------|
| `API_KEYS` | Comma-separated keys. If set, pass `?key=KEY` or header `X-API-Key` | off (open) |
| `RATE_LIMIT` | Requests per minute per key/IP (`0` = off) | `30` |
| `ALLOWED_ORIGIN` | CORS origin | `*` |
| `DEV_NAME`, `DEV_HANDLE`, `DEV_LINK` | Credit shown in every response | S Kanhaiya / @S_kanhaiya / t.me/S_kanhaiya |
| `PORT` | Local port | `5310` |

Note: on Vercel the rate limiter is per server instance, so it is only approximate.
`/universal` and `/audio` refuse localhost / private-network URLs.

## Run locally

```bash
pip install -r requirements.txt
API_KEYS=mysecret python drift.py
# http://127.0.0.1:5310/
```

## Deploy on Vercel

```bash
npm install -g vercel
vercel
```
Set `API_KEYS` etc. in Project → Settings → Environment Variables.

## Notes

- Facebook, Instagram, Snapchat and Pinterest depend on third-party sites (fbdown.blog, grabgram.io, expertstool.com). If they change or block you, those endpoints stop working.
- yt-dlp based endpoints (YouTube, audio, universal) are often blocked from datacenter IPs such as Vercel. They work best on your own server/VPS/Termux.
- Respect each platform's terms of service and copyright.
