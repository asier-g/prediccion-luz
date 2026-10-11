# Experimento: ¿supera el ML a las reglas obvias al prever el precio de la luz a 2–7 días?

_Realizado: 2026-10-11_

## Datos
- **Precios:** OMIE, precio marginal de España, del 01-01-2023 al 11-10-2026 [F23]. Desde octubre de 2025 el mercado es cuartohorario; se promedia a horas.
- **Meteorología prevista, no la observada:** Open-Meteo Previous Runs API [F24]. Para cada día se usa la previsión emitida *k* días antes:
  - viento a 100 m en Zaragoza, Burgos, Lugo y Albacete;
  - radiación solar en Sevilla, Badajoz y Albacete;
  - temperatura en Madrid.

  Las previsiones de viento solo existen desde febrero de 2024.
- Sin precio del gas, sin previsión de demanda de Red Eléctrica y sin hidráulica: es una primera versión deliberadamente pobre.

Los datos no se suben al repositorio; `descarga_datos.py` los descarga en 15–25 minutos.

## Escenario
- El día D por la tarde ya se conoce el precio de D+1, que OMIE publica hacia las 13:00.
- Se prevé cada hora de D+2 a D+7, solo con la información disponible en D.
- **Prueba:** un año entero sin tocar (02-10-2025 a 11-10-2026; 47.160 horas previstas). Los modelos se reentrenan cada mes con todo lo anterior; la red neuronal, cada 3 meses.

## Resultados

**Error medio absoluto (MAE, €/MWh).** El precio medio en la prueba fue de 79 €/MWh, con una desviación típica de 65.

| Método | Total | D+2 | D+3 | D+4 | D+5 | D+6 | D+7 |
|---|---|---|---|---|---|---|---|
| Regla: repetir el precio de mañana | 27,3 | 19,5 | 25,8 | 28,0 | 29,7 | 30,9 | 30,4 |
| Regla: misma hora de la semana pasada | 28,4 | 28,2 | 28,3 | 28,5 | 28,4 | 28,4 | 28,5 |
| Regla: media de los últimos 7 días a esa hora | 25,7 | 22,9 | 24,5 | 25,8 | 26,6 | 27,1 | 27,5 |
| Gradient boosting **sin** meteorología | 27,8 | 22,3 | 25,8 | 28,4 | 29,5 | 30,4 | 30,6 |
| Gradient boosting **con** meteorología | 22,0 | 18,9 | 20,1 | 21,6 | 22,4 | 23,7 | 25,0 |
| Red neuronal (MLP 64-64) con meteorología | **21,7** | **18,3** | **19,5** | **21,2** | **22,2** | **23,5** | 25,7 |

**Diferencias con la mejor regla (media de 7 días), IC 95 % por bootstrap sobre días:**
- Gradient boosting con meteorología: −3,9 €/MWh [−5,0, −2,7], un 15 % menos de error.
- Red neuronal con meteorología: −4,1 €/MWh [−5,3, −3,0], un 16 % menos.
- Gradient boosting **sin** meteorología: **+2,0** [+0,9, +3,2]. Es peor que la regla.

**Decisión 1: elegir las 4 horas seguidas más baratas de un día** (sobrecoste medio frente a la mejor ventana real, €/MWh):

| Método | Sobrecoste |
|---|---|
| Gradient boosting con meteorología | **1,8** |
| Media de 7 días / red neuronal | 2,1 |
| Regla fija "siempre de 13 a 17 h" | 3,7 |
| Regla fija "siempre de 2 a 6 h" (la madrugada de toda la vida) | **70,8** |

El modelo frente a la regla de 13 a 17 h: −1,9 €/MWh [−2,1, −1,6].

**Decisión 2: elegir el día más barato de D+2 a D+7** (sobrecoste frente al día más barato real, €/MWh):

| Método | Sobrecoste |
|---|---|
| Red neuronal con meteorología | **5,0** |
| Gradient boosting con meteorología | 5,6 |
| Regla fija "el domingo" | 7,5 |
| Media de 7 días / repetir mañana | 22,8 |

La red neuronal frente al domingo: −2,5 €/MWh [−3,8, −1,2].

## Lectura
1. **Sí, el ML supera a las reglas obvias, pero solo con meteorología prevista.** Sin ella, el gradient boosting es *peor* que la media de 7 días. Lo que gana no es el algoritmo sino el dato: cuánto viento y sol habrá.
2. **La red neuronal y el gradient boosting empatan.** Con estos datos, un modelo "deep" no aporta sobre un buen modelo tabular. Lo coherente con la literatura es mejorar las variables antes que el modelo [F25].
3. **La ventaja crece con el horizonte hasta D+6** (de −1 a −4 €/MWh frente a repetir mañana y de −4 a −5 frente a la media de 7 días), y cae en D+7, donde la previsión meteorológica ya es mala.
4. **Para un hogar, el ahorro práctico es pequeño.** Lo que más ahorra es dejar de cargar de madrugada (70,8 €/MWh de sobrecoste) y pasarse a las horas de sol (3,7). Eso lo da una regla gratis o el precio de mañana. El modelo añade 2–2,5 €/MWh más.
5. **Referencia externa:** EpexPredictor publica para España un MAE a 1 día de 1,68 (≈ 16,8 €/MWh si son ct/kWh) con meteorología *observada* [F10]. Aquí, a 2 días y con meteorología *prevista*, el error es de 18,3–18,9: un orden de magnitud similar.

## Coste de cálculo
- Todo el experimento (13 reentrenos de cada gradient boosting y 5 de la red neuronal) tarda **unos 3 minutos** en un portátil con un Intel i5-1335U, sin GPU.
- El gradient boosting se entrena en ~2 s; la red neuronal de scikit-learn, en ~16 s.
- La primera versión de la red (300 iteraciones y 13 reentrenos) tuvo la CPU al 100 % más de 10 minutos. Un modelo grande con PyTorch (N-HiTS, TFT) seguiría entrenando en la CPU en minutos u horas, una vez al mes. **No hace falta GPU.**

## Limitaciones
- Un solo año de prueba, con precios altos en el último trimestre de 2026.
- Solo 7 puntos meteorológicos y sin gas, demanda ni hidráulica: el error mejorable es grande.
- El bootstrap de la decisión 1 trata como independientes días que se solapan; el intervalo real es algo más ancho.
- Se prevé el precio mayorista, no el PVPC ni el precio de una tarifa indexada.

## Cómo reproducirlo
```bash
python descarga_datos.py <carpeta>
python -E -P prevision_omie.py <carpeta>/omie <carpeta>/meteo
```
La salida completa está en `resultado.txt`.
