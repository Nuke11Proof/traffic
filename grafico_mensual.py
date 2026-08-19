"""Resumen mensual del tráfico: qué meses del año son los peores, por Telegram.

Agrega TODO el histórico de cada log por mes del año (enero, febrero...),
sin distinguir el año, para ver si hay estacionalidad. Pensado para
ejecutarse una vez al mes. Solo lee los logs: no escribe nada en el repo.

Uso:
    python3 grafico_mensual.py                          # envía a Telegram
    python3 grafico_mensual.py --guardar out.png --no-telegram   # prueba local
"""

import argparse
import io
import os
import sys
from collections import defaultdict
from datetime import datetime

import matplotlib
matplotlib.use("Agg")  # sin ventana: imprescindible en GitHub Actions
import matplotlib.pyplot as plt

from main_mlg import TraficoChecker
from grafico_diario import LINEA_RE, load_credentials, enviar_foto, enviar_texto

RUTAS = TraficoChecker.RUTAS

# Mismos colores que el resumen diario, para que se lean igual
COLOR = {"ida": "royalblue", "vuelta": "seagreen"}
MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def leer_log_mensual(path):
    """Devuelve {'ida'/'vuelta': {mes(1-12): [minutos, ...]}} de todo el histórico."""
    datos = {"ida": defaultdict(list), "vuelta": defaultdict(list)}
    if not os.path.exists(path):
        return datos

    with open(path, encoding="utf-8") as f:
        for linea in f:
            m = LINEA_RE.match(linea.strip())
            if not m:
                continue
            campos = [c.strip() for c in m[3].split("|")]
            # Formato actual: AUTO | peaje | ida/vuelta | etiqueta legible.
            # Las líneas antiguas (2 campos tras "min") no llevan sentido: son ida.
            sentido = campos[2] if len(campos) >= 3 else "ida"
            if sentido not in datos:
                continue
            fecha = datetime.strptime(m[1], "%Y-%m-%d %H:%M")
            datos[sentido][fecha.month].append(float(m[2]))
    return datos


def construir_grafico(por_ruta):
    """Una figura con un panel por ruta: barras ida/vuelta por mes del año."""
    rutas = list(por_ruta)
    fig, axes = plt.subplots(
        len(rutas), 1, figsize=(11, 3.4 * len(rutas)), squeeze=False
    )
    axes = axes[:, 0]

    meses = range(1, 13)
    ancho = 0.38

    for ax, ruta in zip(axes, rutas):
        datos = por_ruta[ruta]
        info = RUTAS[ruta]
        for i, sentido in enumerate(("ida", "vuelta")):
            offset = (-1 if i == 0 else 1) * ancho / 2
            posiciones, alturas = [], []
            for mes in meses:
                valores = datos[sentido].get(mes)
                if not valores:
                    continue
                posiciones.append(mes + offset)
                alturas.append(sum(valores) / len(valores))
            ax.bar(
                posiciones, alturas, width=ancho,
                color=COLOR[sentido], label=sentido.capitalize(),
            )
        ax.set_title(
            f"{info['nombre_origen']} ↔ {info['nombre_destino']}",
            fontsize=10, loc="left",
        )
        ax.set_ylabel("Minutos (media)")
        ax.set_xticks(list(meses))
        ax.set_xticklabels(MESES)
        ax.grid(True, axis="y", alpha=0.3)
        ax.legend(fontsize=8)

    fig.suptitle("Tráfico medio por mes del año (todo el histórico)", fontsize=13)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf


def construir_resumen(por_ruta):
    lineas = ["📊 Tráfico medio por mes del año (todo el histórico)"]
    for ruta, datos in por_ruta.items():
        combinados = defaultdict(list)
        for sentido in ("ida", "vuelta"):
            for mes, valores in datos[sentido].items():
                combinados[mes].extend(valores)
        if not combinados:
            continue
        medias = {mes: sum(v) / len(v) for mes, v in combinados.items()}
        peor_mes = max(medias, key=medias.get)
        mejor_mes = min(medias, key=medias.get)
        n = sum(len(v) for v in combinados.values())
        lineas.append("")
        lineas.append(RUTAS[ruta]["nombre_destino"])
        lineas.append(f"  🚨 Peor mes: {MESES[peor_mes - 1]} (media {medias[peor_mes]:.0f} min)")
        lineas.append(f"  ✅ Mejor mes: {MESES[mejor_mes - 1]} (media {medias[mejor_mes]:.0f} min)")
        lineas.append(f"  ({n} medidas, {len(combinados)} meses con datos)")
    return "\n".join(lineas)


def main():
    p = argparse.ArgumentParser(description="Resumen mensual del tráfico por Telegram")
    p.add_argument("--guardar", help="Guarda además el PNG en esta ruta")
    p.add_argument("--no-telegram", action="store_true", help="No envía nada")
    args = p.parse_args()

    por_ruta = {}
    for ruta, info in RUTAS.items():
        datos = leer_log_mensual(info["log_file"])
        if datos["ida"] or datos["vuelta"]:
            por_ruta[ruta] = datos

    token, chat_id = load_credentials()

    if not por_ruta:
        aviso = "⚠️ Sin datos de tráfico todavía para el resumen mensual"
        print(aviso)
        if not args.no_telegram and token and chat_id:
            enviar_texto(token, chat_id, aviso)
        return 0

    imagen = construir_grafico(por_ruta)
    resumen = construir_resumen(por_ruta)
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
