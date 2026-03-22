import base64
import os
import re
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup

app = FastAPI()

SITE_URL = "https://ak.sv"
ADDON_ID = "community.akwam.direct"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

manifest_data = {
    "id": ADDON_ID,
    "name": "AKWAM Direct",
    "version": "2.0.0",
    "description": "افلام ومسلسلات عربية",
    "resources": ["catalog", "stream"],
    "types": ["movie", "series"],
    "catalogs": [
        {"type": "movie", "id": "ak_movies", "name": "افلام اكوام"},
        {"type": "series", "id": "ak_series", "name": "مسلسلات اكوام"}
    ],
    "behaviorHints": {"adult": False}
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "ar,en;q=0.9",
    "Referer": SITE_URL
}

async def get_html(url):
    async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
        try:
            resp = await client.get(url, headers=HEADERS)
            return resp.text
        except Exception as e:
            print(f"ERROR: {e}")
            return None

@app.get("/manifest.json")
async def manifest():
    return manifest_data

@app.get("/catalog/{media_type}/{catalog_id}.json")
async def catalog(media_type: str, catalog_id: str):
    category = "movies" if media_type == "movie" else "series"
    html = await get_html(f"{SITE_URL}/{category}")
    if not html:
        return {"metas": []}
    soup = BeautifulSoup(html, "html.parser")
    metas = []
    for item in soup.select(".entry-box, .movie-box, .col-lg-2"):
        try:
            title = item.select_one(".entry-title, h2, h3").text.strip()
            link = item.select_one("a")["href"]
            img = item.select_one("img")
            img_url = img.get("src", img.get("data-src", "")) if img else ""
            if not link.startswith("http"):
                link = SITE_URL + link
            metas.append({
                "id": base64.b64encode(link.encode()).decode(),
                "type": media_type,
                "name": title,
                "poster": img_url
            })
        except:
            continue
    return {"metas": metas}

@app.get("/stream/{media_type}/{item_id}.json")
async def stream(media_type: str, item_id: str):
    try:
        page_url = base64.b64decode(item_id).decode()
    except:
        return {"streams": []}
    html = await get_html(page_url)
    if not html:
        return {"streams": []}
    streams = []
    seen = set()
    for m in re.finditer(r"(https?://[^\s\"'\\]+\.m3u8[^\s\"'\\]*)", html):
        url = m.group(1)
        if url not in seen:
            seen.add(url)
            streams.append({"title": "HLS", "url": url})
    for m in re.finditer(r"(https?://[^\s\"'\\]+\.mp4[^\s\"'\\]*)", html):
        url = m.group(1)
        if url not in seen:
            seen.add(url)
            streams.append({"title": "MP4", "url": url})
    soup = BeautifulSoup(html, "html.parser")
    for i, iframe in enumerate(soup.find_all("iframe", src=True)[:5]):
        src = iframe["src"]
        if src.startswith("//"):
            src = "https:" + src
        if not src.startswith("http"):
            continue
        if any(x in src for x in ["google", "facebook", "ads"]):
            continue
        iframe_html = await get_html(src)
        if not iframe_html:
            continue
        for m in re.finditer(r"(https?://[^\s\"'\\]+\.m3u8[^\s\"'\\]*)", iframe_html):
            url = m.group(1)
            if url not in seen:
                seen.add(url)
                streams.append({"title": f"Server {i+1}", "url": url})
    return {"streams": streams}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
