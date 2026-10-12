# Plan de trabajo

Pasos para llevar el baseline a producción. El porqué de cada paso está en `CONTEXTO-PROYECTO.md`; el cómo, en `ARQUITECTURA.md`.

## Cómo usar este plan
- Las tareas van en orden dentro de cada fase. Cada tarea cabe en una sesión de trabajo y acaba en un PR.
- Al terminar una tarea, márcala con `[x]`, la fecha y el enlace al PR, **en el mismo PR**.
- Si una tarea resulta mayor de lo previsto, divídela aquí antes de seguir.
- Las tareas marcadas con 👤 necesitan al autor (cuentas, tokens, decisiones). El agente no puede hacerlas solo.
- "Aceptado" significa que se cumple el criterio escrito en la tarea. Sin criterio cumplido, la tarea no está hecha.

**Por qué este orden:** lo único verdaderamente fuera de muestra son las previsiones que se emiten desde hoy en adelante, y el error real publicado solo se acumula desde que hay producción. Por eso la producción mínima (fase 3) va antes de las mejoras del modelo (fase 4), y los archivos que no se pueden recuperar después (EpexPredictor) empiezan en la fase 1.

## Fase 0. Preparación
- [x] Repositorio, baseline, `CONTEXTO-PROYECTO.md` y `CLAUDE.md` (2026-10-11).
- [x] `README.md`, `PLAN.md` y `ARQUITECTURA.md` (2026-10-12).
- [x] Licencia (2026-10-12): el repo principal queda **sin licencia** (todos los derechos reservados) para no cerrar una comercialización futura. Las integraciones de la fase 6 irán en repos aparte con MIT.
- [ ] 👤 Configurar el entorno en la nube de Claude Code: red **Custom** con `www.omie.es`, `*.open-meteo.com` y `epexpredictor.batzill.com`, más la lista por defecto.
- [ ] 👤 Revisar la tabla "Condiciones de uso de las fuentes" de `ARQUITECTURA.md` y marcar como verificadas las filas cuya cita sea correcta.
- [ ] 👤 Pedir el token personal de ESIOS (consultasios@ree.es) y guardarlo como secreto, nunca en el repo. En el mismo correo, preguntar si se pueden usar sus datos en un servicio de pago. Leer el aviso legal de ESIOS en el navegador y completar su fila.
- [ ] 👤 **Antes de la fase 8:** pedir a OMIE confirmación por escrito de que su aviso legal permite el uso comercial (el texto dice "uso libre" sin excluirlo).

## Fase 1. Canal de datos y archivos
- [ ] **1.1 Esqueleto del paquete.** `pyproject.toml`, paquete en `src/prediccion_luz/`, `pytest` y `ruff`. Workflow de GitHub Actions que pasa las pruebas en cada PR.
  Aceptado: `pytest` pasa en local y en Actions.
- [ ] **1.2 Archivo diario de EpexPredictor.** Workflow diario que guarda su previsión para España **a la hora de nuestro corte** (D a las 15:00, Madrid), para que la comparación de la 2.4 sea justa. Se guarda con un commit en la rama `archivo` (decisión de `ARQUITECTURA.md`), lo que además mantiene el repo activo: GitHub desactiva los workflows programados tras 60 días sin actividad. El archivo es público: avisar a su autor (*issue* o correo) al empezar.
  Aceptado: el workflow guarda un fichero por día sin intervención durante una semana.
- [ ] **1.3 OMIE.** Descarga incremental (solo los días que faltan, 4 hilos como máximo) y lectura de `marginalpdbc` a una tabla con resolución nativa (24, 23, 25, 96, 92 o 100 periodos) y otra horaria. Guardado en Parquet. **Decidir y anotar en `ARQUITECTURA.md`** cómo se representan los días de 23 y 25 horas en las variables y en las decisiones 1 y 2 (el baseline descarta los de 23 y desalinea los de 25).
  Aceptado: pruebas con ficheros de ejemplo pequeños para cada número de periodos, incluidos los cambios de hora antes y después del 1-10-2025. Los precios horarios coinciden con los del baseline en los días sin cambio de hora.
- [ ] **1.4 Open-Meteo Previous Runs.** Descarga incremental de los puntos actuales a la tabla `meteo_prevista` (clave: proveedor, punto, variable, hora de emisión, hora prevista), en Parquet. La descarga del histórico se reparte en varios días si hace falta: una petición con más de 10 variables o más de 2 semanas cuenta como varias llamadas, y el límite gratuito es de 10.000 al día.
  Aceptado: pruebas de lectura y de que una segunda ejecución no vuelve a descargar lo que ya hay.
- [ ] **1.5 Hora de emisión de `previous_dayK` y API de producción.** Averiguar con qué ejecución del modelo se corresponde `previous_day2` para una hora T y si estaba disponible el día D por la tarde. Decidir qué API se usa al prever en producción: entrenar con la Previous Runs API y prever con la Forecast API puede mezclar ejecuciones o modelos distintos; usar la Previous Runs API también en producción lo evita.
  Aceptado: conclusión y fuente documentadas en `ARQUITECTURA.md`. Si hay fuga, ajustar el corte y anotarlo.

## Fase 2. Evaluación como código
- [ ] **2.1 Reglas y modelos del baseline sobre el nuevo canal.** Reglas simples, gradient boosting con y sin meteorología, y MLP, con el mismo procedimiento que el baseline.
  Aceptado: el MAE total de cada método queda a ±0,3 €/MWh del de `baseline/resultado.txt`. Si no, explicar la diferencia.
- [ ] **2.2 Suite de evaluación fija.** Periodo de prueba, reentreno mensual con ventana creciente **agrupado por fecha de emisión D** (el baseline agrupa por fecha prevista T, lo que deja ver hasta 6 días de precios futuros al entrenar), MAE total y por horizonte, decisiones 1 y 2, e IC 95 % por bootstrap **por bloques** de días. Un comando la ejecuta y guarda el resultado en `informes/`.
  Aceptado: la tabla de `informes/` reproduce la 2.1, añade los IC y explica la diferencia con el baseline por el cambio de agrupación.
- [ ] **2.3 Prueba contra fugas.** Comprobar automáticamente dos cosas: que ninguna variable usa información posterior al corte del día D, y que **ningún modelo que prevé desde D se ha entrenado con objetivos posteriores a D+1**.
  Aceptado: la prueba falla si se introduce a propósito una variable con fuga, y también si se agrupa el reentreno por fecha prevista.
- [ ] **2.4 Comparación con EpexPredictor.** Con el archivo de la 1.2, MAE en D+2 y D+3 sobre las mismas horas.
  Aceptado: tabla en `informes/`, actualizable con un comando.

## Fase 3. Producción mínima
El mejor modelo de la fase 2 (gradient boosting con meteorología), solo la mediana y un JSON. Desde aquí, cada previsión archivada es una prueba real fuera de muestra.
- [ ] **3.1 Previsión diaria en GitHub Actions.** Se lanza después del corte, con margen: el cron de GitHub se retrasa a menudo. Comprueba que OMIE ha publicado D+1 antes de prever y reintenta si no. Guarda en la rama `archivo` la previsión emitida y la meteorología usada para hacerla.
  Aceptado: una semana de previsiones archivadas sin intervención.
- [ ] **3.2 JSON público** en GitHub Pages, con el esquema versionado de `ARQUITECTURA.md` (`p10` y `p90` a `null` hasta la fase 5).
- [ ] **3.3 Error real acumulado.** Cada día, comparar las previsiones archivadas con el precio real publicado por OMIE y guardar el MAE por horizonte.
  Aceptado: tabla en `informes/` y en el JSON, actualizada sola.
- [ ] **3.4 Modelos en sombra.** Poder ejecutar cada día uno o varios modelos candidatos junto al de producción, archivando sus previsiones sin publicarlas.
  Aceptado: un candidato de prueba archivado durante una semana junto al de producción.
- [ ] **3.5 Avisos de fallo.** Si la previsión de un día falla, se abre un *issue* automáticamente.

## Fase 4. Mejoras del modelo
**Cómo se acepta una mejora.** El año fijo de la suite sirve para **seleccionar**; las previsiones en sombra (3.4) sirven para **confirmar**. Usar el mismo año para aceptar muchos experimentos sobreajusta a ese año, aunque cada uno tenga su IC.
1. **Selección:** la mejora baja el MAE con el IC 95 % por debajo de cero frente al mejor modelo actual, sobre las mismas filas del año fijo.
2. **Confirmación:** pasa a sombra y se publica si, tras al menos 8 semanas, no es peor que el modelo de producción.
3. **Excepciones**, que cada tarea indica:
   - mejoras que afectan a pocos días (festivos, cambios de hora): se evalúan **solo sobre los días afectados**;
   - cambios de proveedor por motivos de licencia o de fugas (ECMWF): basta con que **no empeore**;
   - previsión probabilística: tiene su propio criterio de cobertura (4.6).

Si una mejora no se acepta, se anota igualmente en `informes/` y se descarta.

- [ ] **4.1 Previsiones de demanda, eólica y solar.** Antes de integrar nada, comprobar en ESIOS y en ENTSO-E (plataforma de transparencia):
  - qué horizontes publican: muchas previsiones son solo a D+1 y no existen el día D para D+2 a D+7;
  - si guardan cada versión de la previsión o solo la última. Si solo guardan la última, su histórico tiene fuga y no sirve para entrenar: hay que **empezar a archivarlo cada día de inmediato** en la rama `archivo` y aplazar el experimento hasta tener histórico suficiente;
  - sus condiciones de uso, también comerciales.

  Aceptado: conclusión documentada en `ARQUITECTURA.md` y, según ella, el experimento hecho o el archivo diario en marcha.
- [ ] **4.2 Festivos completos:** Semana Santa, festivos autonómicos ponderados por población y puentes. Se evalúa solo sobre los días afectados.
- [ ] **4.3 Hidráulica.** Reservas hidroeléctricas: pesan mucho en el precio español. Antes: encontrar la fuente (Red Eléctrica o el boletín hidrológico semanal del Ministerio), su retraso de publicación y sus condiciones de uso.
- [ ] **4.4 ECMWF y más puntos meteorológicos.** Ingesta de los datos abiertos del ECMWF desde AWS (solo los campos necesarios, usando los `.index`; histórico útil desde mediados de 2024) y comparación con Open-Meteo en la suite, con más puntos o una rejilla resumida por región. Ojo:
  - los pasos son de 3 h hasta las 144 h y de 6 h después, así que D+7 hay que interpolarlo;
  - la radiación viene acumulada desde el inicio de la ejecución: hay que restar pasos;
  - con Open-Meteo, una rejilla de muchos puntos puede superar el límite de 10.000 llamadas al día.

  Aceptado: tabla en `informes/` con Open-Meteo frente a ECMWF sobre las mismas filas. Si el ECMWF no empeora, pasar a él: permite uso comercial y su hora de emisión es exacta.
- [ ] **4.5 Precio del gas** (MIBGAS o TTF). Antes: encontrar una fuente gratuita con histórico y condiciones de uso claras.
- [ ] **4.6 Previsión probabilística.** Cuantiles 10, 50 y 90. Medir la cobertura y la pérdida *pinball* **por horizonte**: una cobertura global correcta puede ocultar un 90 % en D+2 y un 70 % en D+7.
  Aceptado: cobertura del intervalo 10–90 entre el 75 % y el 85 % **en cada horizonte**.
- [ ] **4.7 Deep learning.** N-HiTS o TFT con PyTorch, con salida multihorizonte. Comparado en la suite contra el mejor modelo tabular. Para experimentar se puede usar GPU gratuita (Kaggle o Colab), pero el modelo elegido debe reentrenarse en CPU en un tiempo razonable (principio 6 de `ARQUITECTURA.md`).

## Fase 5. Producción completa
- [ ] **5.1 Cuantiles en el JSON** cuando se acepte la 4.6.
- [ ] **5.2 Web** con la previsión, su incertidumbre, el error real acumulado y la atribución a Open-Meteo y OMIE.
- [ ] **5.3 Reentreno mensual automático.** La suite evalúa el procedimiento, no un modelo concreto, así que no sirve para aprobar un reentreno. El control es:
  1. entrenar con datos hasta hace 4 semanas;
  2. comparar con el modelo actual en esas 4 semanas, que ninguno de los dos ha visto;
  3. si no es peor, reentrenar con todo y publicar;
  4. comprobaciones básicas: sin valores vacíos y precios dentro de un rango razonable.

  Si algo falla, se mantiene el modelo actual y se abre un *issue*.

## Fase 6. Integraciones
- [ ] **6.1 Sensor de Home Assistant** instalable por HACS, en español, que lee el JSON público. En un repo aparte (HACS lo exige), con licencia MIT.
- [ ] **6.2 Plantilla para evcc** y PR a su repositorio. evcc ya integra EpexPredictor (1–3 días): la plantilla tiene que aportar lo que él no da (D+4 a D+7 y cuantiles).
- [ ] **6.3 Artículo** con el experimento y los resultados, para difundir en foros de Home Assistant, evcc y coche eléctrico.

## Fase 7. Después
- [ ] Precio final por tarifa: PVPC (55 % a plazo en 2026) e indexadas (Octopus, Som Energia).

## Fase 8. Posible comercialización (sin detallar)
- [ ] 👤 Decidir la licencia definitiva del repo principal: AGPL-3.0, MIT o seguir reservado.
- [ ] Meteorología con uso comercial: plan de pago de Open-Meteo o el ECMWF (tarea 4.4).
- [ ] API de pago fuera de GitHub Pages, cuyas condiciones no permiten usarlo como base de un negocio.
- [ ] 👤 Validar la demanda con 3–5 empresas de consumo flexible antes de construir nada.
