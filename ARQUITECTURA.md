# Arquitectura

Cómo está organizado el sistema y por qué. Cuando se tome una decisión de diseño, se anota aquí, en "Decisiones".

## Visión general

```
 Fuentes                 Canal de datos            Modelo                    Publicación
 ───────                 ──────────────            ──────                    ───────────
 OMIE ─────────┐
 Open-Meteo ───┼──► descarga incremental ──► variables con ──► entrenamiento ──► previsión diaria ──► JSON público
 ESIOS ────────┤      + Parquet               corte en D       (mensual)          (cada día)          (GitHub Pages)
 Gas ──────────┘                                  │                                    │                   │
                                                  ▼                                    ▼                   ▼
                                       suite de evaluación ◄────────── archivo de previsiones ──► web, HACS, evcc
                                         (informes/)                     emitidas (solo crece)
```

## Estructura del repositorio (objetivo)

```
prediccion-luz/
├── src/prediccion_luz/
│   ├── fuentes/          # una por fuente: omie.py, openmeteo.py, esios.py, gas.py
│   ├── almacen.py        # lectura y escritura de Parquet
│   ├── variables.py      # construcción de variables con corte temporal
│   ├── modelos/          # reglas.py, gbm.py, mlp.py, nhits.py...
│   ├── evaluacion/       # backtest.py, metricas.py, decisiones.py, bootstrap.py
│   └── prevision.py      # previsión del día y exportación a JSON
├── tests/                # pruebas y ficheros de ejemplo pequeños
├── informes/             # resultados de la suite, versionados
├── web/                  # página estática
├── integraciones/        # home-assistant/, evcc/
├── baseline/             # experimento original, congelado: no se modifica
├── datos/                # ignorado por git
└── .github/workflows/    # pruebas, previsión diaria, reentreno, archivo de EpexPredictor
```

## Principios

1. **Todo dato lleva su momento de disponibilidad.** Además de la hora a la que se refiere, cada fila sabe cuándo se pudo conocer. Las variables se construyen con un corte: "lo que se sabía el día D a las 15:00 (Madrid)". Es la defensa principal contra las fugas.
2. **Datos crudos inmutables, datos procesados regenerables.** Lo descargado se guarda tal cual; las tablas procesadas se pueden borrar y reconstruir.
3. **Descargas incrementales e idempotentes.** Ejecutar dos veces no cambia nada ni vuelve a descargar.
4. **Una sola suite de evaluación.** Cualquier modelo, regla o variable nueva se mide con el mismo código, periodo y filas. Los resultados se guardan en `informes/` para que la comparación sea reproducible.
5. **Las previsiones emitidas no se regeneran.** El error real publicado se calcula sobre lo que se publicó ese día, no sobre un recálculo posterior.
6. **Producción en CPU y coste cero.** La previsión diaria y el reentreno mensual corren en GitHub Actions sin GPU. Los experimentos pesados (deep learning, búsqueda de hiperparámetros) pueden usar GPU gratuita (Kaggle o Colab), siempre que el modelo elegido se pueda reentrenar en CPU.

## Datos

### Tiempo
- Se guarda en UTC y se convierte a `Europe/Madrid` solo para presentar y para variables de calendario.
- OMIE se guarda con su resolución nativa (15 min desde el 1-10-2025, 60 min antes). El objetivo del modelo es el **precio horario**, media de los cuartos de hora.
- Días de cambio de hora: 23 o 25 horas (92 o 100 cuartos). No se descartan.

### Tablas
| Tabla | Clave | Columnas principales |
|---|---|---|
| `omie_precio` | inicio del periodo (UTC) | precio España (€/MWh), duración del periodo, fecha de publicación |
| `meteo_prevista` | punto, variable, hora prevista (UTC), antelación k | valor, hora de emisión estimada |
| `esios_prevision` | indicador, hora prevista, hora de emisión | valor |
| `previsiones_emitidas` | fecha de emisión, hora prevista, versión del modelo | p10, p50, p90 |

### Disponibilidad en el día D
- OMIE publica el precio de D+1 hacia las 13:00 de D.
- Open-Meteo `previous_dayK`: **pendiente de verificar** (tarea 1.4 de `PLAN.md`).
- ESIOS: pendiente de verificar al incorporarlo (tarea 3.1).

## Modelo
- **Horizontes:** D+2 a D+7, una previsión por hora.
- **Reentreno:** mensual, con ventana creciente.
- **Referencia obligatoria:** las reglas simples se evalúan siempre junto a cualquier modelo.
- **Variables del baseline**, de partida: hora, día de la semana, mes, festivo, horizonte k, precio de D+1 a esa hora, media de 7 días a esa hora, misma hora de la semana anterior, nivel medio de D+1 y de 7 días, rango de D+1, y viento, sol y temperatura previstos con antelación k.

## Publicación
- **Previsión diaria:** GitHub Actions, después de que OMIE publique D+1. Comprueba que el dato existe antes de prever.
- **JSON público** (borrador del esquema, versión 1):
  ```json
  {
    "version_esquema": 1,
    "emitida": "2026-10-11T13:30:00+02:00",
    "modelo": "gbm-2026-10",
    "unidad": "EUR/MWh",
    "zona": "ES",
    "horas": [
      {"inicio": "2026-10-13T00:00:00+02:00", "horizonte": 2, "p10": 61.2, "p50": 72.5, "p90": 88.0}
    ]
  }
  ```
- **Atribución obligatoria** en la web y el JSON: Open-Meteo (CC BY 4.0) y OMIE.

## Decisiones
Formato: fecha, decisión, motivo. Las abiertas se resuelven en la tarea indicada.

| Fecha | Decisión | Motivo |
|---|---|---|
| 2026-10-11 | Python 3.12, paquete en `src/`, `pytest` y `ruff` | Estándar y suficiente; sin dependencias pesadas hasta que hagan falta (pendiente de revisar por el autor) |
| 2026-10-11 | Parquet para los datos | Columnar, rápido con pandas o polars, y sin servidor (pendiente de revisar por el autor) |
| 2026-10-11 | Los datos no se publican en el repositorio | Condiciones de reutilización de OMIE sin verificar (pendiente de revisar por el autor) |
| Abierta (1.1) | pandas o polars | Decidir al crear el esqueleto |
| Abierta (4.1) | Dónde viven los datos en producción: caché de Actions, rama aparte o *release* | Depende de las condiciones de OMIE y del tamaño |
