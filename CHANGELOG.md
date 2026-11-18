# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y versionado semántico.

## [0.6.1] - 2026-11-18

### Añadido
- `install.py`: instalador multiplataforma (usuario o proyecto, `--force` conservando el entorno virtual, `--no-venv`) que copia la skill, crea su entorno virtual, instala las dependencias y comprueba que funciona.
- `skill/sdm-ngsild-generator/VERSION`: versión única, que usan el informe, el instalador, la documentación y el paquete.
- `tools/build_release.py`: paquete de distribución reproducible `dist/sdm-ngsild-generator-<versión>.zip` (skill, instalador, LEEME.md, PDF, casos de referencia, CHANGELOG y LICENSE) con su suma SHA-256.
- `tools/build_docs.py` y `docs/sdm-ngsild-generator-<versión>.pdf`: documentación técnica y de uso (21 páginas, con índice navegable, diagramas y capturas del visor).
- Pruebas del instalador y del paquete de distribución.

## [0.6.0] - 2026-11-18

### Añadido
- `scripts/broker_test.py`: prueba opcional contra un context broker NGSI-LD (health, create, read con comparación de atributos, tipos NGSI, valores, `unitCode`, `observedAt` y objetos de Relationship, query por tipo y delete). Ids de prueba con sufijo único y Relationship internas reescritas; borrado garantizado aunque falle un paso; resultado en `broker-result.json`.
- Modos de `@context`: `inline` (contexto de la previsualización incrustado), `served` (servidor HTTP local y temporal con `application/ld+json`), `published` (contexto publicado vía GitHub Pages) y `auto` (inline con Orion-LD, served con el resto).
- `package.py` incluye automáticamente `broker-result.json` en el informe y en el ZIP.
- `tests/broker/`: docker-compose aislados de Orion-LD 1.12.0 y Stellio 2.37.0 (proyecto propio, solo `127.0.0.1`, sin volúmenes persistentes) y `tests/test_broker_live.py` (se activa con `SDM_BROKER_URLS`). Los tres casos de referencia pasan en ambos brokers.

### Hallazgos de compatibilidad (documentados en SPEC.md)
- Orion-LD 1.12.0: `GET /ngsi-ld/v1/types` se cuelga con la base de datos vacía (la comprobación de salud usa `GET /entities?type=…`), y termina con segfault al recibir un `POST` cuyo `@context` da 404 (la skill no envía entidades de un subject cuyo contexto no está publicado).
- Stellio 2.37.0: no acepta objetos en `@context` (500) ni alojar contextos (`/jsonldContexts`), y rechaza el contexto de `raw.githubusercontent.com` porque se sirve como `text/plain`.
- `uri.etsi.org` responde 403 a clientes sin User-Agent de navegador (Cloudflare); Orion-LD recurre a su copia interna del core context.

### Corregido
- Los recorridos de prueba de `examples/` ignoran ficheros ocultos (`.DS_Store`).

## [0.5.0] - 2026-11-18

### Añadido
- `scripts/preview.py`: previsualización en `preview/` (con `LEEME.txt`, que avisa de que NO forma parte de la contribución) de lo que el repositorio genera automáticamente: `model.yaml` (atributos aplanados con Commons resueltos, `x-ngsi`, metadatos `x-*`), `doc/spec.md` (mismas secciones y marcadores que el generador oficial) y el `context.jsonld` del subject (reglas de `25_create_subject_context`; en un subject existente parte del contexto publicado y añade solo los términos nuevos).
- `scripts/build_viewer.py` y `templates/viewer.html`: visor HTML autocontenido y sin conexión con diagrama SVG de entidades y relaciones (las flechas que saltan columnas van en arco), atributos filtrables por origen (nuevo, reutilizado con su modelo, Commons, original, añadido), ejemplos NGSI v2 y NGSI-LD lado a lado y conceptos presentes. Modo claro y oscuro.
- `scripts/package.py` y `templates/report.md`: validación obligatoria (no empaqueta si hay `fail`), previsualización, visor, informe en el idioma del usuario (resumen, validación, broker, decisiones, origen de los atributos, contenido y siguientes pasos) y ZIP reproducible.
- `scripts/i18n.py`: textos en español e inglés; otros idiomas con `--strings` (plantilla con `i18n.py export en`).
- `scripts/proposal.py`: carga común de la propuesta generada (atributos con Commons resueltos y origen).
- Especificación: `language`, `name` y `label` (traducción de entidades y atributos para el visor y el informe).

### Corregido
- `fetch_schema.parse_description` dejaba un «. » inicial cuando la descripción tenía `Model` y `Units`, y no quitaba la parte `Enum:'…'` del texto.
- Resolución de `$ref` relativos (`#/definitions/...`) en los Commons de subject.

## [0.4.0] - 2026-11-18

### Añadido
- Propuestas con varias entidades relacionadas: las Relationship hacia entidades de la propuesta usan en los ejemplos el `id` real de la entidad destino, de modo que los ejemplos forman un conjunto enlazado.
- Subject nuevo o existente: `newSubject` (dominios y `notes.yaml` del subject) con comprobación contra la lista oficial (error si se declara nuevo y existe, o si no existe y no se declara, con sugerencia ante erratas de mayúsculas).
- Extensiones de modelos existentes (`extensions`): copia del modelo de GitHub con los atributos añadidos al schema y a los 4 ejemplos, versión minor incrementada (`versioning.md`), `notes.yaml` y `ADOPTERS.yaml` originales, `CHANGES-<Model>.md` y `CONTRIBUTORS.yaml`. Solo se permite añadir atributos opcionales.
- `validate.py`: comprobación `extension` (original intacto, versión, atributos añadidos), problemas preexistentes del original rebajados a informativos, y comprobaciones del conjunto de la propuesta (`subject`, `relationship_targets`, `cross_references`). Acepta la carpeta de trabajo con `contribution/` y `extensions/`.
- `fetch_schema.fetch_model_files`: descarga del schema, los 4 ejemplos, `notes.yaml` y `ADOPTERS.yaml` de un modelo.
- Casos de referencia `examples/apiculture/` (3 entidades relacionadas en un subject nuevo) y `examples/weather-extension/` (extensión de WeatherObserved), con pruebas de regeneración y validación.

### Cambiado
- `generate.py --out` recibe la carpeta de trabajo y crea dentro `contribution/` y `extensions/` (antes recibía directamente la carpeta de contribución).

## [0.3.0] - 2026-11-18

### Añadido
- `SKILL.md` completo: siete fases con cierre y confirmación, dos modos de atributos (guiado y lista completa) intercambiables, carpeta de trabajo `sdm-proposal-<nombre>/` con `proposal.yaml` como registro de decisiones, e interpretación de la validación.
- `references/`: `interview-guide.md`, `sdm-principles.md`, `ngsi-ld-basics.md`, `naming-and-descriptions.md` y `units-uncefact.md`, basados en `MANIFESTO.md`, `specs/guidelines.md`, `versioning.md`, `ngsi-ld_howto.md` y `test_data_model` del repositorio smart-data-models.
- Códigos UN/CEFACT: `scripts/units.py` y `scripts/data/uncefact_units.json` (Rec. 20 de UNECE, 2136 códigos, ODC-PDDL), generado con `tools/build_units.py`.
- `search.py batch` (modo lista completa: coincidencias exactas y parecidas de muchos atributos a la vez) y `search.py units`.
- Fase 6 en `generate.py`: `metadata.license` (CC BY 4.0 por defecto, con `LICENSE.md` oficial por entidad), `metadata.contributors` (`CONTRIBUTORS.yaml`) y `decisions` (registro de decisiones).
- `generate.py` rechaza códigos de unidad que no existen y avisa de los obsoletos.
- `validate.py`: comprobaciones `units` (códigos válidos y coherentes en el schema y en los ejemplos) y `license`; recomendaciones de la guía SDM en `naming` (prefijo `date`, verbo en lugar de `ref` en relaciones nuevas, obligatorios mínimos); aviso de atributos reutilizados sin `reusedFrom`.
- Caso de referencia de principio a fin `examples/beehive/` con prueba de regeneración y validación.

## [0.2.0] - 2026-11-18

### Añadido
- `scripts/generate.py`: a partir de una especificación YAML/JSON de la propuesta genera, por entidad y con la estructura oficial, `schema.json` (JSON Schema 2020-12, `allOf` con Commons, descripciones en formato SDM), los cuatro ejemplos (NGSI v2 y NGSI-LD, key-values y normalizado), `notes.yaml` y `ADOPTERS.yaml`. Soporta Property, Relationship (simple o múltiple, con tipo destino) y GeoProperty; tipos string, number, integer, boolean, object y array; unidades UN/CEFACT (`unitCode`) y `observedAt`.
- `scripts/validate.py`: validación local que reproduce las 12 pruebas oficiales de `data-models/test_data_model` y añade coherencia entre los cuatro ejemplos, tipos NGSI declarados frente a usados, URNs y tipo destino de las Relationship, `@context` del subject, redefinición de Commons y atributos «nuevos» que ya existen en el repositorio. Salida JSON con estado `pass`/`warn`/`fail` por comprobación.
- `fetch_schema.py`: resolución de `$ref` remotos a través de la caché (`fetch_document`, `resolve_ref`).
- Plantillas `templates/notes.yaml` y `templates/ADOPTERS.yaml` con el formato oficial.
- Fase 7 (generación y validación) en `SKILL.md`.
- Pruebas con propuestas de cuatro dominios (Agrifood, Environment, Energy y WasteManagement) y una prueba negativa por cada comprobación del validador.

### Cambiado
- `notes.yaml` y `ADOPTERS.yaml` se generan en la carpeta de cada entidad, como exige la prueba oficial `test_file_exists` (antes el SPEC los situaba al nivel de `contribution/`).

## [0.1.0] - 2026-11-18

### Añadido
- Estructura del repositorio según la sección 12 de `SPEC.md` y licencia Apache 2.0.
- `SKILL.md` inicial: reglas, uso de los scripts, criterios de búsqueda y fases 1 y 2 de la entrevista.
- `scripts/sdm_index.py`: descarga y caché local (caducidad de 7 días, respaldo con aviso si GitHub no responde, modo `--offline`) de cuatro índices del repositorio `smart-data-models`: lista oficial de modelos, metadatos de modelos, inventario de atributos y `common-schema.json`.
- `scripts/search.py`: búsqueda por términos de subjects, modelos y atributos, con filtros por dominio y subject. Los atributos se agrupan por nombre con tipo NGSI, tipo JSON, unidades, modelos donde aparecen y pertenencia a los Commons.
- `scripts/fetch_schema.py`: descarga de `schema.json` (y opcionalmente los 4 ejemplos) desde `raw.githubusercontent.com`, resumen de atributos a partir del formato de descripción SDM y resolución de los Commons generales y de subject.
- Pruebas con `unittest` y fixtures reales de 10 subjects (Agrifood, Environment, WaterQuality, Transportation, Streetlighting, Device, WasteManagement, Building, S4BLDG, Energy). Las pruebas con red se activan con `SDM_ONLINE_TESTS=1`.
