from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
import httpx
import os

app = FastAPI()

# Kendi RapidAPI Şifren
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY") 
RAPIDAPI_HOST = "tiktok-scraper7.p.rapidapi.com" 

# --- 1. KISIM: ARAYÜZ VE DOSYA İZİNLERİ ---

@app.get("/", response_class=HTMLResponse)
async def ana_sayfa():
    # index.html dosyasını okuyup tarayıcıya yansıtıyoruz
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

# Ads.txt dosyasını dışarıya açar (Google Onayı İçin Zorunlu)
@app.get("/ads.txt")
async def ads_txt():
    return FileResponse("ads.txt")

# Favicon (Sekme İkonu) dosyasını dışarıya açar
@app.get("/favicon.svg")
async def favicon():
    return FileResponse("favicon.svg")


# --- 2. KISIM: TIKTOK VERİ ÇEKME FONKSİYONLARI ---

# 2.1 - HİKAYE ÇEKİCİ (Senin Mevcut Çalışan Kodun)
@app.get("/api/hikayeler/{kullanici_adi}")
async def hikayeleri_getir(kullanici_adi: str):
    print(f"----> 1. AŞAMA: {kullanici_adi} kimliği aranıyor... <----")
    
    if kullanici_adi.startswith("@"):
        kullanici_adi = kullanici_adi[1:]
        
    url_info = f"https://{RAPIDAPI_HOST}/user/info"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST
    }
    querystring_info = {"unique_id": kullanici_adi}

    async with httpx.AsyncClient(timeout=15.0) as client:
        response_info = await client.get(url_info, headers=headers, params=querystring_info)
        
        if response_info.status_code != 200:
            raise HTTPException(status_code=400, detail="Kullanıcı bulunamadı veya API yanıt vermedi.")
            
        veri_info = response_info.json()
        
        try:
            kullanici_numarasi = veri_info["data"]["user"]["id"]
            print(f"----> KİMLİK BULUNDU: {kullanici_numarasi} <----")
        except KeyError:
            raise HTTPException(status_code=404, detail="Hesap gizli, hatalı veya veri çekilemedi.")

        print("----> 2. AŞAMA: Hikaye videoları çekiliyor... <----")
        url_stories = f"https://{RAPIDAPI_HOST}/user/story" 
        querystring_stories = {"user_id": kullanici_numarasi}
        
        response_stories = await client.get(url_stories, headers=headers, params=querystring_stories)
        
        if response_stories.status_code != 200:
            raise HTTPException(status_code=400, detail="Hikayeler çekilemedi.")
            
        hikaye_verisi = response_stories.json()
        return {"aranan_kisi": kullanici_adi, "hikayeler": hikaye_verisi}

# 2.2 - YENİ: PROFİL RESMİ (PP) BÜYÜTÜCÜ
@app.get("/api/profil/{kullanici_adi}")
async def profil_getir(kullanici_adi: str):
    if kullanici_adi.startswith("@"):
        kullanici_adi = kullanici_adi[1:]
        
    url_info = f"https://{RAPIDAPI_HOST}/user/info"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST
    }
    querystring_info = {"unique_id": kullanici_adi}

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url_info, headers=headers, params=querystring_info)
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Kullanıcı bulunamadı.")
            
        veri = response.json()
        try:
            # API'den gelen verilerin içinden en yüksek çözünürlüklü avatarı alıyoruz
            user_data = veri["data"]["user"]
            pp_url = user_data.get("avatarLarger") or user_data.get("avatar_larger") or user_data.get("avatarThumb")
            return {"durum": "basarili", "kullanici_adi": kullanici_adi, "profil_resmi": pp_url}
        except KeyError:
            raise HTTPException(status_code=404, detail="Profil resmi bulunamadı.")

# 2.3 - YENİ: VİDEO İNDİRİCİ
@app.get("/api/video/")
async def video_getir(url: str):
    # Kullanıcı link yapıştırdığında çalışacak uç nokta
    url_video = f"https://{RAPIDAPI_HOST}/video/info" 
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST
    }
    querystring = {"url": url}
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url_video, headers=headers, params=querystring)
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Video bulunamadı veya bağlantı hatalı.")
            
        return response.json()
