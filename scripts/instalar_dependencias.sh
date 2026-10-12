#!/bin/bash
# Instala las dependencias de Python al arrancar una sesión en la nube de Claude Code.
# En local no hace nada: allí se usa el entorno virtual .venv/.

if [ "$CLAUDE_CODE_REMOTE" != "true" ]; then
  exit 0
fi

DIR="${CLAUDE_PROJECT_DIR:-.}"
pip install -q -r "$DIR/requirements.txt" || true
# El paquete, en modo editable y sin dependencias: sus versiones están en requirements.txt.
pip install -q -e "$DIR" --no-deps || true
exit 0
