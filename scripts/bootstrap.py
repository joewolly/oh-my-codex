#!/usr/bin/env python3
"""Repository-owned bootstrap installer for Oh-My-Codex.

Creates a private tooling venv, installs the current checkout into it, runs the
managed-asset installer, then runs doctor. Installation adds capability only;
$oh-my-codex remains an explicit per-thread activation switch.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

MIN_PYTHON = (3, 11)
ROOT = Path(__file__).resolve().parents[1]


def default_venv_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "Oh-My-Codex" / "venv"
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "oh-my-codex" / "venv"


def venv_python(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(args: list[str]) -> None:
    print("+ " + subprocess.list2cmdline(args))
    subprocess.run(args, check=True)


def ensure_supported_python() -> None:
    if sys.version_info < MIN_PYTHON:
        version = ".".join(map(str, sys.version_info[:3]))
        raise SystemExit(f"Oh-My-Codex requires Python 3.11+; bootstrap is running under {version}")


def ensure_venv(venv_dir: Path) -> Path:
    python = venv_python(venv_dir)
    if python.is_file():
        probe = subprocess.run(
            [str(python), "-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if probe.returncode == 0:
            return python
        shutil.rmtree(venv_dir)
    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    venv.EnvBuilder(with_pip=True).create(venv_dir)
    python = venv_python(venv_dir)
    if not python.is_file():
        raise SystemExit(f"bootstrap could not create tooling Python at {python}")
    return python


def lifecycle_command(
    python: Path,
    command: str,
    *,
    codex_home: Path | None,
    skills_home: Path | None,
) -> list[str]:
    args = [str(python), "-m", "oh_my_codex", command]
    if codex_home is not None:
        args.extend(["--codex-home", str(codex_home)])
    if skills_home is not None:
        args.extend(["--skills-home", str(skills_home)])
    return args


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install Oh-My-Codex from this checkout using a private tooling venv."
    )
    parser.add_argument("--venv-dir", type=Path, default=default_venv_dir())
    parser.add_argument("--codex-home", type=Path)
    parser.add_argument("--skills-home", type=Path)
    parser.add_argument("--skip-doctor", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    ensure_supported_python()
    args = build_parser().parse_args(argv)
    if not (ROOT / "pyproject.toml").is_file() or not (ROOT / "oh_my_codex").is_dir():
        raise SystemExit("bootstrap must run from an Oh-My-Codex repository checkout")

    tooling_python = ensure_venv(args.venv_dir.expanduser().absolute())
    print(f"Oh-My-Codex source: {ROOT}")
    print(f"Tooling environment: {tooling_python.parent.parent}")

    run([
        str(tooling_python),
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-deps",
        "--force-reinstall",
        str(ROOT),
    ])
    run(lifecycle_command(
        tooling_python,
        "install",
        codex_home=args.codex_home,
        skills_home=args.skills_home,
    ))
    if not args.skip_doctor:
        run(lifecycle_command(
            tooling_python,
            "doctor",
            codex_home=args.codex_home,
            skills_home=args.skills_home,
        ))

    print()
    print("Oh-My-Codex capability is installed. It is NOT globally activated.")
    print("Fully quit and relaunch Codex Desktop, start a NEW thread, select Astra or Sol,")
    print("then explicitly invoke $oh-my-codex before the task you want orchestrated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
