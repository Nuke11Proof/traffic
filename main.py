import warnings
from datetime import datetime, timedelta, timezone
import os
import math
from configparser import ConfigParser

# —————————————————————————————————————————
# 1. Carga de configuración local (solo para dev)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
cfg = ConfigParser()
cfg_path = os.path.join(BASE_DIR, "config.ini")
if os.path.exists(cfg_path):
    cfg.read(cfg_path)
    TELEGRAM_TOKEN   = cfg.get("telegram", "token", fallback=None)
    TELEGRAM_CHAT_ID = cfg.get("telegram", "chat_id", fallback=None)
else:
    TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Silenciar warning de urllib3 + LibreSSL antes de importar requests
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL 1.1.1+")
import requests

# —————————————————————————————————————————
# 2. Configuración fija
API_KEY    = 'bqFZ78y80RfNCzQAMqOmxPjeX6KutXIW'
ORIGEN     = (36.4835640, -5.0065981)
DESTINO    = (36.5088687, -4.8669464)
MIN_NORMAL = 18   # inicio de tráfico normal
MAX_NORMAL = 25   # fin de tráfico normal

LOG_FILE = os.path.join(BASE_DIR, "trafico_log.md")
# Definir zona CEST (UTC+2)
CEST = timezone(timedelta(hours=2))

def obtener_duracion_tomtom(origen, destino, api_key):
    url = (
        f"https://api.tomtom.com/routing/1/calculateRoute/"
        f"{origen[0]},{origen[1]}:{destino[0]},{destino[1]}/json"
    )
    params = {
        'key': api_key,
        'traffic': 'true',
        'travelMode': 'car',
        'routeType': 'fastest',
        'departAt': 'now',
        'avoid': 'tollRoads',
    }
    r = requests.get(url, params=params)
    data = r.json()
    if "routes" not in data:
        raise Exception(f"Error en API TomTom: {data}")
    summary = data['routes'][0].get('summary', {})
    segundos = summary.get('travelTimeInSeconds')
    if segundos is None:
        raise Exception("Respuesta TomTom sin 'travelTimeInSeconds'.")
    has_toll = bool(
        summary.get('hasTollRoad') or
        summary.get('hasTollRoads') or
        summary.get('hasTollVignette')
    )
    return segundos / 60, has_toll


def registrar_log(minutos, has_toll):
    ahora = datetime.now(CEST).strftime('%Y-%m-%d %H:%M')
    estado_tiempo = "ALTO" if minutos > MAX_NORMAL else "✅ NORMAL"
    estado_peaje  = "⚠️ PEAJE" if has_toll else "🚫 Sin peaje"
    linea = f"- {ahora} | {minutos} min | {estado_tiempo} | {estado_peaje}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(linea)


def enviar_telegram(mensaje, token, chat_id):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": mensaje}
    resp = requests.post(url, data=payload)

# —————————————————————————————————————————
# 3. Ejecución principal

minutos_float, has_toll = obtener_duracion_tomtom(ORIGEN, DESTINO, API_KEY)
minutos = math.ceil(minutos_float)

print(f"⏱️ Duración estimada: {minutos_float:.1f} min (→ {minutos} min redondeado)")
print("🚫 Ruta sin peaje." if not has_toll else "⚠️ Ruta incluye peaje.")

# Calcular ETA en hora local CEST
now_local = datetime.now(timezone.utc).astimezone(CEST)
eta = (now_local + timedelta(minutes=minutos)).strftime('%H:%M')

# Construir mensaje según rango
if minutos < MIN_NORMAL:
    texto = f"✅ Tráfico muy fluido -> {minutos} min, llegarás a las {eta} :D"
elif minutos <= MAX_NORMAL:
    texto = f"🚗 Tráfico normal -> {minutos} min, llegarás a las {eta} :)"
else:
    texto = f"🚨 Tráfico alto -> {minutos} min, llegarás a las {eta} :/"

# Añadir aviso de peaje
if has_toll:
    texto += "\n⚠️ Ruta con peaje"

# Enviar siempre
print(f"📬 Enviando mensaje a Telegram: {texto}")
enviar_telegram(texto, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)


registrar_log(minutos, has_toll)

