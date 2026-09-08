# traffic

El resumen diario destaca una conclusión por sentido y ruta, usando todas las
horas medidas porque los horarios de viaje varían:

- El mayor cambio de al menos 5 minutos entre salidas separadas por 14–31 minutos
  (tolerancia para las medidas que se retrasan). Indica cuánto cambia el trayecto,
  sin confundirlo con llegar antes al destino.
- Si no hay un cambio así, la franja estable más larga: al menos 45 minutos,
  variación máxima de 2 minutos y ningún hueco entre medidas superior a 20 minutos.
  En empate se elige la de menor duración típica del trayecto.
- Comparación por sentido con hasta cuatro días del mismo día de la semana en
  las seis semanas anteriores. Usa medianas de diferencias en cuartos de hora
  coincidentes, con el mismo peso por día. Exige tres días comparables, al menos
  16 cuartos de hora coincidentes y cobertura del 70 % de las horas del día analizado.
  Diferencias inferiores a 3 minutos se describen como similares.

Se avisa cuando faltan datos; las conclusiones describen observaciones, no una
previsión. El gráfico conserva todas las medidas. En Telegram se publica como
detalle y se fija el resumen de texto que lo acompaña.

Vista previa local, sin enviar mensajes:

```sh
python3 grafico_diario.py --fecha 2026-09-07 --no-telegram
```

Comprobaciones:

```sh
python3 -m unittest discover -v
```
