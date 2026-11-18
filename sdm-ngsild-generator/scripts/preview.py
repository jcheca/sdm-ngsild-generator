#!/usr/bin/env python3
"""Previsualización de los ficheros que el repositorio SDM genera automáticamente.

Crea ``<workdir>/preview/`` (que NO forma parte de la contribución) con::

    preview/LEEME.txt                          aviso explícito
    preview/<subject>/context.jsonld           @context del subject con los términos nuevos
    preview/<subject>/<Model>/model.yaml       como utils/10_model.yaml_v13.py
    preview/<subject>/<Model>/doc/spec.md      como utils/20_create_spec_v11.0.py

Reglas del ``context.jsonld`` (utils/25_create_subject_context_V7.py):
cada atributo y subatributo → ``https://smartdatamodels.org/<subject>/<atributo>``; cada
tipo de entidad → ``https://smartdatamodels.org/<subject>/<Entidad>``; los términos de
``context/common-context.jsonld`` y del core context ETSI tienen prioridad. En un subject
existente se parte de su contexto publicado y solo se añaden los términos nuevos.

Fidelidad: misma estructura, secciones y contenido que los generadores oficiales, no una
copia byte a byte.

Uso::

    python preview.py <workdir> --spec proposal.yaml [--lang es] [--offline]
"""
from __future__ import annotations

import argparse
from datetime import date
import json
import sys
from pathlib import Path
from typing import Any

import yaml

import fetch_schema
import i18n
import proposal as proposal_mod
import sdm_index

SDM_TERMS = "https://smartdatamodels.org"
COMMON_CONTEXT_URL = (f"{sdm_index.RAW_BASE}/data-models/{sdm_index.DEFAULT_BRANCH}/"
                      "context/common-context.jsonld")
CORE_CONTEXT_URL = "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"
DISCLAIMER = ("Redistribution and use in source and binary forms, with or without modification, "
              "are permitted  provided that the license conditions are met. Copyleft (c) {year} "
              "Contributors to Smart Data Models Program")
EXAMPLE_TITLES = {
    "example.json": ("NGSI-v2 key-values", "Here is an example of a {m} in JSON format as key-values. This is compatible with NGSI-v2 when using `options=keyValues` and returns the context data of an individual entity."),
    "example-normalized.json": ("NGSI-v2 normalized", "Here is an example of a {m} in JSON format as normalized. This is compatible with NGSI-v2 when not using options and returns the context data of an individual entity."),
    "example.jsonld": ("NGSI-LD key-values", "Here is an example of a {m} in JSON-LD format as key-values. This is compatible with NGSI-LD when using `options=keyValues` and returns the context data of an individual entity."),
    "example-normalized.jsonld": ("NGSI-LD normalized", "Here is an example of a {m} in JSON-LD format as normalized. This is compatible with NGSI-LD when not using options and returns the context data of an individual entity."),
}


# --------------------------------------------------------------------------- model.yaml

def _yaml_property(schema: dict[str, Any]) -> dict[str, Any]:
    parsed = fetch_schema.parse_description(schema.get("description"))
    out: dict[str, Any] = {}
    if parsed["text"]:
        out["description"] = parsed["text"]
    for key in ("enum", "format", "minimum", "maximum"):
        if key in schema:
            out[key] = schema[key]
    if isinstance(schema.get("properties"), dict):
        out["properties"] = {k: _yaml_property(v) for k, v in sorted(schema["properties"].items())
                             if isinstance(v, dict)}
    if isinstance(schema.get("items"), dict) and "anyOf" not in schema["items"]:
        out["items"] = _yaml_property(schema["items"])
    if "type" in schema:
        out["type"] = schema["type"]
    x_ngsi = {k: v for k, v in (("model", parsed["model"]), ("type", parsed["ngsi_type"]),
                                ("units", parsed["units"])) if v}
    if x_ngsi:
        out["x-ngsi"] = x_ngsi
    return out


def build_model_yaml(item: proposal_mod.Item) -> dict[str, Any]:
    schema = item.schema
    props: dict[str, Any] = {attr.name: _yaml_property(attr.schema) for attr in item.attributes}
    for block in schema.get("allOf", []):
        if isinstance(block, dict) and "type" in (block.get("properties") or {}):
            props["type"] = _yaml_property(block["properties"]["type"])
    return {item.name: {
        "description": schema.get("description", ""),
        "properties": dict(sorted(props.items())),
        "required": sorted(schema.get("required", [])),
        "type": "object",
        "x-derived-from": schema.get("derivedFrom", ""),
        "x-disclaimer": DISCLAIMER.format(year=date.today().year),
        "x-license-url": schema.get("license", ""),
        "x-model-schema": schema.get("$id", ""),
        "x-model-tags": schema.get("modelTags", ""),
        "x-version": schema.get("$schemaVersion", ""),
    }}


def dump_yaml(data: Any) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=10_000)


# --------------------------------------------------------------------------- spec.md

def _property_lines(name: str, schema: dict[str, Any], indent: str = "") -> list[str]:
    parsed = fetch_schema.parse_description(schema.get("description"))
    jtype = schema.get("type")
    label = f"`{name}[{jtype}]`" if isinstance(jtype, str) else f"`{name}`"
    text = f"{indent}- {label}: {parsed['text'] or ''}"
    if parsed["model"]:
        text += f"  . Model: [{parsed['model']}]({parsed['model']})"
    if parsed["units"]:
        text += f". Units: '{parsed['units']}'"
    lines = [text + "  "]
    for sub, sub_schema in sorted((schema.get("properties") or {}).items()):
        if isinstance(sub_schema, dict):
            lines += _property_lines(sub, sub_schema, indent + "\t")
    return lines


def build_spec_md(item: proposal_mod.Item, model_yaml: dict[str, Any]) -> str:
    schema, name = item.schema, item.name
    notes = {}
    notes_path = item.path / "notes.yaml"
    if notes_path.is_file():
        notes = yaml.safe_load(notes_path.read_text(encoding="utf-8")) or {}
    license_url = schema.get("license", "")
    props = sorted(((a.name, a.schema) for a in item.attributes), key=lambda p: p[0].lower())
    out = [
        "<!-- 10-Header -->  ",
        "[![Smart Data Models](https://smartdatamodels.org/wp-content/uploads/2022/01/SmartDataModels_logo.png \"Logo\")](https://smartdatamodels.org)  ",
        f"Entity: {name}  ",
        "=" * (len(name) + 8) + "<!-- /10-Header -->  ",
        "<!-- 15-License -->  ",
        f"[Open License]({license_url})  ",
        "[document generated automatically](https://docs.google.com/presentation/d/e/2PACX-1vTs-Ng5dIAwkg91oTTUdt8ua7woBXhPnwavZ0FxgR8BsAI_Ek3C5q97Nd94HS8KhP-r_quD4H0fgyt3/pub?start=false&loop=false&delayms=3000#slide=id.gb715ace035_0_60)  ",
        "<!-- /15-License -->  ",
        "<!-- 20-Description -->  ",
        f"Global description: **{schema.get('description', '')}**  ",
        f"version: {schema.get('$schemaVersion', '')}  ",
        "<!-- /20-Description -->  ",
        "<!-- 30-PropertiesList -->  ",
        "",
        "## List of properties  ",
        "",
        "<sup><sub>[*] If there is not a type in an attribute is because it could have several types or different formats/patterns</sub></sup>  ",
    ]
    for pname, pschema in props:
        out += _property_lines(pname, pschema)
    out += ["<!-- /30-PropertiesList -->  ", "<!-- 35-RequiredProperties -->  ",
            "Required properties  ",
            "".join(f"- `{r}`  " for r in sorted(schema.get("required", []))) +
            "<!-- /35-RequiredProperties -->  ",
            "<!-- 40-NotesYaml -->  ", str(notes.get("notesHeader") or "") + "  ",
            "<!-- /40-NotesYaml -->  ",
            "<!-- 50-DataModelHeader -->  ", "## Data Model description of properties  ",
            "Sorted alphabetically (click for details)  ", "<!-- /50-DataModelHeader -->  ",
            "<!-- 60-ModelYaml -->  ",
            "<details><summary><strong>full yaml details</strong></summary>    ", "```yaml  "]
    out += [line + "    " for line in dump_yaml(model_yaml).splitlines()]
    out += ["```  ", "</details>    ", "<!-- /60-ModelYaml -->  ", "<!-- 70-MiddleNotes -->  ",
            str(notes.get("notesMiddle") or "") + "  ", "<!-- /70-MiddleNotes -->  ",
            "<!-- 80-Examples -->  ", "## Example payloads    "]
    for fname, (title, intro) in EXAMPLE_TITLES.items():
        if fname not in item.examples:
            continue
        out += [f"#### {name} {title} Example    ", intro.format(m=name) + "  ",
                "<details><summary><strong>show/hide example</strong></summary>    ", "```json  "]
        out += [line + "  " for line in
                json.dumps(item.examples[fname], indent=2, ensure_ascii=False).splitlines()]
        out += ["```  ", "</details>"]
    out += ["<!-- /80-Examples -->  ", "<!-- 90-FooterNotes -->  ",
            str(notes.get("notesFooter") or "") + "  ", "<!-- /90-FooterNotes -->  ",
            "<!-- 95-Units -->  ",
            "See [FAQ 10](https://smartdatamodels.org/index.php/faqs/) to get an answer on how to deal with magnitude units  ",
            "<!-- /95-Units -->  ", "<!-- 97-LastFooter -->  ", "---  ",
            "[Smart Data Models](https://smartdatamodels.org) +++ [Contribution Manual](https://bit.ly/contribution_manual) +++ [About](https://bit.ly/Introduction_SDM)<!-- /97-LastFooter -->  ",
            ""]
    return "\n".join(out)


# --------------------------------------------------------------------------- context.jsonld

def _all_terms(schema: dict[str, Any], out: set[str]) -> None:
    for name, sub in (schema.get("properties") or {}).items():
        out.add(name)
        if isinstance(sub, dict):
            _all_terms(sub, out)
    if isinstance(schema.get("items"), dict):
        _all_terms(schema["items"], out)


def model_terms(item: proposal_mod.Item) -> set[str]:
    terms: set[str] = set()
    for attr in item.attributes:
        terms.add(attr.name)
        _all_terms(attr.schema, terms)
    return terms


def _load_context(url: str, *, offline: bool) -> dict[str, Any] | None:
    try:
        doc = fetch_schema.fetch_document(url, offline=offline)
    except (sdm_index.IndexUnavailable, json.JSONDecodeError):
        return None
    ctx = doc.get("@context") if isinstance(doc, dict) else None
    return ctx if isinstance(ctx, dict) else None


def build_context(subject: str, items: list[proposal_mod.Item], *, new_subject: bool,
                  offline: bool) -> tuple[dict[str, Any], list[str], list[str]]:
    """Devuelve ``(context, términos_nuevos, avisos)`` del subject."""
    warnings: list[str] = []
    base: dict[str, Any] = {}
    if not new_subject:
        official = _load_context(f"{sdm_index.RAW_BASE}/{subject}/{sdm_index.DEFAULT_BRANCH}/"
                                 "context.jsonld", offline=offline)
        if official is None:
            warnings.append(f"No se pudo obtener el @context publicado de {subject}; la "
                            "previsualización solo contiene los términos de la propuesta")
        else:
            base = dict(official)
    common = _load_context(COMMON_CONTEXT_URL, offline=offline) or {}
    if not common:
        warnings.append("No se pudo obtener common-context.jsonld")
    core = _load_context(CORE_CONTEXT_URL, offline=offline) or {}
    if not core:
        warnings.append("No se pudo obtener el core context de ETSI; los términos del núcleo "
                        "NGSI-LD no se han marcado")

    generated: dict[str, Any] = {}
    for item in items:
        generated[item.name] = f"{SDM_TERMS}/{subject}/{item.name}"
        for term in model_terms(item):
            generated[term] = f"{SDM_TERMS}/{subject}/{term}"
    for term in list(generated):
        if term in common:
            generated[term] = common[term]
    generated["ngsi-ld"] = core.get("ngsi-ld", "https://uri.etsi.org/ngsi-ld/")
    for term in list(generated):
        if term in core:
            generated[term] = core[term]

    new_terms = sorted(t for t in generated if t not in base)
    merged = dict(base)
    for term in new_terms:
        merged[term] = generated[term]
    return {"@context": dict(sorted(merged.items()))}, new_terms, warnings


# --------------------------------------------------------------------------- orquestación

def build_preview(workdir: Path, spec: dict[str, Any], *, lang: str = "en",
                  strings_file: Path | None = None, offline: bool = False,
                  loaded: dict[str, Any] | None = None) -> dict[str, Any]:
    strings = i18n.get_strings(lang, strings_file)
    data = loaded or proposal_mod.load_proposal(workdir, spec, offline=offline)
    root = workdir / "preview"
    root.mkdir(parents=True, exist_ok=True)
    (root / "LEEME.txt").write_text(strings["leeme"], encoding="utf-8")
    files = [root / "LEEME.txt"]
    warnings: list[str] = []
    by_subject: dict[str, list[proposal_mod.Item]] = {}
    for item in data["items"]:
        by_subject.setdefault(item.subject, []).append(item)
        target = root / item.subject / item.name
        model_yaml = build_model_yaml(item)
        (target / "doc").mkdir(parents=True, exist_ok=True)
        (target / "model.yaml").write_text(dump_yaml(model_yaml), encoding="utf-8")
        (target / "doc" / "spec.md").write_text(build_spec_md(item, model_yaml), encoding="utf-8")
        files += [target / "model.yaml", target / "doc" / "spec.md"]
    contexts = {}
    for subject, items in by_subject.items():
        is_new = data["new_subject"] and subject == data["subject"]
        context, new_terms, warns = build_context(subject, items, new_subject=is_new,
                                                  offline=offline)
        warnings += warns
        path = root / subject / "context.jsonld"
        path.write_text(json.dumps(context, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
        files.append(path)
        contexts[subject] = {"path": str(path), "new_subject": is_new, "new_terms": new_terms}
    return {"preview": str(root), "files": [str(f) for f in files], "contexts": contexts,
            "warnings": warnings}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Previsualización de ficheros automáticos SDM.")
    parser.add_argument("workdir", type=Path)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--lang", default="en")
    parser.add_argument("--strings", type=Path, help="Catálogo de textos para otro idioma.")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args(argv)
    spec = yaml.safe_load(args.spec.read_text(encoding="utf-8"))
    result = build_preview(args.workdir, spec, lang=args.lang, strings_file=args.strings,
                           offline=args.offline)
    sdm_index.emit(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
