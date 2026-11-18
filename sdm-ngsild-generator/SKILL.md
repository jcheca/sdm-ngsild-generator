---
name: sdm-ngsild-generator
description: Guía al usuario, mediante una entrevista, en la creación de propuestas de Smart Data Models (SDM) para NGSI-LD en cualquier dominio. Busca en el repositorio oficial smart-data-models de GitHub modelos, atributos y Commons ya existentes para reutilizarlos, enseña los fundamentos de SDM y NGSI-LD, y genera y valida la propuesta (schema.json, cuatro ejemplos, notes.yaml, ADOPTERS.yaml). Úsala cuando el usuario quiera crear, diseñar o proponer un data model, una entidad NGSI-LD o un Smart Data Model, o saber si ya existe uno para su caso.
---

# sdm-ngsild-generator

> v0.6.0 · Entrevista completa (una o varias entidades, subject existente o nuevo, extensiones), entrega en ZIP con previsualización, visor HTML e informe, y prueba opcional contra un context broker NGSI-LD.

## Reglas que no se negocian

1. **Reutilizar antes de crear.** Busca siempre en el repositorio antes de proponer una entidad o un atributo. Recomendar un modelo existente tal cual es un resultado válido.
2. **Idiomas.** Habla con el usuario en su idioma. Todo el contenido del modelo va en inglés: entidad en PascalCase y atributos en camelCase, y también descripciones, enumeraciones, notas y ejemplos. Explica por qué eliges cada nombre.
3. **GitHub, solo lectura.** La única fuente es la organización `smart-data-models` de GitHub. Nunca escribas en ella, nunca crees pull requests y nunca pidas un token. No uses smartdatamodels.org como fuente.
4. **Lo mecánico, con scripts.** No inventes de memoria atributos, unidades ni estructuras: compruébalos con los scripts. No edites a mano los ficheros generados: cambia `proposal.yaml` y regenera.
5. **Confirmación en cada fase.** Cierra cada fase con un resumen y una pregunta explícita. No avances sin respuesta.
6. **Trazabilidad.** Anota cada decisión (reutilizado, extendido, nuevo o descartado), con su motivo y su origen, en `proposal.yaml`.
7. **Pedagogía concisa.** Explica cada concepto nuevo una sola vez y en pocas frases (Property frente a Relationship, `@context`, Commons, formato de descripciones, UN/CEFACT). Profundiza solo si te lo piden.

## Referencias (cárgalas cuando las necesites)

| Fichero | Cuándo |
|---|---|
| `references/interview-guide.md` | **Siempre al empezar.** Detalle de cada fase: preguntas, scripts, cierres y situaciones frecuentes. |
| `references/sdm-principles.md` | Fases 2, 3 y 4: reutilizar, dividir, obligatorios, versionado, licencia. |
| `references/ngsi-ld-basics.md` | Cuando aparezcan Property/Relationship, `@context`, URNs, los 4 ejemplos o el patrón Device/Observed. |
| `references/naming-and-descriptions.md` | Fase 4 y 5: nombres y formato de descripciones. |
| `references/units-uncefact.md` | Fase 4: unidades y códigos UN/CEFACT. |

## Cómo ejecutar los scripts

Los scripts están en `scripts/`, dentro del directorio de esta skill (`<skill>`). Necesitan Python 3.10+ y `requirements.txt`. La primera vez, si no existe `<skill>/.venv`:

```bash
python -m venv <skill>/.venv
<skill>/.venv/bin/pip install -r <skill>/requirements.txt          # macOS/Linux
<skill>\.venv\Scripts\pip install -r <skill>\requirements.txt      # Windows
```

Después, ejecuta `<skill>/.venv/bin/python <skill>/scripts/<script>.py …` (en Windows, `.venv\Scripts\python.exe`). Todos escriben JSON. Si traen `warnings` (por ejemplo, caché antigua porque GitHub no responde), comunícaselo al usuario.

| Script | Para qué |
|---|---|
| `sdm_index.py status \| update [--force]` | Estado o actualización de la caché de índices (caduca a los 7 días). |
| `search.py subjects [términos] [--domain D]` | Subjects (`dataModel.X`) y sus dominios. |
| `search.py models <términos> [--domain D] [--subject S]` | Modelos por nombre, título, etiquetas y descripción. |
| `search.py attributes <términos> \| --exact nombre` | Atributos: tipo NGSI, tipo JSON, unidades, modelos donde aparecen y Commons. |
| `search.py batch <lista.json> [--domain D]` | Modo «lista completa»: coincidencia exacta y parecidos de muchos atributos a la vez. |
| `search.py units <nombre en inglés> \| --code X` | Códigos UN/CEFACT (Rec. 20). |
| `fetch_schema.py <Model\|Subject/Model> [--resolve-commons] [--examples]` | Schema real de un candidato y atributos de sus Commons. |
| `generate.py <proposal.yaml> --out <carpeta de trabajo> [--force]` | Genera `contribution/` (entidades nuevas) y `extensions/` (modelos existentes ampliados). Formato de `proposal.yaml` en su cabecera. |
| `package.py <carpeta de trabajo> --spec <proposal.yaml> [--lang es] [--strings f.json]` | Entrega final: valida (no empaqueta si hay `fail`), genera `preview/`, `viewer.html` y `report.md`, y crea `<nombre>.zip`. |
| `broker_test.py <carpeta de trabajo> --spec <proposal.yaml> --broker <URL> [--tenant t] [--context-mode auto\|inline\|served\|published]` | **Solo si el usuario lo pide y da la URL de su broker.** Crea los ejemplos NGSI-LD, los lee y compara, consulta por tipo y los borra. Escribe `broker-result.json`, que `package.py` incluye en el informe. |
| `preview.py` · `build_viewer.py` | Previsualización (model.yaml, spec.md, @context) y visor por separado, si quieres revisarlos antes de empaquetar. |
| `i18n.py export en` | Plantilla de textos para un idioma distinto de es/en: tradúcela y pásala con `--strings`. |
| `validate.py <carpeta de trabajo> --spec <proposal.yaml> [--check-urls]` | Validación local: pruebas oficiales SDM, coherencia NGSI-LD, duplicados con el repositorio, extensiones frente al original y enlaces entre las entidades de la propuesta. |

Los índices están en inglés y la búsqueda es por términos, no por significado. Lanza varias consultas (sinónimos, abreviaturas, el nombre camelCase esperado) y **decide tú la pertinencia** antes de presentar resultados.

## Flujo: siete fases

Trabaja en una carpeta `sdm-proposal-<nombre>/` dentro del directorio actual del usuario. Ve completando `sdm-proposal-<nombre>/proposal.yaml` fase a fase.

1. **Contexto.** Qué se modela, en qué dominio, para qué caso de uso real, quién produce y consume los datos y con qué frecuencia. Pide datos de ejemplo si los hay.
2. **Búsqueda de lo existente.** Subjects y modelos candidatos, revisión de sus schemas y tabla comparativa. Decide con el usuario: **reutilizar tal cual** (puede terminar aquí), **extender** (`extensions`: solo se añaden atributos opcionales) o **crear**. Una misma propuesta puede combinar entidades nuevas y extensiones. Registra los descartes en `decisions`.
3. **Estructura.** Entidades, nombres y subject. Divide solo por ciclos de vida distintos o por conceptos referenciables. Lo que ya existe se enlaza con una Relationship, no se duplica. Subject existente salvo que haya una familia de modelos sin sitio natural; en ese caso, `newSubject` con sus dominios.
4. **Atributos.** Modo **guiado** (uno a uno) o **lista completa** (`search.py batch`, propuesta en bloque y discusión solo de los dudosos); el usuario puede cambiar de modo cuando quiera. Commons referenciados, no redefinidos. Unidades comprobadas. Obligatorios mínimos.
5. **Relaciones.** Destino en la propuesta o en el repositorio (comprobado), nombre (reutilizado o con verbo), cardinalidad y `target`. Los ejemplos de entidades de la propuesta se enlazan solos por su `id`.
6. **Metadatos.** Autoría (`CONTRIBUTORS.yaml`), licencia (CC BY 4.0 recomendada), adoptantes y notas.
7. **Generación y entrega.** Ejemplos realistas, `language` y traducciones (`label`) para el visor, confirmación de `proposal.yaml`, `generate.py --out sdm-proposal-<nombre>`, `validate.py` y corrección hasta que no haya `fail`. Después, `package.py`: ZIP con `contribution/`, `extensions/`, `preview/`, `viewer.html`, `report.md` y `proposal.yaml`. Resume la entrega e invita a abrir `viewer.html`. El usuario decide si contribuye; la skill nunca abre pull requests.

Detalle de cada fase: `references/interview-guide.md`.

## Interpretar la validación

- `fail`: no se entrega. Corrige `proposal.yaml`, regenera con `--force` y valida otra vez.
- `warn` en `repository`: un atributo «nuevo» ya existe. Propón reutilizarlo o registra la `justification`.
- `warn` en `naming`: recomendaciones de la guía SDM, como el prefijo `date` o un verbo en lugar de `ref`. Coméntalas con el usuario.
- `warn` en `units`: código obsoleto en la Rec. 20. Propón el vigente.
- Avisos normales en una propuesta nueva: `derivedFrom` vacío y, con `--check-urls`, el `@context` de un subject aún no publicado.
- Extensiones: los problemas que ya tenía el modelo original aparecen como «(preexistente en el original)» en `info` y no bloquean. Menciónalos al usuario como posibles mejoras, pero no los corrijas: la extensión solo añade.
- Prueba con broker: si `health` falla, el broker no responde en esa URL (pide al usuario que la revise). Si `create` falla en modo `inline` con Stellio u otros brokers, usa `served` (`auto` ya lo hace). `published` no envía entidades de un subject nuevo, porque su `@context` aún no existe. Los avisos sobre «contexto por defecto» indican términos que el broker no podrá expandir con el contexto publicado hasta que SDM lo regenere.
- `proposal`: comprobaciones del conjunto (subject, destinos de las Relationship, enlaces entre ejemplos). Un destino que no está ni en la propuesta ni en el repositorio es un aviso a resolver.
