"""Resumen diario del tráfico: genera un gráfico y lo envía por Telegram.

Pensado para ejecutarse UNA vez al día, al final de la franja de medidas.
Solo lee los logs: no escribe nada en el repo, así no añade otro escritor
que pueda chocar con el rebase del workflow de medición.

Uso:
    python3 grafico_diario.py                    # día de hoy, envía a Telegram
    python3 grafico_diario.py --fecha 2026-08-14 # otro día
    python3 grafico_diario.py --guardar out.png --no-telegram   # prueba local
    python3 grafico_diario.py --probar-fijado    # comprueba el permiso en Telegram
"""

import argparse
import io
import os
import re
import sys
from configparser import ConfigParser
from datetime import datetime

import matplotlib
matplotlib.use("Agg")  # sin ventana: imprescindible en GitHub Actions
import matplotlib.pyplot as plt
import requests

from main_mlg import TraficoChecker

CEST = TraficoChecker.CEST
RUTAS = TraficoChecker.RUTAS

# Mismos colores que los notebooks, para que gráfico y análisis se lean igual
COLOR = {"ida": "royalblue", "vuelta": "seagreen"}

LINEA_RE = re.compile(r"- (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) \| ([\d.]+) min \| (.+)")


def load_credentials():
    cfg = ConfigParser()
    if os.path.exists("config.ini"):
        cfg.read("config.ini")
        token = cfg.get("telegram", "token", fallback=os.getenv("TELEGRAM_TOKEN"))
        chat = cfg.get("telegram", "chat_id", fallback=os.getenv("TELEGRAM_CHAT_ID"))
    else:
        token = os.getenv("TELEGRAM_TOKEN")
        chat = os.getenv("TELEGRAM_CHAT_ID")
    return token, chat


def leer_log(path, fecha):
    """Devuelve {'ida': [(datetime, minutos)], 'vuelta': [...]} para esa fecha."""
    datos = {"ida": [], "vuelta": []}
    if not os.path.exists(path):
        return datos

    prefijo = f"- {fecha.strftime('%Y-%m-%d')} "
    with open(path, encoding="utf-8") as f:
        for linea in f:
            if not linea.startswith(prefijo):
                continue
            m = LINEA_RE.match(linea.strip())
            if not m:
                continue
            campos = [c.strip() for c in m[3].split("|")]
            # Formato actual: AUTO | peaje | ida/vuelta | etiqueta legible.
            # Las líneas antiguas (4 campos en total) no llevan sentido: son ida.
            sentido = campos[2] if len(campos) >= 3 else "ida"
            if sentido not in datos:
                continue
            datos[sentido].append((datetime.strptime(m[1], "%Y-%m-%d %H:%M"), float(m[2])))

    for sentido in datos:
        datos[sentido].sort()
    return datos


def construir_grafico(por_ruta, fecha):
    """Una figura con un panel por ruta, ida y vuelta superpuestas."""
    rutas = list(por_ruta)
    fig, axes = plt.subplots(
        len(rutas), 1, figsize=(11, 3.2 * len(rutas)), sharex=True, squeeze=False
    )
    axes = axes[:, 0]

    for ax, ruta in zip(axes, rutas):
        datos = por_ruta[ruta]
        info = RUTAS[ruta]
        for sentido in ("ida", "vuelta"):
            puntos = datos[sentido]
            if not puntos:
                continue
            horas = [p[0] for p in puntos]
            minutos = [p[1] for p in puntos]
            ax.plot(
                horas, minutos, marker="o", markersize=3.5,
                color=COLOR[sentido], label=sentido.capitalize(),
            )
        ax.set_title(
            f"{info['nombre_origen']} ↔ {info['nombre_destino']}",
            fontsize=10, loc="left",
        )
        ax.set_ylabel("Minutos")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8)

    axes[-1].set_xlabel("Hora")
    fig.autofmt_xdate()
    axes[-1].xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%H:%M"))
    fig.suptitle(f"Tráfico del {fecha.strftime('%d/%m/%Y')}", fontsize=13)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf


def construir_resumen(por_ruta, fecha):
    lineas = [f"📊 Resumen del {fecha.strftime('%d/%m/%Y')}"]
    for ruta, datos in por_ruta.items():
        lineas.append("")
        lineas.append(RUTAS[ruta]["nombre_destino"])
        for sentido in ("ida", "vuelta"):
            minutos = [m for _, m in datos[sentido]]
            if not minutos:
                continue
            peor_hora, peor = max(datos[sentido], key=lambda p: p[1])
            lineas.append(
                f"  {sentido}: {min(minutos):.0f}–{max(minutos):.0f} min "
                f"(media {sum(minutos) / len(minutos):.0f}), "
                f"peor a las {peor_hora.strftime('%H:%M')} con {peor:.0f}"
            )
    return "\n".join(lineas)


def enviar_foto(token, chat_id, imagen, caption):
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    r = requests.post(
        url,
        data={"chat_id": chat_id, "caption": caption},
        files={"photo": ("trafico.png", imagen, "image/png")},
        timeout=30,
    )
    r.raise_for_status()


def enviar_texto(token, chat_id, texto):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, data={"chat_id": chat_id, "text": texto}, timeout=10)
    r.raise_for_status()
    return r.json()["result"]["message_id"]


def fijar_mensaje(token, chat_id, message_id):
    """Fija un mensaje sin generar otra notificacion en Telegram."""
    url = f"https://api.telegram.org/bot{token}/pinChatMessage"
    r = requests.post(
        url,
        data={
            "chat_id": chat_id,
            "message_id": message_id,
            "disable_notification": "true",
        },
        timeout=10,
    )
    r.raise_for_status()
    return r.json().get("ok") is True


def main():
    p = argparse.ArgumentParser(description="Resumen diario del tráfico por Telegram")
    p.add_argument("--fecha", help="YYYY-MM-DD (por defecto, hoy en Europe/Madrid)")
    p.add_argument("--guardar", help="Guarda además el PNG en esta ruta")
    p.add_argument("--no-telegram", action="store_true", help="No envía nada")
    p.add_argument(
        "--probar-fijado",
        action="store_true",
        help="Envía y fija un mensaje de prueba, sin generar el resumen",
    )
    args = p.parse_args()

    token, chat_id = load_credentials()
    if args.probar_fijado:
        if not token or not chat_id:
            print("[ERROR] Faltan TELEGRAM_TOKEN / TELEGRAM_CHAT_ID", file=sys.stderr)
            return 1
        message_id = enviar_texto(
            token,
            chat_id,
            "🧪 Prueba de fijado del resumen diario de tráfico",
        )
        if not fijar_mensaje(token, chat_id, message_id):
            print("[ERROR] Telegram no confirmó el fijado", file=sys.stderr)
            return 1
        print("[OK] Telegram permitió fijar el mensaje de prueba")
        return 0

    if args.fecha:
        fecha = datetime.strptime(args.fecha, "%Y-%m-%d")
    else:
        fecha = datetime.now(CEST)

    por_ruta = {}
    for ruta, info in RUTAS.items():
        datos = leer_log(info["log_file"], fecha)
        if datos["ida"] or datos["vuelta"]:
            por_ruta[ruta] = datos

    if not por_ruta:
        aviso = f"⚠️ Sin medidas de tráfico el {fecha.strftime('%d/%m/%Y')}"
        print(aviso)
        if not args.no_telegram and token and chat_id:
            enviar_texto(token, chat_id, aviso)
        return 0

    imagen = construir_grafico(por_ruta, fecha)
    resumen = construir_resumen(por_ruta, fecha)
    print(resumen)

    if args.guardar:
        with open(args.guardar, "wb") as f:
            f.write(imagen.getvalue())
        imagen.seek(0)
        print(f"\nGráfico guardado en {args.guardar}")

    if args.no_telegram:
        return 0
    if not token or not chat_id:
        print("[ERROR] Faltan TELEGRAM_TOKEN / TELEGRAM_CHAT_ID", file=sys.stderr)
        return 1

    enviar_foto(token, chat_id, imagen, resumen)
    print("\nEnviado a Telegram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
