#!/bin/bash
# Instala las dependencias de Python al arrancar una sesión en la nube de Claude Code.
# En local no hace nada: allí se usa el entorno virtual .venv/.

if [ "$CLAUDE_CODE_REMOTE" != "true" ]; then
  exit 0
fi

pip install -q -r "$CLAUDE_PROJECT_DIR/requirements.txt" || true
exit 0
