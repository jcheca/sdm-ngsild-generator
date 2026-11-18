# Guía de la entrevista

Detalle de las siete fases de `SKILL.md`. En cada fase: objetivo, qué preguntar, qué ejecutar, qué mostrar, qué anotar en `proposal.yaml` y cómo cerrar la fase.

Pautas generales:
- **Pocas preguntas por turno** (dos o tres como máximo), agrupadas y en el idioma del usuario.
- **Propón, no interrogues.** Cuando puedas deducir algo del caso de uso o del repositorio, preséntalo como propuesta para que el usuario lo confirme o lo corrija.
- **Cierra cada fase con un resumen breve y una pregunta explícita de confirmación.** No avances sin un «sí» o una corrección.
- **Anota todo en `proposal.yaml`** según avanzas (formato en la cabecera de `scripts/generate.py`). Si la sesión se interrumpe, ese fichero permite retomarla.
- **Explica cada concepto nuevo una sola vez** con la *explicación corta* de `ngsi-ld-basics.md`. Si el usuario dice que ya lo conoce, no lo repitas.

---

## Fase 1 · Contexto

**Objetivo:** entender qué se modela, en qué dominio y para qué caso de uso real.

Preguntas (adáptalas a lo que el usuario ya haya contado):
1. ¿Qué cosa del mundo real quieres representar y qué datos tienes de ella? Si tiene ejemplos de datos (CSV, JSON, capturas), pídeselos: son la mejor fuente.
2. ¿Para qué se usarán? ¿Quién produce los datos y quién los consume?
3. ¿Hay un despliegue o proyecto real detrás? SDM solo normaliza casos reales (manifiesto, principio 2). Si es hipotético, avísalo con tacto.
4. ¿Cada cuánto cambian los datos? (Distingue datos estáticos de medidas.)

**Cierre:** resume en 3 a 5 líneas lo que se modela, el dominio SDM probable (SmartAgrifood, SmartEnvironment, SmartCities…), el caso de uso, quién produce y quién consume los datos, y la frecuencia. Pregunta: «¿Es correcto? ¿Falta algo?».

**Anota:** crea la carpeta de trabajo `sdm-proposal-<nombre-corto>/` en el directorio actual y empieza `proposal.yaml` con un comentario que resuma el caso de uso.

---

## Fase 2 · Búsqueda de lo existente

**Objetivo:** decidir entre reutilizar, extender o crear.

1. `search.py subjects --domain <Dominio>` y `search.py subjects <términos>`: subjects candidatos.
2. `search.py models <términos>`: varias consultas con sinónimos y abreviaturas, en inglés. Prueba también nombres que esperarías (`SoilObserved`, `SoilProbe`, `SoilMeasurement`).
3. Para los 3 a 5 candidatos más pertinentes: `fetch_schema.py <Model> --resolve-commons`.
4. Evalúa cada candidato frente al caso de uso: qué cubre, qué le falta y si su propósito es el mismo o solo se parece.

**Muestra** una tabla corta:

| Modelo | Subject | Para qué sirve | Cubre del caso | Falta |
|---|---|---|---|---|

Termina con una recomendación argumentada:
- **Reutilizar tal cual:** el modelo cubre el caso, quizá con atributos opcionales sin usar. Es un resultado válido y la skill puede terminar aquí. Entrega el enlace al schema y a los ejemplos, explica cómo usarlo y qué atributos rellenar.
- **Extender:** el modelo es el adecuado pero le faltan atributos. Se anota en `extensions` (`model: dataModel.X/Model`, `reason` y los atributos que se añaden). Reglas:
  - Solo se **añaden** atributos, siempre opcionales. No se cambia ni se borra nada del original (no modificamos modelos del repositorio, proponemos una nueva versión).
  - La versión sube de minor sola (por ejemplo, 0.3.4 → 0.4.0, según `versioning.md`).
  - Se entrega en `extensions/<subject>/<Model>/` con un `CHANGES-<Model>.md` para los mantenedores.
  - Si el original tiene defectos, el validador los muestra como «preexistentes». Coméntalos, pero no los arregles en la extensión.
  - Una propuesta puede tener a la vez entidades nuevas y extensiones (por ejemplo, una entidad nueva que se enlaza con un modelo que además se amplía).
- **Crear:** nada encaja. Explica por qué los candidatos no sirven.

**Cierre:** «Te recomiendo X porque… ¿Seguimos por ahí?».

**Anota** en `decisions` cada candidato evaluado: `reused`, `extended` o `discarded`, con su motivo y el origen `dataModel.X/Model`.

---

## Fase 3 · Estructura

**Objetivo:** fijar las entidades, sus nombres y el subject de destino.

Criterios para dividir en varias entidades (dilo así al usuario):
- **Ciclos de vida distintos:** el dispositivo frente a sus observaciones (patrón `Device` / `XxxObserved`), o el catálogo frente a las instancias.
- **Conceptos que otras entidades podrían referenciar:** si algo tiene identidad propia y se apunta desde varios sitios, merece entidad.
- **No dividir** lo que ya existe en el repositorio: se enlaza con una Relationship (por ejemplo a `Device`, `AgriParcel` o `Building`) en lugar de crear una entidad nueva.
- **No dividir de más** (manifiesto, principio 5): si un dato solo tiene sentido dentro de la entidad, va como atributo, incluso como object.

Nombre de cada entidad: PascalCase, en inglés, singular y genérico. Comprueba que no existe con `search.py models <Nombre>`; el validador también avisa.

Subject:
- **Existente:** elige el que agrupe modelos afines (`search.py subjects`). Es lo preferible.
- **Nuevo:** solo si ningún subject existente encaja, normalmente porque hay una familia de modelos de un mismo ámbito sin sitio natural. Hay precedente: `dataModel.Aquaculture` es un subject separado de `dataModel.Agrifood`. Nombre `dataModel.<Nombre>` en PascalCase. En `proposal.yaml`, `newSubject: {domains: [...], notes: {notesPrevious, notesEnd}}`.
  - Avisa de que la URL de su `@context` no existirá hasta la publicación y de que la prueba oficial `test_valid_ngsild` lo señalará hasta entonces. Es esperable.
  - El generador comprueba contra la lista oficial que el subject no existe si se declara nuevo, y que existe si no se declara.

**Cierre:** lista de entidades con una línea de propósito cada una y el subject. Pregunta de confirmación.

**Anota:** `subject`, y para cada entidad `name`, `title`, `description` (en inglés, 50 caracteres o más, genérica) y `commons`.

Con varias entidades, preséntalas como un pequeño diagrama de texto con sus relaciones (`HoneyHarvest → Beehive → Apiary → AgriParcel`) para que el usuario vea el conjunto antes de entrar en los atributos.

---

## Fase 4 · Atributos

**Objetivo:** para cada atributo, fijar nombre, tipo NGSI, tipo JSON, unidades, obligatoriedad y origen (reutilizado o nuevo).

Pregunta al usuario cómo prefiere trabajar, y recuérdale que puede cambiar de modo cuando quiera:
- **Guiado:** vamos atributo a atributo y te explico cada decisión.
- **Lista completa:** pegas tu lista o tabla (texto libre, CSV, Markdown, cabeceras de un CSV de datos…) y yo propongo todo en bloque.

### Antes de empezar: los Commons

Indica qué aportan los Commons que vas a referenciar (GSMA-Commons: `name`, `description`, `dateCreated`…; Location-Commons: `location`, `address`, `areaServed`). Esos atributos **no** se definen; solo se les da valor en el ejemplo (`example.commons`).

### Modo guiado

Para cada dato del usuario:
1. Tradúcelo a un concepto en inglés y busca: `search.py attributes <términos>` y `--exact <nombreCandidato>`.
2. Propón:
   - nombre (reutilizado si existe);
   - tipo NGSI (Property, Relationship o GeoProperty);
   - tipo JSON;
   - unidades, comprobadas con `search.py units` (ver `units-uncefact.md`);
   - rango (`minimum`/`maximum`; las cantidades relativas van de 0 a 1);
   - enumeración, si procede;
   - si lleva `observedAt` (`temporal: true` para medidas).
3. Explica en una o dos frases el porqué, sobre todo si se reutiliza: «Ya existe en AgriParcelRecord con el mismo significado y unidades».
4. Pide confirmación del atributo y pasa al siguiente.

### Modo lista completa

1. Normaliza la entrada a una lista JSON de conceptos en inglés: `["soil temperature", "leafWetness", {"name": "irrigationVolume", "terms": "irrigation water volume"}]`.
2. Ejecuta `search.py batch lista.json --domain <Dominio>`. Para cada concepto devuelve la coincidencia exacta y los atributos más parecidos.
3. Propón en **una tabla**: dato original · nombre propuesto · NGSI · tipo · unidades · reutilizado de / nuevo · nota.
4. Separa claramente los atributos **dudosos o conflictivos**:
   - varios candidatos con significados distintos;
   - un atributo existente con unidades incoherentes;
   - un nombre nuevo muy parecido a uno existente;
   - datos que quizá deban ser Relationship, o una entidad aparte.

   Discute **solo** esos. Para el resto basta con un «¿los demás te parecen bien?».

### Obligatoriedad

Por defecto, solo `id` y `type`. Si el usuario quiere más obligatorios, pregunta si lo serían para cualquier otro adoptante del modelo (principio 4) y anótalo en `required` solo si la respuesta es sí.

**Cierre:** tabla final de atributos y confirmación.

**Anota:** `attributes` con `origin: reused` + `reusedFrom`, u `origin: new`. Para cada atributo nuevo con un nombre parecido a uno existente, añade una `justification`. Los conceptos descartados van en `decisions`.

---

## Fase 5 · Relaciones

**Objetivo:** enlazar con otras entidades de la propuesta o con modelos existentes.

1. Para cada vínculo: ¿a qué tipo de entidad apunta? Puede ser otra entidad de la propuesta o un modelo existente (`Device`, `Building`, `AgriParcel`, `WasteContainer`…). Si es existente, confirma que existe con `search.py models`.
2. Nombre: si ya existe una relación equivalente en el repositorio (`refDevice`, `hasAgriParcel`), reutilízala. Si es nueva, usa un verbo (`hasX`, `isPartOf`, `operatedBy`); ver `naming-and-descriptions.md`.
3. Cardinalidad: ¿una entidad o varias? (`multiple: true`).
4. `target`: el tipo destino. El validador comprueba que las URN del ejemplo son de ese tipo. Si el destino es una entidad de la propuesta, el ejemplo apunta automáticamente al `id` del ejemplo de esa entidad, y así los ejemplos forman un conjunto enlazado (útil para la prueba con broker).
5. Dirección: la relación va en la entidad que «depende» de la otra (la colmena apunta al colmenar, no al revés). Evita relaciones duplicadas en ambos sentidos salvo que el caso de uso lo exija.

> *Explicación corta* de Property frente a Relationship en `ngsi-ld-basics.md`.

**Cierre:** lista de relaciones (origen → destino, cardinalidad) y confirmación.

---

## Fase 6 · Metadatos

Pregunta, en un único turno:
1. **Autoría:** nombre, apellidos, correo (opcional), organización y proyecto de cada contribuidor. Va a `CONTRIBUTORS.yaml`.
2. **Licencia:** recomienda **CC BY 4.0**, la de SDM. Con otra, pide la URL del texto (`licenseUrl`).
3. **Adoptantes:** ¿alguna organización usa ya el modelo? Va a `ADOPTERS.yaml` (todos los campos son opcionales).
4. **Notas:** ¿algo que deba aparecer en la especificación (`notesHeader`, `notesMiddle`, `notesFooter`) o en el README del modelo (`notesReadme`)? En inglés.

**Cierre:** resumen de los metadatos y confirmación.

**Anota:** `metadata.license`, `metadata.contributors`, y en cada entidad `adopters` y `notes`.

---

## Fase 7 · Generación

1. Completa `example` en cada entidad: un `id` legible, un `observedAt` y valores realistas del caso del usuario, incluidos los de los Commons (`name`, `location`…). Los ejemplos se leen en la especificación pública, así que no inventes cifras absurdas ni pongas datos personales reales.
2. Añade a `proposal.yaml` el idioma del usuario (`language: es`) y, en entidades y atributos, `label` con su traducción. Solo se usan en el visor y en el informe; el modelo sigue en inglés.
3. Muestra `proposal.yaml` completo y pide confirmación antes de generar.
4. Genera: `generate.py <dir>/proposal.yaml --out <dir>`. Se crean `<dir>/contribution/` (entidades nuevas, `CONTRIBUTORS.yaml` y, en un subject nuevo, su `notes.yaml`) y `<dir>/extensions/` (modelos ampliados).
5. Valida: `validate.py <dir> --spec <dir>/proposal.yaml`. Revisa también el bloque `proposal` (subject, destinos de las relaciones, enlaces entre ejemplos).
6. Si algo falla, corrige `proposal.yaml` (nunca los ficheros generados a mano), regenera con `--force` y vuelve a validar.
7. Explica los avisos que queden: cuáles son normales (`derivedFrom` vacío en un modelo nuevo, `@context` de un subject nuevo) y cuáles conviene resolver.
8. Empaqueta: `package.py <dir> --spec <dir>/proposal.yaml`. Vuelve a validar y, si no hay `fail`, genera:
   - `preview/`: lo que el repositorio genera solo (model.yaml, spec.md, @context). **No forma parte de la contribución**; dilo explícitamente.
   - `viewer.html`: diagrama, atributos por origen, ejemplos lado a lado y conceptos, en el idioma del usuario. Se abre sin conexión con doble clic.
   - `report.md`: validación, registro de decisiones y origen de cada atributo, en el idioma del usuario.
   - `<nombre>.zip` con todo lo anterior, `contribution/`, `extensions/` y `proposal.yaml`.

   Para un idioma distinto de español o inglés: `i18n.py export en > strings.json`, traduce los valores (no las claves) y pásalo con `--strings strings.json`.
9. **Prueba contra broker (opcional).** Ofrécela solo una vez y en una línea: «¿Quieres probar los ejemplos contra tu broker NGSI-LD (Orion-LD, Stellio…)? Necesito su URL». Si acepta:
   - `broker_test.py <dir> --spec <dir>/proposal.yaml --broker <URL>` (con `--tenant` si usa tenants).
   - Crea las entidades con ids de prueba (`…-sdmtest-<run>`), las lee y compara, consulta por tipo y **las borra siempre**. No toca otros datos del broker.
   - El modo de `@context` se elige solo (`auto`: incrustado con Orion-LD; servido desde un servidor local temporal con el resto). Si el broker no está en Docker Desktop en la misma máquina, puede hacer falta `--serve-host <IP de este equipo>` y `--serve-bind 0.0.0.0` (avisa al usuario de que eso expone el servidor temporal en su red mientras dura la prueba).
   - Vuelve a ejecutar `package.py` para que el informe incluya el resultado (`broker-result.json`).
10. Resume la entrega: ruta del ZIP, resultado de la validación, decisiones principales (reutilizado frente a nuevo) e invitación a abrir `viewer.html`. Indica que el usuario decide si y cómo contribuirlo. La skill nunca abre pull requests.

Si el usuario no tiene broker y quiere probar, puede levantar uno local con Docker. El repositorio de la skill incluye ejemplos aislados en `tests/broker/` (Orion-LD y Stellio).

---

## Situaciones frecuentes

| Situación | Qué hacer |
|---|---|
| El usuario escribe los nombres en español | Propón el nombre inglés y explica por qué; nunca generes nombres en español. |
| Quiere un atributo con su nombre de proyecto o marca | Proponle uno genérico (principio 4). |
| Un dato es una lista de objetos complejos | Valora si es otra entidad (fase 3) o un `array` de `object` con `properties`. |
| Datos por idioma | Atributo base en inglés más variantes `<atributo>_<idioma>`, o LanguageProperty (todavía no soportado por el generador: avísalo). |
| GitHub no responde | Los scripts usan la caché y devuelven un aviso con su antigüedad. Comunícaselo al usuario. |
| El usuario quiere saltarse una fase | Puede hacerlo, pero resume lo que se asume por defecto y pide confirmación. |
