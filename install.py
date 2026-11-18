#!/usr/bin/env python3
"""Instalador de la skill sdm-ngsild-generator para Claude Code (Windows, macOS y Linux).

Copia la skill en la carpeta de skills de Claude Code, crea su entorno virtual e instala
las dependencias (jsonschema, requests, pyyaml). Uso::

    python install.py                      # para tu usuario: ~/.claude/skills/
    python install.py --project RUTA       # para un proyecto: RUTA/.claude/skills/
    python install.py --force              # actualiza una instalación existente
    python install.py --no-venv            # solo copia (instalarás tú las dependencias)

Requisitos: Python 3.10 o superior. No necesita token de GitHub.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

SKILL = "sdm-ngsild-generator"
MIN_PYTHON = (3, 10)
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".venv", ".DS_Store")


def find_source() -> Path:
    """Carpeta de la skill: junto al instalador (paquete de distribución) o en skill/ (repo)."""
    here = Path(__file__).resolve().parent
    for candidate in (here / SKILL, here / "skill" / SKILL):
        if (candidate / "SKILL.md").is_file():
            return candidate
    raise SystemExit(f"No se encuentra la carpeta '{SKILL}' con SKILL.md junto a install.py.")


def venv_python(target: Path) -> Path:
    if os.name == "nt":
        return target / ".venv" / "Scripts" / "python.exe"
    return target / ".venv" / "bin" / "python"


def copy_skill(source: Path, target: Path, *, force: bool) -> None:
    if target.exists():
        if not force:
            raise SystemExit(f"Ya existe {target}. Usa --force para actualizarla "
                             "(se conserva su entorno virtual).")
        for child in target.iterdir():  # se conserva .venv para no reinstalar dependencias
            if child.name == ".venv":
                continue
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, ignore=IGNORE, dirs_exist_ok=True)


def create_venv(target: Path) -> Path:
    python = venv_python(target)
    if not python.exists():
        print("· Creando el entorno virtual…")
        venv.EnvBuilder(with_pip=True).create(target / ".venv")
    print("· Instalando dependencias…")
    subprocess.run([str(python), "-m", "pip", "install", "--quiet", "--upgrade", "pip"],
                   check=False)
    subprocess.run([str(python), "-m", "pip", "install", "--quiet", "-r",
                    str(target / "requirements.txt")], check=True)
    return python


def smoke_test(python: Path, target: Path) -> None:
    """Comprueba que los scripts arrancan con el entorno instalado (sin red)."""
    result = subprocess.run([str(python), str(target / "scripts" / "sdm_index.py"), "status"],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"La comprobación final ha fallado:\n{result.stderr}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"Instala la skill {SKILL} para Claude Code.")
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--user", action="store_true", help="~/.claude/skills (por defecto).")
    where.add_argument("--project", type=Path, help="Carpeta del proyecto: <RUTA>/.claude/skills.")
    parser.add_argument("--force", action="store_true", help="Actualiza una instalación existente.")
    parser.add_argument("--no-venv", action="store_true", help="No crea el entorno virtual.")
    args = parser.parse_args(argv)

    if sys.version_info < MIN_PYTHON:
        raise SystemExit(f"Se necesita Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} o superior "
                         f"(tienes {sys.version.split()[0]}).")
    source = find_source()
    base = (args.project.expanduser().resolve() if args.project else Path.home()) / ".claude"
    target = base / "skills" / SKILL
    version = (source / "VERSION").read_text(encoding="utf-8").strip() \
        if (source / "VERSION").is_file() else "?"

    print(f"Instalando {SKILL} {version} en {target}")
    copy_skill(source, target, force=args.force)
    if args.no_venv:
        print("· Sin entorno virtual: instala las dependencias con\n"
              f"  python -m venv {target / '.venv'} && "
              f"<venv>/python -m pip install -r {target / 'requirements.txt'}")
    else:
        python = create_venv(target)
        smoke_test(python, target)
    print(f"Listo. Abre Claude Code{' en ' + str(args.project) if args.project else ''} y pide, "
          "por ejemplo: «quiero proponer un Smart Data Model para…».")
    return 0


if __name__ == "__main__":
    sys.exit(main())
