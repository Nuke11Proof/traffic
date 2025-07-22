import warnings
from datetime import datetime
import os
import math  # <-- para redondeo hacia arriba

# Silenciar warning de urllib3 + LibreSSL antes de importar requests
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL 1.1.1+")
import requests

# --- Configuración ---
API_KEY = 'bqFZ78y80RfNCzQAMqOmxPjeX6KutXIW'
ORIGEN = (36.4835640, -5.0065981)
DESTINO = (36.5088687, -4.8669464)
LIMITE_MINUTOS = 20  # umbral

# Secrets (inyectados en GitHub Actions)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Log en el mismo directorio del script
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trafico_log.md")


def obtener_duracion_tomtom(origen, destino, api_key):
    """Devuelve (minutos_float, has_toll, raw_json)."""
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
        'avoid': 'tollRoads',  # evitar peajes
    }
    r = requests.get(url, params=params)
    data = r.json()

    if "routes" not in data:
        raise Exception(f"Error en API TomTom: {data}")

    ruta = data['routes'][0]
    summary = ruta.get('summary', {})

    segundos = summary.get('travelTimeInSeconds')
    if segundos is None:
        raise Exception("Respuesta TomTom sin 'travelTimeInSeconds'.")

    # Detectar peaje
    has_toll = bool(
        summary.get('hasTollRoad')
        or summary.get('hasTollRoads')
        or summary.get('hasTollVignette')
    )

    return segundos / 60, has_toll, data


def registrar_log(minutos_redondeados, has_toll):
    ahora = datetime.now().strftime('%Y-%m-%d %H:%M')
    estado_tiempo = "🚨 ALTO" if minutos_redondeados > LIMITE_MINUTOS else "✅ OK"
    estado_peaje = "⚠️ PEAJE" if has_toll else "🚫 Sin peaje"
    linea = f"- {ahora} | {minutos_redondeados} min | {estado_tiempo} | {estado_peaje}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(linea)


def enviar_telegram(mensaje, token, chat_id):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": mensaje
    }
    try:
        resp = requests.post(url, data=payload)
        print(f"✅ Status Telegram: {resp.status_code}")
        print(f"📦 Respuesta Telegram: {resp.text}")
    except Exception as e:
        print(f"❌ Error enviando a Telegram: {e}")


# --- Ejecución principal ---
try:
    minutos_float, has_toll, _ = obtener_duracion_tomtom(ORIGEN, DESTINO, API_KEY)

    # Redondeo hacia arriba al siguiente minuto entero
    minutos = math.ceil(minutos_float)

    print(f"⏱️ Duración estimada con tráfico: {minutos_float:.1f} min (→ {minutos} min redondeado)")
    print("🚫 Ruta sin peaje." if not has_toll else "⚠️ La ruta incluye peaje (TomTom no encontró alternativa).")

    if minutos > LIMITE_MINUTOS:
        print("🚨 El trayecto supera el límite establecido.")
        if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
            msg = (
                f"🚨 Tráfico alto: {minutos} min.\n"
                f"{'⚠️ Ruta con peaje' if has_toll else '🚫 Sin peaje'}"
            )
            enviar_telegram(msg, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
        else:
            print("⚠️ TELEGRAM_TOKEN o TELEGRAM_CHAT_ID no definidos.")
    else:
        print("✅ Trayecto dentro del tiempo permitido.")

    registrar_log(minutos, has_toll)

except Exception as e:
    print(f"❌ Error: {e}")
