#!/usr/bin/env python3
"""Visor HTML didáctico y autocontenido de una propuesta.

Genera ``<workdir>/viewer.html``: un único fichero sin dependencias externas que funciona
sin conexión. Muestra el diagrama de entidades y relaciones, los atributos (nuevos,
reutilizados con su modelo de origen, de los Commons, originales o añadidos), los
ejemplos NGSI v2 y NGSI-LD lado a lado y los conceptos SDM/NGSI-LD presentes.

Los nombres técnicos van en inglés; si la especificación incluye ``label`` (en el idioma
del usuario) en entidades y atributos, el visor la muestra junto al nombre.

Uso::

    python build_viewer.py <workdir> --spec proposal.yaml [--lang es] [--strings f.json]
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any

import yaml

import i18n
import proposal as proposal_mod
import sdm_index

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "viewer.html"
BOX_W, BOX_H, GAP_X, GAP_Y, MARGIN = 210, 58, 130, 34, 24
STYLES = {
    "new": {"fill": "#e3f4ea", "stroke": "#1e7a46", "dash": ""},
    "extension": {"fill": "#fbeee0", "stroke": "#a8550f", "dash": ""},
    "external": {"fill": "#f1f1ee", "stroke": "#8a8d91", "dash": "6 4"},
}


# --------------------------------------------------------------------------- diagrama

def diagram_graph(items: list[proposal_mod.Item]) -> tuple[dict[str, str], list[tuple[str, str, str]]]:
    """Nodos ``{nombre: tipo}`` y aristas ``(origen, destino, relación)``."""
    nodes = {item.name: ("extension" if item.kind == "extension" else "new") for item in items}
    edges = []
    for item in items:
        for attr, target in item.relationships:
            edges.append((item.name, target, attr))
            nodes.setdefault(target, "external")
    return nodes, edges


def layout(nodes: dict[str, str], edges: list[tuple[str, str, str]]) -> dict[str, tuple[int, int]]:
    """Coloca los nodos en columnas: cada destino a la derecha de quien lo referencia."""
    rank = {n: 0 for n in nodes}
    for _ in range(len(nodes)):  # relajación acotada (tolera ciclos)
        changed = False
        for src, dst, _ in edges:
            if src != dst and rank[dst] < rank[src] + 1 and rank[src] + 1 < len(nodes):
                rank[dst] = rank[src] + 1
                changed = True
        if not changed:
            break
    columns: dict[int, list[str]] = {}
    order = sorted(nodes, key=lambda n: ({"new": 0, "extension": 1, "external": 2}[nodes[n]], n))
    for name in order:
        columns.setdefault(rank[name], []).append(name)
    tallest = max(len(c) for c in columns.values()) if columns else 1
    positions = {}
    for col, names in columns.items():
        offset = (tallest - len(names)) * (BOX_H + GAP_Y) / 2
        for row, name in enumerate(names):
            positions[name] = (MARGIN + col * (BOX_W + GAP_X),
                               int(MARGIN + offset + row * (BOX_H + GAP_Y)))
    return positions


def build_svg(items: list[proposal_mod.Item]) -> str:
    nodes, edges = diagram_graph(items)
    if not nodes:
        return ""
    pos = layout(nodes, edges)
    col = {n: round((x - MARGIN) / (BOX_W + GAP_X)) for n, (x, _) in pos.items()}
    long_edges = [e for e in edges if col[e[1]] - col[e[0]] > 1]
    arc = 40 + 26 * len(long_edges)  # espacio superior para las flechas que saltan columnas
    if long_edges:
        pos = {n: (x, y + arc) for n, (x, y) in pos.items()}
    width = max(x for x, _ in pos.values()) + BOX_W + MARGIN
    height = max(y for _, y in pos.values()) + BOX_H + MARGIN
    labels = {item.name: item.label for item in items}
    kinds = {item.name: item.subject for item in items}
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
             f'width="{width}" height="{height}" role="img" font-family="system-ui, sans-serif">',
             '<defs><marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="8" '
             'markerHeight="8" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" '
             'fill="#8a8d91"/></marker></defs>']
    top = min(y for _, y in pos.values())
    for src, dst, rel in edges:
        (x1, y1), (x2, y2) = pos[src], pos[dst]
        sx, sy = x1 + BOX_W, y1 + BOX_H / 2
        tx, ty = x2, y2 + BOX_H / 2
        if x2 <= x1:  # misma columna o hacia atrás: curva por debajo
            sx, sy, tx, ty = x1 + BOX_W / 2, y1 + BOX_H, x2 + BOX_W / 2, y2 + BOX_H
            c1, c2 = (sx, sy + 60), (tx, ty + 60)
            mx, my = (sx + tx) / 2, max(sy, ty) + 40
        elif (src, dst, rel) in long_edges:  # salta columnas: arco por encima de las cajas
            level = top - 30 - 26 * long_edges.index((src, dst, rel))
            sx, sy, tx, ty = x1 + BOX_W / 2, y1, x2 + BOX_W / 2, y2
            c1, c2 = (sx, level), (tx, level)
            mx, my = (sx + tx) / 2, level + 14
        else:
            c1, c2 = (sx + GAP_X / 2, sy), (tx - GAP_X / 2, ty)
            mx, my = (sx + tx) / 2, (sy + ty) / 2 - 6
        parts.append(f'<path d="M{sx},{sy} C{c1[0]},{c1[1]} {c2[0]},{c2[1]} {tx},{ty}" '
                     'fill="none" stroke="#8a8d91" stroke-width="1.5" marker-end="url(#arrow)"/>')
        text = html.escape(rel)
        parts.append(f'<rect x="{mx - len(rel) * 3.4 - 4}" y="{my - 11}" width="{len(rel) * 6.8 + 8}" '
                     'height="16" rx="3" fill="#ffffff" fill-opacity="0.9"/>')
        parts.append(f'<text x="{mx}" y="{my + 1}" font-size="11" text-anchor="middle" '
                     f'fill="#3c4043">{text}</text>')
    for name, kind in nodes.items():
        x, y = pos[name]
        st = STYLES[kind]
        dash = f' stroke-dasharray="{st["dash"]}"' if st["dash"] else ""
        parts.append(f'<rect x="{x}" y="{y}" width="{BOX_W}" height="{BOX_H}" rx="8" '
                     f'fill="{st["fill"]}" stroke="{st["stroke"]}" stroke-width="2"{dash}/>')
        parts.append(f'<text x="{x + BOX_W / 2}" y="{y + 24}" font-size="14" font-weight="600" '
                     f'text-anchor="middle" fill="#1d1f21">{html.escape(name)}</text>')
        sub = labels.get(name) or kinds.get(name) or ""
        if sub:
            parts.append(f'<text x="{x + BOX_W / 2}" y="{y + 43}" font-size="11" '
                         f'text-anchor="middle" fill="#5f6368">{html.escape(sub)}</text>')
    parts.append("</svg>")
    return "".join(parts)


# --------------------------------------------------------------------------- datos

def detect_concepts(data: dict[str, Any], strings: dict[str, str]) -> list[str]:
    attrs = [a for item in data["items"] for a in item.attributes]
    keys = ["concept_Property"]
    if any(a.ngsi_type == "Relationship" for a in attrs):
        keys.append("concept_Relationship")
    if any(a.ngsi_type == "GeoProperty" for a in attrs):
        keys.append("concept_GeoProperty")
    keys += ["concept_urn", "concept_context"]
    if any(a.origin == "commons" for a in attrs):
        keys.append("concept_commons")
    if any(a.parsed["units"] for a in attrs):
        keys.append("concept_units")
    if any(a.spec.get("temporal") for a in attrs):
        keys.append("concept_observedAt")
    keys.append("concept_formats")
    if any(item.kind == "extension" for item in data["items"]):
        keys.append("concept_extension")
    if data["new_subject"]:
        keys.append("concept_new_subject")
    return [strings[k] for k in keys]


def viewer_data(data: dict[str, Any], strings: dict[str, str], lang: str) -> dict[str, Any]:
    items = []
    reused = new = 0
    for item in data["items"]:
        attrs = []
        for a in item.attributes:
            if a.origin == "reused" or (a.origin == "added" and a.spec.get("origin") == "reused"):
                reused += 1
            elif a.origin in ("new", "added"):
                new += 1
            parsed = a.parsed
            attrs.append({"name": a.name, "label": a.label, "ngsi": a.ngsi_type,
                          "type": a.json_type, "units": parsed["units"], "origin": a.origin,
                          "source": a.source, "description": parsed["text"]})
        order = {"new": 0, "added": 0, "reused": 1, "original": 2, "commons": 3}
        attrs.sort(key=lambda r: (order.get(r["origin"], 9), r["name"].lower()))
        items.append({"name": item.name, "label": item.label, "kind": item.kind,
                      "subject": item.subject, "version": item.schema.get("$schemaVersion"),
                      "originalVersion": item.original_version,
                      "description": item.schema.get("description"),
                      "attributes": attrs, "examples": item.examples})
    n_new = sum(1 for i in data["items"] if i.kind == "new")
    n_ext = sum(1 for i in data["items"] if i.kind == "extension")
    legend = {k: f"background:{STYLES[s]['fill']};border-color:{STYLES[s]['stroke']};"
              + ("border-style:dashed;" if STYLES[s]["dash"] else "")
              for k, s in (("new", "new"), ("ext", "extension"), ("ref", "external"))}
    return {
        "lang": lang, "strings": strings, "subject": data["subject"],
        "newSubject": data["new_subject"], "domains": data["domains"],
        "countsText": strings["summary_counts"].format(entities=n_new, extensions=n_ext,
                                                       reused=reused, new=new),
        "items": items, "diagram": build_svg(data["items"]), "legendStyles": legend,
        "concepts": detect_concepts(data, strings),
    }


def render(viewer: dict[str, Any]) -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    payload = json.dumps(viewer, ensure_ascii=False).replace("</", "<\\/")
    return (template.replace("__LANG__", html.escape(viewer["lang"]))
            .replace("__TITLE__", html.escape(viewer["strings"]["viewer_title"]))
            .replace("/*__DATA__*/", payload))


def build_viewer(workdir: Path, spec: dict[str, Any], *, lang: str | None = None,
                 strings_file: Path | None = None, offline: bool = False,
                 loaded: dict[str, Any] | None = None) -> dict[str, Any]:
    data = loaded or proposal_mod.load_proposal(workdir, spec, offline=offline)
    lang = lang or data["language"]
    strings = i18n.get_strings(lang, strings_file)
    viewer = viewer_data(data, strings, lang)
    out = workdir / "viewer.html"
    out.write_text(render(viewer), encoding="utf-8")
    return {"viewer": str(out), "items": [i["name"] for i in viewer["items"]],
            "size_bytes": out.stat().st_size}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera el visor HTML de la propuesta.")
    parser.add_argument("workdir", type=Path)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--lang", help="Idioma del usuario (es, en...). Por defecto, el de la "
                                       "especificación ('language').")
    parser.add_argument("--strings", type=Path, help="Catálogo de textos para otro idioma.")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args(argv)
    spec = yaml.safe_load(args.spec.read_text(encoding="utf-8"))
    sdm_index.emit(build_viewer(args.workdir, spec, lang=args.lang, strings_file=args.strings,
                                offline=args.offline))
    return 0


if __name__ == "__main__":
    sys.exit(main())
