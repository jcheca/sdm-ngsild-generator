#!/usr/bin/env python3
"""Descarga el ``schema.json`` de modelos candidatos y resume sus atributos.

Descarga solo desde ``raw.githubusercontent.com/smart-data-models`` y guarda una copia
en la caché local (``<cache>/schemas/<subject>/<Model>/``).

Ejemplos::

    python fetch_schema.py AgriParcel
    python fetch_schema.py dataModel.Environment/AirQualityObserved --examples
    python fetch_schema.py WaterQualityObserved --resolve-commons

La salida es JSON con el resumen de cada schema: Commons referenciados, atributos con su
tipo NGSI, modelo de referencia y unidades extraídos del texto de la descripción.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import requests

import sdm_index

EXAMPLE_FILES = (
    "example.json",
    "example-normalized.json",
    "example.jsonld",
    "example-normalized.jsonld",
)
NGSI_TYPES = ("Property", "Relationship", "GeoProperty", "LanguageProperty",
              "VocabularyProperty", "ListProperty", "ListRelationship", "JsonProperty")

_MODEL_RE = re.compile(r"Model:\s*'([^']*)'")
_UNITS_RE = re.compile(r"Units:\s*'([^']*)'")
_ENUM_RE = re.compile(r"Enum:\s*'([^']*)'")


# --------------------------------------------------------------------------- descripciones

def parse_description(text: str | None) -> dict[str, Any]:
    """Descompone una descripción en formato SDM.

    Formato esperado (normas SDM)::

        "Property. Model:'https://schema.org/Number'. Texto libre. Units:'CEL'"

    Devuelve ``ngsi_type``, ``model``, ``units`` y ``text`` (texto libre restante).
    Los campos que no aparecen quedan a ``None``.
    """
    result: dict[str, Any] = {"ngsi_type": None, "model": None, "units": None, "text": None}
    if not text:
        return result
    rest = text.strip()
    for ngsi in sorted(NGSI_TYPES, key=len, reverse=True):
        if rest.startswith(ngsi + ".") or rest == ngsi:
            result["ngsi_type"] = ngsi
            rest = rest[len(ngsi) + 1:].strip()
            break
    if m := _MODEL_RE.search(rest):
        result["model"] = m.group(1)
        rest = (rest[:m.start()] + rest[m.end():]).strip()
    if m := _UNITS_RE.search(rest):
        result["units"] = m.group(1)
        rest = (rest[:m.start()] + rest[m.end():]).strip()
    if m := _ENUM_RE.search(rest):  # los valores ya están en el schema (enum)
        rest = (rest[:m.start()] + rest[m.end():]).strip()
    # Al quitar Model/Units quedan separadores sueltos (". . Texto"): se limpian.
    rest = re.sub(r"(\s*\.\s*){2,}", ". ", rest)
    rest = re.sub(r"^[\s.]+", "", rest)
    rest = re.sub(r"\s*\.\s*$", "", rest)
    rest = re.sub(r"\s{2,}", " ", rest).strip()
    result["text"] = rest or None
    return result


def _type_of(spec: dict[str, Any]) -> Any:
    if "type" in spec:
        return spec["type"]
    for key in ("anyOf", "oneOf"):
        if key in spec:
            types = [s.get("type") or ("$ref" if "$ref" in s else None) for s in spec[key]]
            return {key: types}
    if "$ref" in spec:
        return {"$ref": spec["$ref"]}
    return None


def summarize_properties(properties: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for name, spec in properties.items():
        if not isinstance(spec, dict):
            continue
        parsed = parse_description(spec.get("description"))
        item: dict[str, Any] = {"name": name, "type": _type_of(spec), **parsed}
        for key in ("format", "enum", "minimum", "maximum", "items"):
            if key in spec:
                item[key] = spec[key]
        if spec.get("type") == "object" and "properties" in spec:
            item["subproperties"] = sorted(spec["properties"])
        result.append(item)
    return result


def summarize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Resumen de un schema SDM: Commons referenciados y atributos propios."""
    refs: list[str] = []
    properties: dict[str, Any] = {}
    required: list[str] = list(schema.get("required", []))
    for block in schema.get("allOf", []):
        if not isinstance(block, dict):
            continue
        if "$ref" in block:
            refs.append(block["$ref"])
        properties.update(block.get("properties", {}))
        required.extend(r for r in block.get("required", []) if r not in required)
    properties.update(schema.get("properties", {}))
    return {
        "$schema": schema.get("$schema"),
        "$schemaVersion": schema.get("$schemaVersion"),
        "$id": schema.get("$id"),
        "title": schema.get("title"),
        "description": schema.get("description"),
        "modelTags": schema.get("modelTags"),
        "derivedFrom": schema.get("derivedFrom"),
        "license": schema.get("license"),
        "required": required,
        "commons_refs": refs,
        "properties": summarize_properties(properties),
    }


# --------------------------------------------------------------------------- resolución

def resolve_model(spec: str, official: dict[str, Any]) -> tuple[str, str]:
    """Convierte ``Model`` o ``Subject/Model`` en ``(subject, Model)`` usando la lista oficial.

    Lanza ``LookupError`` si no existe o si el nombre es ambiguo (con las opciones).
    """
    subject_hint: str | None = None
    model = spec
    if "/" in spec:
        subject_hint, model = spec.split("/", 1)
        if not subject_hint.startswith("dataModel."):
            subject_hint = f"dataModel.{subject_hint}"
    matches = []
    for repo in official["officialList"]:
        if subject_hint and repo["repoName"].lower() != subject_hint.lower():
            continue
        for dm in repo["dataModels"]:
            if dm.lower() == model.lower():
                matches.append((repo["repoName"], dm))
    if not matches:
        raise LookupError(f"Modelo '{spec}' no encontrado en la lista oficial.")
    exact = [m for m in matches if m[1] == model]
    candidates = exact or matches
    if len(candidates) > 1:
        options = ", ".join(f"{s}/{m}" for s, m in candidates)
        raise LookupError(f"Nombre ambiguo '{spec}'. Indica el subject: {options}")
    return candidates[0]


def raw_url(subject: str, model: str, filename: str,
            branch: str = sdm_index.DEFAULT_BRANCH) -> str:
    return f"{sdm_index.RAW_BASE}/{subject}/{branch}/{model}/{filename}"


def _cached_fetch(url: str, dest: Path, *, refresh: bool, offline: bool,
                  session: requests.Session) -> tuple[Path, str]:
    if dest.exists() and not refresh:
        return dest, "cache"
    if offline:
        if dest.exists():
            return dest, "cache"
        raise sdm_index.IndexUnavailable(f"Sin conexión y sin copia en caché: {url}")
    try:
        sdm_index.download(url, dest, session)
    except requests.RequestException as exc:
        if dest.exists():
            return dest, "cache-stale"
        raise sdm_index.IndexUnavailable(f"No se pudo descargar {url}: {exc}") from exc
    return dest, "download"


COMMONS_URL = f"{sdm_index.PAGES_BASE}/data-models/common-schema.json"


def fetch_document(url: str, *, offline: bool = False, refresh: bool = False,
                   session: requests.Session | None = None) -> Any:
    """Devuelve el JSON de ``url`` (sin fragmento), usando la caché local.

    ``common-schema.json`` se toma del índice ``commons``; el resto de documentos de
    SDM se descargan desde raw.githubusercontent y se guardan en ``<cache>/shared``.
    """
    url = url.split("#", 1)[0]
    if not url.startswith(("http://", "https://")):
        raise LookupError(f"URL de documento no válida o relativa sin base: '{url}'")
    if url.rstrip("/").endswith("/data-models/common-schema.json"):
        data, _ = sdm_index.load_index("commons", offline=offline, session=session)
        return data
    raw = sdm_index.pages_to_raw(url)
    if raw.startswith(sdm_index.RAW_BASE + "/"):
        rel = raw.removeprefix(sdm_index.RAW_BASE + "/")
        dest = sdm_index.cache_dir() / "shared" / Path(*rel.split("/"))
    else:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", raw)
        dest = sdm_index.cache_dir() / "external" / safe
    path, _ = _cached_fetch(raw, dest, refresh=refresh, offline=offline,
                            session=session or sdm_index.http_session())
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_pointer(document: Any, pointer: str) -> Any:
    """Resuelve un JSON Pointer (RFC 6901) como ``/definitions/GSMA-Commons``."""
    node = document
    for token in [t for t in pointer.split("/") if t != ""]:
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list):
            node = node[int(token)]
        elif isinstance(node, dict) and token in node:
            node = node[token]
        else:
            raise LookupError(f"El puntero '{pointer}' no existe en el documento.")
    return node


def resolve_ref(ref: str, *, offline: bool = False,
                session: requests.Session | None = None) -> Any:
    """Resuelve un ``$ref`` absoluto (URL + puntero) a su fragmento JSON."""
    url, _, pointer = ref.partition("#")
    document = fetch_document(url, offline=offline, session=session)
    return resolve_pointer(document, pointer) if pointer else document


def fetch_model(subject: str, model: str, *, examples: bool = False, refresh: bool = False,
                offline: bool = False, session: requests.Session | None = None) -> dict[str, Any]:
    session = session or sdm_index.http_session()
    base = sdm_index.cache_dir() / "schemas" / subject / model
    url = raw_url(subject, model, "schema.json")
    path, origin = _cached_fetch(url, base / "schema.json", refresh=refresh,
                                 offline=offline, session=session)
    schema = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, Any] = {
        "subject": subject,
        "dataModel": model,
        "url": url,
        "path": str(path),
        "origin": origin,
        **summarize_schema(schema),
    }
    if examples:
        result["examples"] = {}
        for name in EXAMPLE_FILES:
            ex_url = raw_url(subject, model, f"examples/{name}")
            try:
                ex_path, _ = _cached_fetch(ex_url, base / "examples" / name, refresh=refresh,
                                           offline=offline, session=session)
                result["examples"][name] = str(ex_path)
            except sdm_index.IndexUnavailable as exc:
                result["examples"][name] = {"error": str(exc)}
    return result


MODEL_FILES = ("schema.json",) + tuple(f"examples/{n}" for n in EXAMPLE_FILES) + \
    ("notes.yaml", "ADOPTERS.yaml")


def fetch_model_files(subject: str, model: str, *, offline: bool = False, refresh: bool = False,
                      session: requests.Session | None = None) -> tuple[Path, list[str]]:
    """Descarga en la caché el schema, los 4 ejemplos, notes.yaml y ADOPTERS.yaml del modelo.

    Devuelve ``(carpeta, ficheros_que_faltan)``. Falla si no se puede obtener el schema.
    """
    session = session or sdm_index.http_session()
    base = sdm_index.cache_dir() / "schemas" / subject / model
    missing = []
    for rel in MODEL_FILES:
        try:
            _cached_fetch(raw_url(subject, model, rel), base / Path(*rel.split("/")),
                          refresh=refresh, offline=offline, session=session)
        except sdm_index.IndexUnavailable:
            if rel == "schema.json":
                raise
            missing.append(rel)
    return base, missing


def resolve_commons_refs(refs: list[str], commons: dict[str, Any], *, refresh: bool,
                         offline: bool, session: requests.Session) -> dict[str, Any]:
    """Lista los atributos que aporta cada ``$ref`` a Commons.

    Los Commons generales se toman del índice ``commons``; los de un subject
    (p. ej. ``agrifood-schema.json#/definitions/AgriFood-Commons``) se descargan de GitHub.
    """
    resolved: dict[str, Any] = {}
    for ref in refs:
        url, _, pointer = ref.partition("#")
        def_name = pointer.rsplit("/", 1)[-1] if pointer else None
        try:
            if url.endswith("/data-models/common-schema.json"):
                doc = commons
            else:
                raw = sdm_index.pages_to_raw(url)
                rel = raw.removeprefix(sdm_index.RAW_BASE + "/")
                dest = sdm_index.cache_dir() / "shared" / Path(*rel.split("/"))
                path, _ = _cached_fetch(raw, dest, refresh=refresh, offline=offline,
                                        session=session)
                doc = json.loads(path.read_text(encoding="utf-8"))
            definition = doc.get("definitions", {}).get(def_name, {}) if def_name else doc
            resolved[ref] = summarize_properties(definition.get("properties", {}))
        except (sdm_index.IndexUnavailable, json.JSONDecodeError) as exc:
            resolved[ref] = {"error": str(exc)}
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Descarga y resume schemas de Smart Data Models.")
    parser.add_argument("models", nargs="+", help="Model o Subject/Model (p. ej. Agrifood/AgriParcel).")
    parser.add_argument("--examples", action="store_true", help="Descarga también los 4 ejemplos.")
    parser.add_argument("--resolve-commons", action="store_true",
                        help="Lista los atributos que aporta cada Commons referenciado.")
    parser.add_argument("--refresh", action="store_true", help="Ignora la copia en caché.")
    parser.add_argument("--offline", action="store_true", help="Usa solo la caché local.")
    args = parser.parse_args(argv)

    session = sdm_index.http_session()
    try:
        official, status = sdm_index.load_index("official_list", offline=args.offline,
                                                session=session)
        commons = None
        if args.resolve_commons:
            commons, _ = sdm_index.load_index("commons", offline=args.offline, session=session)
    except sdm_index.IndexUnavailable as exc:
        sdm_index.emit({"error": str(exc)})
        return 2

    results, errors = [], []
    for spec in args.models:
        try:
            subject, model = resolve_model(spec, official)
            item = fetch_model(subject, model, examples=args.examples, refresh=args.refresh,
                               offline=args.offline, session=session)
            if args.resolve_commons:
                item["commons"] = resolve_commons_refs(item["commons_refs"], commons,
                                                       refresh=args.refresh,
                                                       offline=args.offline, session=session)
            results.append(item)
        except (LookupError, sdm_index.IndexUnavailable, json.JSONDecodeError) as exc:
            errors.append({"model": spec, "error": str(exc)})
    sdm_index.emit({
        "warnings": [status["warning"]] if status.get("warning") else [],
        "results": results,
        "errors": errors,
    })
    return 1 if errors and not results else 0


if __name__ == "__main__":
    sys.exit(main())
