from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import httpx

app = FastAPI()

# Kendi RapidAPI Şifren
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY") # Şifre yerine bunu yaz"
RAPIDAPI_HOST = "tiktok-scraper7.p.rapidapi.com" 

# --- 1. KISIM: ANA SAYFAYI (ARAYÜZÜ) GÖSTEREN KOD ---
@app.get("/", response_class=HTMLResponse)
async def ana_sayfa():
    # index.html dosyasını okuyup tarayıcıya yansıtıyoruz
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

# --- 2. KISIM: ARKA PLANDA TIKTOK VERİSİ ÇEKEN KOD ---
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
