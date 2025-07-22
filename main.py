import requests
import warnings
from datetime import datetime
import os

# Silenciar warning de urllib3 + LibreSSL
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL 1.1.1+")

# Configuración
API_KEY = 'bqFZ78y80RfNCzQAMqOmxPjeX6KutXIW'
ORIGEN = (36.4835640, -5.0065981)
DESTINO = (36.5088687, -4.8669464)
LIMITE_MINUTOS = 20

# Variables para Telegram desde entorno (GitHub Actions: secrets)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Ruta absoluta al archivo de log
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trafico_log.md")


def obtener_duracion_tomtom(origen, destino, api_key):
    url = f"https://api.tomtom.com/routing/1/calculateRoute/{origen[0]},{origen[1]}:{destino[0]},{destino[1]}/json"
    params = {
        'key': api_key,
        'traffic': 'true',
        'travelMode': 'car',
        'routeType': 'fastest',
        'departAt': 'now'
    }
    response = requests.get(url, params=params)
    data = response.json()

    if "routes" not in data:
        raise Exception(f"Error en API TomTom: {data}")

    segundos = data['routes'][0]['summary']['travelTimeInSeconds']
    return segundos / 60


def registrar_log(minutos):
    ahora = datetime.now().strftime('%Y-%m-%d %H:%M')
    estado = "🚨 ALTO" if minutos > LIMITE_MINUTOS else "✅ OK"
    linea = f"- {ahora} | {minutos:.1f} min | {estado}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(linea)


def enviar_telegram(mensaje, token, chat_id):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": mensaje
    }
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"❌ Error enviando a Telegram: {e}")


# Ejecución principal
try:
    minutos = obtener_duracion_tomtom(ORIGEN, DESTINO, API_KEY)
    print(f"⏱️ Duración estimada con tráfico: {minutos:.1f} minutos")

    if minutos > LIMITE_MINUTOS:
        print("🚨 El trayecto supera el límite establecido.")
        if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
            enviar_telegram(
                f"🚨 Tráfico alto: {minutos:.1f} min entre origen y destino.",
                TELEGRAM_TOKEN,
                TELEGRAM_CHAT_ID
            )
    else:
        print("✅ Trayecto dentro del tiempo permitido.")

    registrar_log(minutos)

except Exception as e:
    print(f"❌ Error: {e}")
