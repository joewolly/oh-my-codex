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

    desktop_parser = commands.add_parser(
        "verify-desktop",
        help="Prepare or evaluate a guided Codex Desktop smoke-test fixture",
    )
    _common(desktop_parser)
    desktop_mode = desktop_parser.add_mutually_exclusive_group(required=True)
    desktop_mode.add_argument("--prepare", action="store_true", help="Create a disposable fixture, prompt, and evidence template")
    desktop_mode.add_argument("--evaluate", metavar="EVIDENCE", type=Path, help="Evaluate operator-entered Desktop evidence JSON")
    desktop_parser.add_argument("--fixture-dir", type=Path, help="Fixture directory for --prepare (must be empty)")
    desktop_parser.add_argument("--desktop-version", help="Current Desktop version observed in the fresh thread")
    desktop_parser.add_argument("--runtime-version", help="Current embedded runtime version observed in the fresh thread")
    desktop_parser.add_argument("--thread-id", help="Current fresh Desktop thread identity")
    desktop_parser.set_defaults(handler=None)
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
        elif args.command == "verify-desktop":
            from .desktop import run_verify_desktop

            result = run_verify_desktop(
                prepare=args.prepare,
                fixture_dir=args.fixture_dir,
                evidence=args.evaluate,
                codex_home=args.codex_home,
                skills_home=args.skills_home,
                desktop_version=args.desktop_version,
                runtime_version=args.runtime_version,
                thread_id=args.thread_id,
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
    for key in ("installed", "removed", "preserved", "warnings", "errors", "lock_paths", "restart_guidance", "main_model_guidance", "verification_label", "surface", "fixture", "prompt", "evidence", "message", "core_orchestration", "behavioral_role_isolation", "strict_sandbox_isolation", "daily_use_readiness", "strict_least_privilege", "evidence_validity", "parent_model_evidence", "activation_required"):
        values = result.get(key)
        if values:
            print(f"{key}: {', '.join(map(str, values)) if isinstance(values, list) else values}")
    for row in result.get("sandbox_roles", []):
        print(f"{row['role']}: configured {row['configured']}; observed {row['observed']}; probe {row['write_probe']} — {row['status']}")
    for check in result.get("checks", []):
        if command == "verify-desktop" and result.get("daily_use_readiness") and check.get("status") == "VERIFIED":
            continue  # Full per-property evidence remains available with --json.
        detail = check.get("detail", check.get("evidence", ""))
        print(f"{check.get('status', 'UNKNOWN')}: {check.get('name', 'check')} — {detail}")


if __name__ == "__main__":
    raise SystemExit(main())
