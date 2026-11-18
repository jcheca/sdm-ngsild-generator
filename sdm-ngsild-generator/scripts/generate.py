#!/usr/bin/env python3
"""Genera los ficheros de contribución SDM a partir de una especificación de propuesta.

Estructura de salida (``<out>`` es la carpeta de trabajo de la propuesta)::

    <out>/contribution/                      entidades nuevas, con la estructura oficial
        <Entity>/schema.json
        <Entity>/examples/example.json                 NGSI v2 key-values
        <Entity>/examples/example-normalized.json      NGSI v2 normalizado
        <Entity>/examples/example.jsonld               NGSI-LD key-values
        <Entity>/examples/example-normalized.jsonld    NGSI-LD normalizado
        <Entity>/notes.yaml
        <Entity>/ADOPTERS.yaml
        <Entity>/LICENSE.md           solo si la licencia es CC-BY-4.0 (texto oficial SDM)
        CONTRIBUTORS.yaml             autoría (formato del CONTRIBUTORS.yaml del subject)
        notes.yaml                    solo en un subject nuevo (notesPrevious, notesEnd)
    <out>/extensions/<subject>/              extensiones de modelos existentes
        <Model>/...                   copia del modelo original con los atributos añadidos
        CHANGES-<Model>.md            resumen del cambio para los mantenedores (inglés)
        CONTRIBUTORS.yaml             autoría

Uso::

    python generate.py proposal.yaml --out ./sdm-proposal-x [--force] [--offline]

Especificación (YAML o JSON; todo el contenido en inglés)::

    name: soil-probe                     # opcional: nombre del ZIP (package.py)
    language: es                         # idioma del usuario para visor e informe
    subject: dataModel.Agrifood          # subject de las entidades nuevas
    newSubject:                          # SOLO si el subject no existe todavía
      domains: [SmartAgrifood]           # dominios SDM a los que pertenecería
      notes: {notesPrevious: "...", notesEnd: "..."}   # notes.yaml del subject (opcional)
    extensions:                          # ampliaciones de modelos existentes (opcional)
      - model: dataModel.Weather/WeatherObserved
        reason: Agro-meteorological stations also publish reference evapotranspiration
        example: {observedAt: "2026-06-01T10:00:00Z"}  # opcional
        adopters: [...]                  # opcional: se añaden a los del modelo
        attributes: [...]                # mismo formato que en las entidades
    metadata:                            # fase 6 (opcional)
      license: CC-BY-4.0                 # recomendada; con otra, indica licenseUrl
      licenseUrl: ...                    # solo si no es CC-BY-4.0
      contributors:
        - {name: Ada, surname: Lovelace, mail: ..., organization: ..., project: ..., year: 2026}
    decisions:                           # registro de decisiones (trazabilidad)
      - item: AgriParcelRecord           # modelo o atributo
        decision: discarded              # reused | extended | new | discarded
        reason: Records parcel-level conditions, not per-probe depth profiles
        source: dataModel.Agrifood/AgriParcelRecord
    entities:
      - name: SoilProbeObserved          # PascalCase
        label: Observación de sonda de suelo   # opcional: traducción para el visor
        version: 0.0.1                   # opcional (0.0.1)
        title: Smart Data Models - Soil Probe Observed
        description: >-                  # 50 caracteres o más
          Observation of soil conditions measured by a probe at a given depth
        modelTags: ""                    # opcional
        derivedFrom: ""                  # opcional
        license: ""                      # opcional; por defecto LICENSE.md del modelo
        commons: [GSMA-Commons, Location-Commons]   # nombres o URLs $ref completas
        required: [id, type, dateObserved]          # id y type se añaden siempre
        notes: {notesHeader: "...", notesReadme: "..."}  # opcional
        adopters: [{adopter: ..., organization: ...}]    # opcional
        example:                         # opcional
          id: urn:ngsi-ld:SoilProbeObserved:probe-001
          observedAt: "2026-05-04T12:30:00Z"
          commons: {name: Probe 1, location: {type: Point, coordinates: [-4.77, 37.88]}}
        attributes:
          - name: soilTemperature        # camelCase
            label: temperatura del suelo # opcional: traducción para el visor/informe
            ngsi: Property               # Property | Relationship | GeoProperty
            type: number                 # number|integer|string|boolean|object|array
            format: date-time            # opcional (date-time, date, uri...)
            model: https://schema.org/Number   # opcional; por defecto según el tipo
            units: CEL                   # código UN/CEFACT (opcional)
            unitsText: degree Celsius    # opcional, solo para la descripción
            description: Soil temperature measured by the probe
            enum: [...]                  # opcional; también minimum, maximum, pattern...
            temporal: true               # opcional: añade observedAt / timestamp
            target: Device               # solo Relationship: tipo apuntado (de la propuesta
                                         # o del repositorio)
            multiple: false              # solo Relationship: lista de entidades
            items: {type: string, description: ...}     # solo array
            properties: {depth: {type: number, description: ...}}  # solo object
            example: 18.5                # valor key-values; si falta se inventa uno
            origin: reused               # new | reused (trazabilidad)
            reusedFrom: dataModel.Agrifood/AgriParcelRecord
            justification: ...           # si es nuevo pero existe un nombre parecido

La salida (JSON) lista los ficheros generados y los avisos.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any

import yaml

import fetch_schema
import sdm_index
import units as uncefact

SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
CORE_CONTEXT = "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"
COMMONS_URL = fetch_schema.COMMONS_URL
TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
EXAMPLE_FILES = fetch_schema.EXAMPLE_FILES
SUPPORTED_NGSI = ("Property", "Relationship", "GeoProperty")
DECISIONS = ("reused", "extended", "new", "discarded")
DEFAULT_LICENSE = "CC-BY-4.0"
JSON_TYPES = ("string", "number", "integer", "boolean", "object", "array")
IDENTIFIER_PATTERN = r"^[\w\-\.\{\}\$\+\*\[\]`|~^@!,:\\]+$"
DEFAULT_GEO = {"type": "Point", "coordinates": [-4.7794, 37.8882]}
DEFAULT_DATETIME = "2026-01-15T10:00:00Z"
ENTITY_NAME_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")
ATTRIBUTE_NAME_RE = re.compile(r"^[a-z][A-Za-z0-9]*$")
# Claves de JSON Schema que se copian tal cual desde la especificación.
PASSTHROUGH_KEYS = ("format", "enum", "minimum", "maximum", "exclusiveMinimum",
                    "exclusiveMaximum", "minLength", "maxLength", "pattern", "minItems",
                    "maxItems", "uniqueItems")


class SpecError(ValueError):
    """La especificación de la propuesta no es correcta."""


# --------------------------------------------------------------------------- utilidades

def subject_context_url(subject: str) -> str:
    """URL del ``@context`` de un subject en GitHub."""
    return f"{sdm_index.RAW_BASE}/{subject}/{sdm_index.DEFAULT_BRANCH}/context.jsonld"


def schema_id(subject: str, entity: str) -> str:
    return f"{sdm_index.PAGES_BASE}/{subject}/{entity}/schema.json"


def default_model(spec: dict[str, Any]) -> str | None:
    """Modelo de referencia (schema.org) por defecto según el tipo JSON y el formato."""
    fmt = spec.get("format")
    if fmt == "date-time":
        return "https://schema.org/DateTime"
    if fmt == "date":
        return "https://schema.org/Date"
    if fmt == "uri":
        return "https://schema.org/URL"
    return {
        "string": "https://schema.org/Text",
        "number": "https://schema.org/Number",
        "integer": "https://schema.org/Integer",
        "boolean": "https://schema.org/Boolean",
        "object": "https://schema.org/StructuredValue",
    }.get(spec.get("type"))


def build_description(ngsi: str, spec: dict[str, Any]) -> str:
    """Descripción en formato SDM: ``NGSI. Model:'…'. Units:'…'. Enum:'…'. Texto``.

    Las partes se separan con ``". "`` porque así las interpreta la prueba oficial
    ``test_schema_descriptions`` del repositorio smart-data-models.
    """
    parts = [ngsi]
    model = spec.get("model", default_model(spec) if ngsi == "Property" else None)
    if model:
        parts.append(f"Model:'{model}'")
    if spec.get("units"):
        units = spec["units"]
        text = spec.get("unitsText")
        parts.append(f"Units:'{text} ({units})'" if text else f"Units:'{units}'")
    if spec.get("enum"):
        parts.append("Enum:'" + ", ".join(str(v) for v in spec["enum"]) + "'")
    text = str(spec.get("description", "")).strip().rstrip(".")
    if not text:
        raise SpecError(f"Falta la descripción de '{spec.get('name', '?')}'.")
    parts.append(text)
    return ". ".join(parts)


def _value_schema(spec: dict[str, Any], *, path: str) -> dict[str, Any]:
    """Schema de un valor (atributo, subatributo o ``items``) de tipo Property."""
    jtype = spec.get("type")
    if jtype not in JSON_TYPES:
        raise SpecError(f"'{path}': tipo '{jtype}' no válido. Usa uno de {JSON_TYPES}.")
    result: dict[str, Any] = {"type": jtype}
    for key in PASSTHROUGH_KEYS:
        if key in spec:
            result[key] = spec[key]
    if jtype == "array":
        items = spec.get("items")
        if not isinstance(items, dict):
            raise SpecError(f"'{path}': un array necesita 'items'.")
        result["items"] = _value_schema(items, path=f"{path}.items")
    if jtype == "object":
        props = spec.get("properties")
        if not isinstance(props, dict) or not props:
            raise SpecError(f"'{path}': un object necesita 'properties'.")
        result["properties"] = {
            name: _value_schema({"name": name, **sub}, path=f"{path}.{name}")
            for name, sub in props.items()
        }
    result["description"] = build_description("Property", spec)
    return result


def identifier_schema() -> dict[str, Any]:
    """Formato de identificador NGSI usado por los modelos SDM para las Relationship."""
    return {
        "anyOf": [
            {"type": "string", "minLength": 1, "maxLength": 256, "pattern": IDENTIFIER_PATTERN,
             "description": "Property. Identifier format of any NGSI entity"},
            {"type": "string", "format": "uri",
             "description": "Property. Identifier format of any NGSI entity"},
        ]
    }


def attribute_schema(attr: dict[str, Any]) -> dict[str, Any]:
    ngsi = attr.get("ngsi", "Property")
    name = attr["name"]
    if ngsi == "Relationship":
        if attr.get("multiple"):
            result: dict[str, Any] = {"type": "array", "items": identifier_schema()}
            for key in ("minItems", "maxItems", "uniqueItems"):
                if key in attr:
                    result[key] = attr[key]
        else:
            result = identifier_schema()
        result["description"] = build_description("Relationship", attr)
        return result
    if ngsi == "GeoProperty":
        return {
            "$ref": f"{COMMONS_URL}#/definitions/Location-Commons/properties/location",
            "description": build_description("GeoProperty", {**attr, "model": None}),
        }
    return _value_schema(attr, path=name)


def resolve_commons(names: list[str]) -> list[str]:
    refs = []
    for item in names:
        if item.startswith("http"):
            refs.append(item)
        else:
            refs.append(f"{COMMONS_URL}#/definitions/{item}")
    return refs


# --------------------------------------------------------------------------- validación de la especificación

SUBJECT_RE = re.compile(r"^dataModel\.[A-Za-z0-9-]+$")
MODEL_REF_RE = re.compile(r"^(dataModel\.[A-Za-z0-9-]+)/([A-Z][A-Za-z0-9]*)$")


def _check_attributes(owner: str, attributes: Any) -> None:
    if not isinstance(attributes, list):
        raise SpecError(f"{owner}: 'attributes' debe ser una lista.")
    seen = set()
    for attr in attributes:
        aname = attr.get("name", "") if isinstance(attr, dict) else ""
        if not ATTRIBUTE_NAME_RE.fullmatch(aname):
            raise SpecError(f"{owner}: atributo '{aname}' no válido: usa camelCase en inglés.")
        if aname in seen or aname in ("id", "type"):
            raise SpecError(f"{owner}: atributo '{aname}' repetido o reservado.")
        seen.add(aname)
        ngsi = attr.get("ngsi", "Property")
        if ngsi not in SUPPORTED_NGSI:
            raise SpecError(f"{owner}.{aname}: tipo NGSI '{ngsi}' no soportado "
                            f"(admitidos: {', '.join(SUPPORTED_NGSI)}).")
        if ngsi == "Relationship" and not attr.get("target"):
            raise SpecError(f"{owner}.{aname}: una Relationship necesita 'target'.")
        for code in _unit_codes(attr):
            level, message = uncefact.check_code(code)
            if level == "error":
                raise SpecError(f"{owner}.{aname}: {message}. Busca el código con "
                                "'search.py units <nombre en inglés>'.")
        if attr.get("origin") not in (None, "new", "reused"):
            raise SpecError(f"{owner}.{aname}: 'origin' debe ser 'new' o 'reused'.")


def check_spec(spec: dict[str, Any]) -> None:
    if not isinstance(spec, dict):
        raise SpecError("La especificación debe ser un objeto con 'entities' y/o 'extensions'.")
    entities = spec.get("entities") or []
    extensions = spec.get("extensions") or []
    if not isinstance(entities, list) or not isinstance(extensions, list):
        raise SpecError("'entities' y 'extensions' deben ser listas.")
    if not entities and not extensions:
        raise SpecError("La propuesta necesita al menos una entidad nueva o una extensión.")
    if entities and not SUBJECT_RE.fullmatch(spec.get("subject") or ""):
        raise SpecError("'subject' debe tener la forma dataModel.<Nombre>.")
    new_subject = spec.get("newSubject")
    if new_subject is not None:
        if not entities:
            raise SpecError("'newSubject' solo tiene sentido con entidades nuevas.")
        if not isinstance(new_subject, dict) or not new_subject.get("domains"):
            raise SpecError("'newSubject' necesita 'domains' (p. ej. [SmartAgrifood]).")
        unknown = set(new_subject.get("notes") or {}) - {"notesPrevious", "notesEnd"}
        if unknown:
            raise SpecError(f"newSubject.notes: claves desconocidas {sorted(unknown)} "
                            "(admitidas: notesPrevious, notesEnd).")
    names: set[str] = set()
    for ent in entities:
        name = ent.get("name", "")
        if not ENTITY_NAME_RE.fullmatch(name):
            raise SpecError(f"Nombre de entidad '{name}' no válido: usa PascalCase en inglés.")
        if name in names:
            raise SpecError(f"Entidad '{name}' repetida en la propuesta.")
        names.add(name)
        if len(ent.get("title", "")) < 15:
            raise SpecError(f"{name}: 'title' debe tener al menos 15 caracteres.")
        if len(ent.get("description", "")) < 50:
            raise SpecError(f"{name}: 'description' debe tener al menos 50 caracteres.")
        if not re.fullmatch(r"\d{1,2}\.\d{1,2}\.\d{1,2}", str(ent.get("version", "0.0.1"))):
            raise SpecError(f"{name}: 'version' debe tener el formato XX.XX.XX.")
        _check_attributes(name, ent.get("attributes", []))
    targets: set[str] = set()
    for ext in extensions:
        ref = ext.get("model", "") if isinstance(ext, dict) else ""
        if not MODEL_REF_RE.fullmatch(ref):
            raise SpecError(f"Extensión '{ref}': 'model' debe tener la forma "
                            "dataModel.<Subject>/<Model>.")
        if ref in targets:
            raise SpecError(f"Extensión '{ref}' repetida.")
        targets.add(ref)
        if not ext.get("reason"):
            raise SpecError(f"Extensión '{ref}': falta 'reason' (por qué hay que ampliarlo).")
        if not ext.get("attributes"):
            raise SpecError(f"Extensión '{ref}': indica los atributos que se añaden.")
        if ext.get("required"):
            raise SpecError(f"Extensión '{ref}': añadir obligatorios rompe la compatibilidad "
                            "con los datos existentes; los atributos nuevos deben ser opcionales.")
        _check_attributes(ref, ext["attributes"])
    metadata = spec.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise SpecError("'metadata' debe ser un objeto.")
    if metadata.get("license", DEFAULT_LICENSE) != DEFAULT_LICENSE and not metadata.get("licenseUrl"):
        raise SpecError("Con una licencia distinta de CC-BY-4.0 hay que indicar 'licenseUrl'.")
    for contributor in metadata.get("contributors") or []:
        if not isinstance(contributor, dict) or not (contributor.get("name") or
                                                       contributor.get("organization")):
            raise SpecError("Cada contribuidor necesita al menos 'name' u 'organization'.")
    for decision in spec.get("decisions") or []:
        if not isinstance(decision, dict) or not decision.get("item") or \
                decision.get("decision") not in DECISIONS or not decision.get("reason"):
            raise SpecError("Cada decisión necesita 'item', 'reason' y 'decision' "
                            f"({' | '.join(DECISIONS)}).")


def _unit_codes(attr: dict[str, Any]) -> list[str]:
    """Códigos de unidad declarados en un atributo y en sus subatributos."""
    codes = [attr["units"]] if attr.get("units") else []
    for sub in (attr.get("properties") or {}).values():
        if isinstance(sub, dict):
            codes += _unit_codes(sub)
    if isinstance(attr.get("items"), dict):
        codes += _unit_codes(attr["items"])
    return codes


def spec_warnings(spec: dict[str, Any]) -> list[str]:
    """Avisos no bloqueantes sobre la especificación."""
    warnings = []
    owners = [(e["name"], e) for e in spec.get("entities") or []] + \
        [(x["model"], x) for x in spec.get("extensions") or []]
    for owner, item in owners:
        for attr in item.get("attributes", []):
            for code in _unit_codes(attr):
                level, message = uncefact.check_code(code)
                if level == "warn":
                    warnings.append(f"{owner}.{attr['name']}: {message}")
    return warnings


def check_subject(spec: dict[str, Any], official: dict[str, Any]) -> None:
    """Contrasta la propuesta con la lista oficial de subjects y modelos."""
    repos = {r["repoName"]: r for r in official["officialList"]}
    subject = spec.get("subject")
    if spec.get("entities"):
        exists = subject in repos
        if spec.get("newSubject") is not None and exists:
            raise SpecError(f"'{subject}' ya existe en el repositorio: quita 'newSubject'.")
        if spec.get("newSubject") is None and not exists:
            close = [r for r in repos if r.lower() == str(subject).lower()]
            hint = f" ¿Querías decir {close[0]}?" if close else \
                " Si es un subject nuevo, decláralo con 'newSubject: {domains: [...]}'."
            raise SpecError(f"El subject '{subject}' no existe en el repositorio.{hint}")
    for ext in spec.get("extensions") or []:
        ext_subject, model = MODEL_REF_RE.fullmatch(ext["model"]).groups()
        if ext_subject not in repos or model not in repos[ext_subject]["dataModels"]:
            raise SpecError(f"Extensión: el modelo '{ext['model']}' no existe en la lista oficial.")


# --------------------------------------------------------------------------- schema

def license_url(entity: dict[str, Any], subject: str,
                metadata: dict[str, Any] | None = None) -> str:
    metadata = metadata or {}
    if entity.get("license"):
        return entity["license"]
    if metadata.get("license", DEFAULT_LICENSE) != DEFAULT_LICENSE:
        return metadata["licenseUrl"]
    return f"{sdm_index.PAGES_BASE}/{subject}/{entity['name']}/LICENSE.md"


def build_schema(entity: dict[str, Any], subject: str,
                 metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    name = entity["name"]
    properties: dict[str, Any] = {
        "type": {
            "type": "string",
            "enum": [name],
            "description": f"Property. NGSI Entity type. It has to be {name}",
        }
    }
    for attr in entity.get("attributes", []):
        properties[attr["name"]] = attribute_schema(attr)
    required = ["id", "type"] + [r for r in entity.get("required", []) if r not in ("id", "type")]
    all_of: list[dict[str, Any]] = [{"$ref": r} for r in resolve_commons(entity.get("commons", []))]
    all_of.append({"properties": properties})
    return {
        "$schema": SCHEMA_DIALECT,
        "$schemaVersion": str(entity.get("version", "0.0.1")),
        "$id": schema_id(subject, name),
        "title": entity["title"],
        "description": entity["description"],
        "modelTags": entity.get("modelTags", ""),
        "derivedFrom": entity.get("derivedFrom", ""),
        "license": license_url(entity, subject, metadata),
        "type": "object",
        "allOf": all_of,
        "required": required,
    }


# --------------------------------------------------------------------------- ejemplos

def example_id(entity_type: str, suffix: str | None = None) -> str:
    suffix = suffix or str(uuid.uuid5(uuid.NAMESPACE_URL, f"sdm-ngsild-generator/{entity_type}"))
    return f"urn:ngsi-ld:{entity_type}:{suffix}"


def default_value(spec: dict[str, Any], ngsi: str = "Property", name: str = "value") -> Any:
    """Valor de ejemplo verosímil cuando la especificación no lo indica."""
    if ngsi == "Relationship":
        target = spec.get("target", "Entity")
        one = example_id(target, str(uuid.uuid5(uuid.NAMESPACE_URL, f"{target}/{name}")))
        return [one] if spec.get("multiple") else one
    if ngsi == "GeoProperty":
        return copy.deepcopy(DEFAULT_GEO)
    if spec.get("enum"):
        return spec["enum"][0]
    jtype, fmt = spec.get("type"), spec.get("format")
    if jtype == "string":
        if fmt == "date-time":
            return DEFAULT_DATETIME
        if fmt == "date":
            return DEFAULT_DATETIME[:10]
        if fmt == "uri":
            return f"https://example.org/{name}"
        return f"Example {name}"
    if jtype in ("number", "integer"):
        lo, hi = spec.get("minimum"), spec.get("maximum")
        if lo is not None and hi is not None:
            val = (lo + hi) / 2
        elif lo is not None:
            val = lo + 1
        elif hi is not None:
            val = hi - 1
        else:
            val = 1
        return int(val) if jtype == "integer" else float(val)
    if jtype == "boolean":
        return True
    if jtype == "object":
        return {k: default_value({"name": k, **v}, name=k)
                for k, v in spec.get("properties", {}).items()}
    if jtype == "array":
        return [default_value(spec.get("items", {}), name=name)]
    return None


def v2_type(ngsi: str, spec: dict[str, Any], value: Any) -> str:
    """Tipo de atributo NGSI v2 (la prueba oficial prohíbe Property/Relationship en v2)."""
    if ngsi == "Relationship":
        return "Text"
    if ngsi == "GeoProperty":
        return "geo:json"
    fmt, jtype = spec.get("format"), spec.get("type")
    if fmt == "date-time":
        return "DateTime"
    if fmt == "date":
        return "Date"
    if fmt == "uri":
        return "URL"
    if jtype is None:
        jtype = {bool: "boolean", int: "number", float: "number", str: "string",
                 dict: "object", list: "array"}.get(type(value), "string")
    return {"string": "Text", "number": "Number", "integer": "Number",
            "boolean": "Boolean"}.get(jtype, "StructuredValue")


def _commons_attribute_info(refs: list[str], *, offline: bool) -> dict[str, dict[str, Any]]:
    """Tipo NGSI y JSON de los atributos aportados por los Commons referenciados."""
    info: dict[str, dict[str, Any]] = {}
    for ref in refs:
        try:
            definition = fetch_schema.resolve_ref(ref, offline=offline)
        except (sdm_index.IndexUnavailable, LookupError, json.JSONDecodeError):
            continue
        for item in fetch_schema.summarize_properties(definition.get("properties", {})):
            jtype = item["type"] if isinstance(item["type"], str) else None
            info[item["name"]] = {"ngsi": item["ngsi_type"] or "Property", "type": jtype,
                                  "format": item.get("format")}
    info.setdefault("location", {"ngsi": "GeoProperty", "type": None, "format": None})
    return info


def entity_example_id(entity: dict[str, Any]) -> str:
    return (entity.get("example") or {}).get("id") or example_id(entity["name"])


def attribute_value(attr: dict[str, Any], *, observed_at: str | None = None,
                    example_ids: dict[str, str] | None = None) -> Any:
    """Valor key-values del atributo: el de la especificación o uno verosímil.

    Una Relationship hacia otra entidad de la propuesta usa el ``id`` del ejemplo de esa
    entidad, para que los ejemplos formen un conjunto de datos coherente.
    """
    ngsi = attr.get("ngsi", "Property")
    if "example" in attr:
        return attr["example"]
    if ngsi == "Relationship" and example_ids and attr.get("target") in example_ids:
        one = example_ids[attr["target"]]
        return [one] if attr.get("multiple") else one
    if observed_at and attr.get("format") == "date-time":
        return observed_at  # coherente con el instante de observación del ejemplo
    return default_value(attr, ngsi, attr["name"])


def attribute_forms(ngsi: str, spec: dict[str, Any], value: Any, *, temporal: bool = False,
                    units: str | None = None,
                    observed_at: str | None = None) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    """Representación de un atributo en key-values, NGSI v2 normalizado y NGSI-LD normalizado."""
    v2attr: dict[str, Any] = {"type": v2_type(ngsi, spec, value), "value": copy.deepcopy(value)}
    metadata: dict[str, Any] = {}
    if units:
        metadata["unitCode"] = {"type": "Text", "value": units}
    if temporal and observed_at:
        metadata["timestamp"] = {"type": "DateTime", "value": observed_at}
    if metadata:
        v2attr["metadata"] = metadata

    if ngsi == "Relationship":
        ldattr: dict[str, Any] = {"type": "Relationship", "object": copy.deepcopy(value)}
    elif ngsi == "GeoProperty":
        ldattr = {"type": "GeoProperty", "value": copy.deepcopy(value)}
    else:
        ldvalue = copy.deepcopy(value)
        if spec.get("format") == "date-time" and isinstance(value, str):
            ldvalue = {"@type": "DateTime", "@value": value}
        ldattr = {"type": "Property", "value": ldvalue}
        if units:
            ldattr["unitCode"] = units
    if temporal and observed_at:
        ldattr["observedAt"] = observed_at
    return copy.deepcopy(value), v2attr, ldattr


def build_examples(entity: dict[str, Any], subject: str, *,
                   commons_info: dict[str, dict[str, Any]],
                   example_ids: dict[str, str] | None = None) -> dict[str, dict[str, Any]]:
    name = entity["name"]
    ex_cfg = entity.get("example", {}) or {}
    ent_id = entity_example_id(entity)
    observed_at = ex_cfg.get("observedAt")

    kv: dict[str, Any] = {"id": ent_id, "type": name}
    v2n: dict[str, Any] = {"id": ent_id, "type": name}
    ldn: dict[str, Any] = {"id": ent_id, "type": name}
    for cname, cvalue in (ex_cfg.get("commons") or {}).items():
        meta = commons_info.get(cname, {"ngsi": "Property", "type": None, "format": None})
        kv[cname], v2n[cname], ldn[cname] = attribute_forms(meta["ngsi"], meta, cvalue)
    for attr in entity.get("attributes", []):
        value = attribute_value(attr, observed_at=observed_at, example_ids=example_ids)
        kv[attr["name"]], v2n[attr["name"]], ldn[attr["name"]] = attribute_forms(
            attr.get("ngsi", "Property"), attr, value, temporal=bool(attr.get("temporal")),
            units=attr.get("units"), observed_at=observed_at)

    context = subject_context_url(subject)
    kv_ld = {**copy.deepcopy(kv), "@context": [context]}
    ldn["@context"] = [CORE_CONTEXT, context]
    return {
        "example.json": kv,
        "example-normalized.json": v2n,
        "example.jsonld": kv_ld,
        "example-normalized.jsonld": ldn,
    }


# --------------------------------------------------------------------------- yaml

def _load_template(name: str) -> Any:
    return yaml.safe_load((TEMPLATES / name).read_text(encoding="utf-8"))


def build_notes(entity: dict[str, Any]) -> dict[str, str]:
    notes = _load_template("notes.yaml")
    for key, value in (entity.get("notes") or {}).items():
        if key not in notes:
            raise SpecError(f"{entity['name']}: clave de notes.yaml desconocida '{key}'.")
        notes[key] = value
    return notes


def build_contributors(metadata: dict[str, Any]) -> dict[str, Any] | None:
    contributors = metadata.get("contributors") or []
    if not contributors:
        return None
    keys = ("name", "surname", "mail", "organization", "project", "comments", "year")
    rows = [{k: c.get(k) for k in keys} for c in contributors]
    rows.sort(key=lambda r: (str(r.get("surname") or r.get("name") or "").lower(),
                             str(r.get("name") or "").lower()))
    return {
        "description": "This is a compilation list of all CONTRIBUTORS across different objects "
                       "(data models) alphabetically ordered. All fields are non mandatory",
        "contributors": rows,
    }


def build_adopters(entity: dict[str, Any], subject: str) -> dict[str, Any]:
    adopters = _load_template("ADOPTERS.yaml")
    adopters["description"] = adopters["description"].format(dataModel=entity["name"],
                                                             subject=subject)
    blank = adopters["currentAdopters"][0]
    if entity.get("adopters"):
        adopters["currentAdopters"] = [{**blank, **a} for a in entity["adopters"]]
    return adopters


# --------------------------------------------------------------------------- escritura

def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------- extensiones

def bump_minor(version: str) -> str:
    """Añadir atributos incrementa la versión minor (data-models/versioning.md)."""
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", str(version).strip())
    if not match:
        return "0.1.0"
    major, minor, _ = (int(g) for g in match.groups())
    return f"{major}.{minor + 1}.0"


def _own_block(schema: dict[str, Any]) -> dict[str, Any]:
    """Bloque ``properties`` propio del modelo (último del allOf, o la raíz)."""
    for block in reversed(schema.get("allOf", [])):
        if isinstance(block, dict) and isinstance(block.get("properties"), dict):
            return block
    schema.setdefault("properties", {})
    return schema


def _with_attribute(doc: dict[str, Any], name: str, value: Any) -> dict[str, Any]:
    """Añade ``name`` al ejemplo manteniendo ``@context`` al final si lo estaba."""
    out = {k: v for k, v in doc.items() if k != "@context"}
    out[name] = value
    if "@context" in doc:
        out["@context"] = doc["@context"]
    return out


def build_changes_md(ext: dict[str, Any], subject: str, model: str, old: str, new: str,
                     metadata: dict[str, Any]) -> str:
    lines = [
        f"# Proposed extension of {model} ({subject})",
        "",
        f"- Model: `{subject}/{model}`",
        f"- Version: `{old}` → `{new}` (minor: new optional attributes, backwards compatible)",
        f"- Reason: {ext['reason']}",
        "",
        "## Added attributes",
        "",
        "| Attribute | NGSI type | Type | Units | Origin | Description |",
        "|---|---|---|---|---|---|",
    ]
    for attr in ext["attributes"]:
        ngsi = attr.get("ngsi", "Property")
        jtype = "array" if ngsi == "Relationship" and attr.get("multiple") else \
            ("URI" if ngsi == "Relationship" else ("GeoJSON" if ngsi == "GeoProperty"
                                                   else attr.get("type", "")))
        origin = f"reused from `{attr['reusedFrom']}`" if attr.get("reusedFrom") else \
            attr.get("origin", "new")
        lines.append(f"| `{attr['name']}` | {ngsi} | {jtype} | {attr.get('units', '')} | "
                     f"{origin} | {str(attr.get('description', '')).strip()} |")
    lines += ["", "All existing attributes, required fields and examples are unchanged; the "
              "new attributes have been added to the schema and to the four examples.", ""]
    contributors = [" ".join(str(c.get(k) or "") for k in ("name", "surname")).strip()
                    or str(c.get("organization")) for c in metadata.get("contributors") or []]
    if contributors:
        lines += ["## Contributors", ""] + [f"- {c}" for c in contributors] + [""]
    return "\n".join(lines)


def build_extension(ext: dict[str, Any], out_root: Path, *, metadata: dict[str, Any],
                    example_ids: dict[str, str], offline: bool, force: bool) -> dict[str, Any]:
    subject, model = MODEL_REF_RE.fullmatch(ext["model"]).groups()
    target = out_root / "extensions" / subject / model
    if target.exists() and any(target.iterdir()) and not force:
        raise SpecError(f"'{target}' ya existe. Usa --force para sobrescribir.")
    try:
        base, missing = fetch_schema.fetch_model_files(subject, model, offline=offline)
    except sdm_index.IndexUnavailable as exc:
        raise SpecError(f"No se pudo obtener {ext['model']} de GitHub: {exc}") from exc
    warnings = [f"{ext['model']}: el original no tiene '{m}'" for m in missing]

    schema = json.loads((base / "schema.json").read_text(encoding="utf-8"))
    block = _own_block(schema)
    existing = set(block["properties"])
    refs = [b["$ref"] for b in schema.get("allOf", []) if isinstance(b, dict) and "$ref" in b]
    commons_attrs = _commons_attribute_info(refs, offline=offline)
    for attr in ext["attributes"]:
        if attr["name"] in existing or attr["name"] in commons_attrs:
            raise SpecError(f"{ext['model']}: '{attr['name']}' ya existe en el modelo o en sus "
                            "Commons; una extensión solo puede añadir atributos.")
        block["properties"][attr["name"]] = attribute_schema(attr)
    old_version = str(schema.get("$schemaVersion", "0.0.0"))
    schema["$schemaVersion"] = bump_minor(old_version)

    observed_at = (ext.get("example") or {}).get("observedAt")
    examples: dict[str, Any] = {}
    for fname in EXAMPLE_FILES:
        path = base / "examples" / fname
        if not path.is_file():
            raise SpecError(f"{ext['model']}: falta el ejemplo original '{fname}'.")
        examples[fname] = json.loads(path.read_text(encoding="utf-8"))
    for attr in ext["attributes"]:
        value = attribute_value(attr, observed_at=observed_at, example_ids=example_ids)
        kv, v2, ld = attribute_forms(attr.get("ngsi", "Property"), attr, value,
                                     temporal=bool(attr.get("temporal")), units=attr.get("units"),
                                     observed_at=observed_at)
        for fname, form in (("example.json", kv), ("example.jsonld", kv),
                            ("example-normalized.json", v2), ("example-normalized.jsonld", ld)):
            examples[fname] = _with_attribute(examples[fname], attr["name"], copy.deepcopy(form))

    files = [target / "schema.json"]
    write_json(files[0], schema)
    for fname in EXAMPLE_FILES:
        write_json(target / "examples" / fname, examples[fname])
        files.append(target / "examples" / fname)
    if (base / "notes.yaml").is_file():
        write_text(target / "notes.yaml", (base / "notes.yaml").read_text(encoding="utf-8"))
        files.append(target / "notes.yaml")
    if (base / "ADOPTERS.yaml").is_file():
        adopters_text = (base / "ADOPTERS.yaml").read_text(encoding="utf-8")
        if ext.get("adopters"):
            adopters = yaml.safe_load(adopters_text) or {}
            current = [a for a in adopters.get("currentAdopters") or []
                       if isinstance(a, dict) and any(a.values())]
            adopters["currentAdopters"] = current + list(ext["adopters"])
            adopters_text = yaml.safe_dump(adopters, sort_keys=False, allow_unicode=True)
        write_text(target / "ADOPTERS.yaml", adopters_text)
        files.append(target / "ADOPTERS.yaml")
    changes = target.parent / f"CHANGES-{model}.md"
    write_text(changes, build_changes_md(ext, subject, model, old_version,
                                         schema["$schemaVersion"], metadata))
    files.append(changes)
    contributors = build_contributors(metadata)
    if contributors:
        write_yaml(target.parent / "CONTRIBUTORS.yaml", contributors)
        files.append(target.parent / "CONTRIBUTORS.yaml")
    return {"model": ext["model"], "path": str(target), "version": [old_version,
            schema["$schemaVersion"]], "files": [str(f) for f in files], "warnings": warnings}


def load_spec(path: Path) -> dict[str, Any]:
    try:
        spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SpecError(f"La especificación no es YAML/JSON válido: {exc}") from exc
    check_spec(spec)
    return spec


def generate(spec: dict[str, Any], out_dir: Path, *, force: bool = False,
             offline: bool = False) -> dict[str, Any]:
    check_spec(spec)
    subject = spec.get("subject")
    metadata = spec.get("metadata") or {}
    entities = spec.get("entities") or []
    result: dict[str, Any] = {"subject": subject, "newSubject": spec.get("newSubject") is not None,
                              "entities": [], "extensions": [], "warnings": spec_warnings(spec)}
    try:
        official, status = sdm_index.load_index("official_list", offline=offline)
        if status.get("warning"):
            result["warnings"].append(status["warning"])
        check_subject(spec, official)
    except sdm_index.IndexUnavailable as exc:
        result["warnings"].append(f"No se pudo comprobar el subject contra la lista oficial: {exc}")

    contribution = out_dir / "contribution"
    example_ids = {e["name"]: entity_example_id(e) for e in entities}
    for entity in entities:
        target = contribution / entity["name"]
        if target.exists() and any(target.iterdir()) and not force:
            raise SpecError(f"'{target}' ya existe. Usa --force para sobrescribir.")
        schema = build_schema(entity, subject, metadata)
        refs = [b["$ref"] for b in schema["allOf"] if "$ref" in b]
        commons_info = _commons_attribute_info(refs, offline=offline)
        unknown = [c for c in (entity.get("example", {}) or {}).get("commons", {})
                   if c not in commons_info]
        if unknown:
            result["warnings"].append(
                f"{entity['name']}: valores de ejemplo para atributos que no aportan los "
                f"Commons referenciados: {', '.join(unknown)}")
        examples = build_examples(entity, subject, commons_info=commons_info,
                                  example_ids=example_ids)
        files = [target / "schema.json"]
        write_json(files[0], schema)
        for fname in EXAMPLE_FILES:
            write_json(target / "examples" / fname, examples[fname])
            files.append(target / "examples" / fname)
        write_yaml(target / "notes.yaml", build_notes(entity))
        write_yaml(target / "ADOPTERS.yaml", build_adopters(entity, subject))
        files += [target / "notes.yaml", target / "ADOPTERS.yaml"]
        if metadata.get("license", DEFAULT_LICENSE) == DEFAULT_LICENSE and not entity.get("license"):
            (target / "LICENSE.md").write_text(
                (TEMPLATES / "LICENSE-CC-BY-4.0.md").read_text(encoding="utf-8"), encoding="utf-8")
            files.append(target / "LICENSE.md")
        else:
            result["warnings"].append(f"{entity['name']}: licencia distinta de CC-BY-4.0; añade "
                                      "tú el texto de la licencia en LICENSE.md")
        result["entities"].append({"name": entity["name"], "path": str(target),
                                   "files": [str(f) for f in files]})
    contributors = build_contributors(metadata)
    if entities and contributors:
        write_yaml(contribution / "CONTRIBUTORS.yaml", contributors)
        result["contributors_file"] = str(contribution / "CONTRIBUTORS.yaml")
    if not contributors:
        result["warnings"].append("Sin contribuidores: añade la autoría en metadata.contributors")
    if entities and spec.get("newSubject") is not None:
        notes = _load_template("subject-notes.yaml")
        notes.update(spec["newSubject"].get("notes") or {})
        write_yaml(contribution / "notes.yaml", notes)
        result["subject_notes_file"] = str(contribution / "notes.yaml")
        result["warnings"].append(
            f"Subject nuevo '{subject}': su @context "
            f"({subject_context_url(subject)}) no existirá hasta que se publique; la prueba "
            "oficial test_valid_ngsild lo marcará hasta entonces")
    for ext in spec.get("extensions") or []:
        info = build_extension(ext, out_dir, metadata=metadata, example_ids=example_ids,
                               offline=offline, force=force)
        result["warnings"] += info.pop("warnings")
        result["extensions"].append(info)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera schema.json, 4 ejemplos y YAML SDM.")
    parser.add_argument("spec", type=Path, help="Especificación de la propuesta (YAML o JSON).")
    parser.add_argument("--out", type=Path, required=True,
                        help="Carpeta de trabajo: se crean contribution/ y extensions/.")
    parser.add_argument("--force", action="store_true", help="Sobrescribe entidades existentes.")
    parser.add_argument("--offline", action="store_true", help="Usa solo la caché local.")
    args = parser.parse_args(argv)
    try:
        spec = load_spec(args.spec)
        result = generate(spec, args.out, force=args.force, offline=args.offline)
    except (SpecError, OSError) as exc:
        sdm_index.emit({"error": str(exc)})
        return 2
    sdm_index.emit(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
