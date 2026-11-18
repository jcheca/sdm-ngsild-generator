#!/usr/bin/env python3
"""Búsqueda local de subjects, modelos y atributos de Smart Data Models.

La búsqueda es por coincidencia de términos (en inglés): el script devuelve candidatos
y Claude evalúa después su pertinencia semántica antes de presentarlos al usuario.

Ejemplos::

    python search.py subjects --domain SmartWater
    python search.py models soil parcel --domain SmartAgrifood
    python search.py attributes soil moisture
    python search.py attributes --exact temperature
    python search.py batch attributes.json        # modo «lista completa»
    python search.py units litre per second
    python search.py units --code CEL

La salida es JSON.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from collections import Counter, defaultdict
from typing import Any, Iterable

import sdm_index
import units as uncefact

# Palabras vacías frecuentes en las descripciones SDM que no aportan a la búsqueda.
STOPWORDS = frozenset(
    "a an and are as at be by for from has in is it its of on or that the this to with "
    "which where when it's into per than other used value values entity property "
    "relationship model ngsi".split()
)
_SPLIT_RE = re.compile(r"[^0-9a-zA-Z]+")
_CAMEL_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")
MIN_PREFIX = 4
# Bonificación por cada término encontrado, para premiar la cobertura de la consulta.
COVERAGE_BONUS = 1.0


# --------------------------------------------------------------------------- texto

def tokenize(text: str | None, *, drop_stopwords: bool = True) -> list[str]:
    """Separa ``text`` en términos en minúsculas, partiendo también camelCase.

    >>> tokenize("soilMoistureVwc of the AgriParcel")
    ['soil', 'moisture', 'vwc', 'agri', 'parcel']
    """
    if not text:
        return []
    tokens: list[str] = []
    for chunk in _SPLIT_RE.split(str(text)):
        for part in _CAMEL_RE.findall(chunk):
            low = part.lower()
            if drop_stopwords and low in STOPWORDS:
                continue
            tokens.append(low)
    return tokens


def _term_matches(term: str, tokens: Iterable[str]) -> bool:
    """Coincidencia exacta o por prefijo (para términos de al menos 4 letras)."""
    for tok in tokens:
        if tok == term:
            return True
        if len(term) >= MIN_PREFIX and len(tok) >= MIN_PREFIX and (
            tok.startswith(term) or term.startswith(tok)
        ):
            return True
    return False


def score_fields(terms: list[str], fields: list[tuple[set[str], float]]) -> tuple[int, float, list[str]]:
    """Puntúa ``terms`` contra varios campos ponderados.

    Devuelve ``(términos_coincidentes, puntuación, lista_de_términos)``. Cada término
    suma el peso del mejor campo en el que aparece.
    """
    matched: list[str] = []
    score = 0.0
    for term in terms:
        best = 0.0
        for tokens, weight in fields:
            if weight > best and _term_matches(term, tokens):
                best = weight
        if best:
            matched.append(term)
            score += best + COVERAGE_BONUS
    return len(matched), score, matched


def _query_terms(query: list[str]) -> list[str]:
    terms: list[str] = []
    for word in query:
        for tok in tokenize(word):
            if tok not in terms:
                terms.append(tok)
    return terms


# --------------------------------------------------------------------------- índices

def _domains_by_subject(official: dict[str, Any]) -> dict[str, list[str]]:
    return {repo["repoName"]: repo.get("domains", []) for repo in official["officialList"]}


def _commons_by_property(commons: dict[str, Any]) -> dict[str, list[str]]:
    """Mapa ``atributo -> [definiciones de common-schema.json que lo declaran]``."""
    result: dict[str, list[str]] = defaultdict(list)
    for def_name, definition in commons.get("definitions", {}).items():
        if isinstance(definition, dict):
            for prop in definition.get("properties", {}):
                result[prop].append(def_name)
    return dict(result)


def _subject_filter(subject: str | None, domain: str | None,
                    domains: dict[str, list[str]]) -> set[str] | None:
    if not subject and not domain:
        return None
    allowed = set(domains)
    if subject:
        wanted = subject if subject.startswith("dataModel.") else f"dataModel.{subject}"
        allowed = {s for s in allowed if s.lower() == wanted.lower()}
    if domain:
        allowed = {s for s in allowed
                   if any(d.lower() == domain.lower() for d in domains.get(s, []))}
    return allowed


# --------------------------------------------------------------------------- subjects

def search_subjects(official: dict[str, Any], *, domain: str | None = None,
                    query: list[str] | None = None) -> list[dict[str, Any]]:
    terms = _query_terms(query or [])
    results = []
    for repo in official["officialList"]:
        domains = repo.get("domains", [])
        if domain and not any(d.lower() == domain.lower() for d in domains):
            continue
        if terms:
            fields = [(set(tokenize(repo["repoName"])), 3.0),
                      (set(t for m in repo["dataModels"] for t in tokenize(m)), 1.0)]
            n, score, _ = score_fields(terms, fields)
            if not n:
                continue
        else:
            n, score = 0, 0.0
        results.append({
            "subject": repo["repoName"],
            "domains": domains,
            "model_count": len(repo["dataModels"]),
            "dataModels": repo["dataModels"],
            "_rank": (n, score),
        })
    if terms:
        results.sort(key=lambda r: r["_rank"], reverse=True)
    else:
        results.sort(key=lambda r: r["subject"].lower())
    for r in results:
        r.pop("_rank")
    return results


# --------------------------------------------------------------------------- modelos

def search_models(query: list[str], official: dict[str, Any], metadata: list[dict[str, Any]],
                  *, domain: str | None = None, subject: str | None = None,
                  limit: int = 15) -> list[dict[str, Any]]:
    terms = _query_terms(query)
    domains = _domains_by_subject(official)
    allowed = _subject_filter(subject, domain, domains)
    results = []
    for item in metadata:
        subj = item.get("subject", "")
        if allowed is not None and subj not in allowed:
            continue
        fields = [
            (set(tokenize(item.get("dataModel"))), 5.0),
            (set(tokenize(item.get("title"))), 3.0),
            (set(tokenize(item.get("modelTags"))), 2.0),
            (set(tokenize(subj)), 1.5),
            (set(tokenize(item.get("description"))), 1.0),
        ]
        n, score, matched = score_fields(terms, fields)
        if not n:
            continue
        if item.get("dataModel", "").lower() == "".join(terms):
            score += 20  # coincidencia exacta con el nombre del modelo
        description = item.get("description", "") or ""
        results.append({
            "subject": subj,
            "dataModel": item.get("dataModel"),
            "domains": domains.get(subj, []),
            "title": item.get("title"),
            "description": description if len(description) <= 400 else description[:397] + "...",
            "version": item.get("version"),
            "jsonSchemaUrl": item.get("jsonSchemaUrl"),
            "matched_terms": matched,
            "score": round(score, 2),
        })
    results.sort(key=lambda r: (r["score"], len(r["matched_terms"])), reverse=True)
    return results[:limit]


# --------------------------------------------------------------------------- atributos

def group_attributes(attributes: list[dict[str, Any]], *, include_subproperties: bool = False,
                     allowed_subjects: set[str] | None = None) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for attr in attributes:
        if not include_subproperties and attr.get("parentId"):
            continue
        if allowed_subjects is not None and attr.get("repoName") not in allowed_subjects:
            continue
        name = attr.get("property")
        if name:
            groups[name].append(attr)
    return groups


def summarize_attribute(name: str, occurrences: list[dict[str, Any]],
                        commons_map: dict[str, list[str]], *,
                        max_models: int = 10) -> dict[str, Any]:
    """Resume todas las apariciones de un atributo en el repositorio."""
    def counter(key: str) -> dict[str, int]:
        return dict(Counter(str(o[key]) for o in occurrences if o.get(key)).most_common())

    descriptions = Counter(o["description"].strip() for o in occurrences if o.get("description"))
    enums: list[Any] = []
    for o in occurrences:
        for value in o.get("enum") or []:
            if value not in enums:
                enums.append(value)
    models = sorted({(o["repoName"], o["dataModel"]) for o in occurrences})
    return {
        "property": name,
        "occurrences": len(models),
        "in_commons": commons_map.get(name, []),
        "typeNGSI": counter("typeNGSI"),
        "type": counter("type"),
        "format": counter("format"),
        "units": counter("units"),
        "model": counter("model"),
        "descriptions": [d for d, _ in descriptions.most_common(3)],
        "enum_sample": enums[:15],
        "models": [{"subject": s, "dataModel": m} for s, m in models[:max_models]],
        "more_models": max(0, len(models) - max_models),
    }


def search_attributes(query: list[str], attributes: list[dict[str, Any]],
                      official: dict[str, Any], commons: dict[str, Any], *,
                      exact: str | None = None, domain: str | None = None,
                      subject: str | None = None, include_subproperties: bool = False,
                      limit: int = 15) -> list[dict[str, Any]]:
    domains = _domains_by_subject(official)
    allowed = _subject_filter(subject, domain, domains)
    groups = group_attributes(attributes, include_subproperties=include_subproperties,
                              allowed_subjects=allowed)
    commons_map = _commons_by_property(commons)

    if exact:
        names = [n for n in groups if n.lower() == exact.lower()]
        names.sort(key=lambda n: (n != exact, -len(groups[n])))
        results = [summarize_attribute(n, groups[n], commons_map) for n in names]
        if not results and exact in commons_map:
            results = [{"property": exact, "occurrences": 0, "in_commons": commons_map[exact]}]
        return results

    return rank_attributes(_query_terms(query), groups, commons_map, limit=limit)


def rank_attributes(terms: list[str], groups: dict[str, list[dict[str, Any]]],
                    commons_map: dict[str, list[str]], *, limit: int = 15,
                    desc_cache: dict[str, set[str]] | None = None) -> list[dict[str, Any]]:
    """Ordena los grupos de atributos por coincidencia con ``terms``.

    ``desc_cache`` permite reutilizar los términos de las descripciones entre consultas
    (modo por lotes).
    """
    joined = "".join(terms)
    ranked = []
    for name, occ in groups.items():
        name_tokens = set(tokenize(name, drop_stopwords=False))
        if desc_cache is not None and name in desc_cache:
            desc_tokens = desc_cache[name]
        else:
            desc_tokens = set()
            for o in occ:
                desc_tokens.update(tokenize(o.get("description")))
            if desc_cache is not None:
                desc_cache[name] = desc_tokens
        n, score, matched = score_fields(terms, [(name_tokens, 5.0), (desc_tokens, 1.0)])
        if not n:
            continue
        if name.lower() == joined:
            score += 20
        models = len({(o["repoName"], o["dataModel"]) for o in occ})
        if name in commons_map:
            score += 2  # preferencia por lo que ya está en los Commons
        ranked.append(((score, n, models), name, matched))
    ranked.sort(key=lambda r: r[0], reverse=True)
    results = []
    for (score, _, _), name, matched in ranked[:limit]:
        summary = summarize_attribute(name, groups[name], commons_map)
        summary["matched_terms"] = matched
        summary["score"] = round(score, 2)
        results.append(summary)
    return results


def _brief(summary: dict[str, Any]) -> dict[str, Any]:
    """Versión compacta de un resumen de atributo para el modo por lotes."""
    return {
        "property": summary["property"],
        "occurrences": summary["occurrences"],
        "in_commons": summary.get("in_commons", []),
        "typeNGSI": summary.get("typeNGSI", {}),
        "type": summary.get("type", {}),
        "units": summary.get("units", {}),
        "description": (summary.get("descriptions") or [None])[0],
        "models": [f"{m['subject']}/{m['dataModel']}" for m in summary.get("models", [])[:3]],
    }


def batch_attributes(items: list[Any], attributes: list[dict[str, Any]],
                     official: dict[str, Any], commons: dict[str, Any], *,
                     domain: str | None = None, candidates: int = 3) -> list[dict[str, Any]]:
    """Modo «lista completa»: para cada atributo propuesto devuelve la coincidencia exacta
    (si existe) y los candidatos más parecidos del repositorio.

    Cada elemento puede ser un texto (``"soil temperature"`` o ``"soilTemperature"``) o un
    objeto ``{"name": "soilTemperature", "terms": "soil temperature"}``.
    """
    groups = group_attributes(attributes)
    commons_map = _commons_by_property(commons)
    allowed = _subject_filter(None, domain, _domains_by_subject(official))
    local = group_attributes(attributes, allowed_subjects=allowed) if allowed is not None else None
    by_lower: dict[str, list[str]] = defaultdict(list)
    for name in groups:
        by_lower[name.lower()].append(name)
    desc_cache: dict[str, set[str]] = {}
    out = []
    for item in items:
        if isinstance(item, dict):
            name, terms_text = item.get("name"), item.get("terms") or item.get("name") or ""
        else:
            text = str(item).strip()
            name = text if re.fullmatch(r"[a-z][A-Za-z0-9]*", text) else None
            terms_text = text
        exact = []
        if name:
            for variant in sorted(by_lower.get(name.lower(), []), key=lambda n: n != name):
                exact.append(_brief(summarize_attribute(variant, groups[variant], commons_map)))
            if not exact and name in commons_map:
                exact.append({"property": name, "occurrences": 0, "in_commons": commons_map[name]})
        ranked = rank_attributes(_query_terms([terms_text]), local or groups, commons_map,
                                 limit=candidates + len(exact), desc_cache=desc_cache)
        exact_names = {e["property"] for e in exact}
        similar = [_brief(r) for r in ranked if r["property"] not in exact_names][:candidates]
        out.append({"input": item, "exact": exact, "similar": similar})
    return out


# --------------------------------------------------------------------------- CLI

def _index_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    return {"offline": args.offline, "max_age_days": args.max_age_days}


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--offline", action="store_true", help="Usa solo la caché local.")
    common.add_argument("--max-age-days", type=float, default=sdm_index.DEFAULT_MAX_AGE_DAYS)
    common.add_argument("--domain", help="Filtra por dominio (p. ej. SmartWater).")
    common.add_argument("--limit", type=int, default=15)

    parser = argparse.ArgumentParser(description="Búsqueda en los índices de Smart Data Models.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_sub = sub.add_parser("subjects", parents=[common], help="Lista o busca subjects.")
    p_sub.add_argument("query", nargs="*")
    p_mod = sub.add_parser("models", parents=[common], help="Busca modelos.")
    p_mod.add_argument("query", nargs="+")
    p_mod.add_argument("--subject")
    p_att = sub.add_parser("attributes", parents=[common], help="Busca atributos.")
    p_att.add_argument("query", nargs="*")
    p_att.add_argument("--exact", help="Nombre exacto del atributo (camelCase).")
    p_att.add_argument("--subject")
    p_att.add_argument("--include-subproperties", action="store_true")
    p_bat = sub.add_parser("batch", parents=[common],
                           help="Modo lista completa: busca muchos atributos de una vez.")
    p_bat.add_argument("file", help="JSON con una lista de textos u objetos {name, terms}, "
                                    "o '-' para leerlo de la entrada estándar.")
    p_bat.add_argument("--candidates", type=int, default=3)
    p_uni = sub.add_parser("units", help="Busca códigos de unidad UN/CEFACT (Rec. 20).")
    p_uni.add_argument("query", nargs="*", help="Nombre o símbolo en inglés (p. ej. 'litre per second').")
    p_uni.add_argument("--code", help="Comprueba un código concreto (p. ej. CEL).")
    p_uni.add_argument("--include-inactive", action="store_true",
                       help="Incluye códigos obsoletos o eliminados.")
    p_uni.add_argument("--limit", type=int, default=15)
    args = parser.parse_args(argv)

    if args.command == "units":
        if args.code:
            status, message = uncefact.check_code(args.code)
            results = [r for r in [uncefact.lookup(args.code)] if r]
            sdm_index.emit({"command": "units", "code": args.code, "status": status,
                            "message": message, "results": results})
        else:
            results = uncefact.search(args.query, limit=args.limit,
                                      include_inactive=args.include_inactive)
            sdm_index.emit({"command": "units", "query": args.query, "count": len(results),
                            "results": results})
        return 0

    if args.command == "attributes" and not args.query and not args.exact:
        parser.error("attributes necesita términos de búsqueda o --exact")

    kw = _index_kwargs(args)
    warnings: list[str] = []
    try:
        official, st = sdm_index.load_index("official_list", **kw)
        statuses = [st]
        if args.command == "subjects":
            results = search_subjects(official, domain=args.domain, query=args.query)[:args.limit]
        elif args.command == "models":
            metadata, st = sdm_index.load_index("models_metadata", **kw)
            statuses.append(st)
            results = search_models(args.query, official, metadata, domain=args.domain,
                                    subject=args.subject, limit=args.limit)
        elif args.command == "batch":
            raw = sys.stdin.read() if args.file == "-" else \
                Path(args.file).read_text(encoding="utf-8")
            items = json.loads(raw)
            if not isinstance(items, list):
                parser.error("batch espera una lista JSON")
            attributes, st = sdm_index.load_index("attributes", **kw)
            statuses.append(st)
            commons, st = sdm_index.load_index("commons", **kw)
            statuses.append(st)
            results = batch_attributes(items, attributes, official, commons,
                                       domain=args.domain, candidates=args.candidates)
        else:
            attributes, st = sdm_index.load_index("attributes", **kw)
            statuses.append(st)
            commons, st = sdm_index.load_index("commons", **kw)
            statuses.append(st)
            results = search_attributes(args.query, attributes, official, commons,
                                        exact=args.exact, domain=args.domain,
                                        subject=args.subject,
                                        include_subproperties=args.include_subproperties,
                                        limit=args.limit)
    except sdm_index.IndexUnavailable as exc:
        sdm_index.emit({"error": str(exc)})
        return 2
    warnings = [s["warning"] for s in statuses if s.get("warning")]
    sdm_index.emit({
        "command": args.command,
        "query": getattr(args, "query", None),
        "warnings": warnings,
        "indexes": {s["name"]: s.get("fetched_at") for s in statuses},
        "count": len(results),
        "results": results,
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
