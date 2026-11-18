"""Códigos de unidad UN/CEFACT (Recomendación 20 de UNECE).

Los datos están en ``data/uncefact_units.json`` (generado con ``tools/build_units.py``
a partir de https://github.com/datasets/unece-units-of-measure, licencia ODC-PDDL 1.0).

Estados: ``active`` (vigente), ``deprecated`` (obsoleto, evitar), ``deleted``
(eliminado, no usar) y ``changed`` (modificado en la última revisión).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_FILE = Path(__file__).resolve().parent / "data" / "uncefact_units.json"


@lru_cache(maxsize=1)
def load_units() -> dict[str, dict[str, str]]:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))["units"]


def lookup(code: str) -> dict[str, str] | None:
    """Datos del código (``name``, ``symbol``, ``status``) o ``None`` si no existe."""
    unit = load_units().get(code)
    return {"code": code, **unit} if unit else None


def check_code(code: str) -> tuple[str, str]:
    """Clasifica un código: ``("ok"|"warn"|"error", mensaje)``."""
    unit = lookup(code)
    if unit is None:
        return "error", f"'{code}' no es un código UN/CEFACT (Rec. 20)"
    if unit["status"] == "deleted":
        return "error", f"'{code}' ({unit['name']}) está eliminado de la Rec. 20"
    if unit["status"] == "deprecated":
        return "warn", f"'{code}' ({unit['name']}) está marcado como obsoleto en la Rec. 20"
    return "ok", f"'{code}' = {unit['name']}"


def search(terms: list[str], *, limit: int = 15, include_inactive: bool = False) -> list[dict[str, Any]]:
    """Busca unidades cuyo nombre o símbolo contenga todos los términos.

    Ordena primero las coincidencias exactas de nombre o símbolo y después las más cortas.
    """
    words = [t.lower() for t in terms if t.strip()]
    if not words:
        return []
    phrase = " ".join(words)
    hits = []
    for code, unit in load_units().items():
        if not include_inactive and unit["status"] in ("deleted", "deprecated"):
            continue
        name, symbol = unit["name"].lower(), unit["symbol"].lower()
        haystack = f"{name} {symbol} {code.lower()}"
        if code.lower() == phrase or name == phrase or symbol == phrase:
            rank = 0
        elif all(w in haystack for w in words):
            rank = 1 if name.startswith(words[0]) else 2
        else:
            continue
        hits.append((rank, len(name), code, unit))
    hits.sort(key=lambda h: (h[0], h[1], h[2]))
    return [{"code": c, **u} for _, _, c, u in hits[:limit]]
