#!/usr/bin/env python3
"""Informe y ZIP final de la propuesta.

Pasos (en este orden; si la validación falla, no se empaqueta nada):

1. Validación local obligatoria (``validate.py``).
2. Previsualización de los ficheros automáticos (``preview.py``).
3. Visor HTML (``build_viewer.py``).
4. Informe ``report.md`` en el idioma del usuario: validación, prueba contra broker (si
   se pasa su resultado), registro de decisiones y origen de cada atributo.
5. ``<workdir>/<nombre>.zip`` con ``contribution/``, ``extensions/`` (si hay),
   ``preview/``, ``viewer.html``, ``report.md`` y ``proposal.yaml``.

Uso::

    python package.py <workdir> --spec proposal.yaml [--lang es] [--name x]
                      [--broker-result broker.json] [--offline]
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from datetime import date
from pathlib import Path
from typing import Any

import yaml

import build_viewer
import i18n
import preview
import proposal as proposal_mod
import sdm_index
import validate

SKILL_VERSION = (Path(__file__).resolve().parent.parent / "VERSION").read_text(
    encoding="utf-8").strip()
BROKER_RESULT = "broker-result.json"
TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "report.md"
ZIP_DATE = (2020, 1, 1, 0, 0, 0)  # fecha fija: el ZIP es reproducible


def _md_escape(text: Any) -> str:
    return str(text if text is not None else "").replace("|", "\\|").replace("\n", " ")


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return ""
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(_md_escape(c) for c in row) + " |" for row in rows]
    return "\n".join(out)


def _status(strings: dict[str, str], status: str) -> str:
    icon = {"pass": "✅", "warn": "⚠️", "fail": "❌"}.get(status, "")
    return f"{icon} {strings.get('status_' + status, status)}"


# --------------------------------------------------------------------------- secciones

def section_summary(data: dict[str, Any], s: dict[str, str]) -> str:
    lines = []
    if data["subject"] and any(i.kind == "new" for i in data["items"]):
        kind = s["new_subject"] if data["new_subject"] else s["existing_subject"]
        domains = f" · {s['domains']}: {', '.join(data['domains'])}" if data["domains"] else ""
        lines.append(f"- **{s['subject']}:** `{data['subject']}` ({kind}){domains}")
    rows = []
    for item in data["items"]:
        counts: dict[str, int] = {}
        for a in item.attributes:
            counts[a.origin] = counts.get(a.origin, 0) + 1
        version = (f"{item.original_version} → " if item.original_version else "") + \
            str(item.schema.get("$schemaVersion", ""))
        detail = ", ".join(f"{s['origin_' + o].lower()}: {n}" for o, n in sorted(counts.items()))
        rows.append([f"`{item.name}`" + (f" ({item.label})" if item.label else ""),
                     s["extension"] if item.kind == "extension" else s["origin_new"].lower(),
                     f"`{item.subject}`", version, detail])
    lines.append("")
    lines.append(_table([s["model"], s["kind"], s["subject"],
                         s["version"], s["attributes"]], rows))
    return "\n".join(lines).strip()


def section_validation(result: dict[str, Any], s: dict[str, str]) -> str:
    lines = [f"**{s['result']}:** {_status(s, result['status'])}", ""]
    rows = []
    for ent in result["entities"]:
        errors = sum(len(c.get("errors", [])) for c in ent["checks"])
        warnings = sum(len(c.get("warnings", [])) for c in ent["checks"])
        rows.append([f"`{ent['entity']}`", _status(s, ent["status"]), errors, warnings])
    lines.append(_table([s["model"], s["result"], s["errors"], s["warnings"]], rows))
    for ent in result["entities"]:
        details = []
        preexisting = 0
        for c in ent["checks"]:
            for msg in c.get("errors", []):
                details.append(f"- ❌ `{c['id']}`: {msg}")
            for msg in c.get("warnings", []):
                details.append(f"- ⚠️ `{c['id']}`: {msg}")
            preexisting += sum(1 for i in c.get("info", []) if i.startswith("(preexistente"))
        if preexisting:
            details.append(f"- ℹ️ {s['preexisting']}: {preexisting}")
        if details:
            lines += ["", f"**`{ent['entity']}`**", ""] + details
    if result.get("proposal"):
        lines += ["", f"**{s['proposal_checks']}**", ""]
        lines.append(_table([s["check"], s["result"], s["notes"]],
                            [[f"`{c['id']}`", _status(s, c["status"]),
                              "; ".join(c.get("errors", []) + c.get("warnings", []) +
                                        c.get("info", []))] for c in result["proposal"]]))
    return "\n".join(lines).strip()


def section_broker(broker: dict[str, Any] | None, s: dict[str, str]) -> str:
    if not broker:
        return s["report_broker_not_run"]
    lines = [f"**{s['result']}:** {_status(s, broker.get('status', 'fail'))}"]
    if broker.get("broker"):
        lines.append(f"- Broker: `{broker['broker']}`" +
                     (f" ({broker['product']})" if broker.get("product") else ""))
    if broker.get("context_mode"):
        lines.append(f"- @context: `{broker['context_mode']}`")
    for step in broker.get("steps", []):
        mark = "✅" if step.get("ok") else "❌"
        lines.append(f"- {mark} {step.get('name', '')}: {step.get('detail', '')}")
    for warning in broker.get("warnings", []):
        lines.append(f"- ⚠️ {warning}")
    return "\n".join(lines)


def section_decisions(data: dict[str, Any], s: dict[str, str]) -> str:
    rows = [[d.get("item"), s.get("dec_" + str(d.get("decision")), d.get("decision")),
             d.get("reason"), d.get("source", "")] for d in data["decisions"]]
    return _table([s["item"], s["decision"], s["reason"], s["source"]], rows) or "-"


def section_attributes(data: dict[str, Any], s: dict[str, str]) -> str:
    parts = []
    for item in data["items"]:
        rows = []
        for a in item.attributes:
            if a.origin in ("commons", "original"):
                continue
            origin = s["origin_" + a.origin]
            if a.origin == "added" and a.spec.get("origin") == "reused":
                origin += f" · {s['origin_reused'].lower()}"
            note = a.source or a.spec.get("justification") or ""
            rows.append([f"`{a.name}`", a.label or "", a.ngsi_type, a.parsed["units"] or "",
                         origin, note])
        commons = sorted({a.source for a in item.attributes if a.origin == "commons"})
        parts.append(f"### `{item.name}`" + (f" ({item.label})" if item.label else "") + "\n")
        parts.append(_table([s["attribute"], s["translation"], s["ngsi_type"], s["units"], s["origin"],
                             s["source"]], rows))
        if commons:
            parts.append(f"\n{s['origin_commons']}: " + ", ".join(f"`{c}`" for c in commons))
        parts.append("")
    return "\n".join(parts).strip()


def section_contents(workdir: Path, s: dict[str, str]) -> str:
    entries = [("contribution/", "contents_contribution"), ("extensions/", "contents_extensions"),
               ("preview/", "contents_preview"), ("viewer.html", "contents_viewer"),
               ("report.md", "contents_report"), ("proposal.yaml", "contents_proposal"),
               (BROKER_RESULT, "contents_broker")]
    return "\n".join(f"- `{name}`: {s[key]}" for name, key in entries
                     if (workdir / name.rstrip("/")).exists() or name in ("report.md",
                                                                           "proposal.yaml"))


def build_report(workdir: Path, data: dict[str, Any], validation: dict[str, Any],
                 strings: dict[str, str], *, name: str,
                 broker: dict[str, Any] | None = None) -> str:
    indexes = {i["name"]: i["fetched_at"] for i in sdm_index.cache_status()}
    values = {
        "title": strings["report_title"], "name": name, "generated_on": strings["generated_on"],
        "date": date.today().isoformat(), "indexes_date": strings["indexes_date"],
        "indexes": (indexes.get("attributes") or "-")[:10], "version": SKILL_VERSION,
        "h_summary": strings["report_summary"], "summary": section_summary(data, strings),
        "h_validation": strings["report_validation"],
        "validation": section_validation(validation, strings),
        "h_broker": strings["report_broker"], "broker": section_broker(broker, strings),
        "h_decisions": strings["report_decisions"], "decisions": section_decisions(data, strings),
        "h_attributes": strings["report_attributes"],
        "attributes": section_attributes(data, strings),
        "h_contents": strings["report_contents"], "contents": section_contents(workdir, strings),
        "h_next": strings["report_next"], "next": strings["report_next_text"],
    }
    text = TEMPLATE.read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text


# --------------------------------------------------------------------------- ZIP

def build_zip(workdir: Path, zip_path: Path, spec_path: Path | None) -> list[str]:
    members: list[tuple[Path, str]] = []
    for folder in ("contribution", "extensions", "preview"):
        root = workdir / folder
        if root.is_dir():
            for f in sorted(root.rglob("*")):
                if f.is_file():
                    members.append((f, f.relative_to(workdir).as_posix()))
    for single in ("viewer.html", "report.md", BROKER_RESULT):
        if (workdir / single).is_file():
            members.append((workdir / single, single))
    if spec_path and spec_path.is_file():
        members.append((spec_path, "proposal.yaml"))
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, arcname in members:
            info = zipfile.ZipInfo(arcname, date_time=ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, path.read_bytes())
    return [arc for _, arc in members]


def package(workdir: Path, spec: dict[str, Any], *, spec_path: Path | None = None,
            lang: str | None = None, strings_file: Path | None = None,
            name: str | None = None, broker: dict[str, Any] | None = None,
            offline: bool = False) -> dict[str, Any]:
    validation = validate.validate_path(workdir, spec=spec, offline=offline)
    if validation["status"] == validate.FAIL:
        return {"status": "fail", "message": "La validación local falla: no se empaqueta. "
                "Corrige proposal.yaml, regenera y vuelve a intentarlo.", "validation": validation}
    data = proposal_mod.load_proposal(workdir, spec, offline=offline)
    lang = lang or data["language"]
    strings = i18n.get_strings(lang, strings_file)
    prev = preview.build_preview(workdir, spec, lang=lang, strings_file=strings_file,
                                 offline=offline, loaded=data)
    viewer = build_viewer.build_viewer(workdir, spec, lang=lang, strings_file=strings_file,
                                       offline=offline, loaded=data)
    name = name or spec.get("name") or workdir.resolve().name.removeprefix("sdm-proposal-")
    if broker is None and (workdir / BROKER_RESULT).is_file():
        broker = json.loads((workdir / BROKER_RESULT).read_text(encoding="utf-8"))
    report = build_report(workdir, data, validation, strings, name=name, broker=broker)
    (workdir / "report.md").write_text(report, encoding="utf-8")
    zip_path = workdir / f"{name}.zip"
    members = build_zip(workdir, zip_path, spec_path)
    return {"status": validation["status"], "zip": str(zip_path), "members": len(members),
            "report": str(workdir / "report.md"), "viewer": viewer["viewer"],
            "preview": prev["preview"], "contexts": prev["contexts"],
            "warnings": prev["warnings"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Informe y ZIP de la propuesta SDM.")
    parser.add_argument("workdir", type=Path)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--lang", help="Idioma del usuario; por defecto 'language' de la spec.")
    parser.add_argument("--strings", type=Path, help="Catálogo de textos para otro idioma.")
    parser.add_argument("--name", help="Nombre del ZIP (por defecto, el de la carpeta).")
    parser.add_argument("--broker-result", type=Path,
                        help="JSON de broker_test.py (por defecto, <workdir>/broker-result.json "
                             "si existe).")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args(argv)
    spec = yaml.safe_load(args.spec.read_text(encoding="utf-8"))
    broker = json.loads(args.broker_result.read_text(encoding="utf-8")) \
        if args.broker_result else None
    result = package(args.workdir, spec, spec_path=args.spec, lang=args.lang,
                     strings_file=args.strings, name=args.name, broker=broker,
                     offline=args.offline)
    sdm_index.emit(result)
    return 1 if result["status"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
