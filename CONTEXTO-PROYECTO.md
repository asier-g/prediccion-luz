# Contexto del proyecto: previsión del precio de la luz en España a 7 días

_Preparado el 2026-10-11 a partir de la investigación del banco de ideas. Es el punto de partida para el agente que desarrolle el proyecto._

## Objetivo
Previsión abierta del precio horario del mercado diario de OMIE (España) de **D+2 a D+7**, con su incertidumbre y su error real publicado, integrada en Home Assistant (HACS) y evcc.

**Para qué:** es un proyecto de portfolio para que el autor entre en un departamento de IA. Tiene que estar en producción, tener algunos usuarios reales y enseñar ML/DL sobre series temporales con resultados medidos con rigor.

**Después, posible comercialización** como API para empresas con consumo flexible (regantes, frío industrial, baterías, flotas). No para particulares: el modelo les ahorra 3–4 €/año frente a reglas gratuitas. **Ninguna decisión de hoy debe cerrar esa puerta:** licencia del código, condiciones de uso de las fuentes de datos y alojamiento.

**Autor:** estudiante de último curso de informática y ciencia de datos. Unas 5 h/semana, desarrollando con un agente de IA. Prefiere ML/DL a visión por computador y distribución por internet antes que vender.

## Lo que ya está demostrado (`baseline/`)
- Backtest con un año fuera de muestra (02-10-2025 a 11-10-2026, 47.160 horas), reentreno mensual y solo la información disponible en D (el precio de D+1 ya publicado).
- **Números a batir (MAE, €/MWh):**

| Método | Total | D+2 | D+7 |
|---|---|---|---|
| Mejor regla: media de 7 días a esa hora | 25,7 | 22,9 | 27,5 |
| Gradient boosting con meteorología | 22,0 | 18,9 | 25,0 |
| MLP 64-64 con meteorología | 21,7 | 18,3 | 25,7 |

- **Sin meteorología, el ML pierde contra la regla.** Lo que aporta valor son las previsiones de viento y sol, no el algoritmo.
- **Decisiones prácticas** (sobrecoste frente a lo óptimo, €/MWh):
  - mejores 4 horas del día: modelo 1,8 frente a "de 13 a 17 h" 3,7 (la madrugada cuesta 70,8);
  - mejor día de la semana: modelo 5,0 frente a "el domingo" 7,5.
- Detalle completo en `baseline/README.md` y `baseline/resultado.txt`.

## Datos

| Fuente | Qué | Acceso | Cuidado con |
|---|---|---|---|
| OMIE `marginalpdbc` | Precio marginal diario; 6ª columna = España | `https://www.omie.es/es/file-download?parents%5B0%5D=marginalpdbc&filename=marginalpdbc_AAAAMMDD.1`, gratis y sin clave | **Desde el 1-10-2025, 96 periodos de 15 min** (antes 24). Días de cambio de hora: 23 o 25 periodos (92 o 100). Uso libre citando la fuente (ver "Condiciones de uso de las fuentes" en `ARQUITECTURA.md`). Descarga lenta: usar 4 hilos como máximo |
| Open-Meteo Previous Runs API | Previsiones emitidas 1–7 días antes (`*_previous_dayK`) | `https://previous-runs-api.open-meteo.com/v1/forecast` | Viento previsto solo desde febrero de 2024. **Verificar la hora exacta de emisión de `previous_dayK`** (posible fuga de unas horas). Gratis **solo sin uso comercial** (< 10.000 llamadas al día); CC BY 4.0, hay que citarlo. Peticiones de varios años tardan minutos |
| Open-Meteo Forecast API | Previsión actual para producción | `https://api.open-meteo.com/v1/forecast` | Mismas condiciones |
| ESIOS (Red Eléctrica) | Previsiones oficiales de demanda, eólica y solar; PVPC | Token personal gratuito (se pide por correo) | Aún no se ha usado. **Por comprobar antes de contar con ella** (tarea 1.6 de `PLAN.md`): si sus previsiones llegan a D+2–D+7 y si guarda cada versión de la previsión o solo la última |
| Gas (MIBGAS, TTF) | Fija el precio en muchas horas | Por investigar | Sin fuente gratuita verificada |

`baseline/datos/` incluye los datos ya descargados (2023 a 11-10-2026), si se copiaron. Si no, se regeneran con `baseline/descarga_datos.py` (15–25 min).

## Competencia a tener en cuenta
- **EpexPredictor** (https://github.com/b3nn0/epexpredictor): gratis y abierto (BSD-3), ya cubre España con LightGBM, Open-Meteo, carga y gas, y API pública sin garantías de servicio. **evcc ya lo integra de forma nativa.** MAE publicado para España a 1 día: 1,68 (unidades sin confirmar, probablemente ct/kWh) con meteorología observada, no prevista. Comprobado el 2026-10-12.
  - **Su API sirve unos 7 días para España, no 1–3** (comprobado el 2026-10-12: 671 cuartos de hora, hasta D+7). El error que publica solo llega a 3 días, así que no se sabe cómo de buena es su previsión de D+4 a D+7: eso lo dirá la comparación (tarea 3.4).
  - **Primera tarea:** guardar cada día su previsión y compararla con la propia.
  - Si no se le gana en ningún horizonte, diferenciarse en cuantiles, precio final por tarifa e integración en español.
- **AleaSoft:** consultora de previsión para empresas desde 1999, en más de 45 mercados, MIBEL incluido. Corto, medio y largo plazo. Precios no publicados. Es la competencia si se comercializa para empresas.
- Energy Price Forecast EU (sin España por ahora), Energyforecast.de (solo Alemania).

## Hoja de ruta sugerida
_Versión inicial. La hoja de ruta viva, con tareas y criterios de aceptación, está en `PLAN.md`._

1. **Repo y canal de datos:** descarga diaria e incremental de OMIE y la meteorología, en un formato ordenado (Parquet o SQLite), con pruebas.
2. **Evaluación como código:** reproducir el baseline como suite fija. El mismo periodo de prueba, métricas (MAE por horizonte, decisiones prácticas) e IC por bootstrap. Ningún modelo nuevo se acepta sin pasar por ella.
3. **Mejoras del modelo, por orden:**
   - previsiones de ESIOS (demanda, eólica, solar);
   - festivos completos (Semana Santa, autonómicos);
   - más puntos meteorológicos;
   - precio del gas;
   - después, deep learning de verdad (N-HiTS o TFT con PyTorch, salida multihorizonte);
   - previsión probabilística (cuantiles 10/50/90, con calibración medida).
4. **Comparación diaria con EpexPredictor** desde la primera semana.
5. **Producción mínima y gratis:**
   - GitHub Actions (gratis en repos públicos) que prevé cada día;
   - JSON estático en GitHub Pages o Cloudflare Pages;
   - web con la previsión y el error real acumulado.
6. **Integraciones:** sensor HACS para Home Assistant y plantilla para evcc (PR a su repo).
7. **Después:** precio final por tarifa (PVPC con 55 % a plazo en 2026; indexadas de Octopus y Som Energia).

## Lecciones del experimento
- La red neuronal de scikit-learn con 300 iteraciones y 13 reentrenos tuvo el portátil (i5-1335U) al 100 % más de 10 minutos, y el ordenador se reinició durante esa ejecución (no se sabe si por eso). Con lotes de 1.024, 60 iteraciones y reentreno trimestral tarda 82 s. El gradient boosting tarda unos 2 s por entrenamiento. **No hace falta GPU.**
- `python -I` no ve los paquetes instalados en el usuario; usar un entorno virtual del proyecto.
- Comparar siempre todos los métodos sobre las mismas filas, y siempre contra reglas simples (Lago et al., 2021: https://arxiv.org/abs/2008.08004).

## Material de referencia (`investigacion/`)
- `01-idea.md`: puntuación, veredicto y respuestas a las preguntas del autor.
- `02-viabilidad.md`: competidores, viabilidad, riesgos y validación.
- `03-mercado-y-monetizacion.md`: usuarios de Home Assistant en España, ahorro medido y monetización.
- `fuentes.md`: todas las URLs.
