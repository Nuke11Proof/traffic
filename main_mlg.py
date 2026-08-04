import os
import math
import warnings
from datetime import datetime, timedelta, timezone
from configparser import ConfigParser
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL 1.1.1+")
import requests

# Prefer zoneinfo (py3.9+). If no zoneinfo, try pytz. If neither, fall back to fixed CET offset.
try:
    from zoneinfo import ZoneInfo as _ZoneInfo
except Exception:
    _ZoneInfo = None

ENVIAR_TELEGRAM = True


class TraficoChecker:
    # ---- RELLENA AQUÍ LAS COORDENADAS DE TU CASA ----
    CASA       = (36.4835640, -5.0065981)   # <-- sustituir por tu casa
    MARBELLA   = (36.5088687, -4.8669464)   # Policia Local Marbella
    LOG_FILE   = "trafico_log_mlg.md"

    NOMBRE_CASA     = "Hotel Barceló Guadalmina"
    NOMBRE_MARBELLA = "Policía Local Marbella"

    # timezone-aware object for Europe/Madrid that handles DST transitions
    if _ZoneInfo:
        CEST = _ZoneInfo("Europe/Madrid")
    else:
        try:
            import pytz as _pytz
            CEST = _pytz.timezone("Europe/Madrid")
        except Exception:
            # Last resort: fixed CET offset (UTC+1). This will NOT handle DST.
            CEST = timezone(timedelta(hours=1))

    def __init__(self, sentido="ida"):
        self.token, self.chat_id = self.load_credentials()
        self.api_key = self.load_api_key()
        self.sentido = sentido
        if sentido == "ida":
            self.punto_inicio = self.CASA
            self.punto_fin = self.MARBELLA
            self.sentido_str = f"{self.NOMBRE_CASA} → {self.NOMBRE_MARBELLA}"
        else:
            self.punto_inicio = self.MARBELLA
            self.punto_fin = self.CASA
            self.sentido_str = f"{self.NOMBRE_MARBELLA} → {self.NOMBRE_CASA}"

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
            f"{self.punto_inicio[0]},{self.punto_inicio[1]}:{self.punto_fin[0]},{self.punto_fin[1]}/json"
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
            f.write(f"- {ahora} | {minutos:.0f} min | {nivel} | {toll} | {self.sentido} | {self.sentido_str}\n")

    def _linea_relevante(self, linea, parts):
        """Decide si una línea del log cuenta para el sentido actual.

        Formatos posibles, de más antiguo a más reciente:
          - 4 campos: sin sentido -> histórico de la ida (anterior a ago 2026).
          - 5 campos: solo etiqueta legible (transición) -> se compara texto.
          - 6+ campos: clave estable "ida"/"vuelta" -> comparación exacta,
            inmune a que se renombren las etiquetas legibles más adelante.
        """
        if len(parts) >= 6:
            return parts[-2].strip() == self.sentido
        if len(parts) == 5:
            return parts[-1].strip() == self.sentido_str
        if len(parts) == 4:
            return self.sentido == "ida"
        return False

    def media_historica_dia(self):
        """Devuelve la media histórica de minutos para el día de la semana y sentido actual."""
        if not os.path.exists(self.LOG_FILE):
            return None
        minutos = []
        hoy = datetime.now(self.CEST)
        dia_semana = hoy.strftime("%A")
        with open(self.LOG_FILE, encoding="utf-8") as f:
            for linea in f:
                parts = linea.strip().split("|")
                if len(parts) < 2:
                    continue
                if not self._linea_relevante(linea, parts):
                    continue
                fecha_str = parts[0].replace("-", "").strip()[1:].strip()
                try:
                    fecha = datetime.strptime(fecha_str, "%Y%m%d %H:%M")
                    # attach timezone so weekday comparisons respect DST rules
                    if hasattr(self.CEST, 'localize'):
                        fecha = self.CEST.localize(fecha)
                    else:
                        fecha = fecha.replace(tzinfo=self.CEST)
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

        texto = f"{self.sentido_str}\n{clasificacion} ({minutos} min) → ETA {eta}"
        if peaje:
            texto += "\n⚠️ Ruta con peaje"

        print(texto)
        self.send_telegram(texto)
        self.log(minutos, peaje)


if __name__ == "__main__":
    for sentido in ("ida", "vuelta"):
        try:
            TraficoChecker(sentido=sentido).run()
        except Exception as e:
            # Un fallo en un sentido no debe impedir que se registre el otro
            print(f"[ERROR] Sentido '{sentido}' fallido: {e}")
