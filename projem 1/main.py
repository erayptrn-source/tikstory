import asyncio
import logging
import os
import time
from functools import lru_cache

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

# --------------------------------------------------------------------------
# Loglama: Render'daki "Logs" ekranında neler olduğunu görebilmek için.
# Eskiden hiçbir hata Render loglarına düşmüyordu; artık her sorun görünür.
# --------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("tikstory")

# --------------------------------------------------------------------------
# Ortam değişkenleri (Render Dashboard > Environment kısmından ayarlanır)
# --------------------------------------------------------------------------
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")
INSTA_KEY = os.environ.get("INSTA_KEY", "")
HOST_SCRAPER7 = "tiktok-scraper7.p.rapidapi.com"
HOST_API23 = "tiktok-api23.p.rapidapi.com"
INSTA_HOST = "instagram120.p.rapidapi.com"

# Prod ortamında Swagger/ReDoc'u kapatmak istersen ENV=production yap.
IS_PROD = os.environ.get("ENV", "development") == "production"

app = FastAPI(
    title="TikStory API",
    docs_url=None if IS_PROD else "/docs",
    redoc_url=None if IS_PROD else "/redoc",
)

# --------------------------------------------------------------------------
# CORS: index.html farklı bir alan adından (ör. www vs non-www, ya da ileride
# ayrı bir frontend barındırırsan) API'ye istek atarsa tarayıcı engellemesin.
# --------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://tikstory.xyz",
        "https://www.tikstory.xyz",
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Metin ağırlıklı yanıtları sıkıştır (index.html büyüdükçe daha hızlı yüklenir).
app.add_middleware(GZipMiddleware, minimum_size=1000)


# --------------------------------------------------------------------------
# index.html'i her istekte diskten okumak yerine bir kez belleğe al.
# Eski kod her ziyaretçide dosyayı yeniden açıp okuyordu; bu hem yavaş hem de
# senkron (bloklayan) bir işlemdi ve async event loop'u kilitleyebiliyordu.
# --------------------------------------------------------------------------
_INDEX_HTML_CACHE = ""


def load_index_html() -> str:
    global _INDEX_HTML_CACHE
    with open("index.html", "r", encoding="utf-8") as f:
        _INDEX_HTML_CACHE = f.read()
    return _INDEX_HTML_CACHE


@app.on_event("startup")
async def on_startup():
    load_index_html()
    if not RAPIDAPI_KEY:
        log.warning("RAPIDAPI_KEY tanımlı değil! /api/hikayeler ve /api/video çalışmayacak.")
    if not INSTA_KEY:
        log.warning("INSTA_KEY tanımlı değil! /api/insta çalışmayacak.")
    log.info("Uygulama basladi. IS_PROD=%s", IS_PROD)


@app.get("/", response_class=HTMLResponse)
async def ana_sayfa():
    return _INDEX_HTML_CACHE or load_index_html()


# --------------------------------------------------------------------------
# Render/UptimeRobot gibi servislerin siteyi "uyanık" tutmak için pingleyebileceği
# hafif bir sağlık kontrolü. Ücretsiz planda 15 dakikada bir buraya istek atan
# bir cron (cron-job.org, UptimeRobot vb.) kurarsan spin-down sorunu büyük
# ölçüde azalır.
# --------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok", "time": time.time()}


@app.get("/ads.txt")
async def ads_txt():
    return FileResponse("ads.txt")


@app.get("/favicon.svg")
async def favicon():
    return FileResponse("favicon.svg")


# --------------------------------------------------------------------------
# Basit kullanıcı adı doğrulaması: URL'e enjekte edilebilecek garip
# karakterleri (RapidAPI'ye gereksiz/zararlı istek gitmesini) baştan eler.
# --------------------------------------------------------------------------
def temizle_kullanici_adi(kullanici_adi: str) -> str:
    kullanici_adi = kullanici_adi.strip()
    if kullanici_adi.startswith("@"):
        kullanici_adi = kullanici_adi[1:]
    if not kullanici_adi or len(kullanici_adi) > 60 or not all(
        c.isalnum() or c in "._" for c in kullanici_adi
    ):
        raise HTTPException(status_code=400, detail="Geçersiz kullanıcı adı.")
    return kullanici_adi


# --------------------------------------------------------------------------
# Çok küçük bir bellek-içi önbellek: aynı kullanıcı adı kısa süre içinde
# tekrar sorgulanırsa RapidAPI'ye tekrar gitmeyip son sonucu döner.
# Bu, ücretli API kotanı (ve sunucu maliyetini) doğrudan korur.
# --------------------------------------------------------------------------
_CACHE: dict[str, tuple[float, dict]] = {}
CACHE_TTL_SANIYE = 60


def cache_getir(anahtar: str):
    kayit = _CACHE.get(anahtar)
    if kayit and (time.time() - kayit[0]) < CACHE_TTL_SANIYE:
        return kayit[1]
    return None


def cache_kaydet(anahtar: str, veri: dict):
    _CACHE[anahtar] = (time.time(), veri)


@app.get("/api/hikayeler/{kullanici_adi}")
async def hikayeleri_getir(kullanici_adi: str):
    if not RAPIDAPI_KEY:
        raise HTTPException(status_code=500, detail="TikTok API anahtarı eksik.")

    kullanici_adi = temizle_kullanici_adi(kullanici_adi)

    cache_anahtari = f"hikaye:{kullanici_adi}"
    onbellek = cache_getir(cache_anahtari)
    if onbellek is not None:
        return onbellek

    headers_23 = {"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": HOST_API23}
    headers_7 = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": HOST_SCRAPER7}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Eski kod bu iki isteği sırayla (await, await) yapıyordu.
            # Aralarında hiçbir veri bağımlılığı olmadığı için paralel
            # çalıştırmak toplam bekleme süresini ~yarıya indirir.
            response_profil, response_info = await asyncio.gather(
                client.get(
                    f"https://{HOST_API23}/api/user/info",
                    headers=headers_23,
                    params={"uniqueId": kullanici_adi},
                ),
                client.get(
                    f"https://{HOST_SCRAPER7}/user/info",
                    headers=headers_7,
                    params={"unique_id": kullanici_adi},
                ),
            )
    except httpx.TimeoutException:
        log.warning("RapidAPI zaman asimi: %s", kullanici_adi)
        raise HTTPException(status_code=504, detail="Kaynak servis yanıt vermedi, tekrar deneyin.")
    except httpx.HTTPError as exc:
        log.error("RapidAPI baglanti hatasi: %s", exc)
        raise HTTPException(status_code=502, detail="Kaynak servise ulaşılamadı.")

    profil_verisi = response_profil.json() if response_profil.status_code == 200 else {}

    if response_info.status_code != 200:
        raise HTTPException(status_code=400, detail="Kullanıcı bulunamadı.")

    try:
        kullanici_numarasi = response_info.json()["data"]["user"]["id"]
    except (KeyError, ValueError):
        raise HTTPException(status_code=404, detail="Hesap gizli veya veri yok.")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response_stories = await client.get(
                f"https://{HOST_SCRAPER7}/user/story",
                headers=headers_7,
                params={"user_id": kullanici_numarasi},
            )
    except httpx.HTTPError as exc:
        log.error("Hikaye cekme hatasi: %s", exc)
        raise HTTPException(status_code=502, detail="Hikayeler alınamadı.")

    hikaye_verisi = response_stories.json() if response_stories.status_code == 200 else {}

    sonuc = {
        "aranan_kisi": kullanici_adi,
        "profil": profil_verisi,
        "hikayeler": hikaye_verisi,
    }
    cache_kaydet(cache_anahtari, sonuc)
    return sonuc


@app.get("/api/video/")
async def video_getir(url: str):
    if not RAPIDAPI_KEY:
        raise HTTPException(status_code=500, detail="TikTok API anahtarı eksik.")

    api_url = f"https://{HOST_API23}/api/download/video"
    headers = {"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": HOST_API23}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(api_url, headers=headers, params={"url": url})
    except httpx.HTTPError as exc:
        log.error("Video indirme hatasi: %s", exc)
        raise HTTPException(status_code=502, detail="Video servisine ulaşılamadı.")

    if response.status_code != 200:
        raise HTTPException(status_code=400, detail="Video bulunamadı veya bağlantı hatalı.")
    return response.json()


@app.get("/api/profil/{kullanici_adi}")
async def profil_getir(kullanici_adi: str):
    if not RAPIDAPI_KEY:
        raise HTTPException(status_code=500, detail="TikTok API anahtarı eksik.")

    kullanici_adi = temizle_kullanici_adi(kullanici_adi)

    api_url = f"https://{HOST_API23}/api/user/info"
    headers = {"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": HOST_API23}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(api_url, headers=headers, params={"uniqueId": kullanici_adi})
    except httpx.HTTPError as exc:
        log.error("Profil cekme hatasi: %s", exc)
        raise HTTPException(status_code=502, detail="Profil servisine ulaşılamadı.")

    if response.status_code != 200:
        raise HTTPException(status_code=400, detail="Kullanıcı bulunamadı.")
    return response.json()


@app.get("/api/insta/{arac_tipi}/{kullanici_adi}")
async def insta_getir(arac_tipi: str, kullanici_adi: str):
    if not INSTA_KEY:
        raise HTTPException(status_code=500, detail="Instagram API anahtarı Render'da bulunamadı.")

    kullanici_adi = temizle_kullanici_adi(kullanici_adi)

    endpoint_map = {
        "hikaye": ("/api/instagram/stories", {"username": kullanici_adi}),
        "post": ("/api/instagram/posts", {"username": kullanici_adi}),
        "highlight": ("/api/instagram/highlights", {"username": kullanici_adi}),
        "highlight_stories": (
            "/api/instagram/highlightStories",
            {"id": kullanici_adi, "highlight_id": kullanici_adi, "highlightId": kullanici_adi},
        ),
        "profil": ("/api/instagram/userInfo", {"username": kullanici_adi}),
    }

    if arac_tipi not in endpoint_map:
        raise HTTPException(status_code=400, detail="Geçersiz araç türü.")

    endpoint, payload = endpoint_map[arac_tipi]
    url = f"https://{INSTA_HOST}{endpoint}"
    headers = {
        "x-rapidapi-key": INSTA_KEY,
        "x-rapidapi-host": INSTA_HOST,
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        log.error("Instagram API hatasi: %s", exc)
        raise HTTPException(status_code=502, detail="Instagram verisine ulaşılamadı.")

    if response.status_code != 200:
        raise HTTPException(status_code=400, detail="Instagram verisi çekilemedi veya kullanıcı bulunamadı.")
    return response.json()


# --------------------------------------------------------------------------
# Beklenmeyen tüm hataları yakalayıp 500 sayfası yerine düzgün JSON döner ve
# Render loglarına yazar; kullanıcıya iç sistem detaylarını sızdırmaz.
# --------------------------------------------------------------------------
@app.exception_handler(Exception)
async def genel_hata_yakalayici(request: Request, exc: Exception):
    log.exception("Beklenmeyen hata: %s %s", request.method, request.url)
    return JSONResponse(status_code=500, content={"detail": "Beklenmeyen bir hata oluştu."})


# --------------------------------------------------------------------------
# Render'ın dışarıdan gelen müşterileri içeri alabilmesi için 0.0.0.0 + PORT
# şart. Render Start Command'ı zaten "uvicorn main:app --host 0.0.0.0 --port
# $PORT" olarak ayarlıysa bu blok hiç çalışmaz (o zaman Render doğrudan kendi
# komutunu kullanır) — yine de "python main.py" ile de çalışsın diye kalsın.
# --------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
