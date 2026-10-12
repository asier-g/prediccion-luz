# Archivo

Rama que **solo crece**: guarda lo que no se puede regenerar. Nunca se reescribe ni se fusiona con `main`. La escriben los workflows de `main`.

| Carpeta | Contenido | Desde |
|---|---|---|
| `epexpredictor/ES/AAAA/` | Previsión de EpexPredictor para España, capturada cada día entre las 15:00 y las 18:00 de Madrid (tarea 1.2). Un fichero por día, **cifrado** | 2026-10 |

## Ficheros cifrados
Los de `epexpredictor/` van cifrados (JSON → gzip → Fernet) con la clave del secreto `CLAVE_ARCHIVO`. Se descifran con `prediccion_luz.fuentes.epexpredictor.descifrar`:

```python
from pathlib import Path
from prediccion_luz.fuentes.epexpredictor import descifrar

sobre = descifrar(Path("epexpredictor/ES/2026/2026-10-13.json.gz.cifrado").read_bytes(), clave)
sobre["capturado_utc"], sobre["respuesta"]["prices"]
```
