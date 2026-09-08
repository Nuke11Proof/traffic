"""Conclusiones del tráfico observado, sin predicciones ni llamadas externas."""

from collections import defaultdict
from statistics import median

DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábados", "domingos")


def puntos_unicos(puntos):
    """Los reintentos de una misma medida no deben aumentar su peso."""
    agrupados = defaultdict(list)
    for hora, minutos in puntos:
        agrupados[hora].append(minutos)
    return sorted((hora, median(valores)) for hora, valores in agrupados.items())


def resumir_sentido(puntos):
    puntos = puntos_unicos(puntos)
    if not puntos:
        return "sin medidas."
    if len(puntos) == 1:
        hora, minutos = puntos[0]
        return f"solo una medida, {minutos:.0f} min a las {hora:%H:%M}; faltan datos para comparar."

    # Comparaciones locales: jamás presentar la diferencia mañana/noche como ahorro.
    cambios = []
    for i, (hora, minutos) in enumerate(puntos):
        for otra_hora, otros_minutos in puntos[i + 1:]:
            separacion = (otra_hora - hora).total_seconds() / 60
            if separacion > 31:  # tolera un minuto de retraso del recolector
                break
            if separacion < 14:
                continue
            diferencia = otros_minutos - minutos
            if abs(diferencia) >= 5:
                cambios.append((abs(diferencia), -separacion, hora, minutos,
                                otra_hora, otros_minutos))
    if cambios:
        # En empate, prima el menor desplazamiento y después el primer caso del día.
        _, _, hora, minutos, otra_hora, otros_minutos = max(cambios, key=lambda c: c[:2])
        direccion = "menos" if otros_minutos < minutos else "más"
        desplazamiento = (otra_hora - hora).total_seconds() / 60
        return (f"{hora:%H:%M} ({minutos:.0f} min) → {otra_hora:%H:%M} ({otros_minutos:.0f} min). "
                f"{abs(otros_minutos - minutos):.0f} min {direccion} de trayecto "
                f"saliendo {desplazamiento:.0f} min después.")

    # Busca continuidad real: no unir franjas separadas por medidas ausentes.
    estables = []
    for i in range(len(puntos)):
        tramo = [puntos[i]]
        for punto in puntos[i + 1:]:
            if (punto[0] - tramo[-1][0]).total_seconds() > 20 * 60:
                break
            valores = [v for _, v in tramo] + [punto[1]]
            if max(valores) - min(valores) > 2:
                break
            tramo.append(punto)
            duracion = (tramo[-1][0] - tramo[0][0]).total_seconds() / 60
            if duracion >= 45:
                estables.append((duracion, -median(valores), tramo[:]))
    if estables:
        _, _, tramo = max(estables, key=lambda t: t[:2])
        valores = [v for _, v in tramo]
        tiempo = f"{min(valores):.0f}–{max(valores):.0f}" if min(valores) != max(valores) else f"{valores[0]:.0f}"
        return f"tiempos estables de {tramo[0][0]:%H:%M} a {tramo[-1][0]:%H:%M}: {tiempo} min."
    return "sin cambios destacados entre salidas cercanas; no hay una franja estable suficientemente cubierta."


def por_cuarto_hora(puntos):
    agrupados = defaultdict(list)
    for hora, minutos in puntos_unicos(puntos):
        agrupados[(hora.hour * 60 + hora.minute) // 15].append(minutos)
    return {hora: median(valores) for hora, valores in agrupados.items()}


def comparar_historico(datos, historico, fecha):
    """Mediana de diferencias a las mismas horas, con el mismo peso por día.

    Exige tres días equivalentes en seis semanas, cuatro horas de medidas
    actuales (16 cuartos de hora) y al menos un 70 % de coincidencias por día.
    """
    resultados = []
    similares = []
    for sentido in ("ida", "vuelta"):
        actuales = por_cuarto_hora(datos[sentido])
        diferencias = []
        for dia, anteriores in sorted(historico.items(), reverse=True):
            distancia = (fecha.date() - dia).days
            if not 0 < distancia <= 42 or dia.weekday() != fecha.weekday():
                continue
            previos = por_cuarto_hora(anteriores[sentido])
            comunes = actuales.keys() & previos.keys()
            if len(actuales) < 16 or len(comunes) < max(16, len(actuales) * 0.7):
                continue
            diferencias.append(median(actuales[h] - previos[h] for h in comunes))
            if len(diferencias) == 4:
                break
        if len(diferencias) < 3:
            resultados.append(f"{sentido}: histórico insuficiente")
            continue
        diferencia = median(diferencias)
        cambio = "similar" if abs(diferencia) < 3 else f"{abs(diferencia):.0f} min {'más' if diferencia > 0 else 'menos'}"
        if cambio == "similar":
            similares.append(len(diferencias))
        resultados.append(f"{sentido}: {cambio} frente a {len(diferencias)} {DIAS[fecha.weekday()]} previos")
    if len(similares) == 2 and similares[0] == similares[1]:
        return (f"  📅 Ida y vuelta similares a las mismas horas "
                f"de {similares[0]} {DIAS[fecha.weekday()]} previos.")
    return "  📅 A las mismas horas, " + "; ".join(resultados) + "."
