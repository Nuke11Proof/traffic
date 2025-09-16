import os
import math
import warnings
from datetime import datetime, timedelta, timezone
from configparser import ConfigParser
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL 1.1.1+")
import requests

# Ejecutar solo hasta el 12 de diciembre incluido para enviar Telegram
#ENVIAR_TELEGRAM = datetime.now().date() <= datetime(2025, 12, 31).date()
ENVIAR_TELEGRAM = True

class TraficoChecker:
    ORIGEN     = (36.4835640, -5.0065981) # Hotel Barceló Guadalmina
    DESTINO    = (36.5088687, -4.8669464) # Policia Local Marbella
    LOG_FILE   = "trafico_log_mlg.md" 
    CEST       = timezone(timedelta(hours=2))

    def __init__(self):
        self.token, self.chat_id = self.load_credentials()
        self.api_key = self.load_api_key()

    def load_api_key(self):
        cfg = ConfigParser()
        if os.path.exists("config.ini"):
            cfg.read("config.ini")
            return cfg.get("tomtom", "api_key", fallback=os.getenv("TOMTOM_TOKEN"))
        else:
            return os.getenv("TOMTOM_TOKEN")

    def load_credentials(self):
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
        url = (
            f"https://api.tomtom.com/routing/1/calculateRoute/"
            f"{self.ORIGEN[0]},{self.ORIGEN[1]}:{self.DESTINO[0]},{self.DESTINO[1]}/json"
        )
        params = {
            'key': self.api_key,
            'traffic': 'true',
            'travelMode': 'car',
            'routeType': 'fastest',
            'departAt': 'now',
            'avoid': 'tollRoads'
        }

        try:
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            summary = data['routes'][0]['summary']
            minutos = summary['travelTimeInSeconds'] / 60
            peaje = any([
                summary.get('hasTollRoad'),
                summary.get('hasTollRoads'),
                summary.get('hasTollVignette')
            ])
            return minutos, peaje

        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Fallo en la solicitud HTTP: {e}")
            raise
        except (ValueError, KeyError, IndexError) as e:
            print(f"[ERROR] Respuesta inesperada o malformada: {e}")
            raise

    def send_telegram(self, texto):
        if ENVIAR_TELEGRAM:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            requests.post(url, data={"chat_id": self.chat_id, "text": texto})

    def log(self, minutos, peaje):
        ahora = datetime.now(self.CEST).strftime('%Y-%m-%d %H:%M')
        nivel = "AUTO"
        toll  = "⚠️ PEAJE" if peaje else "🚫 Sin peaje"
        with open(self.LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"- {ahora} | {minutos:.0f} min | {nivel} | {toll}\n")

    def media_historica_dia(self):
        """Devuelve la media histórica de minutos para el día de la semana."""
        if not os.path.exists(self.LOG_FILE):
            return None
        from datetime import datetime
        minutos = []
        hoy = datetime.now(self.CEST)
        dia_semana = hoy.strftime("%A")
        with open(self.LOG_FILE, encoding="utf-8") as f:
            for linea in f:
                # - 2025-08-04 06:58 | 26 min | ... | ... 
                parts = linea.strip().split("|")
                if len(parts) < 2:
                    continue
                fecha_str = parts[0].replace("-", "").strip()[1:].strip()
                try:
                    fecha = datetime.strptime(fecha_str, "%Y%m%d %H:%M")
                except Exception:
                    continue
                if fecha.strftime("%A") == dia_semana:
                    try:
                        min_val = int(parts[1].strip().split(" ")[0])
                        minutos.append(min_val)
                    except Exception:
                        continue
        if minutos:
            return sum(minutos) / len(minutos)
        else:
            return None

    def clasifica_trafico(self, minutos, media):
        """Clasifica el tráfico según la media histórica del día."""
        if media is None:
            # Si no hay histórico, usa valores fijos razonables
            if minutos <= 19:
                return "✅ Tráfico muy fluido"
            elif minutos < 25:
                return "🚗 Tráfico normal"
            else:
                return "🚨 Tráfico alto"
        # Umbrales relativos a la media histórica
        if minutos <= media:
            return "✅ Tráfico muy fluido"
        elif minutos <= media + 5:
            return "🚗 Tráfico normal"
        else:
            return "🚨 Tráfico alto"

    def run(self):
        minutos_float, peaje = self.obtener_duracion()
        minutos = math.ceil(minutos_float)
        ahora = datetime.now(timezone.utc).astimezone(self.CEST)
        eta = (ahora + timedelta(minutes=minutos)).strftime('%H:%M')

        media = self.media_historica_dia()
        clasificacion = self.clasifica_trafico(minutos, media)

        trayecto = "Hotel Barceló Guadalmina → Policia Local Marbella"
        texto = f"{trayecto}\n{clasificacion} ({minutos} min) → ETA {eta}"
        if peaje:
            texto += "\n⚠️ Ruta con peaje"
        
        print(texto)
        self.send_telegram(texto)
        self.log(minutos, peaje)

if __name__ == "__main__":
    checker = TraficoChecker()
    checker.run()