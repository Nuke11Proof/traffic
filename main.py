import warnings
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL 1.1.1+")

from urllib3.exceptions import NotOpenSSLWarning
warnings.filterwarnings("ignore", category=NotOpenSSLWarning)

import requests
from datetime import datetime
import os

# Configuración
API_KEY = 'bqFZ78y80RfNCzQAMqOmxPjeX6KutXIW'
ORIGEN = (36.4835640, -5.0065981)
DESTINO = (36.5088687, -4.8669464)
LIMITE_MINUTOS = 20

# Ruta absoluta al log
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
    return segundos / 60  # Convertimos a minutos

def registrar_log(minutos):
    ahora = datetime.now().strftime('%Y-%m-%d %H:%M')
    estado = "🚨 ALTO" if minutos > LIMITE_MINUTOS else "✅ OK"
    linea = f"- {ahora} | {minutos:.1f} min | {estado}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(linea)

# Ejecución
try:
    minutos = obtener_duracion_tomtom(ORIGEN, DESTINO, API_KEY)
    print(f"⏱️ Duración estimada con tráfico: {minutos:.1f} minutos")

    if minutos > LIMITE_MINUTOS:
        print("🚨 El trayecto supera el límite establecido.")
    else:
        print("✅ Trayecto dentro del tiempo permitido.")

    registrar_log(minutos)

except Exception as e:
    print(f"❌ Error: {e}")
