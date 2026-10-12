# Plan de trabajo

Pasos para llevar el baseline a producción. El porqué de cada paso está en `CONTEXTO-PROYECTO.md`; el cómo, en `ARQUITECTURA.md`.

## Cómo usar este plan
- Las tareas van en orden dentro de cada fase. Cada tarea cabe en una sesión de trabajo y acaba en un PR.
- Al terminar una tarea, márcala con `[x]`, la fecha y el enlace al PR, **en el mismo PR**.
- Si una tarea resulta mayor de lo previsto, divídela aquí antes de seguir.
- Las tareas marcadas con 👤 necesitan al autor (cuentas, tokens, decisiones). El agente no puede hacerlas solo.
- "Aceptado" significa que se cumple el criterio escrito en la tarea. Sin criterio cumplido, la tarea no está hecha.

## Fase 0. Preparación
- [x] Repositorio, baseline, `CONTEXTO-PROYECTO.md` y `CLAUDE.md` (2026-10-11).
- [x] `README.md`, `PLAN.md` y `ARQUITECTURA.md` (2026-10-11).
- [x] Licencia (2026-10-12): el repo principal queda **sin licencia** (todos los derechos reservados) para no cerrar una comercialización futura. Las integraciones de la fase 5 irán en repos aparte con MIT.
- [ ] 👤 Configurar el entorno en la nube de Claude Code: red **Custom** con `www.omie.es` y `*.open-meteo.com`, más la lista por defecto.
- [ ] 👤 Revisar la tabla "Condiciones de uso de las fuentes" de `ARQUITECTURA.md` y marcar como verificadas las filas cuya cita sea correcta.
- [ ] 👤 Pedir el token personal de ESIOS (consultasios@ree.es) y guardarlo como secreto, nunca en el repo. En el mismo correo, preguntar si se pueden usar sus datos en un servicio de pago. Leer el aviso legal de ESIOS en el navegador y completar su fila.
- [ ] 👤 **Antes de la fase 7:** pedir a OMIE confirmación por escrito de que su aviso legal permite el uso comercial (el texto dice "uso libre" sin excluirlo).

## Fase 1. Canal de datos
- [ ] **1.1 Esqueleto del paquete.** `pyproject.toml`, paquete en `src/prediccion_luz/`, `pytest` y `ruff`. Workflow de GitHub Actions que pasa las pruebas en cada PR.
  Aceptado: `pytest` pasa en local y en Actions.
- [ ] **1.2 OMIE.** Descarga incremental (solo los días que faltan, 4 hilos como máximo) y lectura de `marginalpdbc` a una tabla con resolución nativa (24, 23, 25, 96, 92 o 100 periodos) y otra horaria. Guardado en Parquet.
  Aceptado: pruebas con ficheros de ejemplo pequeños para cada número de periodos, incluidos los cambios de hora antes y después del 1-10-2025. Los precios horarios coinciden con los del baseline en los días sin cambio de hora.
- [ ] **1.3 Open-Meteo Previous Runs.** Descarga incremental de los puntos actuales a una tabla larga (punto, variable, antelación k, hora prevista), en Parquet.
  Aceptado: pruebas de lectura y de que una segunda ejecución no vuelve a descargar lo que ya hay.
- [ ] **1.4 Verificar la hora de emisión de `previous_dayK`.** Averiguar con qué ejecución del modelo se corresponde `previous_day2` para una hora T y si estaba disponible el día D por la tarde.
  Aceptado: conclusión y fuente documentadas en `ARQUITECTURA.md`. Si hay fuga, ajustar el corte y anotarlo.
- [ ] **1.5 Archivar EpexPredictor cada día.** Workflow diario que guarda su previsión para España. Empezar pronto: este histórico no se puede recuperar después.
  Aceptado: el workflow guarda un fichero por día sin intervención durante una semana.

## Fase 2. Evaluación como código
- [ ] **2.1 Reglas y modelos del baseline sobre el nuevo canal.** Reglas simples, gradient boosting con y sin meteorología, y MLP.
  Aceptado: el MAE total de cada método queda a ±0,3 €/MWh del de `baseline/resultado.txt`. Si no, explicar la diferencia.
- [ ] **2.2 Suite de evaluación fija.** Periodo de prueba, reentreno mensual con ventana creciente, MAE total y por horizonte, decisiones 1 y 2, e IC 95 % por bootstrap **por bloques** de días (corrige la limitación del baseline). Un comando la ejecuta y guarda el resultado en `informes/`.
  Aceptado: la tabla de `informes/` reproduce la 2.1 y añade los IC.
- [ ] **2.3 Prueba contra fugas.** Comprobar automáticamente que ninguna variable usa información posterior al corte del día D.
  Aceptado: la prueba falla si se introduce a propósito una variable con fuga.
- [ ] **2.4 Comparación con EpexPredictor.** Con el archivo de la 1.5, MAE en D+2 y D+3 sobre las mismas horas.
  Aceptado: tabla en `informes/`, actualizable con un comando.

## Fase 3. Mejoras del modelo
Cada mejora es un experimento que pasa por la suite de la 2.2. Se acepta solo si baja el MAE con el IC 95 % por debajo de cero frente al mejor modelo actual. Si no mejora, se anota igualmente en `informes/` y se descarta.
- [ ] **3.1 Previsiones de ESIOS** (demanda, eólica, solar). Antes: comprobar qué horizontes publica Red Eléctrica y desde cuándo hay histórico de esas previsiones. Necesita el token de la fase 0.
- [ ] **3.2 Festivos completos:** Semana Santa, festivos autonómicos ponderados por población y puentes.
- [ ] **3.3 Más puntos meteorológicos**, o una rejilla resumida por región.
- [ ] **3.4 Precio del gas** (MIBGAS o TTF). Antes: encontrar una fuente gratuita con histórico y condiciones de uso claras.
- [ ] **3.5 Previsión probabilística.** Cuantiles 10, 50 y 90. Medir la cobertura y la pérdida *pinball*.
  Aceptado: cobertura del intervalo 10–90 entre el 75 % y el 85 % en la prueba.
- [ ] **3.6 Deep learning.** N-HiTS o TFT con PyTorch, con salida multihorizonte. Comparado en la suite contra el mejor modelo tabular. Para experimentar se puede usar GPU gratuita (Kaggle o Colab), pero el modelo elegido debe reentrenarse en CPU en un tiempo razonable (principio 6 de `ARQUITECTURA.md`).

## Fase 4. Producción
- [ ] **4.1 Previsión diaria en GitHub Actions.** Se lanza cuando OMIE ha publicado D+1. Comprueba que el dato está antes de prever y reintenta si no. Guarda cada previsión emitida en un archivo que solo crece.
- [ ] **4.2 JSON público** en GitHub Pages, con el esquema versionado de `ARQUITECTURA.md`.
- [ ] **4.3 Web** con la previsión, su incertidumbre, el error real acumulado y la atribución a Open-Meteo y OMIE.
- [ ] **4.4 Reentreno mensual** automático, que solo publica el modelo nuevo si pasa la suite.
- [ ] **4.5 Avisos de fallo.** Si la previsión de un día falla, se abre un *issue* automáticamente.

## Fase 5. Integraciones
- [ ] **5.1 Sensor de Home Assistant** instalable por HACS, en español, que lee el JSON público. En un repo aparte, con licencia MIT.
- [ ] **5.2 Plantilla para evcc** y PR a su repositorio. evcc ya integra EpexPredictor (1–3 días): la plantilla tiene que aportar lo que él no da (D+4 a D+7 y cuantiles).
- [ ] **5.3 Artículo** con el experimento y los resultados, para difundir en foros de Home Assistant, evcc y coche eléctrico.

## Fase 6. Después
- [ ] Precio final por tarifa: PVPC (55 % a plazo en 2026) e indexadas (Octopus, Som Energia).

## Fase 7. Posible comercialización (sin detallar)
- [ ] 👤 Decidir la licencia definitiva del repo principal: AGPL-3.0, MIT o seguir reservado.
- [ ] Meteorología con uso comercial: plan de pago de Open-Meteo o fuente alternativa (comprobar los datos abiertos del ECMWF).
- [ ] API de pago fuera de GitHub Pages, cuyas condiciones no permiten usarlo como base de un negocio.
- [ ] 👤 Validar la demanda con 3–5 empresas de consumo flexible antes de construir nada.
