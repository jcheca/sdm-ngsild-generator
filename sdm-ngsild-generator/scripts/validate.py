#!/usr/bin/env python3
"""Validación local de una propuesta SDM (una o varias entidades).

Reproduce las pruebas oficiales que el repositorio smart-data-models aplica a cada
contribución (``data-models/test_data_model``) y añade comprobaciones de coherencia
NGSI-LD y de reutilización:

======================  ===========================================================
files                   Existen los 7 ficheros obligatorios.
json / yaml             Los JSON y YAML se pueden leer.
schema_valid            ``schema.json`` es un JSON Schema 2020-12 válido.
schema_metadata         $schema, $schemaVersion, title, description, $id, required...
type_property           ``type`` es un enum con el nombre de la entidad.
descriptions            Formato SDM de descripciones (también subatributos e items).
structure               string sin items/properties, array con items, object con properties.
naming                  Entidad en PascalCase, atributos en camelCase y ASCII, y las
                        recomendaciones de specs/guidelines.md (prefijo date, ref...).
commons                 Los $ref a Commons existen y no se redefinen sus atributos.
keyvalues_schema        example.json y example.jsonld validan contra el schema.
payload_defined         Todo atributo de los ejemplos key-values está en el schema.
ngsiv2_normalized       Formato NGSI v2 normalizado (sin tipos NGSI-LD).
ngsild_normalized       Formato NGSI-LD normalizado (Property/Relationship/GeoProperty).
consistency             Los cuatro ejemplos contienen los mismos atributos y valores, y
                        los tipos NGSI coinciden con los declarados en el schema.
urns                    ids ``urn:ngsi-ld:<Type>:…`` y objetos de Relationship como URN
                        (con --spec, del tipo de entidad declarado en ``target``).
context                 ``@context`` del subject en los ejemplos NGSI-LD.
units                   Códigos UN/CEFACT (Rec. 20) en unitCode y en las descripciones.
license                 LICENSE.md presente si el schema apunta a él.
repository              Atributos nuevos que ya existen en el repositorio o en los Commons.
extension               (solo extensiones) el original se conserva intacto, la versión sube
                        de minor y solo se añaden los atributos de la especificación. Los
                        problemas que ya tenía el modelo original se rebajan a informativos.

Con ``--spec``, además, comprobaciones del conjunto de la propuesta: subject nuevo o
existente, destinos de las Relationship (en la propuesta o en el repositorio) y enlaces
entre los ejemplos de las entidades de la propuesta.
======================  ===========================================================

Uso::

    python validate.py <dir> [--spec proposal.yaml] [--offline] [--check-urls]

``<dir>`` puede ser la carpeta de trabajo (con ``contribution/`` y ``extensions/``), la
carpeta de una entidad o una carpeta con varias entidades.
Salida JSON; código de salida 1 si alguna comprobación falla.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import requests
import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

import fetch_schema
import sdm_index
import units as uncefact

MANDATORY_FILES = (
    "schema.json",
    "examples/example.json",
    "examples/example-normalized.json",
    "examples/example.jsonld",
    "examples/example-normalized.jsonld",
    "notes.yaml",
    "ADOPTERS.yaml",
)
SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
# Tipos NGSI admitidos por la prueba oficial de descripciones.
DESCRIPTION_NGSI_TYPES = ("Property", "GeoProperty", "Relationship", "LanguageProperty",
                          "ListProperty")
LD_ATTRIBUTE_TYPES = ("Property", "GeoProperty", "Relationship", "LanguageProperty",
                      "ListProperty")
NGSILD_ONLY_TYPES = {"Property", "Relationship", "GeoProperty"}
OPTIONAL_DESCRIPTION_KEYS = ("Model:", "Units:", "Enum:", "Privacy:", "Multilingual")
ID_RE = re.compile(r"^https://smart-data-models\.github\.io/(dataModel\.[^/]+)/([^/]+)/schema\.json$")
MAX_REF_DEPTH = 6

PASS, WARN, FAIL = "pass", "warn", "fail"


class Check:
    """Resultado de una comprobación: estado y mensajes."""

    def __init__(self, check_id: str, title: str) -> None:
        self.id, self.title = check_id, title
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.info: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def note(self, msg: str) -> None:
        self.info.append(msg)

    @property
    def status(self) -> str:
        return FAIL if self.errors else WARN if self.warnings else PASS

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id, "title": self.title, "status": self.status}
        for key in ("errors", "warnings", "info"):
            if getattr(self, key):
                out[key] = getattr(self, key)
        return out


# --------------------------------------------------------------------------- descripciones

def validate_description(description: str) -> str | None:
    """Comprueba el formato SDM de una descripción. Devuelve el error o ``None``.

    Misma lógica que ``test_schema_descriptions.validate_description`` del repositorio
    oficial: partes separadas por ``". "``, tipo NGSI obligatorio como parte exacta y
    claves opcionales con formato ``Clave:'valor'``.
    """
    if len(description) < 15:
        return "la descripción debe tener al menos 15 caracteres"
    parts = description.split(". ")
    if not any(p in DESCRIPTION_NGSI_TYPES for p in parts):
        for part in parts:
            for ngsi in DESCRIPTION_NGSI_TYPES:
                if ngsi in part and part != ngsi:
                    return f"el tipo NGSI '{part}' contiene caracteres de más"
        return ("falta el tipo NGSI (Property, GeoProperty, Relationship, LanguageProperty "
                "o ListProperty) como una de las partes separadas por '. '")
    for part in parts:
        for key in OPTIONAL_DESCRIPTION_KEYS:
            if part.startswith(key):
                rest = part[len(key):]
                if not rest.startswith("'") or not part.endswith("'"):
                    return f"formato incorrecto de '{key}': se espera {key}'valor'"
    return None


def _walk_descriptions(props: dict[str, Any], path: str, chk: Check) -> None:
    for name, spec in props.items():
        here = f"{path}.{name}" if path else name
        if not isinstance(spec, dict):
            continue
        if "$ref" in spec:
            continue  # descripción heredada del Commons referenciado
        _check_node_description(spec, here, chk)


def _check_node_description(spec: dict[str, Any], here: str, chk: Check) -> None:
    if "description" not in spec:
        chk.error(f"'{here}' no tiene descripción")
    else:
        err = validate_description(spec["description"])
        if err:
            chk.error(f"'{here}': {err}")
    if isinstance(spec.get("properties"), dict):
        _walk_descriptions(spec["properties"], here, chk)
    items = spec.get("items")
    if isinstance(items, dict) and "$ref" not in items:
        if "anyOf" in items:
            for i, alt in enumerate(items["anyOf"]):
                if isinstance(alt, dict):
                    _check_node_description(alt, f"{here}.items.anyOf[{i}]", chk)
        elif "properties" in items:
            _walk_descriptions(items["properties"], f"{here}.items", chk)
        else:
            _check_node_description(items, f"{here}.items", chk)


# --------------------------------------------------------------------------- utilidades de schema

def own_properties(schema: dict[str, Any]) -> dict[str, Any]:
    """Atributos declarados en el propio schema (bloques ``properties`` del allOf)."""
    props: dict[str, Any] = {}
    for block in schema.get("allOf", []):
        if isinstance(block, dict) and isinstance(block.get("properties"), dict):
            props.update(block["properties"])
    if isinstance(schema.get("properties"), dict):
        props.update(schema["properties"])
    return props


def commons_refs(schema: dict[str, Any]) -> list[str]:
    return [b["$ref"] for b in schema.get("allOf", []) if isinstance(b, dict) and "$ref" in b]


class RefResolver:
    """Resuelve ``$ref`` remotos con la caché local (sin red si ``offline``)."""

    def __init__(self, *, offline: bool) -> None:
        self.offline = offline
        self.failures: dict[str, str] = {}

    def document(self, url: str) -> Any:
        return fetch_schema.fetch_document(url, offline=self.offline)

    def resolve(self, ref: str, base: str) -> tuple[Any, str]:
        url, _, pointer = ref.partition("#")
        url = url or base.split("#", 1)[0]
        doc = self.document(url)
        return (fetch_schema.resolve_pointer(doc, pointer) if pointer else doc), url

    def registry(self) -> Registry:
        def retrieve(uri: str) -> Resource:
            try:
                return Resource.from_contents(self.document(uri),
                                              default_specification=DRAFT202012)
            except (sdm_index.IndexUnavailable, json.JSONDecodeError) as exc:
                self.failures[uri] = str(exc)
                raise
        return Registry(retrieve=retrieve)


def schema_paths(node: Any, resolver: RefResolver, base: str, prefix: str = "",
                 depth: int = 0) -> set[str]:
    """Rutas de atributos definidas en un schema (resolviendo $ref), como la prueba oficial
    ``test_duplicated_attributes``: los elementos de un array comparten la ruta del padre."""
    paths: set[str] = set()
    if not isinstance(node, dict) or depth > MAX_REF_DEPTH:
        return paths
    if "$ref" in node:
        try:
            target, new_base = resolver.resolve(node["$ref"], base)
        except (sdm_index.IndexUnavailable, LookupError, json.JSONDecodeError) as exc:
            resolver.failures[node["$ref"]] = str(exc)
            return paths
        paths |= schema_paths(target, resolver, new_base, prefix, depth + 1)
    for key, sub in (node.get("properties") or {}).items():
        full = f"{prefix}.{key}" if prefix else key
        paths.add(full)
        paths |= schema_paths(sub, resolver, base, full, depth + 1)
    items = node.get("items")
    if isinstance(items, dict):
        paths |= schema_paths(items, resolver, base, prefix, depth + 1)
    elif isinstance(items, list):
        for it in items:
            paths |= schema_paths(it, resolver, base, prefix, depth + 1)
    for comb in ("allOf", "anyOf", "oneOf"):
        for it in node.get(comb) or []:
            paths |= schema_paths(it, resolver, base, prefix, depth + 1)
    if isinstance(node.get("additionalProperties"), dict):
        paths |= schema_paths(node["additionalProperties"], resolver, base, prefix, depth + 1)
    return paths


def payload_paths(payload: Any, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            full = f"{prefix}.{key}" if prefix else key
            paths.add(full)
            paths |= payload_paths(value, full)
    elif isinstance(payload, list):
        for item in payload:
            paths |= payload_paths(item, prefix)
    return paths


def declared_ngsi_types(schema: dict[str, Any], resolver: RefResolver) -> dict[str, str]:
    """Tipo NGSI declarado (en la descripción) de cada atributo, incluidos los Commons."""
    result: dict[str, str] = {}
    for ref in commons_refs(schema):
        try:
            definition, _ = resolver.resolve(ref, schema.get("$id", ""))
        except (sdm_index.IndexUnavailable, LookupError, json.JSONDecodeError):
            continue
        for item in fetch_schema.summarize_properties(definition.get("properties", {})):
            if item["ngsi_type"]:
                result[item["name"]] = item["ngsi_type"]
    for name, spec in own_properties(schema).items():
        if isinstance(spec, dict):
            ngsi = fetch_schema.parse_description(spec.get("description"))["ngsi_type"]
            if ngsi:
                result[name] = ngsi
    result.pop("type", None)
    result.pop("id", None)
    return result


def _ld_value(attr: dict[str, Any]) -> Any:
    if attr.get("type") == "Relationship":
        return attr.get("object")
    value = attr.get("value")
    if isinstance(value, dict) and set(value) == {"@type", "@value"}:
        return value["@value"]
    return value


def _contexts(doc: dict[str, Any]) -> list[str]:
    ctx = doc.get("@context")
    if isinstance(ctx, str):
        return [ctx]
    if isinstance(ctx, list):
        return [c for c in ctx if isinstance(c, str)]
    return []


# --------------------------------------------------------------------------- validación de una entidad

class EntityValidator:
    def __init__(self, path: Path, *, spec_entity: dict[str, Any] | None = None,
                 offline: bool = False, check_urls: bool = False,
                 session: requests.Session | None = None,
                 baseline: Path | None = None) -> None:
        self.path = path
        self.baseline = baseline  # carpeta del modelo original (solo extensiones)
        self.spec_entity = spec_entity
        self.offline = offline
        self.check_urls = check_urls
        self.session = session
        self.resolver = RefResolver(offline=offline)
        self.checks: list[Check] = []
        self.docs: dict[str, Any] = {}
        self.schema: dict[str, Any] | None = None
        self.subject: str | None = None
        self.entity_type: str | None = None

    # -- infraestructura
    def check(self, check_id: str, title: str, fn: Callable[[Check], None]) -> Check:
        chk = Check(check_id, title)
        try:
            fn(chk)
        except Exception as exc:  # noqa: BLE001 - un fallo inesperado no debe ocultar el resto
            chk.error(f"Error inesperado: {exc.__class__.__name__}: {exc}")
        self.checks.append(chk)
        return chk

    def example(self, name: str) -> Any:
        return self.docs.get(f"examples/{name}")

    def run_checks_only(self) -> None:
        """Ejecuta las comprobaciones sin construir el informe (uso interno)."""
        self.run()

    def run(self) -> dict[str, Any]:
        self.check("files", "Ficheros obligatorios", self._files)
        self.check("json", "JSON válido", self._json)
        self.check("yaml", "YAML válido", self._yaml)
        if isinstance(self.docs.get("schema.json"), dict):
            self.schema = self.docs["schema.json"]
            self.check("schema_valid", "schema.json es un JSON Schema 2020-12 válido",
                       self._schema_valid)
            self.check("schema_metadata", "Metadatos de schema.json", self._schema_metadata)
            self.check("type_property", "Atributo type", self._type_property)
            self.check("descriptions", "Formato SDM de las descripciones", self._descriptions)
            self.check("structure", "Estructura de arrays, objects y strings", self._structure)
            self.check("naming", "Nombres y recomendaciones de la guía SDM", self._naming)
            self.check("commons", "Referencias a los Commons", self._commons)
            self.check("keyvalues_schema", "Ejemplos key-values validan contra el schema",
                       self._keyvalues_schema)
            self.check("payload_defined", "Atributos de los ejemplos definidos en el schema",
                       self._payload_defined)
        self.check("ngsiv2_normalized", "NGSI v2 normalizado", self._ngsiv2)
        self.check("ngsild_normalized", "NGSI-LD normalizado", self._ngsild)
        if self.schema is not None:
            self.check("consistency", "Coherencia entre los cuatro ejemplos", self._consistency)
        self.check("urns", "Identificadores URN NGSI-LD", self._urns)
        self.check("context", "@context de los ejemplos NGSI-LD", self._context)
        self.check("units", "Códigos de unidad UN/CEFACT", self._units)
        if self.schema is not None and self.baseline is None:
            self.check("license", "Licencia del modelo", self._license)
        if self.schema is not None:
            self.check("repository", "Duplicados con el repositorio y los Commons",
                       self._repository)
        if self.baseline is not None:
            self.check("extension", "Extensión: el modelo original se conserva", self._extension)
            self._downgrade_preexisting()
        statuses = {c.status for c in self.checks}
        status = FAIL if FAIL in statuses else WARN if WARN in statuses else PASS
        return {
            "entity": self.entity_type or self.path.name,
            "kind": "extension" if self.baseline is not None else "new",
            "subject": self.subject,
            "path": str(self.path),
            "status": status,
            "summary": dict(Counter(c.status for c in self.checks)),
            "checks": [c.as_dict() for c in self.checks],
        }

    # -- ficheros
    def _files(self, chk: Check) -> None:
        for rel in MANDATORY_FILES:
            if not (self.path / rel).is_file():
                chk.error(f"Falta '{rel}'")

    def _json(self, chk: Check) -> None:
        for rel in MANDATORY_FILES:
            if rel.endswith((".json", ".jsonld")) and (self.path / rel).is_file():
                try:
                    self.docs[rel] = json.loads((self.path / rel).read_text(encoding="utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    chk.error(f"'{rel}' no es JSON válido: {exc}")

    def _yaml(self, chk: Check) -> None:
        for rel in ("notes.yaml", "ADOPTERS.yaml"):
            if (self.path / rel).is_file():
                try:
                    yaml.safe_load((self.path / rel).read_text(encoding="utf-8"))
                except yaml.YAMLError as exc:
                    chk.error(f"'{rel}' no es YAML válido: {exc}")

    # -- schema
    def _schema_valid(self, chk: Check) -> None:
        try:
            Draft202012Validator.check_schema(self.schema)
        except SchemaError as exc:
            chk.error(f"JSON Schema no válido: {exc.message}")

    def _schema_metadata(self, chk: Check) -> None:
        s = self.schema
        if s.get("$schema") != SCHEMA_DIALECT:
            chk.error(f"$schema debe ser {SCHEMA_DIALECT}")
        if "modelTags" not in s:
            chk.error("Falta modelTags (puede estar vacío)")
        if not re.fullmatch(r"\d{1,2}\.\d{1,2}\.\d{1,2}", str(s.get("$schemaVersion", ""))):
            chk.error("$schemaVersion falta o no tiene el formato XX.XX.XX")
        if len(s.get("title", "")) < 15:
            chk.error("title falta o tiene menos de 15 caracteres")
        if len(s.get("description", "")) < 50:
            chk.error("description falta o tiene menos de 50 caracteres")
        match = ID_RE.match(s.get("$id", ""))
        if not match:
            chk.error("$id debe ser https://smart-data-models.github.io/dataModel.<Subject>/"
                      "<Entity>/schema.json")
        else:
            self.subject = match.group(1)
            if match.group(2) != self.path.name:
                chk.error(f"$id apunta a '{match.group(2)}' pero la carpeta es '{self.path.name}'")
        required = s.get("required")
        if not isinstance(required, list) or "id" not in required or "type" not in required:
            chk.error("required debe ser una lista que incluya 'id' y 'type'")
        else:
            own = set(own_properties(s)) | {"id"}
            for name in required:
                if name not in own and not self._in_commons(name):
                    chk.warn(f"'{name}' está en required pero no se define en el schema")
        if not s.get("derivedFrom"):
            chk.warn("derivedFrom vacío o ausente (aviso, como en la prueba oficial)")
        if not s.get("license"):
            chk.warn("license vacío o ausente")

    def _in_commons(self, name: str) -> bool:
        for ref in commons_refs(self.schema):
            try:
                definition, _ = self.resolver.resolve(ref, self.schema.get("$id", ""))
            except (sdm_index.IndexUnavailable, LookupError, json.JSONDecodeError):
                continue
            if name in definition.get("properties", {}):
                return True
        return False

    def _type_property(self, chk: Check) -> None:
        tspec = own_properties(self.schema).get("type")
        if not isinstance(tspec, dict):
            chk.error("El schema no define el atributo 'type'")
            return
        enum = tspec.get("enum")
        if not (isinstance(enum, list) and len(enum) == 1):
            chk.error("'type' debe ser un enum con un único valor: el nombre de la entidad")
            return
        self.entity_type = enum[0]
        if enum[0] != self.path.name:
            chk.error(f"El tipo '{enum[0]}' no coincide con la carpeta '{self.path.name}'")

    def _descriptions(self, chk: Check) -> None:
        if not self.schema.get("description"):
            chk.error("El schema no tiene descripción raíz")
        _walk_descriptions(own_properties(self.schema), "", chk)

    def _structure(self, chk: Check) -> None:
        def walk(props: dict[str, Any], path: str) -> None:
            for name, spec in props.items():
                if not isinstance(spec, dict):
                    continue
                here = f"{path}{name}"
                jtype = spec.get("type")
                if jtype == "string" and ("items" in spec or "properties" in spec):
                    chk.error(f"'{here}' es string pero tiene 'items' o 'properties'")
                if jtype == "array" and "items" not in spec:
                    chk.error(f"'{here}' es array pero no tiene 'items'")
                if jtype == "object" and "properties" not in spec:
                    chk.error(f"'{here}' es object pero no tiene 'properties'")
                if isinstance(spec.get("properties"), dict):
                    walk(spec["properties"], here + ".")
                if isinstance(spec.get("items"), dict):
                    walk({"items": spec["items"]}, here + ".")
        walk(own_properties(self.schema), "")

    def _naming(self, chk: Check) -> None:
        if self.entity_type and not re.fullmatch(r"[A-Z][A-Za-z0-9]*", self.entity_type):
            chk.error(f"El tipo de entidad '{self.entity_type}' debe estar en PascalCase (ASCII)")

        def walk(props: dict[str, Any], path: str, top: bool) -> None:
            for name, spec in props.items():
                if name in ("id", "type") or name.startswith("@"):
                    continue
                here = f"{path}{name}"
                if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", name):
                    chk.error(f"'{here}' contiene caracteres no permitidos (solo ASCII alfanumérico)")
                elif name[0].isupper():
                    (chk.error if top else chk.warn)(
                        f"'{here}' empieza por mayúscula: usa camelCase")
                if isinstance(spec, dict) and isinstance(spec.get("properties"), dict):
                    walk(spec["properties"], here + ".", False)
        walk(own_properties(self.schema), "", True)

        # Recomendaciones de data-models/specs/guidelines.md (avisos, no errores).
        spec_attrs = {a["name"]: a for a in (self.spec_entity or {}).get("attributes", [])}
        for name, spec in own_properties(self.schema).items():
            if not isinstance(spec, dict) or name in ("id", "type"):
                continue
            if self.baseline is not None and name not in self.added_attributes():
                continue  # en una extensión solo se juzgan los atributos añadidos
            ngsi = fetch_schema.parse_description(spec.get("description"))["ngsi_type"]
            reused = spec_attrs.get(name, {}).get("origin") == "reused"
            if ngsi == "Relationship" and name.startswith("ref") and not reused \
                    and self.spec_entity is not None:
                chk.warn(f"'{name}': para Relationship nuevas la guía SDM recomienda un verbo "
                         "(hasX, isPartOf, operatedBy) en lugar del prefijo 'ref'")
            if spec.get("format") in ("date-time", "date") and not name.startswith("date") \
                    and not reused:
                chk.warn(f"'{name}': la guía SDM recomienda el prefijo 'date' para fechas "
                         "(p. ej. dateLastEmptying)")
        extra = [r for r in self.schema.get("required", []) if r not in ("id", "type")]
        if extra:
            chk.note(f"Obligatorios además de id y type: {', '.join(extra)}. La guía SDM pide "
                     "reservar los obligatorios al mínimo (idealmente id y type)")

    def _commons(self, chk: Check) -> None:
        base = self.schema.get("$id", "")
        own = set(own_properties(self.schema))
        for ref in commons_refs(self.schema):
            try:
                definition, _ = self.resolver.resolve(ref, base)
            except (sdm_index.IndexUnavailable, json.JSONDecodeError) as exc:
                chk.warn(f"No se pudo descargar '{ref}' para comprobarlo: {exc}")
                continue
            except LookupError as exc:
                chk.error(f"'{ref}' no existe: {exc}")
                continue
            redefined = own & set(definition.get("properties", {}))
            for name in sorted(redefined):
                chk.error(f"'{name}' ya lo aporta {ref.rsplit('/', 1)[-1]}: no lo redefinas")
        if not commons_refs(self.schema):
            chk.warn("El schema no referencia ningún Commons (lo habitual es GSMA-Commons, "
                     "que aporta 'id')")

    def _keyvalues_schema(self, chk: Check) -> None:
        validator = Draft202012Validator(self.schema, registry=self.resolver.registry())
        for name in ("example.json", "example.jsonld"):
            doc = self.example(name)
            if doc is None:
                chk.error(f"No se puede validar '{name}': falta o no es JSON válido")
                continue
            try:
                errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
            except Unresolvable as exc:
                chk.warn(f"No se pudo resolver un $ref para validar '{name}': {exc}")
                continue
            for err in errors[:20]:
                where = "/".join(str(p) for p in err.absolute_path) or "(raíz)"
                chk.error(f"{name} → {where}: {err.message}")

    def _payload_defined(self, chk: Check) -> None:
        defined = schema_paths(self.schema, self.resolver, self.schema.get("$id", ""))
        for name in ("example.json", "example.jsonld"):
            doc = self.example(name)
            if not isinstance(doc, dict):
                continue
            payload = {k: v for k, v in doc.items() if k != "@context"}
            for path in sorted(payload_paths(payload) - defined):
                chk.error(f"{name}: '{path}' no está definido en el schema")
        for ref, err in self.resolver.failures.items():
            chk.warn(f"No se pudo resolver '{ref}': {err}")

    # -- ejemplos normalizados
    def _ngsiv2(self, chk: Check) -> None:
        doc = self.example("example-normalized.json")
        if not isinstance(doc, dict):
            chk.error("example-normalized.json falta o no es un objeto")
            return
        for key in ("id", "type"):
            if not isinstance(doc.get(key), str):
                chk.error(f"Falta '{key}' o no es un string")
        for name, attr in doc.items():
            if name in ("id", "type"):
                continue
            if not isinstance(attr, dict):
                chk.error(f"'{name}' debe ser un objeto con 'type' y 'value'")
                continue
            for key in ("type", "value"):
                if key not in attr:
                    chk.error(f"'{name}' no tiene '{key}'")
            if attr.get("type") in NGSILD_ONLY_TYPES:
                chk.error(f"'{name}' usa el tipo NGSI-LD '{attr['type']}', no válido en NGSI v2")

    def _ngsild(self, chk: Check) -> None:
        doc = self.example("example-normalized.jsonld")
        if not isinstance(doc, dict):
            chk.error("example-normalized.jsonld falta o no es un único objeto entidad")
            return
        for key in ("id", "type", "@context"):
            if key not in doc:
                chk.error(f"Falta '{key}'")
        for name, attr in doc.items():
            if name in ("id", "type", "@context"):
                continue
            if not isinstance(attr, dict):
                chk.error(f"'{name}' debe ser un objeto")
                continue
            atype = attr.get("type")
            if atype not in LD_ATTRIBUTE_TYPES:
                chk.error(f"'{name}': tipo '{atype}' no válido; usa {', '.join(LD_ATTRIBUTE_TYPES)}")
            elif atype == "LanguageProperty":
                if "languageMap" not in attr or "value" in attr or "object" in attr:
                    chk.error(f"'{name}': una LanguageProperty lleva 'languageMap' y no "
                              "'value' ni 'object'")
            elif atype == "Relationship":
                if "object" not in attr:
                    chk.error(f"'{name}': una Relationship necesita 'object'")
            elif "value" not in attr:
                chk.error(f"'{name}': falta 'value'")
            if "observedAt" in attr and not re.match(r"\d{4}-\d{2}-\d{2}T", str(attr["observedAt"])):
                chk.error(f"'{name}': observedAt debe ser fecha y hora ISO 8601")

    def _consistency(self, chk: Check) -> None:
        kv, kvld = self.example("example.json"), self.example("example.jsonld")
        v2n, ldn = self.example("example-normalized.json"), self.example("example-normalized.jsonld")
        if not all(isinstance(d, dict) for d in (kv, kvld, v2n, ldn)):
            chk.error("No se puede comparar: falta algún ejemplo")
            return
        strip = lambda d: {k: v for k, v in d.items() if k != "@context"}  # noqa: E731
        kv, kvld, ldn_ = strip(kv), strip(kvld), strip(ldn)

        if set(kv) != set(kvld):
            chk.warn("example.json y example.jsonld tienen atributos distintos: "
                     f"{sorted(set(kv) ^ set(kvld))}")
        for a in set(kv) & set(kvld):
            if kv[a] != kvld[a]:
                chk.warn(f"'{a}' tiene valores distintos en example.json y example.jsonld")

        for label, norm, ref in (("example-normalized.json", v2n, kv),
                                 ("example-normalized.jsonld", ldn_, kvld)):
            if set(norm) != set(ref):
                chk.error(f"{label} y su key-values tienen atributos distintos: "
                          f"{sorted(set(norm) ^ set(ref))}")
            for a in set(norm) & set(ref) - {"id", "type"}:
                attr = norm[a]
                if not isinstance(attr, dict):
                    continue
                value = attr.get("value") if label.endswith(".json") else _ld_value(attr)
                if value != ref[a]:
                    chk.error(f"'{a}' tiene un valor distinto en {label} y en key-values")
            for key in ("id", "type"):
                if norm.get(key) != ref.get(key):
                    chk.error(f"'{key}' distinto en {label} y en key-values")

        declared = declared_ngsi_types(self.schema, self.resolver)
        for a, attr in ldn_.items():
            if a in ("id", "type") or not isinstance(attr, dict):
                continue
            want = declared.get(a)
            if want and attr.get("type") != want:
                chk.error(f"'{a}' se declara {want} en el schema pero es {attr.get('type')} "
                          "en example-normalized.jsonld")
        for a, attr in v2n.items():
            if not isinstance(attr, dict):
                continue
            if declared.get(a) == "GeoProperty" and attr.get("type") != "geo:json":
                chk.warn(f"'{a}' es GeoProperty: en NGSI v2 su tipo debería ser 'geo:json'")

    # -- NGSI-LD
    def _urns(self, chk: Check) -> None:
        etype = self.entity_type
        for name in fetch_schema.EXAMPLE_FILES:
            doc = self.example(name)
            if not isinstance(doc, dict):
                continue
            eid, dtype = doc.get("id"), doc.get("type")
            prefix = f"urn:ngsi-ld:{etype or dtype}:"
            if not isinstance(eid, str) or not eid.startswith(prefix) or len(eid) == len(prefix):
                chk.error(f"{name}: id '{eid}' debe tener la forma {prefix}<identificador>")
            if etype and dtype != etype:
                chk.error(f"{name}: type '{dtype}' no coincide con '{etype}'")
        ldn = self.example("example-normalized.jsonld")
        targets = {a["name"]: a.get("target") for a in (self.spec_entity or {}).get("attributes", [])
                   if a.get("ngsi") == "Relationship"}
        if isinstance(ldn, dict):
            for a, attr in ldn.items():
                if not isinstance(attr, dict) or attr.get("type") != "Relationship":
                    continue
                objs = attr.get("object")
                for obj in objs if isinstance(objs, list) else [objs]:
                    if not isinstance(obj, str) or not obj.startswith("urn:ngsi-ld:"):
                        chk.error(f"'{a}': el objeto '{obj}' debe ser una URN urn:ngsi-ld:")
                    elif targets.get(a) and not obj.startswith(f"urn:ngsi-ld:{targets[a]}:"):
                        chk.error(f"'{a}' debe apuntar a entidades {targets[a]} y apunta a '{obj}'")
        if self.spec_entity is None:
            chk.note("Sin --spec no se comprueba el tipo de entidad al que apunta cada Relationship")

    def _context(self, chk: Check) -> None:
        expected = (f"{sdm_index.RAW_BASE}/{self.subject}/{sdm_index.DEFAULT_BRANCH}/context.jsonld"
                    if self.subject else None)
        urls: set[str] = set()
        for name in ("example.jsonld", "example-normalized.jsonld"):
            doc = self.example(name)
            if not isinstance(doc, dict):
                continue
            ctx = doc.get("@context")
            if ctx is None:
                chk.error(f"{name}: falta @context")
                continue
            if not (isinstance(ctx, str) or (isinstance(ctx, list) and ctx
                                              and all(isinstance(c, str) for c in ctx))):
                chk.error(f"{name}: @context debe ser una URL o una lista de URLs")
                continue
            found = _contexts(doc)
            urls.update(found)
            if expected and expected not in found:
                chk.error(f"{name}: @context no incluye el contexto del subject ({expected})")
        if self.check_urls:
            session = self.session or sdm_index.http_session()
            for url in sorted(urls):
                try:
                    code = session.get(url, timeout=sdm_index.HTTP_TIMEOUT).status_code
                except requests.RequestException as exc:
                    code = exc.__class__.__name__
                if code != 200:
                    chk.warn(f"El @context '{url}' no responde ({code}). Es normal si el subject "
                             "es nuevo y aún no está publicado; la prueba oficial lo marcará.")

    # -- unidades y licencia
    def _units(self, chk: Check) -> None:
        def report(code: Any, where: str) -> None:
            level, message = uncefact.check_code(str(code))
            if level == "error":
                chk.error(f"{where}: {message}")
            elif level == "warn":
                chk.warn(f"{where}: {message}")

        ldn = self.example("example-normalized.jsonld")
        ld_units: dict[str, Any] = {}
        if isinstance(ldn, dict):
            for a, attr in ldn.items():
                if isinstance(attr, dict) and "unitCode" in attr:
                    ld_units[a] = attr["unitCode"]
                    report(attr["unitCode"], f"example-normalized.jsonld → {a}.unitCode")
        v2n = self.example("example-normalized.json")
        if isinstance(v2n, dict):
            for a, attr in v2n.items():
                meta = attr.get("metadata", {}) if isinstance(attr, dict) else {}
                uc = meta.get("unitCode") if isinstance(meta, dict) else None
                if isinstance(uc, dict):
                    report(uc.get("value"), f"example-normalized.json → {a}.metadata.unitCode")
                    if a in ld_units and uc.get("value") != ld_units[a]:
                        chk.error(f"'{a}': unitCode distinto en los ejemplos v2 y LD")
        if self.schema is None:
            return
        for name, spec in own_properties(self.schema).items():
            if not isinstance(spec, dict):
                continue
            units_text = fetch_schema.parse_description(spec.get("description"))["units"]
            if not units_text:
                continue
            match = re.search(r"\(([A-Z0-9]{2,3})\)$", units_text.strip()) or \
                re.fullmatch(r"([A-Z0-9]{2,3})", units_text.strip())
            if match:
                code = match.group(1)
                report(code, f"schema → {name} (Units)")
                if name in ld_units and ld_units[name] != code:
                    chk.error(f"'{name}': Units:'{units_text}' en el schema pero unitCode "
                              f"'{ld_units[name]}' en los ejemplos")
            else:
                chk.note(f"'{name}': Units:'{units_text}' no incluye un código UN/CEFACT")

    def _license(self, chk: Check) -> None:
        url = self.schema.get("license", "")
        if url.endswith(f"/{self.path.name}/LICENSE.md") and not (self.path / "LICENSE.md").is_file():
            chk.warn("El schema apunta a LICENSE.md pero el fichero no está en la carpeta")

    # -- extensiones
    def added_attributes(self) -> set[str]:
        return {a["name"] for a in (self.spec_entity or {}).get("attributes", [])}

    def _extension(self, chk: Check) -> None:
        original_path = self.baseline / "schema.json"
        original = json.loads(original_path.read_text(encoding="utf-8"))
        old_props, new_props = own_properties(original), own_properties(self.schema)
        for name, spec in old_props.items():
            if name not in new_props:
                chk.error(f"Se ha eliminado el atributo original '{name}'")
            elif new_props[name] != spec:
                chk.error(f"Se ha modificado la definición del atributo original '{name}'")
        added = set(new_props) - set(old_props)
        expected = self.added_attributes()
        if self.spec_entity is not None and added != expected:
            chk.error(f"Atributos añadidos {sorted(added)} distintos de los de la especificación "
                      f"{sorted(expected)}")
        for key in ("$id", "title", "description", "required", "allOf"):
            if key == "allOf":
                old_refs, new_refs = commons_refs(original), commons_refs(self.schema)
                if old_refs != new_refs:
                    chk.error("Han cambiado las referencias a los Commons del original")
            elif original.get(key) != self.schema.get(key):
                chk.error(f"Ha cambiado '{key}' respecto al original")
        old_v = str(original.get("$schemaVersion", ""))
        new_v = str(self.schema.get("$schemaVersion", ""))
        m_old = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", old_v)
        m_new = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", new_v)
        if m_old and m_new:
            o, n = [int(x) for x in m_old.groups()], [int(x) for x in m_new.groups()]
            if not (n[0] == o[0] and n[1] == o[1] + 1 and n[2] == 0):
                chk.error(f"La versión debe subir de minor ({old_v} → {o[0]}.{o[1] + 1}.0) al "
                          f"añadir atributos (versioning.md); es {new_v}")
        for name in ("example.json", "example-normalized.json", "example.jsonld",
                     "example-normalized.jsonld"):
            path = self.baseline / "examples" / name
            doc = self.example(name)
            if not path.is_file() or not isinstance(doc, dict):
                continue
            before = json.loads(path.read_text(encoding="utf-8"))
            for key, value in before.items():
                if doc.get(key) != value:
                    chk.error(f"{name}: se ha modificado '{key}' del ejemplo original")
        chk.note(f"Versión {old_v} → {new_v}; atributos añadidos: {', '.join(sorted(added))}")

    def _downgrade_preexisting(self) -> None:
        """Rebaja a informativos los problemas que ya tenía el modelo original."""
        base = EntityValidator(self.baseline, offline=self.offline, session=self.session)
        base.run_checks_only()
        before = {c.id: c for c in base.checks}
        for chk in self.checks:
            old = before.get(chk.id)
            if old is None:
                continue
            for bucket in ("errors", "warnings"):
                keep = []
                for msg in getattr(chk, bucket):
                    if msg in old.errors or msg in old.warnings:
                        chk.note(f"(preexistente en el original) {msg}")
                    else:
                        keep.append(msg)
                setattr(chk, bucket, keep)

    # -- repositorio
    def _repository(self, chk: Check) -> None:
        try:
            attributes, status = sdm_index.load_index("attributes", offline=self.offline,
                                                      session=self.session)
            commons, _ = sdm_index.load_index("commons", offline=self.offline,
                                              session=self.session)
            official, _ = sdm_index.load_index("official_list", offline=self.offline,
                                               session=self.session)
        except sdm_index.IndexUnavailable as exc:
            chk.warn(f"No se pudo comparar con el repositorio: {exc}")
            return
        if status.get("warning"):
            chk.note(status["warning"])

        spec_attrs = {a["name"]: a for a in (self.spec_entity or {}).get("attributes", [])}
        own = {n for n in own_properties(self.schema) if n not in ("id", "type")}
        if self.baseline is not None:
            own &= self.added_attributes()
        top = [a for a in attributes if not a.get("parentId")]
        by_lower: dict[str, list[dict[str, Any]]] = {}
        for a in top:
            by_lower.setdefault(a["property"].lower(), []).append(a)
        commons_props: dict[str, list[str]] = {}
        for def_name, definition in commons.get("definitions", {}).items():
            if isinstance(definition, dict):
                for p in definition.get("properties", {}):
                    commons_props.setdefault(p, []).append(def_name)

        etype = self.entity_type
        if etype and self.baseline is None:
            existing = [f"{r['repoName']}/{m}" for r in official["officialList"]
                        for m in r["dataModels"] if m.lower() == etype.lower()]
            if existing:
                chk.warn(f"Ya existe un modelo llamado '{etype}': {', '.join(existing)}")

        for name in sorted(own):
            if name in commons_props:
                chk.warn(f"'{name}' ya existe en {', '.join(commons_props[name])}: referencia "
                         "ese Commons en lugar de definirlo")
            occ = [o for o in by_lower.get(name.lower(), [])
                   if not (o["repoName"] == self.subject and o["dataModel"] == etype)]
            if not occ:
                continue
            models = sorted({f"{o['repoName']}/{o['dataModel']}" for o in occ})
            spec = spec_attrs.get(name, {})
            exact = [o for o in occ if o["property"] == name]
            if not exact:
                variants = sorted({o["property"] for o in occ})
                chk.warn(f"'{name}' existe con otra capitalización ({', '.join(variants)}); "
                         "usa la misma grafía")
                continue
            ngsi_types = Counter(o.get("typeNGSI") for o in exact if o.get("typeNGSI"))
            json_types = Counter(o.get("type") for o in exact if o.get("type"))
            mine = own_properties(self.schema)[name]
            my_ngsi = fetch_schema.parse_description(mine.get("description"))["ngsi_type"]
            my_type = mine.get("type") if isinstance(mine, dict) else None
            if ngsi_types and my_ngsi and my_ngsi not in ngsi_types:
                chk.warn(f"'{name}' es {my_ngsi} aquí pero {dict(ngsi_types)} en el repositorio")
            if json_types and my_type and my_type not in json_types:
                chk.warn(f"'{name}' es de tipo {my_type} aquí pero {dict(json_types)} en el repositorio")
            sample = ", ".join(models[:3]) + (f" y {len(models) - 3} más" if len(models) > 3 else "")
            if spec.get("origin") == "reused" and not spec.get("reusedFrom"):
                chk.warn(f"'{name}' figura como reutilizado pero sin 'reusedFrom' (subject/modelo "
                         "de origen): añádelo para la trazabilidad")
            elif spec.get("origin") == "reused":
                chk.note(f"'{name}' reutilizado; aparece en {len(models)} modelos ({sample})")
            elif spec.get("justification"):
                chk.note(f"'{name}' nuevo pero ya existe en {sample}; justificación: "
                         f"{spec['justification']}")
            elif self.spec_entity is not None:
                chk.warn(f"'{name}' figura como nuevo pero ya existe en {len(models)} modelos "
                         f"({sample}): márcalo como reutilizado (origin: reused) o justifícalo")
            else:
                chk.note(f"'{name}' ya existe en {len(models)} modelos ({sample})")


# --------------------------------------------------------------------------- CLI

def find_entity_dirs(path: Path) -> list[Path]:
    if (path / "schema.json").is_file():
        return [path]
    return sorted(p for p in path.iterdir() if p.is_dir() and (p / "schema.json").is_file())


def find_targets(path: Path) -> tuple[list[Path], list[Path]]:
    """Carpetas de entidades nuevas y de extensiones bajo ``path``."""
    if (path / "contribution").is_dir() or (path / "extensions").is_dir():
        new = find_entity_dirs(path / "contribution") if (path / "contribution").is_dir() else []
        ext = []
        if (path / "extensions").is_dir():
            for subject_dir in sorted(p for p in (path / "extensions").iterdir() if p.is_dir()):
                ext += find_entity_dirs(subject_dir)
        return new, ext
    if path.parent.parent.name == "extensions" and (path / "schema.json").is_file():
        return [], [path]
    return find_entity_dirs(path), []


def _relationship_attrs(spec: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    owners = [(e["name"], e) for e in spec.get("entities") or []] + \
        [(x["model"], x) for x in spec.get("extensions") or []]
    return [(owner, a) for owner, item in owners for a in item.get("attributes", [])
            if a.get("ngsi") == "Relationship"]


def proposal_checks(spec: dict[str, Any], new_dirs: list[Path], ext_dirs: list[Path], *,
                    offline: bool) -> list[Check]:
    """Comprobaciones del conjunto de la propuesta (necesitan la especificación)."""
    checks = []
    try:
        official, _ = sdm_index.load_index("official_list", offline=offline)
    except sdm_index.IndexUnavailable as exc:
        chk = Check("proposal_repository", "Propuesta frente al repositorio")
        chk.warn(f"No se pudo leer la lista oficial: {exc}")
        return [chk]
    repos = {r["repoName"]: r for r in official["officialList"]}
    all_models = {m for r in official["officialList"] for m in r["dataModels"]}
    proposal_names = {e["name"] for e in spec.get("entities") or []}

    chk = Check("subject", "Subject nuevo o existente")
    subject = spec.get("subject")
    if spec.get("entities"):
        exists = subject in repos
        if spec.get("newSubject") is not None:
            if exists:
                chk.error(f"'{subject}' ya existe pero la propuesta lo declara como nuevo")
            else:
                chk.note(f"Subject nuevo '{subject}' (dominios: "
                         f"{', '.join(spec['newSubject'].get('domains', []))})")
                if not (new_dirs and (new_dirs[0].parent / "notes.yaml").is_file()):
                    chk.warn("Falta el notes.yaml del subject nuevo en contribution/")
        elif not exists:
            chk.error(f"El subject '{subject}' no existe; decláralo con 'newSubject'")
        else:
            chk.note(f"Subject existente '{subject}' (dominios: "
                     f"{', '.join(repos[subject].get('domains', []))})")
    checks.append(chk)

    chk = Check("relationship_targets", "Destinos de las Relationship")
    for owner, attr in _relationship_attrs(spec):
        target = attr.get("target")
        if target in proposal_names:
            chk.note(f"{owner}.{attr['name']} → {target} (entidad de la propuesta)")
        elif target in all_models:
            chk.note(f"{owner}.{attr['name']} → {target} (modelo existente)")
        else:
            chk.warn(f"{owner}.{attr['name']} apunta a '{target}', que no está ni en la propuesta "
                     "ni en el repositorio")
    checks.append(chk)

    chk = Check("cross_references", "Enlaces entre los ejemplos de la propuesta")
    ids: dict[str, str] = {}
    for d in new_dirs:
        try:
            doc = json.loads((d / "examples" / "example-normalized.jsonld").read_text(encoding="utf-8"))
            ids[doc.get("type")] = doc.get("id")
        except (OSError, json.JSONDecodeError):
            continue
    dirs = {d.name: d for d in new_dirs}
    dirs.update({f"{d.parent.name}/{d.name}": d for d in ext_dirs})
    for owner, attr in _relationship_attrs(spec):
        target = attr.get("target")
        if target not in ids or owner not in dirs:
            continue
        try:
            doc = json.loads((dirs[owner] / "examples" / "example-normalized.jsonld")
                             .read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        objs = (doc.get(attr["name"]) or {}).get("object")
        objs = objs if isinstance(objs, list) else [objs]
        if ids[target] not in objs:
            chk.warn(f"{owner}.{attr['name']} no apunta al ejemplo de {target} ({ids[target]}); "
                     "los ejemplos no forman un conjunto enlazado")
        else:
            chk.note(f"{owner}.{attr['name']} → {ids[target]}")
    checks.append(chk)
    return checks


def validate_path(path: Path, *, spec: dict[str, Any] | None = None, offline: bool = False,
                  check_urls: bool = False) -> dict[str, Any]:
    new_dirs, ext_dirs = find_targets(path)
    spec_entities = {e["name"]: e for e in (spec or {}).get("entities") or []}
    spec_exts = {x["model"]: x for x in (spec or {}).get("extensions") or []}
    results = []
    session = sdm_index.http_session()
    for edir in new_dirs:
        validator = EntityValidator(edir, spec_entity=spec_entities.get(edir.name) if spec else None,
                                    offline=offline, check_urls=check_urls, session=session)
        results.append(validator.run())
    for edir in ext_dirs:
        subject, model = edir.parent.name, edir.name
        try:
            baseline, _ = fetch_schema.fetch_model_files(subject, model, offline=offline,
                                                         session=session)
        except sdm_index.IndexUnavailable as exc:
            results.append({"entity": model, "kind": "extension", "subject": subject,
                            "path": str(edir), "status": FAIL, "summary": {FAIL: 1},
                            "checks": [{"id": "extension", "status": FAIL,
                                        "errors": [f"No se pudo obtener el original: {exc}"]}]})
            continue
        validator = EntityValidator(edir, spec_entity=spec_exts.get(f"{subject}/{model}")
                                    if spec else None, offline=offline, check_urls=check_urls,
                                    session=session, baseline=baseline)
        results.append(validator.run())
    missing = sorted((set(spec_entities) - {d.name for d in new_dirs}) |
                     (set(spec_exts) - {f"{d.parent.name}/{d.name}" for d in ext_dirs}))
    statuses = {r["status"] for r in results}
    out: dict[str, Any] = {"path": str(path), "entities": results}
    if spec:
        pchecks = proposal_checks(spec, new_dirs, ext_dirs, offline=offline)
        out["proposal"] = [c.as_dict() for c in pchecks]
        statuses |= {c.status for c in pchecks}
    out["status"] = FAIL if (FAIL in statuses or not results or missing) else \
        WARN if WARN in statuses else PASS
    if missing:
        out["missing_entities"] = missing
    if not results:
        out["error"] = "No se encontró ninguna carpeta de entidad con schema.json"
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validación local de una propuesta SDM.")
    parser.add_argument("path", type=Path,
                        help="Carpeta de trabajo, de una entidad o de varias entidades.")
    parser.add_argument("--spec", type=Path, help="Especificación usada para generar (opcional).")
    parser.add_argument("--offline", action="store_true", help="Usa solo la caché local.")
    parser.add_argument("--check-urls", action="store_true",
                        help="Comprueba que las URLs de @context responden.")
    args = parser.parse_args(argv)
    spec = None
    if args.spec:
        try:
            spec = yaml.safe_load(args.spec.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            sdm_index.emit({"error": f"No se pudo leer la especificación: {exc}"})
            return 2
    if not args.path.is_dir():
        sdm_index.emit({"error": f"'{args.path}' no es una carpeta"})
        return 2
    result = validate_path(args.path, spec=spec, offline=args.offline, check_urls=args.check_urls)
    sdm_index.emit(result)
    return 1 if result["status"] == FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
