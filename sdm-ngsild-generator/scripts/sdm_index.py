#!/usr/bin/env python3
"""Descarga y caché local de los índices que publica Smart Data Models en GitHub.

Índices utilizados (todos en la organización ``smart-data-models``):

* ``official_list``: ``data-models/specs/AllSubjects/official_list_data_models.json``.
  Lista oficial de subjects, sus modelos y sus dominios.
* ``models_metadata``: ``data-models/pysmartdatamodels/pysmartdatamodels/model-assets/
  datamodels_metadata.json``. Título, descripción, versión y URLs de cada modelo.
* ``attributes``: ``.../model-assets/smartdatamodels.json.gz``. Inventario de todos los
  atributos (y subatributos) de todos los modelos.
* ``commons``: ``data-models/common-schema.json``. Definiciones de los Commons
  (GSMA-Commons, Location-Commons...).

Uso desde la línea de órdenes::

    python sdm_index.py status
    python sdm_index.py update [--force]

La salida es JSON para que Claude la interprete.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests

APP_NAME = "sdm-ngsild-generator"
USER_AGENT = f"{APP_NAME} (Claude Code skill)"
GITHUB_ORG = "smart-data-models"
RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_ORG}"
PAGES_BASE = f"https://{GITHUB_ORG}.github.io"
DEFAULT_BRANCH = "master"
DEFAULT_MAX_AGE_DAYS = 7
HTTP_TIMEOUT = 60

_ASSETS = f"{RAW_BASE}/data-models/{DEFAULT_BRANCH}/pysmartdatamodels/pysmartdatamodels/model-assets"


class IndexUnavailable(RuntimeError):
    """Error al obtener un índice sin red ni caché disponible."""


@dataclass(frozen=True)
class IndexSource:
    name: str
    url: str
    filename: str
    loader: Callable[[Path], Any]


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _load_json_gz(path: Path) -> Any:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


INDEX_SOURCES: dict[str, IndexSource] = {
    "official_list": IndexSource(
        "official_list",
        f"{RAW_BASE}/data-models/{DEFAULT_BRANCH}/specs/AllSubjects/official_list_data_models.json",
        "official_list_data_models.json",
        _load_json,
    ),
    "models_metadata": IndexSource(
        "models_metadata",
        f"{_ASSETS}/datamodels_metadata.json",
        "datamodels_metadata.json",
        _load_json,
    ),
    "attributes": IndexSource(
        "attributes",
        f"{_ASSETS}/smartdatamodels.json.gz",
        "smartdatamodels.json.gz",
        _load_json_gz,
    ),
    "commons": IndexSource(
        "commons",
        f"{RAW_BASE}/data-models/{DEFAULT_BRANCH}/common-schema.json",
        "common-schema.json",
        _load_json,
    ),
}


# --------------------------------------------------------------------------- caché

def cache_dir() -> Path:
    """Directorio de caché del usuario, multiplataforma.

    Prioridad: variable ``SDM_CACHE_DIR``; en Windows ``%LOCALAPPDATA%``; en macOS
    ``~/Library/Caches``; en el resto ``$XDG_CACHE_HOME`` o ``~/.cache``.
    """
    override = os.environ.get("SDM_CACHE_DIR")
    if override:
        base = Path(override).expanduser()
    elif sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / APP_NAME
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches" / APP_NAME
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def _meta_path() -> Path:
    return cache_dir() / "cache_meta.json"


def _read_meta() -> dict[str, Any]:
    path = _meta_path()
    if not path.exists():
        return {}
    try:
        return _load_json(path)
    except (OSError, json.JSONDecodeError):
        return {}


def _write_meta(meta: dict[str, Any]) -> None:
    tmp = _meta_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    tmp.replace(_meta_path())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _age_days(fetched_at: str | None) -> float | None:
    if not fetched_at:
        return None
    try:
        then = datetime.fromisoformat(fetched_at)
    except ValueError:
        return None
    return round((_now() - then).total_seconds() / 86400, 2)


# --------------------------------------------------------------------------- red

def http_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return session


def download(url: str, dest: Path, session: requests.Session | None = None) -> None:
    """Descarga ``url`` en ``dest`` de forma atómica (fichero temporal + rename)."""
    session = session or http_session()
    resp = session.get(url, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    tmp.write_bytes(resp.content)
    tmp.replace(dest)


def pages_to_raw(url: str, branch: str = DEFAULT_BRANCH) -> str:
    """Convierte una URL de GitHub Pages de SDM en su equivalente en raw.githubusercontent.

    ``https://smart-data-models.github.io/dataModel.X/a/b.json`` →
    ``https://raw.githubusercontent.com/smart-data-models/dataModel.X/master/a/b.json``.
    Las URLs que no son de GitHub Pages de SDM se devuelven sin cambios.
    """
    prefix = PAGES_BASE + "/"
    if not url.startswith(prefix):
        return url
    rest = url[len(prefix):]
    repo, _, path = rest.partition("/")
    return f"{RAW_BASE}/{repo}/{branch}/{path}"


# --------------------------------------------------------------------------- índices

def ensure_index(
    name: str,
    *,
    max_age_days: float = DEFAULT_MAX_AGE_DAYS,
    force: bool = False,
    offline: bool = False,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Garantiza que el índice ``name`` está en caché y devuelve su estado.

    Si la caché está vigente no descarga nada. Si la descarga falla pero existe una
    copia previa, se usa esa copia y el estado incluye un aviso con su antigüedad.
    """
    source = INDEX_SOURCES[name]
    path = cache_dir() / source.filename
    meta = _read_meta()
    entry = meta.get(name, {})
    age = _age_days(entry.get("fetched_at")) if path.exists() else None
    fresh = age is not None and age <= max_age_days
    status: dict[str, Any] = {"name": name, "url": source.url, "path": str(path)}

    if offline or (fresh and not force):
        if not path.exists():
            raise IndexUnavailable(f"Índice '{name}' no disponible en caché y modo sin conexión.")
        status.update(fetched_at=entry.get("fetched_at"), age_days=age, source="cache",
                      stale=not fresh)
        if not fresh:
            status["warning"] = f"Caché de '{name}' con {age} días de antigüedad."
        return status

    try:
        download(source.url, path, session)
    except requests.RequestException as exc:
        if path.exists():
            status.update(fetched_at=entry.get("fetched_at"), age_days=age, source="cache",
                          stale=True,
                          warning=(f"GitHub no responde ({exc.__class__.__name__}); se usa la "
                                   f"caché de '{name}' con {age} días de antigüedad."))
            return status
        raise IndexUnavailable(f"No se pudo descargar '{name}' y no hay caché: {exc}") from exc

    fetched_at = _now().isoformat(timespec="seconds")
    meta[name] = {"fetched_at": fetched_at, "url": source.url}
    _write_meta(meta)
    status.update(fetched_at=fetched_at, age_days=0.0, source="download", stale=False)
    return status


_LOADED: dict[str, Any] = {}


def load_index(name: str, **kwargs: Any) -> tuple[Any, dict[str, Any]]:
    """Devuelve ``(datos, estado)`` del índice, descargándolo si hace falta."""
    status = ensure_index(name, **kwargs)
    if name not in _LOADED or status["source"] == "download":
        _LOADED[name] = INDEX_SOURCES[name].loader(Path(status["path"]))
    return _LOADED[name], status


def cache_status() -> list[dict[str, Any]]:
    meta = _read_meta()
    result = []
    for name, source in INDEX_SOURCES.items():
        path = cache_dir() / source.filename
        entry = meta.get(name, {})
        result.append({
            "name": name,
            "cached": path.exists(),
            "fetched_at": entry.get("fetched_at"),
            "age_days": _age_days(entry.get("fetched_at")) if path.exists() else None,
            "size_bytes": path.stat().st_size if path.exists() else None,
            "url": source.url,
        })
    return result


def emit(data: Any) -> None:
    """Escribe ``data`` como JSON en la salida estándar (UTF-8 en cualquier SO)."""
    text = json.dumps(data, ensure_ascii=False, indent=2)
    sys.stdout.buffer.write(text.encode("utf-8") + b"\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Caché de índices de Smart Data Models.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="Muestra el estado de la caché.")
    upd = sub.add_parser("update", help="Descarga los índices caducados o ausentes.")
    upd.add_argument("--force", action="store_true", help="Descarga aunque la caché esté vigente.")
    upd.add_argument("--max-age-days", type=float, default=DEFAULT_MAX_AGE_DAYS)
    args = parser.parse_args(argv)

    if args.command == "status":
        emit({"cache_dir": str(cache_dir()), "indexes": cache_status()})
        return 0

    session = http_session()
    results, errors = [], []
    for name in INDEX_SOURCES:
        try:
            results.append(ensure_index(name, force=args.force,
                                        max_age_days=args.max_age_days, session=session))
        except IndexUnavailable as exc:
            errors.append({"name": name, "error": str(exc)})
    emit({"cache_dir": str(cache_dir()), "indexes": results, "errors": errors})
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
