#!/usr/bin/env python3
"""Prueba opcional de la propuesta contra un context broker NGSI-LD (Orion-LD, Stellio...).

Solo se ejecuta si el usuario lo pide e indica la URL de su broker. Pasos:

1. ``health``: el broker responde a la API NGSI-LD.
2. ``create``: crea cada ejemplo normalizado NGSI-LD de la propuesta (entidades nuevas
   y extensiones).
3. ``read``: lee cada entidad y compara atributos, tipos NGSI, valores, ``unitCode``,
   ``observedAt`` y objetos de las Relationship con lo enviado.
4. ``query``: consulta por tipo y comprueba que aparece cada entidad.
5. ``delete``: borra todo lo creado (siempre, aunque falle un paso) y comprueba que ya no
   existe. No deja residuos.

Para no chocar con datos existentes, los ids se renombran con un sufijo único
(``…:sdmtest-<run>``) y las Relationship entre entidades de la propuesta se reescriben
igual. Modos de ``@context`` (``--context-mode``):

* ``inline``: el contexto de la previsualización (``preview.py``) va incrustado en cada
  entidad. Funciona con un subject nuevo aún no publicado. Orion-LD lo admite; Stellio
  2.37.0 no (responde 500).
* ``served``: el script sirve ese mismo contexto en un servidor HTTP local y temporal
  (``application/ld+json``) y las entidades lo referencian por URL. El broker debe poder
  alcanzar ``--serve-host`` (por defecto ``host.docker.internal``, válido para un broker en
  Docker Desktop; con un broker nativo, ``127.0.0.1``; en Docker sobre Linux, la IP del
  host y ``--serve-bind 0.0.0.0``).
* ``published``: el contexto publicado del subject, por la URL de GitHub Pages
  (``smart-data-models.github.io``), que lo sirve como ``application/ld+json``; la URL
  ``raw.githubusercontent.com`` de los ejemplos lo sirve como ``text/plain`` y los
  procesadores JSON-LD estrictos (Stellio) la rechazan. No se envían entidades de un
  subject cuyo contexto no está publicado.
* ``auto`` (por defecto): ``inline`` con Orion-LD y ``served`` con el resto.

Uso::

    python broker_test.py <workdir> --spec proposal.yaml --broker http://localhost:1026
                          [--tenant t] [--context-mode auto|inline|served|published]
                          [--serve-host host.docker.internal] [--serve-bind 127.0.0.1]

Escribe ``<workdir>/broker-result.json``, que ``package.py`` incluye en el informe.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import json
import math
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
import yaml

import fetch_schema
import preview
import proposal as proposal_mod
import sdm_index

API = "/ngsi-ld/v1"
LD_JSON = "application/ld+json"
RESULT_FILE = "broker-result.json"
DEFAULT_CONTEXT = "https://uri.etsi.org/ngsi-ld/default-context/"
HEALTH_TYPE = "https://smartdatamodels.org/sdm-ngsild-generator/HealthCheck"


class BrokerError(RuntimeError):
    pass


# --------------------------------------------------------------------------- utilidades

def _step(name: str, ok: bool, detail: str, **extra: Any) -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail, **extra}


def _norm(value: Any) -> Any:
    """Normaliza un valor para comparar lo enviado con lo devuelto por el broker.

    JSON-LD puede compactar listas de un elemento a escalar y representar DateTime como
    ``{"@type": "DateTime", "@value": ...}`` o como texto; ambos casos se igualan.
    """
    if isinstance(value, dict):
        if "@value" in value and set(value) <= {"@type", "type", "@value"}:
            return _norm(value["@value"])
        return {k: _norm(v) for k, v in value.items()}
    if isinstance(value, list):
        items = [_norm(v) for v in value]
        return items[0] if len(items) == 1 else items
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def same(a: Any, b: Any) -> bool:
    """Igualdad profunda con tolerancia en los números (los brokers con PostGIS redondean
    las coordenadas a 8 decimales)."""
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-7)
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


def _norm_time(value: Any) -> str:
    """``2026-05-12T09:15:00Z`` y ``2026-05-12T09:15:00.000Z`` son el mismo instante."""
    text = str(_norm(value))
    if text.endswith("Z") and "." in text:
        head, frac = text[:-1].split(".", 1)
        frac = frac.rstrip("0")
        text = f"{head}.{frac}Z" if frac else f"{head}Z"
    return text


def _type_of(attr: Any) -> str | None:
    if isinstance(attr, dict):
        t = attr.get("type") or attr.get("@type")
        return t[0] if isinstance(t, list) else t
    return None


class TermMap:
    """Traduce nombres cortos a la forma con que los devuelve el broker sin ``Link``.

    Sin cabecera ``Link`` el broker compacta con el core context: los términos del core
    vuelven como nombre corto y el resto como IRI completo. Un término que no está en el
    contexto usado se expande al contexto por defecto de NGSI-LD.
    """

    def __init__(self, context: dict[str, Any], core: dict[str, Any]) -> None:
        self.context, self.core = context, core
        self.prefixes = {k: v for k, v in core.items()
                         if isinstance(v, str) and v.startswith("http") and v.endswith(("/", "#"))}
        self.reverse: dict[str, str] = {}
        for source in (context, core):  # el core, al final: tiene prioridad
            for term, value in source.items():
                iri = value.get("@id") if isinstance(value, dict) else value
                if isinstance(iri, str) and iri.startswith("http"):
                    self.reverse[iri] = term

    @staticmethod
    def _iri_of(value: Any) -> str | None:
        iri = value.get("@id") if isinstance(value, dict) else value
        return iri if isinstance(iri, str) and iri.startswith("http") else None

    def iri(self, term: str) -> str:
        """IRI con que el broker expande ``term``.

        Los términos del core context de ETSI no se pueden redefinir (NGSI-LD): el core
        tiene prioridad sobre el contexto del subject.
        """
        return (self._iri_of(self.core.get(term)) or self._iri_of(self.context.get(term))
                or DEFAULT_CONTEXT + term)

    def candidates(self, term: str) -> list[str]:
        """Formas en que el broker puede devolver ``term``: corta, IRI o CURIE.

        Se aceptan el IRI del core y el del contexto del subject porque cada broker usa
        su propia versión del core context (Orion-LD 1.12: v1.6, sin ``name``; Stellio:
        una posterior que sí lo define).
        """
        iris = [i for i in (self._iri_of(self.core.get(term)), self._iri_of(self.context.get(term)),
                            DEFAULT_CONTEXT + term) if i]
        out = [term]
        for iri in iris:
            out.append(iri)
            for prefix, base in self.prefixes.items():
                if iri.startswith(base):
                    out.append(f"{prefix}:{iri[len(base):]}")
        return list(dict.fromkeys(out))

    def shorten(self, key: str) -> str:
        """Convierte una clave devuelta (IRI o CURIE) en el nombre corto."""
        if ":" in key and not key.startswith("http"):
            prefix, rest = key.split(":", 1)
            if prefix in self.prefixes:
                key = self.prefixes[prefix] + rest
        if key in self.reverse:
            return self.reverse[key]
        if key.startswith(DEFAULT_CONTEXT):
            return key[len(DEFAULT_CONTEXT):]
        return key.rsplit("/", 1)[-1] if key.startswith("http") else key

    def shorten_keys(self, value: Any) -> Any:
        """Aplica ``shorten`` a las claves de los objetos anidados de un valor."""
        if isinstance(value, dict):
            return {self.shorten(k): self.shorten_keys(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.shorten_keys(v) for v in value]
        return value

    def find(self, entity: dict[str, Any], term: str) -> Any:
        for key in self.candidates(term):
            if key in entity:
                return entity[key]
        return None


# --------------------------------------------------------------------------- cliente

class BrokerClient:
    def __init__(self, url: str, *, tenant: str | None = None, timeout: float = 20,
                 session: requests.Session | None = None) -> None:
        self.base = url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.headers: dict[str, str] = {"User-Agent": sdm_index.USER_AGENT}
        if tenant:
            self.headers["NGSILD-Tenant"] = tenant

    def request(self, method: str, path: str, **kw: Any) -> requests.Response:
        headers = {**self.headers, **kw.pop("headers", {})}
        return self.session.request(method, self.base + path, headers=headers,
                                    timeout=self.timeout, **kw)

    def product(self) -> str | None:
        try:
            resp = self.request("GET", "/version")
            if resp.ok:
                data = resp.json()
                if "orionld version" in data or "orionld" in json.dumps(data).lower():
                    return f"Orion-LD {data.get('orionld version', '')}".strip()
        except (requests.RequestException, ValueError):
            pass
        try:
            resp = self.request("GET", "/actuator/info")
            if resp.ok and "stellio" in resp.text.lower():
                return "Stellio"
        except requests.RequestException:
            pass
        return None


# --------------------------------------------------------------------------- contextos

def pages_context_url(subject: str) -> str:
    """URL del contexto en GitHub Pages (servido como application/ld+json)."""
    return f"{sdm_index.PAGES_BASE}/{subject}/context.jsonld"


class ContextServer:
    """Servidor HTTP local y temporal que sirve los ``@context`` de la previsualización."""

    def __init__(self, contexts: dict[str, dict[str, Any]], *, host: str, bind: str) -> None:
        bodies = {f"/{subject}/context.jsonld": json.dumps({"@context": ctx}).encode("utf-8")
                  for subject, ctx in contexts.items()}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - nombre fijado por http.server
                body = bodies.get(self.path.split("?", 1)[0])
                if body is None:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/ld+json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: Any) -> None:
                pass

        self.httpd = ThreadingHTTPServer((bind, 0), Handler)
        self.base = f"http://{host}:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def url(self, subject: str) -> str:
        return f"{self.base}/{subject}/context.jsonld"

    def __enter__(self) -> "ContextServer":
        self.thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


# --------------------------------------------------------------------------- preparación

def _load_core(offline: bool) -> dict[str, Any]:
    try:
        doc = fetch_schema.fetch_document(preview.CORE_CONTEXT_URL, offline=offline)
        ctx = doc.get("@context", {})
        return ctx if isinstance(ctx, dict) else {}
    except (sdm_index.IndexUnavailable, json.JSONDecodeError, LookupError):
        return {}


def prepare_entities(data: dict[str, Any], *, run_id: str, context_mode: str, offline: bool,
                     served: ContextServer | None = None
                     ) -> tuple[list[dict[str, Any]], dict[str, TermMap], list[str]]:
    """Devuelve las entidades a enviar (ids renombrados), un ``TermMap`` por subject y avisos."""
    warnings: list[str] = []
    core = _load_core(offline)
    if not core:
        warnings.append("No se pudo obtener el core context de ETSI; la comparación de "
                        "nombres usará solo los IRIs del contexto del subject")
    by_subject: dict[str, list[proposal_mod.Item]] = {}
    for item in data["items"]:
        by_subject.setdefault(item.subject, []).append(item)
    contexts: dict[str, dict[str, Any]] = {}
    unpublished: set[str] = set()
    for subject, items in by_subject.items():
        is_new = data["new_subject"] and subject == data["subject"]
        ctx, new_terms, warns = preview.build_context(subject, items, new_subject=is_new,
                                                      offline=offline)
        warnings += warns
        if context_mode in ("inline", "served"):
            contexts[subject] = ctx["@context"]
            continue
        url = f"{sdm_index.RAW_BASE}/{subject}/{sdm_index.DEFAULT_BRANCH}/context.jsonld"
        published = preview._load_context(url, offline=offline)
        if published is None:
            # No se envía: un @context inexistente puede tumbar el broker (Orion-LD 1.12.0
            # termina con segfault al recibir un POST cuyo @context da 404).
            unpublished.add(subject)
            warnings.append(f"El @context publicado de {subject} no existe (¿subject nuevo?): "
                            "sus entidades no se envían en modo 'published'; usa 'inline' o "
                            "'served'")
            published = {}
        contexts[subject] = published
        pending = [t for t in new_terms if t not in published and t != "ngsi-ld"]
        if pending:
            warnings.append(f"{subject}: {len(pending)} términos aún no están en el @context "
                            f"publicado y el broker los expande al contexto por defecto de "
                            f"NGSI-LD hasta que SDM regenere el contexto: {', '.join(pending)}")

    rename: dict[str, str] = {}
    for item in data["items"]:
        doc = item.examples.get("example-normalized.jsonld")
        if isinstance(doc, dict) and isinstance(doc.get("id"), str):
            rename[doc["id"]] = f"{doc['id']}-sdmtest-{run_id}"

    def rewrite(obj: Any) -> Any:
        if isinstance(obj, str):
            return rename.get(obj, obj)
        if isinstance(obj, list):
            return [rewrite(o) for o in obj]
        return obj

    entities = []
    for item in data["items"]:
        doc = copy.deepcopy(item.examples.get("example-normalized.jsonld"))
        if not isinstance(doc, dict):
            warnings.append(f"{item.name}: falta example-normalized.jsonld")
            continue
        doc["id"] = rename[doc["id"]]
        for key, attr in doc.items():
            if isinstance(attr, dict) and attr.get("type") == "Relationship":
                attr["object"] = rewrite(attr.get("object"))
        if context_mode == "inline":
            doc["@context"] = [contexts[item.subject], preview.CORE_CONTEXT_URL]
        elif context_mode == "served" and served is not None:
            doc["@context"] = [served.url(item.subject), preview.CORE_CONTEXT_URL]
        elif context_mode == "published":
            raw = f"{sdm_index.RAW_BASE}/{item.subject}/{sdm_index.DEFAULT_BRANCH}/context.jsonld"
            ctx_list = doc.get("@context") or []
            ctx_list = ctx_list if isinstance(ctx_list, list) else [ctx_list]
            doc["@context"] = [pages_context_url(item.subject) if c == raw else c
                               for c in ctx_list] or [pages_context_url(item.subject)]
        entities.append({"item": item, "payload": doc, "subject": item.subject,
                         "skip": item.subject in unpublished})
    term_maps = {s: TermMap(c, core) for s, c in contexts.items()}
    return entities, term_maps, warnings


# --------------------------------------------------------------------------- comparación

def compare(sent: dict[str, Any], got: dict[str, Any], terms: TermMap) -> list[str]:
    """Diferencias entre la entidad enviada y la devuelta por el broker."""
    problems = []
    if got.get("id") != sent["id"]:
        problems.append(f"id devuelto {got.get('id')!r}")
    sent_type = sent.get("type")
    got_type = got.get("type")
    if got_type not in terms.candidates(sent_type) and _norm(got_type) not in terms.candidates(sent_type):
        problems.append(f"type devuelto {got_type!r}")
    for name, attr in sent.items():
        if name in ("id", "type", "@context") or not isinstance(attr, dict):
            continue
        back = terms.find(got, name)
        if back is None:
            problems.append(f"'{name}' no aparece en la respuesta")
            continue
        if _type_of(back) != attr.get("type"):
            problems.append(f"'{name}': tipo {_type_of(back)!r} en lugar de {attr.get('type')!r}")
            continue
        field = "object" if attr.get("type") == "Relationship" else "value"
        sent_value = _norm(attr.get(field))
        got_value = _norm(terms.shorten_keys(back.get(field)))
        if isinstance(sent_value, str) and isinstance(got_value, str) and sent_value != got_value \
                and sent_value[:4].isdigit() and "T" in sent_value:
            sent_value, got_value = _norm_time(sent_value), _norm_time(got_value)
        if not same(sent_value, got_value):
            problems.append(f"'{name}': valor {got_value!r} en lugar de {sent_value!r}")
        if "unitCode" in attr and _norm(back.get("unitCode")) != attr["unitCode"]:
            problems.append(f"'{name}': unitCode {back.get('unitCode')!r}")
        if "observedAt" in attr and _norm_time(back.get("observedAt")) != _norm_time(attr["observedAt"]):
            problems.append(f"'{name}': observedAt {back.get('observedAt')!r}")
    return problems


# --------------------------------------------------------------------------- ejecución

def _preview_contexts(data: dict[str, Any], *, offline: bool) -> dict[str, dict[str, Any]]:
    by_subject: dict[str, list[proposal_mod.Item]] = {}
    for item in data["items"]:
        by_subject.setdefault(item.subject, []).append(item)
    out = {}
    for subject, items in by_subject.items():
        is_new = data["new_subject"] and subject == data["subject"]
        ctx, _, _ = preview.build_context(subject, items, new_subject=is_new, offline=offline)
        out[subject] = ctx["@context"]
    return out


def run(workdir: Path, spec: dict[str, Any], broker: str, *, tenant: str | None = None,
        context_mode: str = "auto", offline: bool = False, timeout: float = 20,
        session: requests.Session | None = None, run_id: str | None = None,
        serve_host: str = "host.docker.internal", serve_bind: str = "127.0.0.1") -> dict[str, Any]:
    client = BrokerClient(broker, tenant=tenant, timeout=timeout, session=session)
    run_id = run_id or uuid.uuid4().hex[:8]
    result: dict[str, Any] = {"broker": broker, "tenant": tenant, "context_mode": context_mode,
                              "run_id": run_id, "product": None, "steps": [], "warnings": []}
    steps = result["steps"]

    # Consulta estándar con un tipo que no existe: la soportan todos los brokers.
    # (GET /types se cuelga en un Orion-LD 1.12.0 vacío, por eso no se usa.)
    try:
        resp = client.request("GET", f"{API}/entities",
                              params={"type": HEALTH_TYPE, "limit": 1},
                              headers={"Accept": "application/json"})
        ok = resp.status_code == 200
        steps.append(_step("health", ok, f"GET /ngsi-ld/v1/entities?type=… → {resp.status_code}"))
    except requests.RequestException as exc:
        steps.append(_step("health", False, f"El broker no responde: {exc.__class__.__name__}"))
        result["status"] = "fail"
        return result
    if not ok:
        result["status"] = "fail"
        return result
    result["product"] = client.product()
    if context_mode == "auto":
        context_mode = "inline" if (result["product"] or "").startswith("Orion-LD") else "served"
        result["context_mode"] = context_mode

    data = proposal_mod.load_proposal(workdir, spec, offline=offline)
    server_cm: Any = contextlib.nullcontext()
    server = None
    if context_mode == "served":
        server = ContextServer(_preview_contexts(data, offline=offline), host=serve_host,
                               bind=serve_bind)
        server_cm = server
        result["served_contexts"] = server.base
    with server_cm:
        _run_steps(client, data, result, run_id=run_id, context_mode=context_mode,
                   offline=offline, server=server)
    result["status"] = "pass" if all(s["ok"] for s in result["steps"]) else "fail"
    return result


def _run_steps(client: BrokerClient, data: dict[str, Any], result: dict[str, Any], *,
               run_id: str, context_mode: str, offline: bool,
               server: ContextServer | None) -> None:
    steps = result["steps"]
    entities, term_maps, warnings = prepare_entities(data, run_id=run_id,
                                                     context_mode=context_mode, offline=offline,
                                                     served=server)
    result["warnings"] += warnings
    created: list[dict[str, Any]] = []
    try:
        # create
        failures = []
        for ent in entities:
            payload = ent["payload"]
            if ent.get("skip"):
                failures.append(f"{ent['item'].name}: no enviada (@context del subject no "
                                "publicado; usa --context-mode inline o served)")
                continue
            if context_mode == "published" and "@context" not in payload:
                failures.append(f"{payload['id']}: el ejemplo no tiene @context")
                continue
            try:
                resp = client.request("POST", f"{API}/entities",
                                      headers={"Content-Type": LD_JSON}, data=json.dumps(payload))
            except requests.RequestException as exc:
                failures.append(f"{ent['item'].name}: el broker no respondió "
                                f"({exc.__class__.__name__})")
                continue
            if resp.status_code == 201:
                created.append(ent)
            else:
                failures.append(f"{ent['item'].name}: {resp.status_code} {resp.text[:300]}")
        steps.append(_step("create", not failures,
                           f"{len(created)}/{len(entities)} entidades creadas" +
                           (f". {'; '.join(failures)}" if failures else "")))

        # read
        read_problems = []
        for ent in created:
            payload = ent["payload"]
            try:
                resp = client.request("GET", f"{API}/entities/{quote(payload['id'], safe='')}",
                                      headers={"Accept": "application/json"})
            except requests.RequestException as exc:
                read_problems.append(f"{ent['item'].name}: {exc.__class__.__name__}")
                continue
            if resp.status_code != 200:
                read_problems.append(f"{ent['item'].name}: GET → {resp.status_code}")
                continue
            for problem in compare(payload, resp.json(), term_maps[ent["subject"]]):
                read_problems.append(f"{ent['item'].name}: {problem}")
        if not created:
            read_detail = "Sin entidades creadas: nada que leer"
        elif read_problems:
            read_detail = f"{len(created)} entidades leídas. {'; '.join(read_problems[:20])}"
        else:
            read_detail = (f"{len(created)} entidades leídas y comparadas: atributos, tipos NGSI, "
                           "valores, unitCode y observedAt coinciden")
        steps.append(_step("read", bool(created) and not read_problems, read_detail))

        # query
        missing = []
        for ent in created:
            payload = ent["payload"]
            type_iri = term_maps[ent["subject"]].iri(payload["type"])
            try:
                resp = client.request("GET", f"{API}/entities",
                                      params={"type": type_iri, "limit": 100},
                                      headers={"Accept": "application/json"})
                code = resp.status_code
                ids = [e.get("id") for e in resp.json()] if code == 200 else []
            except (requests.RequestException, ValueError) as exc:
                code, ids = exc.__class__.__name__, []
            if payload["id"] not in ids:
                missing.append(f"{ent['item'].name} ({code})")
        steps.append(_step("query", bool(created) and not missing,
                           "Sin entidades creadas: nada que consultar" if not created else
                           "Consulta por tipo: todas las entidades aparecen" if not missing
                           else f"No aparecen al consultar por tipo: {', '.join(missing)}"))
    finally:
        # delete (siempre)
        leftovers = []
        for ent in created:
            path = f"{API}/entities/{quote(ent['payload']['id'], safe='')}"
            try:
                client.request("DELETE", path)
                if client.request("GET", path).status_code != 404:
                    leftovers.append(ent["payload"]["id"])
            except requests.RequestException:
                leftovers.append(ent["payload"]["id"])
        steps.append(_step("delete", not leftovers,
                           f"{len(created)} entidades borradas; sin residuos" if not leftovers
                           else f"Quedan entidades en el broker: {', '.join(leftovers)}"))
    result["entities"] = [e["payload"]["id"] for e in entities]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prueba la propuesta contra un broker NGSI-LD.")
    parser.add_argument("workdir", type=Path)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--broker", required=True, help="URL base del broker (http://host:puerto).")
    parser.add_argument("--tenant", help="Tenant NGSI-LD (cabecera NGSILD-Tenant).")
    parser.add_argument("--context-mode", choices=("auto", "inline", "served", "published"),
                        default="auto")
    parser.add_argument("--serve-host", default="host.docker.internal",
                        help="Nombre con el que el broker alcanza este equipo (modo served).")
    parser.add_argument("--serve-bind", default="127.0.0.1",
                        help="Interfaz local del servidor de contextos (modo served).")
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--offline", action="store_true",
                        help="Contextos y schemas solo desde la caché (el broker sí se usa).")
    args = parser.parse_args(argv)
    spec = yaml.safe_load(args.spec.read_text(encoding="utf-8"))
    result = run(args.workdir, spec, args.broker, tenant=args.tenant,
                 context_mode=args.context_mode, offline=args.offline, timeout=args.timeout,
                 serve_host=args.serve_host, serve_bind=args.serve_bind)
    (args.workdir / RESULT_FILE).write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                            encoding="utf-8")
    result["result_file"] = str(args.workdir / RESULT_FILE)
    sdm_index.emit(result)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
