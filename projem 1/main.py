from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
import httpx
import os

app = FastAPI()

# --- API ŞİFRELERİ VE HOSTLARI ---
# TikTok İçin: (Render'daki Environment Variables'dan çeker)
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY") 
HOST_SCRAPER7 = "tiktok-scraper7.p.rapidapi.com" 
HOST_API23 = "tiktok-api23.p.rapidapi.com"

# Instagram İçin: (Senin bulduğun yeni API)
INSTA_HOST = "instagram120.p.rapidapi.com"
INSTA_KEY = "c3fc1d6f5fmsh00a84fec84ec710p15095djsn820438b65da3"


# --- 1. KISIM: ARAYÜZ VE DOSYA İZİNLERİ ---
@app.get("/", response_class=HTMLResponse)
async def ana_sayfa():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/ads.txt")
async def ads_txt():
    return FileResponse("ads.txt")

@app.get("/favicon.svg")
async def favicon():
    return FileResponse("favicon.svg")


# --- 2. KISIM: TIKTOK ARAÇLARI ---

# ARAÇ 1: HİKAYE VE PROFİL KARTI
@app.get("/api/hikayeler/{kullanici_adi}")
async def hikayeleri_getir(kullanici_adi: str):
    if kullanici_adi.startswith("@"):
        kullanici_adi = kullanici_adi[1:]

    async with httpx.AsyncClient(timeout=15.0) as client:
        url_profil = f"https://{HOST_API23}/api/user/info"
        headers_23 = {"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": HOST_API23}
        response_profil = await client.get(url_profil, headers=headers_23, params={"uniqueId": kullanici_adi})
        profil_verisi = response_profil.json() if response_profil.status_code == 200 else {}

        headers_7 = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": HOST_SCRAPER7}
        response_info = await client.get(f"https://{HOST_SCRAPER7}/user/info", headers=headers_7, params={"unique_id": kullanici_adi})
        
        if response_info.status_code != 200:
            raise HTTPException(status_code=400, detail="Kullanıcı bulunamadı.")
            
        try:
            kullanici_numarasi = response_info.json()["data"]["user"]["id"]
        except KeyError:
            raise HTTPException(status_code=404, detail="Hesap gizli veya veri yok.")

        response_stories = await client.get(f"https://{HOST_SCRAPER7}/user/story", headers=headers_7, params={"user_id": kullanici_numarasi})
        hikaye_verisi = response_stories.json() if response_stories.status_code == 200 else {}

        return {"aranan_kisi": kullanici_adi, "profil": profil_verisi, "hikayeler": hikaye_verisi}

# ARAÇ 2: VİDEO İNDİRİCİ
@app.get("/api/video/")
async def video_getir(url: str):
    api_url = f"https://{HOST_API23}/api/download/video"
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": HOST_API23
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(api_url, headers=headers, params={"url": url})
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Video bulunamadı veya bağlantı hatalı.")
        return response.json()

# ARAÇ 3: PROFİL RESMİ (PP) BÜYÜTÜCÜ
@app.get("/api/profil/{kullanici_adi}")
async def profil_getir(kullanici_adi: str):
    if kullanici_adi.startswith("@"):
        kullanici_adi = kullanici_adi[1:]
        
    api_url = f"https://{HOST_API23}/api/user/info"
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": HOST_API23
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(api_url, headers=headers, params={"uniqueId": kullanici_adi})
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Kullanıcı bulunamadı.")
        return response.json()


# --- 3. KISIM: INSTAGRAM ARAÇLARI (YENİ EKLENEN) ---

@app.get("/api/insta/{arac_tipi}/{kullanici_adi}")
async def insta_getir(arac_tipi: str, kullanici_adi: str):
    if kullanici_adi.startswith("@"):
        kullanici_adi = kullanici_adi[1:]

    endpoint = ""
    if arac_tipi == "hikaye":
        endpoint = "/api/instagram/stories"
    elif arac_tipi == "post":
        endpoint = "/api/instagram/posts"
    elif arac_tipi == "highlight":
        endpoint = "/api/instagram/highlights"
    elif arac_tipi == "profil":
        endpoint = "/api/instagram/profile"
    else:
        raise HTTPException(status_code=400, detail="Geçersiz araç türü.")

    url = f"https://{INSTA_HOST}{endpoint}"
    
    headers = {
        "x-rapidapi-key": INSTA_KEY,
        "x-rapidapi-host": INSTA_HOST,
        "Content-Type": "application/json"
    }
    
    # Instagram API'si verileri JSON formatında POST olarak istiyor
    payload = {"username": kullanici_adi}

    # Asenkron (hızlı) istek atıyoruz
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Instagram verisi çekilemedi veya hesap gizli.")
            
        return response.json()
