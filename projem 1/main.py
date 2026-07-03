from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
import httpx
import os

app = FastAPI()

# RapidAPI Şifren
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY") 

# İki Farklı Host Kullanıyoruz
HOST_SCRAPER7 = "tiktok-scraper7.p.rapidapi.com" 
HOST_API23 = "tiktok-api23.p.rapidapi.com"

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


# --- 2. KISIM: ARAÇLAR (API BAĞLANTILARI) ---

# ARAÇ 1: HİKAYE VE PROFİL KARTI (Birleşik)
@app.get("/api/hikayeler/{kullanici_adi}")
async def hikayeleri_getir(kullanici_adi: str):
    if kullanici_adi.startswith("@"):
        kullanici_adi = kullanici_adi[1:]

    async with httpx.AsyncClient(timeout=15.0) as client:
        # A. Profil Bilgisini Çek
        url_profil = f"https://{HOST_API23}/api/user/info"
        headers_23 = {"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": HOST_API23}
        response_profil = await client.get(url_profil, headers=headers_23, params={"uniqueId": kullanici_adi})
        profil_verisi = response_profil.json() if response_profil.status_code == 200 else {}

        # B. Hikaye Verisi İçin ID Bul
        headers_7 = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": HOST_SCRAPER7}
        response_info = await client.get(f"https://{HOST_SCRAPER7}/user/info", headers=headers_7, params={"unique_id": kullanici_adi})
        
        if response_info.status_code != 200:
            raise HTTPException(status_code=400, detail="Kullanıcı bulunamadı.")
            
        try:
            kullanici_numarasi = response_info.json()["data"]["user"]["id"]
        except KeyError:
            raise HTTPException(status_code=404, detail="Hesap gizli veya veri yok.")

        # C. Hikayeleri Çek
        response_stories = await client.get(f"https://{HOST_SCRAPER7}/user/story", headers=headers_7, params={"user_id": kullanici_numarasi})
        hikaye_verisi = response_stories.json() if response_stories.status_code == 200 else {}

        return {"aranan_kisi": kullanici_adi, "profil": profil_verisi, "hikayeler": hikaye_verisi}

# ARAÇ 2: VİDEO İNDİRİCİ (Senin Bulduğun API)
@app.get("/api/video/")
async def video_getir(url: str):
    api_url = f"https://{HOST_API23}/api/download/video"
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": HOST_API23
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        # url parametresini doğrudan iletiyoruz, httpx şifreleme (encode) işini kendi yapıyor
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
import http.client
import json
from flask import Flask, jsonify # (Framework'üne göre uyarla)

# Instagram API Rotaları
@app.route('/api/insta/<type>/<username>', methods=['GET'])
def insta_api(type, username):
    conn = http.client.HTTPSConnection("instagram120.p.rapidapi.com")
    payload = json.dumps({"username": username})
    headers = {
        'x-rapidapi-key': "c3fc1d6f5fmsh00a84fec84ec710p15095djsn820438b65da3",
        'x-rapidapi-host': "instagram120.p.rapidapi.com",
        'Content-Type': "application/json"
    }
    
    endpoint = ""
    if type == "hikaye": endpoint = "/api/instagram/stories"
    elif type == "post": endpoint = "/api/instagram/posts"
    elif type == "highlight": endpoint = "/api/instagram/highlights"
    elif type == "profil": endpoint = "/api/instagram/profile"
    else: return jsonify({"error": "Geçersiz araç."}), 400

    conn.request("POST", endpoint, payload, headers)
    res = conn.getresponse()
    data = res.read()
    
    return data.decode("utf-8")
