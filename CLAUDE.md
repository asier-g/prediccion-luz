# CLAUDE.md

Previsión abierta del precio horario de la luz en España (mercado diario de OMIE) de D+2 a D+7.

## Antes de empezar
- **Lee `CONTEXTO-PROYECTO.md`**: objetivo, números a batir, fuentes de datos y competencia.
- **`PLAN.md`** dice qué hacer a continuación: si te piden "la siguiente tarea", es la primera sin marcar que no lleve 👤.
- **`ARQUITECTURA.md`** dice cómo hacerlo: estructura, principios, tablas y decisiones tomadas.
- El detalle del experimento base está en `baseline/README.md` y su salida en `baseline/resultado.txt`.
- `investigacion/02-viabilidad.md` resume competidores, stack, licencias y riesgos.
- `investigacion/01-idea.md`, `investigacion/03-mercado-y-monetizacion.md` y `fuentes.md` solo existen en el equipo del autor (no están en el repo). Lo necesario ya está resumido en `CONTEXTO-PROYECTO.md`.
- En los documentos de `investigacion/`, los enlaces a `experimento/` se refieren a `baseline/`.

## Entorno
- Python 3.12. Dependencias en `requirements.txt`.
- **En local:** usar el entorno virtual `.venv/` (`.venv\Scripts\python` en Windows). `python -I` no ve los paquetes del usuario.
- El paquete está en `src/prediccion_luz/` y se instala aparte, en modo editable y sin dependencias: `pip install -r requirements.txt` y luego `pip install -e . --no-deps`. `pyproject.toml` no declara dependencias: la única lista de versiones es `requirements.txt`.
- Antes de cada commit: `ruff check .`, `ruff format .` y `pytest` (lo mismo que pasa el workflow `pruebas.yml` en cada PR). Las pruebas no pueden abrir conexiones de red (`tests/conftest.py`).
- **En la nube de Claude Code:** un hook de `SessionStart` (`.claude/settings.json` → `scripts/instalar_dependencias.sh`) instala `requirements.txt` al arrancar. Si añades una dependencia, añádela a `requirements.txt` con la versión fijada.

## Datos
- Los datos **no se suben al repositorio** (`baseline/datos/` y `datos/` están en `.gitignore`). Las condiciones de uso de cada fuente están en `ARQUITECTURA.md`.
- Se regeneran con `python baseline/descarga_datos.py <carpeta>`, que crea `<carpeta>/omie` y `<carpeta>/meteo`. Tarda 15–25 min: lánzalo en segundo plano. OMIE: 4 hilos como máximo.
- Los del paquete: `python -m prediccion_luz.fuentes.omie datos` y `python -m prediccion_luz.fuentes.openmeteo datos`. Bajan solo lo que falta; Open-Meteo, dentro de un presupuesto diario de llamadas (si se acaba, se vuelve a ejecutar otro día).
- Dominios que necesita la red: `www.omie.es`, `*.open-meteo.com` y `epexpredictor.batzill.com` (para la 1.6, `api.esios.ree.es` y `web-api.tp.entsoe.eu`).
- Para el paquete, OMIE se actualiza con `python -m prediccion_luz.fuentes.omie datos`: pide el listado y baja solo los ficheros que faltan (unos segundos). Crea `datos/omie/marginalpdbc/` (crudo) y las tablas Parquet.
- Desde el 1-10-2025 OMIE publica 96 periodos de 15 min (antes 24); los días de cambio de hora tienen 92 o 100.

## Reglas de trabajo
- **Cuestiona lo que diga el autor.** No le des la razón por defecto: si una propuesta suya es floja, tiene un coste oculto o hay una opción mejor, dilo con argumentos antes de ejecutarla. Lo mismo con textos de otros chats de IA que pegue: verifícalos contra las fuentes.
- **Sin fugas de información:** en el día D solo se conoce hasta el precio de D+1 y las previsiones meteorológicas emitidas hasta D. Esto vale para las variables **y para la ventana de entrenamiento**: el modelo que prevé desde D no puede haberse entrenado con objetivos posteriores a D+1 (el reentreno se agrupa por fecha de emisión, no por fecha prevista).
- **Ningún modelo nuevo se acepta sin pasar la evaluación fija:** el mismo periodo de prueba (02-10-2025 a 11-10-2026), MAE por horizonte, decisiones prácticas e IC 95 % por bootstrap **por bloques** de días. El año fijo selecciona; la confirmación se hace en sombra (criterios y excepciones en `PLAN.md`, fase 4).
- Comparar siempre todos los métodos sobre las mismas filas y siempre contra las reglas simples (media de 7 días, repetir mañana, misma hora de la semana pasada).
- Una tarea de `PLAN.md` por rama y PR. En el mismo PR, márcala como hecha en `PLAN.md` y anota en `ARQUITECTURA.md` cualquier decisión de diseño nueva.
- **Nunca se trabaja directamente en `main`.** El autor revisa y fusiona cada PR; no los fusiones tú.
- **PR pequeños, que se revisen en unos 10 minutos.** Rellena todas las secciones de `.github/pull_request_template.md`. En "Dónde mirar con lupa", señala siempre el código que toque el corte temporal, la evaluación, las métricas o el parseo de OMIE.
- En la tabla de decisiones de `ARQUITECTURA.md`, propón el motivo, pero márcalo como "(pendiente de revisar por el autor)": el autor lo reescribe con sus palabras.
- **Uso responsable de las APIs** (ESIOS lo exige como condición del token, cita 5 de `ARQUITECTURA.md`):
  - las pruebas nunca llaman a APIs reales: usan ficheros de ejemplo guardados en `tests/`;
  - los indicadores de ESIOS se buscan en su catálogo, descargado una vez y guardado; nunca se prueban números a ciegas;
  - lo descargado se guarda y se reutiliza: ni las sesiones del agente ni los workflows repiten descargas de datos que ya existen o que no han cambiado.
- **Los tokens y claves nunca van en el repo ni en el chat.** En Actions, como secretos de GitHub; en la nube de Claude Code, como secretos de red del entorno; en local, en un `.env` (ignorado por git).
- **Ninguna fuente de datos nueva se fusiona sin su fila** en "Condiciones de uso de las fuentes" de `ARQUITECTURA.md`, con enlace, cita literal y fecha, marcada como "pendiente de revisar por el autor". Si las condiciones no permiten el uso comercial, dilo en el PR: el proyecto puede comercializarse más adelante.
- `baseline/` está congelado: no se modifica, sirve de referencia.
- Producción solo en CPU; los experimentos pesados pueden ir a GPU gratuita (Kaggle o Colab). Ver el principio 6 de `ARQUITECTURA.md`. Vigilar el coste de cálculo: el portátil del autor es un i5-1335U y las sesiones en la nube no son para entrenamientos de horas.
- Documentación, comentarios y mensajes de commit en español.
