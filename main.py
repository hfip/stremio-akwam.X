import base64
import os
import re
import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup

app = FastAPI()

SITE_URL = “https://ak.sv”
ADDON_ID = “community.akwam.direct”

app.add_middleware(
CORSMiddleware,
allow_origins=[”*”],
allow_methods=[”*”],
allow_headers=[”*”],
)

manifest_data = {
“id”: ADDON_ID,
“name”: “AKWAM Direct”,
“version”: “2.0.0”,
“description”: “إضافة أكوام - أفلام ومسلسلات عربية”,
“resources”: [“catalog”, “stream”],
“types”: [“movie”, “series”],
“catalogs”: [
{“type”: “movie”, “id”: “ak_movies”, “name”: “أفلام أكوام”},
{“type”: “series”, “id”: “ak_series”, “name”: “مسلسلات أكوام”}
],
“behaviorHints”: {“adult”: False}
}

HEADERS = {
“User-Agent”: “Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36”,
“Accept-Language”: “ar,en;q=0.9”,
“Accept”: “text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8”,
“Referer”: SITE_URL
}

async def get_html(url: str) -> str | None:
async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
try:
resp = await client.get(url, headers=HEADERS)
resp.raise_for_status()
return resp.text
except Exception as e:
print(f”[ERROR] get_html({url}): {e}”)
return None

async def resolve_iframe(iframe_url: str) -> list[dict]:
“”“ادخل على الـ iframe واستخرج الروابط منه”””
streams = []
html = await get_html(iframe_url)
if not html:
return streams

```
# m3u8
for m in re.finditer(r'(https?://[^\s"\'\\]+\.m3u8[^\s"\'\\]*)', html):
    url = m.group(1)
    if url not in [s["url"] for s in streams]:
        streams.append({"title": "🎬 HLS", "url": url, "behaviorHints": {"notWebReady": False}})

# mp4
for m in re.finditer(r'(https?://[^\s"\'\\]+\.mp4[^\s"\'\\]*)', html):
    url = m.group(1)
    if url not in [s["url"] for s in streams]:
        streams.append({"title": "🎬 MP4", "url": url})

# file: أو source: في JavaScript
for m in re.finditer(r'(?:file|src|source)\s*:\s*["\']+(https?://[^\s"\']+)["\']', html):
    url = m.group(1)
    if url not in [s["url"] for s in streams] and ("m3u8" in url or "mp4" in url):
        streams.append({"title": "🎬 Direct", "url": url})

return streams
```

async def extract_streams(page_url: str) -> list[dict]:
“”“استخرج روابط البث من صفحة الفيلم أو الحلقة”””
html = await get_html(page_url)
if not html:
return []

```
streams = []
seen_urls = set()

# ── 1: روابط m3u8 مباشرة ──
for m in re.finditer(r'(https?://[^\s"\'\\]+\.m3u8[^\s"\'\\]*)', html):
    url = m.group(1)
    if url not in seen_urls:
        seen_urls.add(url)
        streams.append({"title": "🎬 HLS", "url": url})

# ── 2: روابط mp4 مباشرة ──
for m in re.finditer(r'(https?://[^\s"\'\\]+\.mp4[^\s"\'\\]*)', html):
    url = m.group(1)
    if url not in seen_urls:
        seen_urls.add(url)
        streams.append({"title": "🎬 MP4", "url": url})

# ── 3: iframes ──
soup = BeautifulSoup(html, "html.parser")
iframes = soup.find_all("iframe", src=True)
for i, iframe in enumerate(iframes[:5]):  # أول 5 iframes فقط
    src = iframe["src"]
    if src.startswith("//"):
        src = "https:" + src
    if not src.startswith("http"):
        continue
    # تجاهل Google وFacebook
    if any(x in src for x in ["google", "facebook", "twitter", "youtube", "ads"]):
        continue

    iframe_streams = await resolve_iframe(src)
    for s in iframe_streams:
        if s["url"] not in seen_urls:
            seen_urls.add(s["url"])
            s["title"] = f"🎬 سيرفر {i+1}"
            streams.append(s)

# ── 4: data-src أو data-link ──
for tag in soup.find_all(attrs={"data-src": True}):
    url = tag["data-src"]
    if url not in seen_urls and url.startswith("http"):
        seen_urls.add(url)
        streams.append({"title": "🎬 Stream", "url": url})

return streams
```

async def search_akwam(title: str, media_type: str) -> str | None:
“”“ابحث عن الفيلم أو المسلسل في أكوام”””
search_url = f”{SITE_URL}/search?q={httpx.URL(’’, params={‘q’: title}).params}”
html = await get_html(f”{SITE_URL}/search?q={title.replace(’ ’, ‘+’)}”)
if not html:
return None

```
soup = BeautifulSoup(html, "html.parser")

# ابحث عن أول نتيجة مطابقة
for a in soup.find_all("a", href=True):
    href = a["href"]
    if media_type == "movie" and "/movie/" in href:
        return href if href.startswith("http") else SITE_URL + href
    if media_type == "series" and "/series/" in href:
        return href if href.startswith("http") else SITE_URL + href

return None
```

@app.get(”/manifest.json”)
async def manifest():
return manifest_data

@app.get(”/catalog/{media_type}/{catalog_id}.json”)
async def catalog(media_type: str, catalog_id: str):
category = “movies” if media_type == “movie” else “series”
html = await get_html(f”{SITE_URL}/{category}”)
if not html:
return {“metas”: []}

```
soup = BeautifulSoup(html, "html.parser")
metas = []

for item in soup.select(".entry-box, .movie-box, .item"):
    try:
        title_el = item.select_one(".entry-title, .movie-title, h3, h2")
        link_el = item.select_one("a[href]")
        img_el = item.select_one("img")

        if not title_el or not link_el:
            continue

        title = title_el.text.strip()
        link = link_el["href"]
        if not link.startswith("http"):
            link = SITE_URL + link

        img = ""
        if img_el:
            img = img_el.get("src", img_el.get("data-src", ""))
            if img and not img.startswith("http"):
                img = SITE_URL + img

        item_id = base64.b64encode(link.encode()).decode()
        metas.append({
            "id": item_id,
            "type": media_type,
            "name": title,
            "poster": img
        })
    except Exception as e:
        print(f"[CATALOG ERROR] {e}")
        continue

return {"metas": metas}
```

@app.get(”/stream/{media_type}/{item_id}.json”)
async def stream(media_type: str, item_id: str):
try:
page_url = base64.b64decode(item_id).decode()
except Exception:
return {“streams”: []}

```
print(f"[STREAM] Fetching: {page_url}")
streams = await extract_streams(page_url)

if not streams:
    print(f"[STREAM] No streams found for: {page_url}")

return {"streams": streams}
```

if **name** == “**main**”:
import uvicorn
port = int(os.environ.get(“PORT”, 8000))
uvicorn.run(app, host=“0.0.0.0”, port=port)
