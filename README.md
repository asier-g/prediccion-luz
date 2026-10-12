# Previsión del precio de la luz en España a 7 días

Previsión abierta del precio horario del mercado diario de OMIE (España) de **2 a 7 días vista**, con su incertidumbre y su error real publicado.

> **Estado:** en desarrollo. Por ahora hay un experimento base; el canal de datos y la previsión diaria están en construcción (ver [PLAN.md](PLAN.md)).

## Por qué
El precio de mañana se publica hacia las 13:00. Más allá no hay nada en las herramientas que se usan en España. Quien carga un coche eléctrico, una batería o la aerotermia con una tarifa indexada no puede elegir el mejor **día** de la semana, solo la mejor hora de mañana.

## Resultados del experimento base
Un año entero fuera de muestra (02-10-2025 a 11-10-2026, 47.160 horas), con solo la información disponible el día de la previsión. Error medio absoluto en €/MWh (precio medio en la prueba: 79 €/MWh):

| Método | Total | D+2 | D+7 |
|---|---|---|---|
| Mejor regla simple: media de 7 días a esa hora | 25,7 | 22,9 | 27,5 |
| Gradient boosting con meteorología prevista | 22,0 | 18,9 | 25,0 |
| Red neuronal (MLP) con meteorología prevista | **21,7** | **18,3** | 25,7 |

- El ML reduce el error un 15–16 % frente a la mejor regla (IC 95 % por debajo de cero).
- **Sin meteorología prevista, el ML pierde contra la regla.** El valor está en saber cuánto viento y sol habrá.

Detalle, decisiones prácticas y limitaciones en [baseline/README.md](baseline/README.md).

## Estructura
- [baseline/](baseline/): experimento original, reproducible.
- [PLAN.md](PLAN.md): pasos a seguir.
- [ARQUITECTURA.md](ARQUITECTURA.md): diseño del sistema y decisiones.
- [CONTEXTO-PROYECTO.md](CONTEXTO-PROYECTO.md): objetivo, datos y competencia.

## Reproducir el experimento base
```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # en Linux/macOS: .venv/bin/pip
.venv/Scripts/python baseline/descarga_datos.py datos   # 15–25 min
.venv/Scripts/python baseline/prevision_omie.py datos/omie datos/meteo
```

## Fuentes de datos
- Precios: [OMIE](https://www.omie.es/), mercado diario.
- Meteorología prevista: [Open-Meteo](https://open-meteo.com/), Previous Runs API, con licencia [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

## Licencia
Por ahora, todos los derechos reservados. Las integraciones para Home Assistant y evcc se publicarán con licencia abierta.

## Aviso
Es una previsión orientativa, no el precio oficial. El precio oficial es el que publica OMIE.
