"""Command line entry point for the Oh-My-Codex lifecycle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .lifecycle import LifecycleError, doctor, install, resolve_paths, uninstall


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--codex-home", type=Path, help="Codex home (default: CODEX_HOME or ~/.codex)")
    parser.add_argument("--skills-home", type=Path, help="Skills home (default: ~/.agents/skills)")
    parser.add_argument("--json", action="store_true", dest="as_json", default=argparse.SUPPRESS, help="Emit machine-readable output")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oh-my-codex", description="Install and inspect Oh-My-Codex safely")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Emit machine-readable output")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    for name, fn in (("install", install), ("uninstall", uninstall), ("doctor", doctor)):
        sub = commands.add_parser(name)
        _common(sub)
        if name == "install":
            sub.add_argument("--source-root", type=Path, help=argparse.SUPPRESS)
        sub.set_defaults(handler=fn)

    verify_parser = commands.add_parser("verify")
    _common(verify_parser)
    verify_parser.add_argument("--codex-bin", default="codex")
    verify_parser.add_argument("--timeout", type=float, default=300.0)
    verify_parser.add_argument("--runtime", choices=("v1", "v2"), default="v2")
    verify_parser.add_argument("--keep-artifacts", action="store_true")
    verify_parser.set_defaults(handler=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            # Verification is optional so installation and doctor do not import it.
            from .verify import run_verify

            codex_home, skills_home = resolve_paths(args.codex_home, args.skills_home)
            result = run_verify(
                codex_home,
                skills_home,
                codex_bin=args.codex_bin,
                timeout=args.timeout,
                runtime=args.runtime,
                keep_artifacts=args.keep_artifacts,
            )
        elif args.command == "install":
            result = install(args.codex_home, args.skills_home, source_root=args.source_root)
        else:
            result = args.handler(args.codex_home, args.skills_home)
    except (LifecycleError, OSError, ValueError) as exc:
        if args.as_json:
            print(json.dumps({"overall": "FAIL", "error": str(exc)}, sort_keys=True))
        else:
            print(f"oh-my-codex: {exc}", file=sys.stderr)
        return 2

    if args.as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        _print_human(args.command, result)
    overall = str(result.get("overall", result.get("status", "PASS")))
    return 0 if overall.startswith("PASS") or overall == "completed" else 1


def _print_human(command: str, result: dict) -> None:
    overall = result.get("overall", result.get("status", "PASS"))
    print(f"{command}: {overall}")
    for key in ("installed", "removed", "preserved", "warnings", "errors", "lock_paths"):
        values = result.get(key)
        if values:
            print(f"{key}: {', '.join(map(str, values)) if isinstance(values, list) else values}")
    for check in result.get("checks", []):
        detail = check.get("detail", check.get("evidence", ""))
        print(f"{check.get('status', 'UNKNOWN')}: {check.get('name', 'check')} — {detail}")


if __name__ == "__main__":
    raise SystemExit(main())
