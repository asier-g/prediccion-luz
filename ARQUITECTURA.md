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
├── baseline/             # experimento original, congelado: no se modifica
├── datos/                # ignorado por git
└── .github/workflows/    # pruebas, previsión diaria, reentreno, archivo de EpexPredictor
```

- **Rama `archivo`:** lo que no se puede regenerar (previsiones de EpexPredictor, previsiones emitidas, meteorología usada al prever). Un commit diario con ficheros pequeños. Lo de EpexPredictor, y su comparación con el modelo, va **cifrado** con la clave del secreto `CLAVE_ARCHIVO`: es privado aunque el repo sea público.
- **Integraciones:** en repos aparte con licencia MIT. HACS exige un repo propio y lo de evcc es un PR a su repositorio.

## Principios

1. **Todo dato lleva su momento de disponibilidad.** Además de la hora a la que se refiere, cada fila sabe cuándo se pudo conocer. Las variables se construyen con un corte: "lo que se sabía el día D a las 15:00 (Madrid)". Es la defensa principal contra las fugas.
2. **Datos crudos inmutables, datos procesados regenerables.** Lo descargado se guarda tal cual; las tablas procesadas se pueden borrar y reconstruir.
3. **Descargas incrementales e idempotentes.** Ejecutar dos veces no cambia nada ni vuelve a descargar.
4. **Una sola suite de evaluación.** Cualquier modelo, regla o variable nueva se mide con el mismo código, periodo y filas. Los resultados se guardan en `informes/` para que la comparación sea reproducible. El año fijo sirve para **seleccionar**; la **confirmación** se hace con previsiones en sombra (ver `PLAN.md`, fase 4), porque reutilizar el mismo año en muchos experimentos sobreajusta a ese año.
5. **Las previsiones emitidas no se regeneran.** El error real publicado se calcula sobre lo que se publicó ese día, no sobre un recálculo posterior.
6. **Producción en CPU y coste cero.** La previsión diaria y el reentreno mensual corren en GitHub Actions sin GPU. Los experimentos pesados (deep learning, búsqueda de hiperparámetros) pueden usar GPU gratuita (Kaggle o Colab), siempre que el modelo elegido se pueda reentrenar en CPU.
7. **El modelo depende de variables, no de proveedores.** Cada fuente vive en su módulo de `fuentes/` y escribe en una tabla común (por ejemplo, `meteo_prevista` con una columna de proveedor). Las variables y los modelos nunca llaman a una fuente directamente. Así, cambiar de proveedor (Open-Meteo → ECMWF, ESIOS → ENTSO-E) es un experimento medible en la suite, no una reescritura.

## Datos

### Tiempo
- Se guarda en UTC y se convierte a `Europe/Madrid` solo para presentar y para variables de calendario.
- OMIE se guarda con su resolución nativa (15 min desde el 1-10-2025, 60 min antes). El objetivo del modelo es el **precio horario**, media de los cuartos de hora.
- Días de cambio de hora: 23 o 25 horas (92 o 100 cuartos). No se descartan. Cómo se representan en las variables (la variable "hora") y en las decisiones 1 y 2, que suponen días de 24 horas, se decide en la tarea 1.3.

### Tablas
| Tabla | Clave | Columnas principales |
|---|---|---|
| `omie_precio` | inicio del periodo (UTC) | precio España (€/MWh), duración del periodo, fecha de publicación |
| `meteo_prevista` | proveedor, punto, variable, hora de emisión (UTC), hora prevista (UTC) | valor. La antelación k se calcula a partir de las dos horas. Para Open-Meteo, la hora de emisión es la que se determine en la tarea 1.5 |
| `prevision_red` | proveedor (ESIOS, ENTSO-E), indicador, hora de emisión, hora prevista | valor |
| `epexpredictor_archivo` | hora de captura, hora prevista | precio previsto (€/MWh, cuartos de hora), `knownUntil` (hasta dónde el precio ya es real). Un fichero cifrado por día con la respuesta tal cual |
| `previsiones_emitidas` | fecha de emisión, hora prevista, modelo, en producción o en sombra | p10, p50, p90 |

### Disponibilidad en el día D
- OMIE publica el precio de D+1 hacia las 13:00 de D.
- Open-Meteo `previous_dayK`: **pendiente de verificar** (tarea 1.5 de `PLAN.md`).
- ESIOS y ENTSO-E: pendiente de verificar, incluido si guardan cada versión de la previsión (tarea 1.6).

## Modelo
- **Horizontes:** D+2 a D+7, una previsión por hora.
- **Reentreno:** mensual, con ventana creciente.
- **En la evaluación, el reentreno se agrupa por fecha de emisión D:** el modelo que prevé desde D solo se entrena con objetivos conocidos en D (hasta D+1). El baseline agrupaba por fecha prevista T, lo que dejaba ver hasta 6 días de precios futuros al entrenar.
- **En producción, el reentreno no se aprueba con la suite** (que evalúa el procedimiento, no un modelo concreto), sino comprobando los datos del mes nuevo y que las previsiones del modelo nuevo no se separen de más de las del actual (tarea 5.3).
- **Referencia obligatoria:** las reglas simples se evalúan siempre junto a cualquier modelo.
- **Variables del baseline**, de partida: hora, día de la semana, mes, festivo, horizonte k, precio de D+1 a esa hora, media de 7 días a esa hora, misma hora de la semana anterior, nivel medio de D+1 y de 7 días, rango de D+1, y viento, sol y temperatura previstos con antelación k.

## Publicación
- **Previsión diaria:** GitHub Actions, después del corte y con margen, porque el cron de GitHub se retrasa a menudo. Comprueba que OMIE ha publicado D+1 antes de prever y reintenta si no. Archiva la previsión y la meteorología usada en la rama `archivo`.
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
  En la producción mínima (fase 3), `p10` y `p90` van a `null`.
- **Atribución obligatoria** en la web y el JSON: Open-Meteo (CC BY 4.0) y OMIE.

## Condiciones de uso de las fuentes
Antes de añadir una fuente nueva, se registra aquí. El agente busca las condiciones, cita la frase exacta y marca la fila como "pendiente de revisar por el autor". El autor comprueba la cita y la marca como verificada.

| Fuente | Uso en el proyecto | Uso gratuito actual | Uso comercial | Atribución | Estado |
|---|---|---|---|---|---|
| OMIE | Precio objetivo y variables | Sí | **Probablemente sí**: uso libre sin excluir el comercial (cita 1) | Obligatoria | Cita verificada por el autor el 2026-10-12. Confirmar por escrito antes de cobrar |
| Open-Meteo, API gratuita | Meteorología prevista | Sí, si no hay suscripciones ni publicidad (cita 2) | **No**: plan de pago desde unos 29 $/mes (blog de Open-Meteo, sin confirmar en su web) | CC BY 4.0 | Cita verificada por el autor el 2026-10-12. El precio del plan de pago sigue sin confirmar |
| ECMWF, datos abiertos | Posible sustituto de Open-Meteo (tarea 4.4) | Sí | **Sí** (cita 3). Su portal solo guarda ~12 ejecuciones, pero las copias en AWS (desde 2023-01-18) y Azure (desde 2022-01-21, según Herbie) guardan el histórico. **El viento a 100 m y la radiación solar solo existen desde mediados de 2024** (ver nota) | CC BY 4.0 y condiciones de uso del ECMWF | Cita verificada por el autor el 2026-10-12. Leer sus condiciones de uso completas antes de cobrar |
| ESIOS (Red Eléctrica) | Previsiones de demanda, eólica y solar (tareas 1.6 y 4.1) | Sí, con token personal. Se puede dar acceso público a proyectos que usen sus datos si se sirven desde un almacén propio, no desde REE (cita 5) | **Sin confirmar**. Las condiciones del token no lo mencionan; el aviso legal de ree.es prohíbe copiar su contenido con fines comerciales | Sin confirmar | Token recibido el 2026-10-12 con las condiciones de la cita 5, pendiente de revisar por el autor. 👤 Pendiente: leer el aviso legal de ESIOS y preguntar por correo por el uso comercial |
| MIBGAS | Precio del gas (tarea 4.5) | Probablemente sí | **Dudoso**: uso libre citando la fuente, pero también exige autorización previa (cita 4) | Obligatoria | Cita verificada por el autor el 2026-10-12. Sigue siendo dudoso: preguntar antes de usarlo |
| TTF (ICE Endex) | Precio del gas, alternativa | Sin investigar | Probablemente de pago | Sin investigar | Sin investigar |
| EpexPredictor, API pública | Solo comparación (tareas 1.2 y 3.4), no entra en el modelo | Sí, "uso razonable" y sin garantías (cita 6) | No aplica: no forma parte del producto | Citar el proyecto si se publica la comparación | Leído el 2026-10-12. El archivo es privado (cifrado) y hace 1 petición al día, así que no hace falta avisar a su autor. Pendiente de revisar por el autor |

**Citas literales:**
1. OMIE, [aviso legal](https://www.omie.es/es/aviso-legal): "la Información de carácter público y gratuito puede ser utilizada libremente", respetando íntegramente su contenido original; "En caso de que se utilice la información de la página Web de OMIE en su formato original, se debe citar la fuente."
2. Open-Meteo, [condiciones](https://open-meteo.com/en/terms): uso no comercial es "Using our service for private or non-profit websites or apps that do not have subscriptions or advertising"; es comercial "Operating websites or apps that have subscriptions or display advertisements".
3. ECMWF, [datos abiertos](https://www.ecmwf.int/en/forecasts/datasets/open-data): "the data may be redistributed and used commercially, subject to appropriate attribution". Su licencia estándar parece limitar la redistribución: revisar antes de redistribuir los datos tal cual.
4. MIBGAS, [aviso legal](https://www.mibgas.es/es/cccontent/aviso-legal): "Sin citar la fuente queda prohibida la reproducción total o parcial, explotación, distribución" y "Cualquier uso no autorizado previamente se considera un incumplimiento grave de los derechos de propiedad intelectual".
5. ESIOS, condiciones enviadas con el token (correo del 2026-10-12): "Este token se emite para uso personal del solicitante"; "Si va a dar acceso público a los proyectos desarrollados por Vd. [...] debe llevarse la información que devuelve la API a un servidor de su propiedad, de tal forma que esas aplicaciones, páginas o scripts accedan a los datos almacenados en su servidor y no a los sistemas de REE"; "no realice peticiones masivas, redundantes o innecesarias, tal como información ya descargada con anterioridad o información que se sabe que no se ha modificado, así como peticiones a indicadores inexistentes".
6. EpexPredictor, [README](https://github.com/b3nn0/EpexPredictor) (leído el 2026-10-12): "There are no guarantees given whatsoever - it might work for you or not"; "I might stop or block this service at any time. Fair use is expected!"

**Nota sobre el ECMWF** (comprobado el 2026-10-12 en los ficheros `.index` del bucket `s3://ecmwf-forecasts`, ejecución de las 00z, paso de 48 h):
- 2023-02-01 (0,4°) y 2024-03-01 (0,25°): hay viento a 10 m (`10u`, `10v`) y temperatura (`2t`), pero **no** viento a 100 m (`100u`, `100v`) ni radiación solar (`ssrd`).
- 2024-08-01, 2024-09-01 y 2025-03-01: ya están `100u`, `100v` y `ssrd`.
- Por tanto, el histórico útil para este modelo empieza entre marzo y agosto de 2024: unos 2 años, no 3–4.

**Idea si se comercializa:** usar el histórico del ECMWF en AWS como fuente meteorológica utilizable comercialmente, en lugar del plan de pago de Open-Meteo. Inconvenientes: los ficheros son globales (hay que descargar solo los campos necesarios usando los `.index`), el volumen total ronda los 100–200 GB (ESTIMACIÓN) y AWS limita la frecuencia de peticiones.

## Decisiones
Formato: fecha, decisión, motivo. Las abiertas se resuelven en la tarea indicada.

| Fecha | Decisión | Motivo |
|---|---|---|
| 2026-10-11 | Python 3.12, paquete en `src/`, `pytest` y `ruff` | Estándar y suficiente; sin dependencias pesadas hasta que hagan falta (pendiente de revisar por el autor) |
| 2026-10-11 | Parquet para los datos | Columnar, rápido con pandas o polars, y sin servidor (pendiente de revisar por el autor) |
| 2026-10-11 | Los datos no se publican en el repositorio | OMIE permite el uso libre citando la fuente (ver "Condiciones de uso de las fuentes"), así que el motivo ya no es legal: el tamaño crece cada día y el código queda separado de los datos (pendiente de revisar por el autor) |
| 2026-10-12 | Producción mínima (fase 3) antes de las mejoras del modelo | Lo único verdaderamente fuera de muestra son las previsiones que se emiten desde hoy, y el error real publicado solo se acumula desde que hay producción (pendiente de revisar por el autor) |
| 2026-10-12 | Lo que no se puede regenerar se guarda en la rama `archivo` con un commit diario; lo regenerable (histórico de OMIE y Open-Meteo) se descarga y se guarda en la caché de Actions | El archivo es pequeño y no se puede recuperar si se pierde; el commit diario quizá evite también que GitHub desactive los workflows programados tras 60 días sin actividad: su documentación solo habla de "repository activity" y no está confirmado que cuenten los commits fuera de `main` (pendiente de revisar por el autor) |
| 2026-10-12 | pandas (con pyarrow para Parquet), no polars. Se añade en la 1.3, la primera tarea que lo usa | Los datos son pequeños (≈9.000 h al año de OMIE) y la velocidad de polars no hace falta; scikit-learn y las librerías de deep learning de la 4.7 trabajan con pandas (pendiente de revisar por el autor) |
| 2026-10-12 | `requirements.txt` es la única lista de versiones, fijadas con `==` e incluidas `pytest` y `ruff`; `pyproject.toml` no declara dependencias y el paquete se instala con `pip install -e . --no-deps` | Es una aplicación, no una librería que se publique: tener las versiones en dos sitios acabaría desincronizándolas. Un `requirements-dev.txt` aparte sería otro fichero que mantener, para ahorrar unos segundos de instalación (pendiente de revisar por el autor) |
| 2026-10-12 | Ruff con las reglas `E, F, I, B, UP, DTZ`, sin tocar `baseline/` | `DTZ` prohíbe fechas sin zona horaria, que es como se cuelan los errores de UTC y de corte temporal (pendiente de revisar por el autor) |
| 2026-10-12 | Las pruebas no pueden abrir conexiones de red: un *fixture* de `tests/conftest.py` hace fallar `socket.connect` | Hace cumplir solo la regla de que las pruebas no llaman a APIs reales, sin depender de `pytest-socket` (pendiente de revisar por el autor) |
| 2026-10-12 | El archivo de EpexPredictor y su comparación se guardan cifrados (Fernet, de `cryptography`) en la rama `archivo` del repo público. La clave está en el secreto `CLAVE_ARCHIVO`, en el `.env` local y en un gestor de contraseñas | El autor quiere que sean privados. Un repo privado aparte obliga a mantener dos repos; los artefactos y la caché de Actions caducan; el portátil no está encendido cada día. Riesgo: si se pierde la clave, el archivo es ilegible (pendiente de revisar por el autor) |
| 2026-10-12 | EpexPredictor se captura entre las 15:00 y las 18:00 de Madrid, con tres crons UTC (13:07, 14:07 y 15:07) y un fichero por día; se guarda la hora real de captura | El cron va en UTC y Madrid cambia de hora: el script decide con `Europe/Madrid`. Capturar después de las 15:00 da a EpexPredictor más información, nunca menos, así que el retraso perjudica a nuestro modelo en la comparación, no lo favorece. La 3.4 decide qué capturas tardías acepta (pendiente de revisar por el autor) |
| 2026-10-12 | Se guarda la respuesta de EpexPredictor tal cual (resolución nativa, €/MWh, UTC), dentro de un sobre con la URL y la hora de captura, y nunca se sobrescribe | Principio 2: datos crudos inmutables. Lo que se publicó ese día no se puede volver a descargar (pendiente de revisar por el autor) |
| 2026-10-12 | HTTP con `urllib` de la biblioteca estándar, sin `requests` | Una petición al día no justifica otra dependencia (pendiente de revisar por el autor) |
| 2026-10-12 | `tzdata` en `requirements.txt` | En Windows, `zoneinfo` no encuentra `Europe/Madrid` sin él (pendiente de revisar por el autor) |
| Abierta (1.3) | Cómo se representan los días de 23 y 25 horas en las variables y en las decisiones | Decidir al implementar OMIE |
| Abierta (2.2) | Margen δ de "no empeora" y semanas de sombra (provisional: δ = 1 €/MWh y 8 semanas) | Calibrarlos con la variabilidad real de las diferencias diarias de error que mida la suite |
| Abierta (1.5) | Qué API de Open-Meteo se usa al prever en producción | Entrenar con una API y prever con otra puede mezclar ejecuciones o modelos distintos |
