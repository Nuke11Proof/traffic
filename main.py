import os
import warnings
from datetime import datetime, timedelta, timezone
import math
from configparser import ConfigParser

# 1) Carga credenciales
cfg = ConfigParser()
if os.path.exists("config.ini"):
    cfg.read("config.ini")
    TOKEN = cfg.get("telegram",   "token",   fallback=os.getenv("TELEGRAM_TOKEN"))
    CHAT  = cfg.get("telegram",   "chat_id", fallback=os.getenv("TELEGRAM_CHAT_ID"))
else:
    TOKEN = os.getenv("TELEGRAM_TOKEN")
    CHAT  = os.getenv("TELEGRAM_CHAT_ID")

# 2) Silenciar warning antes de requests
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL 1.1.1+")
# (import requests _después_ de filtrar)
import requests

# 3) Parámetros
API_KEY    = 'bqFZ78y80RfNCzQAMqOmxPjeX6KutXIW'
ORIGEN     = (36.4835640, -5.0065981)
DESTINO    = (36.5088687, -4.8669464)
MIN_NORMAL = 18
MAX_NORMAL = 25

LOG_FILE   = "trafico_log.md"
CEST       = timezone(timedelta(hours=2))

def obtener_duracion():
    url = (
        f"https://api.tomtom.com/routing/1/calculateRoute/"
        f"{ORIGEN[0]},{ORIGEN[1]}:{DESTINO[0]},{DESTINO[1]}/json"
    )
    params = {
        'key': API_KEY, 'traffic': 'true',
        'travelMode': 'car', 'routeType': 'fastest',
        'departAt': 'now',   'avoid': 'tollRoads'
    }
    r = requests.get(url, params=params).json()
    suma = r['routes'][0]['summary']
    minutos = suma['travelTimeInSeconds'] / 60
    peaje   = bool(
        suma.get('hasTollRoad') or
        suma.get('hasTollRoads') or
        suma.get('hasTollVignette')
    )
    return minutos, peaje

def send_telegram(texto):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT, "text": texto})

def log(minutos, peaje):
    ahora = datetime.now(CEST).strftime('%Y-%m-%d %H:%M')
    nivel = "ALTO" if minutos > MAX_NORMAL else "✅ NORMAL"
    toll  = "⚠️ PEAJE" if peaje else "🚫 Sin peaje"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"- {ahora} | {minutos:.0f} min | {nivel} | {toll}\n")

def main():
    m_f, peaje = obtener_duracion()
    m = math.ceil(m_f)
    ahora = datetime.now(timezone.utc).astimezone(CEST)
    eta   = (ahora + timedelta(minutes=m)).strftime('%H:%M')

    if m < MIN_NORMAL:
        texto = f"✅ Tráfico muy fluido ({m} min) → ETA {eta}"
    elif m <= MAX_NORMAL:
        texto = f"🚗 Tráfico normal ({m} min) → ETA {eta}"
    else:
        texto = f"🚨 Tráfico alto ({m} min) → ETA {eta}"

    if peaje:
        texto += "\n⚠️ Ruta con peaje"

    print(texto)
    send_telegram(texto)
    log(m, peaje)

if __name__ == "__main__":
    main()
