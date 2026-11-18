# Principios de Smart Data Models

Resumen para Claude, basado en el repositorio `smart-data-models/data-models`: `MANIFESTO.md`, `specs/guidelines.md`, `versioning.md` y las pruebas de `test_data_model`. Úsalo para justificar decisiones ante el usuario con una o dos frases, no para soltar el texto entero.

## Manifiesto de estandarización ágil (MANIFESTO.md)

| # | Principio | Qué implica en la entrevista |
|---|---|---|
| 0 | Estandarizar con agilidad | Automatizar (scripts) y no bloquear decisiones. |
| 1 | No reinventar la rueda | Buscar en el repositorio, schema.org y estándares (Open311, DATEX II…) antes de crear. |
| 2 | Normalizar casos reales | Exigir un caso de uso real (fase 1). |
| 3 | Ser abiertos | Licencia abierta: CC BY 4.0 recomendada. |
| 4 | No ser demasiado específicos | Pocos obligatorios. «Lo que es obligatorio para ti puede ser opcional para otros». Nombres genéricos, no ligados a un proyecto o fabricante. |
| 5 | Plano, no profundo | Modelos autocontenidos. Evitar cadenas largas de entidades que se referencian unas a otras. Preferir pocos niveles de objetos anidados. |
| 6 | Sostenibilidad | Pensar en la evolución del modelo (versionado). |

## Reutilización

1. Antes de crear un modelo, buscar si ya existe uno que cubra el caso. La guía lo recuerda: usa sinónimos («Public Transport» está en `UrbanMobility`).
2. Antes de crear un atributo, buscar el mismo concepto en otros modelos y reutilizarlo si es pertinente: mismo nombre, mismo tipo NGSI y mismas unidades.
3. Mirar schema.org en busca de un término con la misma semántica (sirve para `Model:'…'`).
4. Referenciar los Commons en lugar de redefinir sus atributos:
   - `GSMA-Commons`: id, dateCreated, dateModified, source, name, alternateName, description, dataProvider, owner, seeAlso.
   - `Location-Commons`: location, address, areaServed.
   - `PhysicalObject-Commons`: color, image, annotations.
   - `DateTime-Commons`, `Contact-Commons`, `Person-Commons`…
   - Commons del subject, como `AgriFood-Commons` en `agrifood-schema.json`.

## Obligatorios y valores

- Los obligatorios deben ser los mínimos, idealmente solo `id` y `type`. Cada atributo que el usuario quiera hacer obligatorio debe justificarse.
- `null` está prohibido en NGSI-LD: si no hay dato, el atributo no se envía.
- Las enumeraciones conviene dejarlas abiertas a ampliación, siempre que el valor nuevo no esté ya cubierto semánticamente.

## Fechas

- Prefijo `date` para los atributos de fecha: `dateObserved`, `dateLastEmptying`, `dateIssued`.
- `dateCreated` y `dateModified` los gestiona la plataforma NGSI y no hace falta modelarlos; ya están en GSMA-Commons. Si se necesita la fecha real del mundo físico, se crea un atributo específico.
- El instante de una medida va en `observedAt` (NGSI-LD) o en el metadato `timestamp` (NGSI v2), no en `dateModified`.

## Versionado (versioning.md)

- Formato `X.Y.Z`. Las versiones `0.y.z` son borradores: **una propuesta nueva empieza en `0.0.1`**.
- `1.0.0` es la primera versión pública.
- Añadir un atributo incrementa la minor. Un cambio incompatible incrementa la major. Una versión publicada no se modifica.

## Licencia

Cada modelo lleva su `LICENSE.md`. SDM usa **CC BY 4.0**, y el generador copia el texto oficial de `templates/dataModel/LICENSE.md`. Con otra licencia, el usuario aporta la URL y el texto.

## Estructura de una contribución

Por modelo (lo exige `test_file_exists`): `schema.json`, `examples/` con los 4 ejemplos, `notes.yaml` y `ADOPTERS.yaml`. También `LICENSE.md`.

Por subject: `CONTRIBUTORS.yaml` (autoría) y, si hay atributos compartidos, `<subject>-schema.json` con sus Commons. El README, la especificación, `model.yaml` y `context.jsonld` los genera el repositorio automáticamente.

Un subject nuevo lleva además su `notes.yaml` (`notesPrevious`, `notesEnd`, según `templates/Subject/notes.yaml`).

Una **extensión** de un modelo existente es una nueva versión de ese modelo: mismo schema y mismos ejemplos, más atributos opcionales y la versión minor incrementada. Nunca cambia ni elimina nada del original, porque los datos existentes deben seguir siendo válidos.

## Qué comprueban las pruebas oficiales (`test_data_model`)

Ficheros obligatorios · JSON y YAML válidos · descripciones con formato SDM en todos los atributos, subatributos e items · metadatos del schema (`$schema` 2020-12, `$schemaVersion` XX.XX.XX, título de 15 caracteres o más, descripción de 50 o más, `$id`, `required` con id y type) · string sin items/properties · ejemplos key-values válidos contra el schema · NGSI v2 normalizado sin tipos NGSI-LD · NGSI-LD normalizado con `@context` accesible · todos los atributos del ejemplo definidos en el schema · arrays con `items` y objects con `properties` · atributos en camelCase. `scripts/validate.py` reproduce todas estas pruebas.
