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
- **En la nube de Claude Code:** un hook de `SessionStart` (`.claude/settings.json` → `scripts/instalar_dependencias.sh`) instala `requirements.txt` al arrancar. Si añades una dependencia, añádela a `requirements.txt` con la versión fijada.

## Datos
- Los datos **no se suben al repositorio** (`baseline/datos/` está en `.gitignore`; las condiciones de reutilización de OMIE están sin verificar).
- Se regeneran con `python baseline/descarga_datos.py <carpeta>`, que crea `<carpeta>/omie` y `<carpeta>/meteo`. Tarda 15–25 min: lánzalo en segundo plano. OMIE: 4 hilos como máximo.
- Dominios que necesita la red: `www.omie.es` y `*.open-meteo.com` (más adelante `api.esios.ree.es`).
- Desde el 1-10-2025 OMIE publica 96 periodos de 15 min (antes 24); los días de cambio de hora tienen 92 o 100.

## Reglas de trabajo
- **Sin fugas de información:** en el día D solo se conoce hasta el precio de D+1 y las previsiones meteorológicas emitidas hasta D.
- **Ningún modelo nuevo se acepta sin pasar la evaluación fija:** el mismo periodo de prueba (02-10-2025 a 11-10-2026), MAE por horizonte, decisiones prácticas e IC 95 % por bootstrap sobre días.
- Comparar siempre todos los métodos sobre las mismas filas y siempre contra las reglas simples (media de 7 días, repetir mañana, misma hora de la semana pasada).
- Una tarea de `PLAN.md` por rama y PR. En el mismo PR, márcala como hecha en `PLAN.md` y anota en `ARQUITECTURA.md` cualquier decisión de diseño nueva.
- **Nunca se trabaja directamente en `main`.** El autor revisa y fusiona cada PR; no los fusiones tú.
- **PR pequeños, que se revisen en unos 10 minutos.** Rellena todas las secciones de `.github/pull_request_template.md`. En "Dónde mirar con lupa", señala siempre el código que toque el corte temporal, la evaluación, las métricas o el parseo de OMIE.
- En la tabla de decisiones de `ARQUITECTURA.md`, propón el motivo, pero márcalo como "(pendiente de revisar por el autor)": el autor lo reescribe con sus palabras.
- `baseline/` está congelado: no se modifica, sirve de referencia.
- No hace falta GPU. Vigilar el coste de cálculo: el portátil del autor es un i5-1335U.
- Documentación, comentarios y mensajes de commit en español.
