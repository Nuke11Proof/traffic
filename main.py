import os
import math
import warnings
from datetime import datetime, timedelta, timezone
from configparser import ConfigParser
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL 1.1.1+")
import requests

class TraficoChecker:
    API_KEY    = 'bqFZ78y80RfNCzQAMqOmxPjeX6KutXIW'
    ORIGEN     = (36.4835640, -5.0065981)
    DESTINO    = (36.5088687, -4.8669464)
    MIN_NORMAL = 19
    MAX_NORMAL = 25
    LOG_FILE   = "trafico_log.md"
    CEST       = timezone(timedelta(hours=2))

    def __init__(self):
        # Inicializa la clase y carga las credenciales de Telegram
        self.token, self.chat_id = self.load_credentials()        

    def load_credentials(self):
        # Carga el token y chat_id de Telegram desde config.ini o variables de entorno
        cfg = ConfigParser()
        if os.path.exists("config.ini"):
            cfg.read("config.ini")
            token = cfg.get("telegram", "token", fallback=os.getenv("TELEGRAM_TOKEN"))
            chat  = cfg.get("telegram", "chat_id", fallback=os.getenv("TELEGRAM_CHAT_ID"))
        else:
            token = os.getenv("TELEGRAM_TOKEN")
            chat  = os.getenv("TELEGRAM_CHAT_ID")
        return token, chat

    def obtener_duracion(self):
        # Consulta la API de TomTom para obtener la duración y si hay peaje en la ruta
        url = (
            f"https://api.tomtom.com/routing/1/calculateRoute/"
            f"{self.ORIGEN[0]},{self.ORIGEN[1]}:{self.DESTINO[0]},{self.DESTINO[1]}/json"
        )
        params = {
            'key': self.API_KEY, 'traffic': 'true',
            'travelMode': 'car', 'routeType': 'fastest',
            'departAt': 'now', 'avoid': 'tollRoads'
        }
        r = requests.get(url, params=params).json()
        suma = r['routes'][0]['summary']
        minutos = suma['travelTimeInSeconds'] / 60
        peaje = any([
            suma.get('hasTollRoad'),
            suma.get('hasTollRoads'),
            suma.get('hasTollVignette')
        ])
        return minutos, peaje

    def send_telegram(self, texto):
        # Envía un mensaje de texto al chat de Telegram configurado
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        requests.post(url, data={"chat_id": self.chat_id, "text": texto})

    def log(self, minutos, peaje):
        # Registra en un archivo el resultado del tráfico consultado
        ahora = datetime.now(self.CEST).strftime('%Y-%m-%d %H:%M')
        nivel = "ALTO" if minutos > self.MAX_NORMAL else "✅ NORMAL"
        toll  = "⚠️ PEAJE" if peaje else "🚫 Sin peaje"
        with open(self.LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"- {ahora} | {minutos:.0f} min | {nivel} | {toll}\n")

    def run(self):
        # Ejecuta el flujo principal: consulta tráfico, genera mensaje, envía y registra
        minutos_float, peaje = self.obtener_duracion()
        minutos = math.ceil(minutos_float)
        ahora = datetime.now(timezone.utc).astimezone(self.CEST)
        eta = (ahora + timedelta(minutes=minutos)).strftime('%H:%M')

        if minutos <= self.MIN_NORMAL:
            texto = f"✅ Tráfico muy fluido ({minutos} min) → ETA {eta}"
        elif self.MIN_NORMAL < minutos < self.MAX_NORMAL:
            texto = f"🚗 Tráfico normal ({minutos} min) → ETA {eta}"
        else:  # minutos >= self.MAX_NORMAL
            texto = f"🚨 Tráfico alto ({minutos} min) → ETA {eta}"

        if peaje:
            texto += "\n⚠️ Ruta con peaje"

        print(texto)
        self.send_telegram(texto)
        self.log(minutos, peaje)

if __name__ == "__main__":
    # Punto de entrada: crea una instancia y ejecuta el chequeo de tráfico
    checker = TraficoChecker()
    checker.run()
