import base64
import os
import re
import httpx
from fastapi import FastAPI, Request, Path, Query
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup

app = FastAPI()

# إعدادات بسيطة
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
    "version": "1.0.0",
    "description": "إضافة أكوام المباشرة - تعمل بدون تعقيدات",
    "resources": ["catalog", "stream"],
    "types": ["movie", "series"],
    "catalogs": [
        {"type": "movie", "id": "ak_movies", "name": "أفلام أكوام"},
        {"type": "series", "id": "ak_series", "name": "مسلسلات أكوام"}
    ]
}

async def get_html(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': SITE_URL
    }
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            resp = await client.get(url, headers=headers, timeout=10.0)
            return resp.text
        except:
            return None

@app.get("/manifest.json")
async def manifest():
    return manifest_data

@app.get("/catalog/{type}/{id}.json")
async def catalog(type: str):
    category = "movies" if type == "movie" else "series"
    html = await get_html(f"{SITE_URL}/{category}")
    if not html: return {"metas": []}
    
    soup = BeautifulSoup(html, 'html.parser')
    metas = []
    for item in soup.select(".entry-box"):
        title = item.select_one(".entry-title").text.strip()
        link = item.select_one("a.box")['href']
        img = item.select_one("img")['src']
        
        metas.append({
            "id": base64.b64encode(link.encode()).decode(),
            "type": type,
            "name": title,
            "poster": img if img.startswith('http') else f"{SITE_URL}{img}"
        })
    return {"metas": metas}

@app.get("/stream/{type}/{id}.json")
async def stream(id: str):
    url = base64.b64decode(id).decode()
    html = await get_html(url)
    if not html: return {"streams": []}
    
    # البحث عن روابط mp4
    links = re.findall(r'https?://[^\s"\']+\.mp4', html)
    streams = [{"title": f"Server {i+1}", "url": link} for i, link in enumerate(set(links))]
    return {"streams": streams}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
