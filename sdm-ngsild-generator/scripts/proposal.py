"""Carga de una propuesta ya generada (carpeta de trabajo + especificación).

Reúne en una estructura lo que necesitan la previsualización, el visor y el informe:
entidades nuevas y extensiones, atributos con los Commons resueltos, origen de cada
atributo (nuevo, reutilizado, Commons, original o añadido) y los cuatro ejemplos.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import fetch_schema
import sdm_index

EXAMPLE_FILES = fetch_schema.EXAMPLE_FILES
MAX_DEPTH = 6


@dataclass
class Attribute:
    name: str
    schema: dict[str, Any]           # definición resuelta (sin $ref)
    origin: str                      # new | reused | commons | original | added
    source: str | None = None        # modelo de origen si es reutilizado; Commons si es commons
    label: str | None = None         # traducción para el usuario (visor)
    spec: dict[str, Any] = field(default_factory=dict)

    @property
    def parsed(self) -> dict[str, Any]:
        return fetch_schema.parse_description(self.schema.get("description"))

    @property
    def ngsi_type(self) -> str:
        return self.parsed["ngsi_type"] or "Property"

    @property
    def json_type(self) -> str:
        if self.ngsi_type == "Relationship":
            return "array" if self.schema.get("type") == "array" else "URI"
        if self.ngsi_type == "GeoProperty":
            return "GeoJSON"
        jtype = self.schema.get("type")
        if isinstance(jtype, list):
            return " | ".join(str(t) for t in jtype)
        return str(jtype) if jtype else "-"


@dataclass
class Item:
    name: str
    kind: str                        # new | extension
    subject: str
    path: Path
    schema: dict[str, Any]
    examples: dict[str, Any]
    spec: dict[str, Any]
    attributes: list[Attribute]
    label: str | None = None
    original_version: str | None = None

    @property
    def relationships(self) -> list[tuple[str, str]]:
        """``(atributo, tipo destino)`` de las Relationship del modelo."""
        targets = {a["name"]: a.get("target") for a in self.spec.get("attributes", [])}
        out = []
        for attr in self.attributes:
            if attr.ngsi_type != "Relationship" or attr.name in ("id", "type"):
                continue
            target = targets.get(attr.name) or _target_from_name(attr.name)
            if target:
                out.append((attr.name, target))
        return out


def _target_from_name(name: str) -> str | None:
    """Deducción del destino de una relación por convención (refX, hasX)."""
    for prefix in ("ref", "has"):
        if name.startswith(prefix) and len(name) > len(prefix) and name[len(prefix)].isupper():
            return name[len(prefix):]
    return None


def resolve_schema_node(node: Any, *, offline: bool, base: str = "", depth: int = 0) -> Any:
    """Resuelve recursivamente los ``$ref`` de un nodo de schema (con límite de profundidad).

    ``base`` es la URL del documento donde está el nodo, para resolver ``$ref`` relativos
    (``#/definitions/...``). Si el nodo tiene ``$ref`` y una ``description`` propia, se
    conserva la propia.
    """
    if depth > MAX_DEPTH:
        return node
    if isinstance(node, list):
        return [resolve_schema_node(n, offline=offline, base=base, depth=depth + 1) for n in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        ref = urljoin(base, node["$ref"]) if base else node["$ref"]
        try:
            target = fetch_schema.resolve_ref(ref, offline=offline)
        except (sdm_index.IndexUnavailable, LookupError, json.JSONDecodeError, OSError):
            target = {}
        merged = copy.deepcopy(resolve_schema_node(target, offline=offline,
                                                   base=ref.split("#", 1)[0], depth=depth + 1))
        if not isinstance(merged, dict):
            merged = {}
        for key, value in node.items():
            if key != "$ref":
                merged[key] = resolve_schema_node(value, offline=offline, base=base,
                                                  depth=depth + 1)
        return merged
    return {k: resolve_schema_node(v, offline=offline, base=base, depth=depth + 1)
            for k, v in node.items()}


def split_properties(schema: dict[str, Any], *, offline: bool) -> tuple[dict[str, Any], dict[str, tuple[dict[str, Any], str]]]:
    """Separa los atributos propios de los aportados por Commons (con su origen)."""
    own: dict[str, Any] = {}
    commons: dict[str, tuple[dict[str, Any], str]] = {}
    for block in schema.get("allOf", []):
        if not isinstance(block, dict):
            continue
        if "$ref" in block:
            name = block["$ref"].rsplit("/", 1)[-1]
            try:
                definition = fetch_schema.resolve_ref(block["$ref"], offline=offline)
            except (sdm_index.IndexUnavailable, LookupError, json.JSONDecodeError, OSError):
                continue
            doc_url = block["$ref"].split("#", 1)[0]
            for prop, spec in (definition.get("properties") or {}).items():
                commons[prop] = (resolve_schema_node(spec, offline=offline, base=doc_url), name)
        base = schema.get("$id", "")
        if isinstance(block.get("properties"), dict):
            for prop, spec in block["properties"].items():
                own[prop] = resolve_schema_node(spec, offline=offline, base=base)
    for prop, spec in (schema.get("properties") or {}).items():
        own[prop] = resolve_schema_node(spec, offline=offline, base=schema.get("$id", ""))
    return own, commons


def _read_examples(path: Path) -> dict[str, Any]:
    out = {}
    for name in EXAMPLE_FILES:
        p = path / "examples" / name
        if p.is_file():
            out[name] = json.loads(p.read_text(encoding="utf-8"))
    return out


def _build_item(path: Path, kind: str, subject: str, spec: dict[str, Any], *,
                offline: bool) -> Item:
    schema = json.loads((path / "schema.json").read_text(encoding="utf-8"))
    own, commons = split_properties(schema, offline=offline)
    spec_attrs = {a["name"]: a for a in spec.get("attributes", [])}
    attributes: list[Attribute] = []
    for name, (prop, source) in sorted(commons.items()):
        if name in own:
            continue
        attributes.append(Attribute(name, prop, "commons", source))
    for name, prop in own.items():
        if name == "type":
            continue
        sattr = spec_attrs.get(name, {})
        if kind == "extension":
            origin = "added" if name in spec_attrs else "original"
        else:
            origin = "reused" if sattr.get("origin") == "reused" else "new"
        attributes.append(Attribute(name, prop, origin, sattr.get("reusedFrom"),
                                    sattr.get("label"), sattr))
    item = Item(name=path.name, kind=kind, subject=subject, path=path, schema=schema,
                examples=_read_examples(path), spec=spec, attributes=attributes,
                label=spec.get("label"))
    if kind == "extension":
        try:
            base, _ = fetch_schema.fetch_model_files(subject, path.name, offline=offline)
            original = json.loads((base / "schema.json").read_text(encoding="utf-8"))
            item.original_version = original.get("$schemaVersion")
        except (sdm_index.IndexUnavailable, OSError, json.JSONDecodeError):
            pass
    return item


def load_proposal(workdir: Path, spec: dict[str, Any], *, offline: bool = False) -> dict[str, Any]:
    """Carga la propuesta generada en ``workdir`` (con ``contribution/`` y ``extensions/``)."""
    items: list[Item] = []
    subject = spec.get("subject")
    for ent in spec.get("entities") or []:
        path = workdir / "contribution" / ent["name"]
        if (path / "schema.json").is_file():
            items.append(_build_item(path, "new", subject, ent, offline=offline))
    for ext in spec.get("extensions") or []:
        ext_subject, model = ext["model"].split("/", 1)
        path = workdir / "extensions" / ext_subject / model
        if (path / "schema.json").is_file():
            items.append(_build_item(path, "extension", ext_subject, ext, offline=offline))
    return {
        "subject": subject,
        "new_subject": spec.get("newSubject") is not None,
        "domains": (spec.get("newSubject") or {}).get("domains", []),
        "language": spec.get("language", "en"),
        "items": items,
        "decisions": spec.get("decisions") or [],
        "metadata": spec.get("metadata") or {},
    }
