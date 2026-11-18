# sdm-ngsild-generator 0.6.1

Skill de Claude Code que guía, mediante una entrevista, la creación de propuestas de
Smart Data Models para NGSI-LD, priorizando la reutilización de lo que ya existe en el
repositorio oficial `smart-data-models` de GitHub.

Documentación completa: `docs/sdm-ngsild-generator-0.6.1.pdf`.

## Requisitos

- Claude Code (VSCode o terminal) en Windows, macOS o Linux.
- Python 3.10 o superior.
- Conexión a internet para consultar el repositorio de Smart Data Models (sin token).
- Opcional: un context broker NGSI-LD (Orion-LD, Stellio…) para la prueba con broker.

## Instalación

Desde esta carpeta:

```bash
python install.py                    # para tu usuario (~/.claude/skills)
python install.py --project RUTA     # solo para un proyecto (RUTA/.claude/skills)
python install.py --force            # para actualizar una instalación anterior
```

En Windows usa `py install.py` si `python` no está en el PATH. El instalador copia la
skill, crea su entorno virtual, instala las dependencias y comprueba que funciona.

## Uso

Abre Claude Code y pide, por ejemplo: «quiero proponer un Smart Data Model para…».
La skill conduce una entrevista en siete fases y entrega un ZIP con la propuesta, un
visor HTML y un informe. Nunca escribe en GitHub: tú decides si contribuyes la propuesta.

En `examples/` hay tres casos de referencia (una entidad, tres entidades en un subject
nuevo y una extensión de un modelo existente).
