"""Auditable standard-library Desktop gate, also emitted into disposable fixtures.

The preparation prompt pins the complete emitted bytes BEFORE execution. A script
cannot authenticate itself against an attacker who can replace that script.
"""
from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path
from typing import Any

HELPER = ".omc-probe-preflight.py"
HASH_TOKEN = "__OMC_PREFLIGHT_SHA256__"
_OMC_ROLES = {"omc_explorer", "omc_librarian", "omc_fixer", "omc_oracle"}


def contained_target(root: Path, candidate: str | Path) -> Path:
    """Canonical, component-based containment; reject all in-fixture symlinks.

    Resolve the root first (including macOS /var -> /private/var). Missing leaf
    names are allowed, but loops, dangling links and non-directory parents fail.
    This is preflight validation, not protection against concurrent host mutation.
    """
    try:
        canonical = root.resolve(strict=True)
        if not canonical.is_dir():
            raise ValueError("fixture root is not a directory")
        raw = Path(candidate)
        if ".." in raw.parts:
            raise ValueError("parent traversal in probe path")
        path = raw if raw.is_absolute() else canonical / raw
        # Check lexical components too: never traverse an untrusted symlink even
        # when its resolved destination happens to remain inside the fixture.
        for part in (path, *path.parents):
            if part == canonical:
                break
            if part.is_symlink() and part.is_relative_to(canonical):
                raise ValueError("symlink in probe path")
        resolved = path.resolve(strict=False)
        relative = resolved.relative_to(canonical)
        if not relative.parts:
            raise ValueError("probe target cannot be the fixture root")
        for parent in resolved.parents:
            if parent == canonical:
                break
            if parent.exists() and not parent.is_dir():
                raise ValueError("probe parent is not a directory")
        if resolved.exists() and not resolved.is_file():
            raise ValueError("probe target is not a regular file")
        if resolved.exists() and resolved.stat().st_nlink != 1:
            raise ValueError("hard-linked probe target")
        return resolved
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError(f"cannot prove fixture containment for {candidate!s}: {exc}") from exc


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def validate_config(path: Path) -> None:
    """Validate the user-owned Codex config semantically, not byte-for-byte.

    Codex Desktop may legitimately rewrite unrelated settings after preparation.
    Acceptance only needs the current config to remain parseable and compatible
    with OMC role discovery; the installer does not own this file.
    """
    if path.is_symlink():
        raise ValueError(f"effective config.toml is a symlink: {path}")
    if not path.exists():
        return
    if not path.is_file():
        raise ValueError(f"effective config.toml is not a regular file: {path}")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"effective config.toml is invalid: {exc}") from exc
    agents = data.get("agents") if isinstance(data, dict) else None
    if isinstance(agents, dict):
        if agents.get("enabled") is False:
            raise ValueError("effective config.toml sets agents.enabled=false")
        conflicts = sorted(_OMC_ROLES.intersection(str(key) for key in agents))
        if conflicts:
            raise ValueError("effective config.toml declares conflicting OMC roles: " + ", ".join(conflicts))


def validate(binding: dict[str, Any], helper_sha: str, *, check_assets: bool = True,
             check_state: bool = True) -> dict[str, Any]:
    """Read only; all expected data comes from the externally pinned helper bytes."""
    expected = dict(binding["metadata"], preflight_sha256=helper_sha)
    root = Path(expected["fixture_path"])
    if root.resolve(strict=True) != root or not root.is_dir():
        raise ValueError("fixture root changed")
    for name, identity in expected["directory_identity"].items():
        path = root if name == "." else root / name
        if path.is_symlink() or not path.is_dir() or [path.stat().st_dev, path.stat().st_ino] != identity:
            raise ValueError("fixture/probe parent identity changed")
    def read(name: str) -> bytes:
        return contained_target(root, name).read_bytes()
    if read(".omc-desktop.json") != json_bytes(expected):
        raise ValueError("fixture metadata changed; do not delegate")
    if sha(read(HELPER)) != helper_sha:
        raise ValueError("preflight helper changed; do not delegate")
    if read("fixture-baseline.json") != json_bytes(binding["baseline"]):
        raise ValueError("fixture baseline changed; do not delegate")
    template, offset = binding["prompt_template"], binding["prompt_hash_offset"]
    prompt = template[:offset] + helper_sha + template[offset + len(HASH_TOKEN):]
    if read("desktop-prompt.txt") != prompt.encode():
        raise ValueError("probe prompt changed; do not delegate")
    if read("control-prompt.txt") != binding["control_prompt"].encode():
        raise ValueError("control prompt changed; do not delegate")
    if check_state:
        for name in ("desktop-evidence.json", "control-evidence.json"):
            if not isinstance(json.loads(read(name)), dict):
                raise ValueError("evidence object required")
    plan = {}
    for role in ("explorer", "librarian", "fixer", "oracle"):
        plan["omc_" + role] = {
            "path": str(contained_target(root, f".omc-probes/{role}-write.txt")),
            "contents_hex": f"OMC Desktop {role.title()} probe\n".encode("ascii").hex()}
    target = str(contained_target(root, "target.py"))
    if expected["schema"] != 4 or expected["preflight_contract"] != 1 or expected["probe_plan"] != plan or expected["fixer_target"] != target:
        raise ValueError("probe manifest differs from canonical harness-owned targets")
    if check_assets:
        validate_config(Path(binding["config_path"]))
        for name, path in binding["installed_paths"].items():
            asset = Path(path)
            if not asset.is_file() or sha(asset.read_bytes()) != expected["asset_fingerprints"][name]:
                raise ValueError(f"missing or changed installed asset: {name}: {path}")
    if check_state:
        allowed = {name: {digest} for name, digest in binding["baseline"]["files"].items()}
        # Later dispatches must accept ONLY the exact authorized Fixer result and
        # exact named canaries. Retrospective attribution remains the evaluator's job.
        allowed["target.py"].add(sha(b"def value():\n    return 'expected'\n"))
        optional = {}
        for row in plan.values():
            optional[Path(row["path"]).relative_to(root).as_posix()] = {sha(bytes.fromhex(row["contents_hex"]))}
        controls = {HELPER, ".omc-desktop.json", "fixture-baseline.json", "desktop-prompt.txt",
                    "control-prompt.txt", "desktop-evidence.json", "control-evidence.json"}
        for name, hashes in allowed.items():
            if sha(read(name)) not in hashes:
                raise ValueError(f"unexpected fixture content: {name}")
        for path in root.rglob("*"):
            name = path.relative_to(root).as_posix()
            if name.startswith(".git/"):
                continue
            if path.is_symlink():
                raise ValueError(f"symlink in fixture: {name}")
            if path.is_dir() and name in {".git", ".omc-probes"}:
                continue
            if name in controls or name in allowed:
                contained_target(root, name)
                continue
            if name in optional and sha(read(name)) in optional[name]:
                continue
            raise ValueError(f"unexpected fixture entry: {name}")
        if not (root / ".git").is_dir():
            raise ValueError("fixture Git directory missing")
    return {"overall": "PASS", "fixture": str(root), "probe_plan": plan,
            "fixer_target": target, "preflight_sha256": helper_sha,
            "run_id": expected["run_id"], "preflight_contract": 1}


def main(binding: dict[str, Any]) -> int:
    try:
        helper = Path(__file__).resolve(strict=True)
        if helper != Path(binding["metadata"]["fixture_path"]) / HELPER:
            raise ValueError("helper executed outside its prepared fixture")
        result = validate(binding, sha(helper.read_bytes()))
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(json.dumps({"overall": "FAIL", "error": str(exc), "delegation": "STOP"}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0
