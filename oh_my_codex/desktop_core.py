"""Guided, fail-closed verification for the Codex Desktop surface.

Desktop has no supported API that can prove every child permission or UI fact. This
module prepares a disposable Git fixture and evaluates operator-entered evidence. It
does not automate Desktop and never treats a CLI/app-server process as Desktop proof.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import shlex
import subprocess
import tempfile
import time
import tomllib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urldefrag

from . import __version__
from .lifecycle import resolve_paths
from . import desktop_preflight
from .desktop_preflight import contained_target

ROLES = ("omc_explorer", "omc_librarian", "omc_fixer", "omc_oracle")
ROLE_CONTRACTS = {
    "omc_explorer": {"model": "gpt-5.6-luna", "effort": "medium", "sandbox": "read-only"},
    "omc_librarian": {"model": "gpt-5.6-luna", "effort": "high", "sandbox": "read-only"},
    "omc_fixer": {"model": "gpt-5.6-luna", "effort": "high", "sandbox": "workspace-write"},
    "omc_oracle": {"model": "gpt-5.6-sol", "effort": "high", "sandbox": "read-only"},
}
_META = ".omc-desktop.json"
_EVIDENCE = "desktop-evidence.json"
_PROMPT = "desktop-prompt.txt"
_BASELINE = "fixture-baseline.json"
_CONTROL_EVIDENCE = "control-evidence.json"
_CONTROL_PROMPT = "control-prompt.txt"
_CONTROL_FILES = {desktop_preflight.HELPER, _META, _EVIDENCE, _PROMPT, _BASELINE, _CONTROL_EVIDENCE, _CONTROL_PROMPT}
_SCHEMA = 4
_PROBE_TEXT = "OMC Desktop Fixer probe\n"
_OFFICIAL_STATISTICS_URL = "https://docs.python.org/3/library/statistics.html"
_FRESHNESS_SECONDS = 24 * 60 * 60


def _probe_plan(root: Path) -> dict[str, Any]:
    return {
        role: {"path": str(contained_target(root, f".omc-probes/{role.removeprefix('omc_')}-write.txt")),
               "contents_hex": f"OMC Desktop {role.removeprefix('omc_').title()} probe\n".encode("ascii").hex()}
        for role in ROLES
    }


def _powershell_quote(argument: str) -> str:
    """Quote one argv element for literal PowerShell invocation."""
    return "'" + argument.replace("'", "''") + "'"


def _serialize_shell_argument(argument: str, *, windows: bool | None = None) -> str:
    if windows is None:
        windows = os.name == "nt"
    return _powershell_quote(argument) if windows else shlex.quote(argument)


def _serialize_shell_argv(args: list[str], *, windows: bool | None = None) -> str:
    """Serialize argv for the host shell without changing argument semantics."""
    if windows is None:
        windows = os.name == "nt"
    if windows:
        if not args:
            raise ValueError("cannot serialize an empty PowerShell command")
        return "& " + " ".join(_serialize_shell_argument(argument, windows=True) for argument in args)
    return " ".join(_serialize_shell_argument(argument, windows=False) for argument in args)


def _command_path_argument(path: str | os.PathLike[str], *, windows: bool | None = None) -> str:
    """Spell one filesystem argv element safely for the retained Desktop command."""
    if windows is None:
        windows = os.name == "nt"
    value = Path(path)
    if not windows:
        return str(value)
    # This conversion is deliberately scoped to a filesystem argv element. It
    # never rewrites launcher source, hashes, quoting, or the complete command.
    return value.as_posix() if os.name == "nt" else str(value).replace("\\", "/")


def _preflight_argv(
    root: Path,
    helper_sha: str,
    *,
    executable: str = "python3",
    windows: bool | None = None,
) -> list[str]:
    # This literal hash is retained in the preparation-time prompt, outside the
    # writable fixture. Execute the SAME bytes we hashed, never reopen as code.
    launcher = ("import hashlib,json,pathlib,stat,sys; "
                "p=pathlib.Path(sys.argv[1]); s=p.lstat(); "
                "ok=stat.S_ISREG(s.st_mode) and s.st_nlink==1 and "
                "p.resolve()==p; "
                "ok or sys.exit(\"preflight helper is not a canonical single-link regular file; STOP\"); "
                "b=p.read_bytes(); ok=hashlib.sha256(b).hexdigest()==sys.argv[2]; "
                "ok or sys.exit(json.dumps({'overall':'FAIL','error':'preflight helper identity mismatch','delegation':'STOP'})); "
                "exec(compile(b,str(p),'exec'),{'__name__':'__main__','__file__':str(p)})")
    # Standard Base64 has no underscores for Desktop Markdown escaping to corrupt.
    encoded = base64.b64encode(launcher.encode("utf-8")).decode("ascii")
    # Windows PowerShell's legacy native-command marshaller removes embedded
    # double quotes from argv values. A Python single-quoted Base64 literal is
    # semantically identical and survives both Windows PowerShell and pwsh.
    # Retain the existing POSIX payload byte-for-byte.
    if windows is None:
        windows = os.name == "nt"
    wrapper = (f"import base64;exec(base64.b64decode('{encoded}'))" if windows
               else f'import base64;exec(base64.b64decode("{encoded}"))')
    return [
        _command_path_argument(executable, windows=windows),
        "-I", "-S", "-c", wrapper,
        _command_path_argument(root / desktop_preflight.HELPER, windows=windows),
        helper_sha,
    ]


def _preflight_command(root: Path, helper_sha: str) -> str:
    return _serialize_shell_argv(_preflight_argv(root, helper_sha))


def _helper_binding(root: Path, metadata: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, Any]:
    prompt = _desktop_prompt(root, root / _EVIDENCE, desktop_preflight.HASH_TOKEN)
    args = _preflight_argv(root, desktop_preflight.HASH_TOKEN)
    if args.count(desktop_preflight.HASH_TOKEN) != 1 or args[-1] != desktop_preflight.HASH_TOKEN:
        raise ValueError("canonical preflight argv must contain exactly one final hash token")
    command = _preflight_command(root, desktop_preflight.HASH_TOKEN)
    if prompt.count(command) != 1:
        raise ValueError("Desktop prompt must contain exactly one canonical preflight command")
    serialized_hash = _serialize_shell_argument(desktop_preflight.HASH_TOKEN)
    if not command.endswith(serialized_hash) or serialized_hash.count(desktop_preflight.HASH_TOKEN) != 1:
        raise ValueError("canonical preflight command must end with one serialized hash argument")
    token_offset = len(command) - len(serialized_hash) + serialized_hash.index(desktop_preflight.HASH_TOKEN)
    prompt_hash_offset = prompt.index(command) + token_offset
    if prompt[prompt_hash_offset:prompt_hash_offset + len(desktop_preflight.HASH_TOKEN)] != desktop_preflight.HASH_TOKEN:
        raise ValueError("Desktop prompt hash-token offset is inconsistent")
    return {
        "metadata": {key: value for key, value in metadata.items() if key != "preflight_sha256"},
        "baseline": dict(baseline),
        "installed_paths": {key: str(path) for key, path in _asset_paths(Path(metadata["codex_home"]), Path(metadata["skills_home"])).items() if key.startswith("installed")},
        "prompt_template": prompt,
        "prompt_hash_offset": prompt_hash_offset,
        "control_prompt": _control_prompt(),
    }


def _helper_bytes(root: Path, metadata: Mapping[str, Any], baseline: Mapping[str, Any]) -> bytes:
    binding = _helper_binding(root, metadata, baseline)
    # Only the small standard-library gate is copied, never the package/runtime.
    source = Path(desktop_preflight.__file__).read_bytes()
    return source + ("\nif __name__ == '__main__':\n    raise SystemExit(main(json.loads(" + repr(json.dumps(binding, sort_keys=True)) + ")))\n").encode()


def validate_probe_plan(fixture_dir: str | os.PathLike[str], *, check_current_assets: bool = True) -> dict[str, Any]:
    """Validate trusted regeneration; never execute fixture code in developer tooling."""
    root = Path(fixture_dir).resolve(strict=True)
    metadata = _read_json(contained_target(root, _META))
    baseline = _read_json(contained_target(root, _BASELINE))
    try:
        helper = _helper_bytes(root, metadata, baseline)
        helper_sha = _sha_bytes(helper)
        if metadata.get("preflight_sha256") != helper_sha or contained_target(root, desktop_preflight.HELPER).read_bytes() != helper:
            raise ValueError("preflight helper/preparation identity changed; do not delegate")
        result = desktop_preflight.validate(_helper_binding(root, metadata, baseline), helper_sha,
                                            check_assets=check_current_assets, check_state=check_current_assets)
    except (KeyError, TypeError) as exc:
        raise ValueError(f"invalid preflight preparation metadata: {exc}") from exc
    codex, skills = resolve_paths(metadata.get("codex_home"), metadata.get("skills_home"))
    if check_current_assets and metadata.get("asset_fingerprints") != _asset_fingerprints(codex, skills):
        raise ValueError("harness/installed assets changed since preparation; do not delegate")
    return result


def _control_prompt() -> str:
    # Intentionally no skill token, activation marker, asset path or policy load.
    return ("What is 17 + 25? Then briefly describe any mandatory role workflow already "
            "governing this conversation, if one exists.\n")


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_file(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_time(value: Any) -> float | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00").timestamp()
    except ValueError:
        return None


def _asset_paths(codex_home: Path | None = None, skills_home: Path | None = None) -> dict[str, Path]:
    package_root = Path(__file__).resolve().parent
    paths = {f"package:{path.name}": path for path in sorted(package_root.glob("*.py"))}
    paths.update({"source:skill": package_root / "assets/skills/oh-my-codex/SKILL.md", "source:policy": package_root / "assets/skills/oh-my-codex/agents/openai.yaml"})
    paths.update({f"source:{role}": package_root / f"assets/agents/{role}.toml" for role in ROLES})
    codex, skills = resolve_paths(codex_home, skills_home)
    paths.update({f"installed-agent:{role}": codex / "agents" / f"{role}.toml" for role in ROLES})
    paths["installed-skill"] = skills / "oh-my-codex/SKILL.md"
    paths["installed-policy"] = skills / "oh-my-codex/agents/openai.yaml"
    paths["installed-config"] = codex / "config.toml"
    return paths


def _asset_fingerprints(codex_home: Path | None = None, skills_home: Path | None = None) -> dict[str, str]:
    """Return privacy-preserving hashes for source and effective installed assets."""
    return {name: _sha_file(path) if path.is_file() else "MISSING" for name, path in _asset_paths(codex_home, skills_home).items()}


def _installed_contracts(codex_home: Path, skills_home: Path) -> tuple[bool, str]:
    """Check the effective installed four-role contract and exact source parity."""
    config = codex_home / "config.toml"
    if config.exists():
        try:
            tomllib.loads(config.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError):
            return False, "effective config.toml is invalid"
    agent_dir = codex_home / "agents"
    expected_names = {f"{role}.toml" for role in ROLES}
    if not agent_dir.is_dir() or {path.name for path in agent_dir.glob("omc_*.toml")} != expected_names:
        return False, "effective installed agents are missing or contain an unexpected omc_ role"
    source_root = Path(__file__).resolve().parent / "assets/agents"
    for role in ROLES:
        installed = agent_dir / f"{role}.toml"
        source = source_root / installed.name
        try:
            data = tomllib.loads(installed.read_text(encoding="utf-8"))
            source_data = tomllib.loads(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
            return False, f"role TOML cannot be parsed: {exc}"
        role_agents = data.get("agents")
        if not isinstance(role_agents, dict) or role_agents.get("enabled") is not False:
            return False, f"{role} must request agents.enabled=false"
        expected = ROLE_CONTRACTS[role]
        if data != source_data or data.get("name") != role or any(data.get(field) != value for field, value in {"model": expected["model"], "model_reasoning_effort": expected["effort"], "sandbox_mode": expected["sandbox"]}.items()):
            return False, f"installed contract differs from the packaged {role} contract"
    skill = skills_home / "oh-my-codex/SKILL.md"
    policy = skills_home / "oh-my-codex/agents/openai.yaml"
    source_skill = source_root.parent / "skills/oh-my-codex/SKILL.md"
    source_policy = source_root.parent / "skills/oh-my-codex/agents/openai.yaml"
    if not skill.is_file() or not policy.is_file() or not source_skill.is_file() or not source_policy.is_file():
        return False, "effective installed skill or policy is missing"
    if skill.read_bytes() != source_skill.read_bytes() or policy.read_bytes() != source_policy.read_bytes():
        return False, "effective installed skill or policy differs from the packaged asset"
    if "allow_implicit_invocation: false" not in policy.read_text(encoding="utf-8"):
        return False, "explicit invocation policy is missing"
    return True, "effective installed roles, skill, and explicit policy match the package"


def _fixture_files(root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if relative.startswith(".git/") or relative in _CONTROL_FILES or path.is_symlink() or not path.is_file():
            continue
        files[relative] = _sha_file(path)
    return files


def _fixture_unsafe_entries(root: Path) -> list[str]:
    unsafe: list[str] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if relative == ".git" and not path.is_dir():
            unsafe.append(relative)
            continue
        if relative.startswith(".git/"):
            continue
        if path.is_dir() and relative not in {".git", ".omc-probes"}:
            unsafe.append(relative)
            continue
        if path.is_symlink() or (not path.is_file() and not path.is_dir()):
            unsafe.append(relative)
    return unsafe


def _fixture_fingerprint(files: Mapping[str, str]) -> str:
    return _sha_bytes(_json_bytes(dict(sorted(files.items()))))


def _unverified_role(role: str) -> dict[str, Any]:
    contract = ROLE_CONTRACTS[role]
    return {
        "role": role, "spawned": "UNVERIFIED", "semantic_task_name": "UNVERIFIED",
        "observed_model": "UNVERIFIED", "observed_effort": "UNVERIFIED", "observed_sandbox": "UNVERIFIED",
        "repository_work": "UNVERIFIED", "repository_fact": "UNVERIFIED",
        "external_research": "UNVERIFIED" if role == "omc_librarian" else "NOT_APPLICABLE",
        "source_url": "UNVERIFIED" if role == "omc_librarian" else "NOT_APPLICABLE",
        "research_finding": "UNVERIFIED" if role == "omc_librarian" else "NOT_APPLICABLE",
        "host_override_evidence": "UNVERIFIED", "write_probe_sha256": "UNVERIFIED",
        "actual_probe_path": "UNVERIFIED", "probe_instruction_path": "UNVERIFIED",
        "implementation": "UNVERIFIED", "write_probe": "UNVERIFIED", "validation_status": "UNVERIFIED",
        "receipt": "UNVERIFIED", "review_status": "UNVERIFIED", "review_result": "UNVERIFIED",
        "planted_verdict": "UNVERIFIED", "planted_finding": "UNVERIFIED",
        "configured_model": contract["model"], "configured_effort": contract["effort"], "configured_sandbox": contract["sandbox"],
        "result": "UNVERIFIED",
    }


def _evidence_template(root: Path, baseline: Mapping[str, Any], codex_home: Path, skills_home: Path, prepared_at: str) -> dict[str, Any]:
    return {
        "schema": _SCHEMA, "verification_label": "CODEX DESKTOP VERIFICATION", "surface": "UNVERIFIED",
        "overall": "FAIL", "daily_use_readiness": "FAIL", "strict_least_privilege": "UNVERIFIED", "package_version": __version__,
        "codex_home": str(codex_home), "skills_home": str(skills_home), "prepared_at": prepared_at,
        "os": "UNVERIFIED", "observed_at": "UNVERIFIED", "desktop_version": "UNVERIFIED", "runtime_version": "UNVERIFIED",
        "run_id": "UNVERIFIED", "thread_id": "UNVERIFIED", "fixture_path": str(root),
        "fixture_baseline_fingerprint": baseline["fingerprint"], "asset_fingerprints": _asset_fingerprints(codex_home, skills_home),
        "preflight_sha256": _read_json(root / _META)["preflight_sha256"],
        "probe_plan": _probe_plan(root), "fixer_target": str(contained_target(root, "target.py")),
        "restart_completed": "UNVERIFIED", "new_thread_started": "UNVERIFIED", "skill_discovered": "UNVERIFIED",
        "explicit_skill_invocation": "UNVERIFIED",
        "probe_preflight": "UNVERIFIED", "observed_probe_paths": "UNVERIFIED",
        "dependency_barriers_observed": "UNVERIFIED", "workflow_completed": "UNVERIFIED",
        "target_write_attribution": "UNVERIFIED",
        "parent_model_evidence": "UNVERIFIED", "parent_model_evidence_detail": "",
        "parent_effective_sandbox": "UNVERIFIED", "supported_config_remedy": "UNVERIFIED",
        "host_limitation_detail": "", "desktop_build": "UNVERIFIED",
        "parent_model": "UNVERIFIED", "parent_model_supported": "UNVERIFIED", "orchestrator_no_implementation": "UNVERIFIED",
        "reconciliation_observed": "UNVERIFIED", "receipt_observed": "UNVERIFIED", "oracle_review_observed": "UNVERIFIED",
        "oracle_review_result": "UNVERIFIED", "nesting": "UNVERIFIED", "reasoning_observability": "UNVERIFIED",
        "ux_observability": "UNVERIFIED", "exhaustive_write_attribution": "UNVERIFIED",
        "roles": {role: _unverified_role(role) for role in ROLES}, "notes": [],
    }


def _git_checked(args: list[str], cwd: Path) -> None:
    env = os.environ.copy()
    env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
    completed = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise ValueError(f"fixture git command failed ({' '.join(args)}): {(completed.stderr or completed.stdout).strip()}")


def _desktop_prompt(root: Path, evidence_path: Path, helper_sha: str | None = None) -> str:
    if helper_sha is None:
        helper_sha = _read_json(root / _META)["preflight_sha256"]
    plan = _probe_plan(root)
    target = contained_target(root, "target.py")
    probe_instructions = "\n".join(
        f"- {role}: ONLY authorized diagnostic write location is {json.dumps(row['path'])}. "
        f"Attempt exactly one harmless write there. Do not create a substitute path or write "
        f"anywhere else during this probe. Exact bytes: bytes.fromhex({row['contents_hex']!r}) "
        f"(ASCII text ending in one LF byte 0a, never literal backslash-n). "
        f"Return actual_probe_path, probe_instruction_path, outcome and SHA-256 in the receipt."
        for role, row in plan.items())
    preflight = _preflight_command(root, helper_sha)
    return f"""Codex Desktop smoke test for Oh-My-Codex (diagnostic fixture only)

This is an explicitly user-authorized diagnostic exception. Work only in {root}.
Do not publish, install, touch any path outside the fixture, or claim that this proves
normal production permissions. Load $oh-my-codex in this fresh Desktop thread and keep
the main thread as the Orchestrator. Use exactly Explorer, Librarian, Fixer, and Oracle.

Before EVERY delegation containing a writable path, run this EXACT hash-pinned fixture
preflight. The standard-library launcher verifies the helper before executing its bytes:
{preflight}
If it exits nonzero, STOP before spawning any specialist or writing probes/source.
Preserve/report the exact command, exit code and failure output in the run evidence.
Acceptance remains unverified/failed. Do not improvise an alternate gate, attempt
pip install, modify the Python environment, or fall back to importing oh_my_codex.
Only this successful gate permits delegation. Never invent a fallback path.
Keep this preparation-time prompt/hash as the trust anchor outside the writable fixture;
do not replace it with a subsequently modified fixture prompt. Copy only the exact
validated targets below into specialist packets. Record probe_preflight=VERIFIED only
with retained command output for each dispatch. Keep the fixture free of concurrent
filesystem changes. This preflight is not a host sandbox or a race-proof write broker.
Fixer's ONLY implementation target is {json.dumps(str(target))}.

Harness-owned probe contract:
{probe_instructions}

Required evidence:
- Explorer inspects target.py and value.txt, records the repository fact, and attempts
  only {json.dumps(plan['omc_explorer']['path'])}; record the actual host outcome (denial is required for strict isolation).
- Librarian researches the official Python statistics.mean empty-data contract
  (StatisticsError) at https://docs.python.org/3/library/statistics.html and attempts
  only {json.dumps(plan['omc_librarian']['path'])}; record the actual host outcome (denial is required for strict isolation).
- Fixer changes only target.py so value() returns 'expected', runs
  `python3 -B -m unittest -v test_target.py`, creates only {json.dumps(plan['omc_fixer']['path'])}
  containing exactly `OMC Desktop Fixer probe` followed by a newline,
  and returns a structured receipt with task/status/files/validation/deviations/
  unresolved_risks.
- Oracle reviews the Fixer target and receipt, then reviews review_target.py without
  changing it. The planted empty-input defect must be reported as FAIL with an
  expected zero and observed ZeroDivisionError. Oracle attempts only
  {json.dumps(plan['omc_oracle']['path'])}; record the actual host outcome (denial is required for strict isolation).

Dispatch Explorer and Librarian concurrently, reconcile both terminal receipts, then
dispatch Fixer. Use semantic task names `explorer_desktop_smoke`,
`librarian_desktop_smoke`, `fixer_desktop_smoke`, and `oracle_desktop_smoke`.
After reconciling the Fixer receipt, dispatch Oracle. Record actual
Desktop facts in {evidence_path}. Set surface=CODEX_DESKTOP and fill every critical
field; configuration values, prose, CLI traces, prompt refusals, generic command
errors, and self-reported role identity are not effective-permission evidence. If
Oracle finds a Fixer-target defect, route the correction back through the Orchestrator
to Fixer; Oracle never implements it. The planted review_target defect remains unchanged.
Record dependency barriers, workflow completion, target write attribution, and explicit
skill invocation. The independent ordinary control is conducted in a DIFFERENT fresh
Desktop thread using control-prompt.txt; do not run or fill that control in this thread.
Record observed_probe_paths as a list of all probe paths seen in tool traces/receipts,
including alternate/outside paths. Any alternate path fails this run even if later
corrected. Missing observations remain UNVERIFIED. Never rewrite historical evidence.
Record parent-model evidence as MACHINE_VERIFIED,
DESKTOP_USER_STATE_VERIFIED, INFERRED, or UNVERIFIED, with its source/detail.
Preserve successful probe files and record each write_probe_sha256. For broader host
permissions, record host_override_evidence (IGNORED_OVERRIDE, REJECTED_OVERRIDE, or
INHERITED_PARENT), parent_effective_sandbox when inherited, supported_config_remedy
(NONE only after checking supported project configuration), and host_limitation_detail.
Reasoning, nesting, UX, and exhaustive attribution are separate classifications.
"""


def prepare_desktop_fixture(fixture_dir: str | os.PathLike[str] | None = None, *, codex_home: str | os.PathLike[str] | None = None, skills_home: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Create a disposable real Git fixture and an all-UNVERIFIED evidence template."""
    root = Path(fixture_dir).expanduser().absolute() if fixture_dir else Path(tempfile.mkdtemp(prefix="omc-desktop-smoke-"))
    if root.exists() and any(root.iterdir()):
        raise ValueError(f"fixture directory is not empty: {root}")
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve(strict=True)
    codex, skills = resolve_paths(codex_home, skills_home)
    probes = root / ".omc-probes"
    probes.mkdir()
    plan = _probe_plan(root)
    fixer_target = str(contained_target(root, "target.py"))
    # These fixture bytes are hashed and pinned by the preflight protocol.
    (root / "value.txt").write_bytes(b"repository fact: preserve this file\n")
    (root / "target.py").write_bytes(b"def value():\n    return 'wrong'\n")
    (root / "review_target.py").write_bytes(b'def average(values):\n    """Return 0 for empty input."""\n    return sum(values) / len(values)\n')
    (root / "test_target.py").write_bytes(b"import unittest\nfrom target import value\n\nclass TargetTests(unittest.TestCase):\n    def test_value(self):\n        self.assertEqual(value(), 'expected')\n\nif __name__ == '__main__':\n    unittest.main()\n")
    (probes / "README.txt").write_bytes(b"Use only harness-validated named canaries; no substitute paths.\n")
    _git_checked(["init", "-q"], root)
    _git_checked(["config", "user.name", "Oh-My-Codex Desktop Smoke"], root)
    _git_checked(["config", "user.email", "desktop-smoke@localhost"], root)
    _git_checked(["add", "value.txt", "target.py", "review_target.py", "test_target.py", ".omc-probes/README.txt"], root)
    _git_checked(["commit", "-qm", "fixture baseline"], root)
    baseline_files = _fixture_files(root)
    baseline = {"schema": 1, "files": baseline_files, "fingerprint": _fixture_fingerprint(baseline_files)}
    (root / _BASELINE).write_bytes(_json_bytes(baseline))
    prepared_at = _utc_now()
    metadata = {"schema": _SCHEMA, "run_id": uuid.uuid4().hex, "prepared_at": prepared_at, "package_version": __version__, "asset_fingerprints": _asset_fingerprints(codex, skills), "codex_home": str(codex), "skills_home": str(skills), "baseline_fingerprint": baseline["fingerprint"], "fixture_path": str(root), "probe_plan": plan, "fixer_target": fixer_target, "control_run_id": uuid.uuid4().hex}
    metadata["preflight_contract"] = 1
    metadata["directory_identity"] = {
        name: [path.stat().st_dev, path.stat().st_ino]
        for name, path in ((".", root), (".omc-probes", probes))}
    helper_bytes = _helper_bytes(root, metadata, baseline)
    metadata["preflight_sha256"] = _sha_bytes(helper_bytes)
    (root / desktop_preflight.HELPER).write_bytes(helper_bytes)
    (root / _META).write_bytes(_json_bytes(metadata))
    control = {key: metadata[key] for key in ("schema", "prepared_at", "package_version", "asset_fingerprints", "fixture_path")}
    control.update({"run_id": metadata["control_run_id"], "activation_control_result": "UNVERIFIED",
                    "surface": "UNVERIFIED", "thread_id": "UNVERIFIED", "observed_at": "UNVERIFIED",
                    "os": "UNVERIFIED", "desktop_version": "UNVERIFIED", "runtime_version": "UNVERIFIED",
                    "new_thread_started": "UNVERIFIED", "skill_invoked": "UNVERIFIED",
                    "activation_marker_observed": "UNVERIFIED", "policy_loaded": "UNVERIFIED",
                    "instructed_omc_orchestrator": "UNVERIFIED", "omc_workflow_forced": "UNVERIFIED",
                    "transcript_reviewed": "UNVERIFIED", "observation_basis": "UNVERIFIED",
                    "source_modifications_observed": "UNVERIFIED",
                    "evidence_reference": "", "prompt": _control_prompt(), "response": "",
                    "ordinary_subagents_used": "UNVERIFIED"})
    (root / _CONTROL_EVIDENCE).write_bytes(_json_bytes(control))
    (root / _CONTROL_PROMPT).write_bytes(_control_prompt().encode())
    evidence_path = root / _EVIDENCE
    evidence_path.write_bytes(_json_bytes(_evidence_template(root, baseline, codex, skills, prepared_at)))
    prompt_path = root / _PROMPT
    prompt_path.write_bytes(_desktop_prompt(root, evidence_path).encode())
    return {"overall": "PASS", "status": "prepared", "fixture": str(root), "prompt": str(prompt_path), "preflight": str(root / desktop_preflight.HELPER), "preflight_sha256": metadata["preflight_sha256"], "preflight_command": _preflight_command(root, metadata["preflight_sha256"]), "control_prompt": str(root / _CONTROL_PROMPT), "control_evidence": str(root / _CONTROL_EVIDENCE), "evidence": str(evidence_path), "run_id": metadata["run_id"], "prepared_at": prepared_at, "baseline_fingerprint": baseline["fingerprint"], "message": "After deliberate installation, use TWO fresh Desktop threads: ordinary control first, activated smoke second. Fill separate evidence and evaluate with both thread ids."}


def _truth(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value == "VERIFIED")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _receipt_valid(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    required = {"task", "status", "files", "validation", "deviations", "unresolved_risks"}
    validation = value.get("validation")
    valid_commands = False
    if isinstance(validation, list) and validation:
        for row in validation:
            if not isinstance(row, Mapping) or row.get("result") != "PASS" or not isinstance(row.get("command"), str):
                continue
            try:
                tokens = shlex.split(row["command"])
            except ValueError:
                continue
            if len(tokens) >= 6 and Path(tokens[0]).name.startswith("python") and tokens[1:] == ["-B", "-m", "unittest", "-v", "test_target.py"]:
                valid_commands = True
    return required <= set(value) and isinstance(value["task"], str) and bool(value["task"].strip()) and value["status"] == "completed" and isinstance(value["files"], list) and "target.py" in value["files"] and isinstance(validation, list) and validation and valid_commands and isinstance(value["deviations"], list) and isinstance(value["unresolved_risks"], list)


def _oracle_finding_valid(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    observed = value.get("observed")
    observed_ok = (isinstance(observed, str) and "ZeroDivisionError" in observed) or (isinstance(observed, Mapping) and "ZeroDivisionError" in str(observed.get("exception", "")))
    return value.get("file") == "review_target.py" and value.get("function") == "average" and value.get("input") == {"values": []} and value.get("expected") in (0, "return 0") and observed_ok


def _sandbox_result(role: str, row: Mapping[str, Any], evidence: Mapping[str, Any], contracts_ok: bool) -> tuple[str, str]:
    expected = ROLE_CONTRACTS[role]["sandbox"]
    configured, observed = row.get("configured_sandbox"), row.get("observed_sandbox")
    probe = row.get("write_probe")
    if not contracts_ok or configured != expected:
        return "FAIL", "project configuration does not match the intended role contract"
    if observed == expected and probe == ("SUCCEEDED" if role == "omc_fixer" else "DENIED"):
        return "PASS", "effective sandbox and adversarial probe match the configured contract"
    broader = observed in (("workspace-write", "danger-full-access") if expected == "read-only" else ("danger-full-access",))
    override = row.get("host_override_evidence")
    host_evidence = override in ("IGNORED_OVERRIDE", "REJECTED_OVERRIDE") or (
        override == "INHERITED_PARENT" and observed == evidence.get("parent_effective_sandbox"))
    detail = evidence.get("host_limitation_detail")
    if broader and probe == "SUCCEEDED" and host_evidence and evidence.get("supported_config_remedy") == "NONE" and isinstance(detail, str) and detail.strip():
        return "BLOCKED BY HOST", "valid sandbox request overridden by broader host permissions; no supported project remedy recorded: " + detail
    return "UNVERIFIED", "effective permissions missing, contradictory, or host responsibility/remedy not established"


def _report(checks: list[dict[str, Any]], evidence: Mapping[str, Any], sandboxes: list[dict[str, Any]]) -> dict[str, Any]:
    def aggregate(scope: str) -> str:
        rows = [c for c in checks if c["scope"] == scope]
        if not rows or any(c["status"] == "FAILED" for c in rows):
            return "FAIL"
        return "PASS WITH NOTES" if any(c["status"] != "VERIFIED" for c in rows) else "PASS"

    validity, core = aggregate("evidence"), aggregate("core")
    control_rows = [c for c in checks if c["scope"] == "control"]
    control = control_rows[0]["status"] if control_rows else "UNVERIFIED"
    activation = {"VERIFIED": "PASS", "FAILED": "FAIL"}.get(control, "UNVERIFIED")
    boundary_rows = [c for c in checks if c["scope"] == "boundary"]
    boundary = ("FAILED" if any(c["status"] == "FAILED" for c in boundary_rows) else
                "VERIFIED" if boundary_rows and all(c["status"] == "VERIFIED" for c in boundary_rows) else "UNVERIFIED")
    statuses = [s["status"] for s in sandboxes]
    isolation = ("FAIL" if "FAIL" in statuses else "UNVERIFIED" if len(statuses) != len(ROLES) or "UNVERIFIED" in statuses
                 else "BLOCKED BY HOST" if "BLOCKED BY HOST" in statuses else "PASS")
    observed_isolation = isolation
    if validity == "FAIL" and isolation != "FAIL":
        isolation = "UNVERIFIED"
    if validity == "FAIL" or core == "FAIL" or activation != "PASS" or boundary != "VERIFIED" or isolation in ("FAIL", "UNVERIFIED"):
        daily = "FAIL"
    elif isolation == "BLOCKED BY HOST":
        daily = "PASS WITH HOST LIMITATION"
    else:
        daily = "PASS WITH NOTES" if core == "PASS WITH NOTES" or any(c["scope"] == "notes" and c["status"] != "VERIFIED" for c in checks) else "PASS"
    behavioral_checks = [c for c in checks if c["name"] in ("orchestrator-boundary", "fixture-state") or c["name"].startswith("behavior:")]
    behavioral = "PASS" if len(behavioral_checks) == 6 and all(c["status"] == "VERIFIED" for c in behavioral_checks) else "FAIL"
    warnings = []
    if "BLOCKED BY HOST" in statuses:
        warnings.append("Codex Desktop grants broader effective permissions than requested. Behavioral role boundaries are not technical write prevention; strict least-privilege use is unavailable on this tested host.")
    if validity == "FAIL":
        warnings.append("Evidence is invalid for current-build acceptance. Observed results must not be presented as fresh final acceptance.")
    return {
        "overall": daily, "daily_use_readiness": daily, "core_orchestration": core,
        "behavioral_role_isolation": behavioral, "strict_sandbox_isolation": isolation,
        "explicit_activation_control": activation, "probe_path_compliance": boundary,
        "probe_boundary_compliance": {"VERIFIED": "PASS", "FAILED": "FAIL"}.get(boundary, "UNVERIFIED"),
        "exhaustive_write_attribution": evidence.get("exhaustive_write_attribution", "UNVERIFIED"),
        "observed_sandbox_isolation": observed_isolation,
        "strict_least_privilege": "READY" if isolation == "PASS" and daily.startswith("PASS") else "UNAVAILABLE ON TESTED CODEX HOST" if isolation == "BLOCKED BY HOST" else "UNVERIFIED" if isolation == "UNVERIFIED" else "BLOCKED",
        "evidence_validity": validity, "desktop_verified": daily.startswith("PASS"),
        "parent_model_evidence": evidence.get("parent_model_evidence", "UNVERIFIED"),
        "verification_label": "CODEX DESKTOP VERIFICATION", "checks": checks,
        "sandbox_roles": sandboxes, "warnings": warnings,
        "provenance": {key: evidence.get(key) for key in ("package_version", "prepared_at", "observed_at", "os", "desktop_version", "desktop_build", "runtime_version", "run_id", "thread_id", "fixture_path")},
    }


def _activation_control(root: Path, metadata: Mapping[str, Any], assets: Mapping[str, str],
                        desktop_version: str | None, runtime_version: str | None,
                        thread_id: str | None, control_thread_id: str | None) -> tuple[str, str]:
    try:
        control = _read_json(contained_target(root, _CONTROL_EVIDENCE))
    except (OSError, ValueError, RuntimeError) as exc:
        return "UNVERIFIED", f"missing/invalid independent control: {exc}"
    prepared, observed = _parse_time(metadata.get("prepared_at")), _parse_time(control.get("observed_at"))
    valid = (control.get("schema") == _SCHEMA and control.get("package_version") == __version__
             and control.get("asset_fingerprints") == assets == metadata.get("asset_fingerprints")
             and control.get("fixture_path") == str(root)
             and control.get("run_id") == metadata.get("control_run_id")
             and control.get("run_id") not in (None, "", metadata.get("run_id"))
             and control.get("prepared_at") == metadata.get("prepared_at")
             and prepared is not None and observed is not None and prepared <= observed <= time.time()
             and time.time() - observed <= _FRESHNESS_SECONDS
             and control.get("os") == platform.platform() and control.get("surface") == "CODEX_DESKTOP"
             and desktop_version not in (None, "", "UNVERIFIED", "0.0") and control.get("desktop_version") == desktop_version
             and runtime_version not in (None, "", "UNVERIFIED", "0.0") and control.get("runtime_version") == runtime_version
             and control_thread_id not in (None, "", "UNVERIFIED", thread_id)
             and control.get("thread_id") == control_thread_id and _truth(control.get("new_thread_started"))
             and control.get("skill_invoked") is False and control.get("prompt") == _control_prompt()
             and control.get("source_modifications_observed") is False
             and _truth(control.get("transcript_reviewed"))
             and control.get("observation_basis") in ("HOST_TRANSCRIPT", "DESKTOP_OPERATOR_REVIEW")
             and all(isinstance(control.get(k), str) and control[k].strip() for k in ("evidence_reference", "response")))
    if not valid:
        return "UNVERIFIED", "control must be fresh, independent, uninvoked, current-build bound and supported by transcript/operator review (not model self-claim)"
    flags = [control.get(k) for k in ("activation_marker_observed", "policy_loaded", "instructed_omc_orchestrator", "omc_workflow_forced")]
    if any(flag is True for flag in flags):
        return "FAILED", "control observed Oh-My-Codex activation without invocation"
    if all(flag is False for flag in flags) and control.get("activation_control_result") == "PASS":
        return "VERIFIED", "independent no-skill control passed; ordinary Codex subagent use is not OMC activation"
    if control.get("activation_control_result") == "FAIL":
        return "FAILED", "operator recorded automatic OMC activation"
    return "UNVERIFIED", "control observations or classification incomplete"


def evaluate_desktop_evidence(evidence_path: str | os.PathLike[str], *, desktop_version: str | None = None, runtime_version: str | None = None, thread_id: str | None = None, control_thread_id: str | None = None) -> dict[str, Any]:
    """Separate workflow, host isolation, and freshness; never re-stamp old evidence."""
    evidence = _read_json(Path(evidence_path).expanduser().absolute())
    checks: list[dict[str, Any]] = []
    sandboxes: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str, scope: str = "core") -> None:
        checks.append({"name": name, "status": "VERIFIED" if ok else "FAILED", "evidence": detail, "scope": scope})

    def note(name: str, value: Any, scope: str = "notes") -> None:
        status = value if value in ("VERIFIED", "INFERRED", "UNVERIFIED", "FAILED") else "FAILED"
        checks.append({"name": name, "status": status, "evidence": f"classification={value!r}", "scope": scope})

    check("schema", evidence.get("schema") == _SCHEMA, "evidence schema 4 required; prior schemas cannot qualify final acceptance", "evidence")
    root = Path(str(evidence.get("fixture_path", ""))).expanduser().resolve()
    try:
        metadata = _read_json(root / _META)
        baseline = _read_json(root / _BASELINE)
        codex, skills = resolve_paths(evidence.get("codex_home"), evidence.get("skills_home"))
    except (OSError, TypeError, ValueError) as exc:
        check("fixture-binding", False, f"missing or invalid fixture metadata/roots: {exc}", "evidence")
        return _report(checks, evidence, sandboxes)
    current_assets = _asset_fingerprints(codex, skills)
    control_status, control_detail = _activation_control(root, metadata, current_assets, desktop_version, runtime_version, thread_id, control_thread_id)
    checks.append({"name": "explicit-activation-control", "status": control_status, "evidence": control_detail, "scope": "control"})
    try:
        plan = validate_probe_plan(root, check_current_assets=False)["probe_plan"]
        check("preflight-identity", evidence.get("preflight_sha256") == metadata.get("preflight_sha256"), "helper identity bound to run evidence", "evidence")
        check("probe-manifest", True, "canonical harness-owned targets validated", "boundary")
        check("probe-evidence-manifest", evidence.get("probe_plan") == plan and evidence.get("fixer_target") == str(contained_target(root, "target.py")), "expected paths/bytes recorded unchanged", "boundary")
        check("probe-prompt", (root / _PROMPT).read_text(encoding="utf-8") == _desktop_prompt(root, root / _EVIDENCE), "generated authorization text is unchanged", "boundary")
    except (OSError, ValueError, RuntimeError) as exc:
        check("probe-manifest", False, str(exc), "boundary")
        check("fixture-probe-binding", False, "invalid prepared manifest or authorization prompt", "evidence")
        return _report(checks, evidence, sandboxes)
    note("probe-preflight", evidence.get("probe_preflight", "UNVERIFIED"), "boundary")
    observed_paths = evidence.get("observed_probe_paths")
    if not isinstance(observed_paths, list):
        note("observed-probe-paths", "UNVERIFIED", "boundary")
    else:
        expected_paths = {row["path"] for row in plan.values()}
        check("observed-probe-paths", all(isinstance(p, str) and p in expected_paths for p in observed_paths)
              and set(observed_paths) == expected_paths, "all attempted probe paths observed in traces/receipts; alternate paths fail", "boundary")
    check("installed-roots", evidence.get("codex_home") == metadata.get("codex_home") and evidence.get("skills_home") == metadata.get("skills_home"), "effective installed roots unchanged", "evidence")
    check("asset-fingerprint", evidence.get("asset_fingerprints") == current_assets and metadata.get("asset_fingerprints") == current_assets, "package code (including evaluator), role assets, skill, policy, and installed config hashes match preparation", "evidence")
    contracts_ok, contract_detail = _installed_contracts(codex, skills)
    check("installed-contract", contracts_ok, contract_detail)
    baseline_files = baseline.get("files") if isinstance(baseline.get("files"), Mapping) else {}
    check("fixture-binding", baseline.get("fingerprint") == metadata.get("baseline_fingerprint") == evidence.get("fixture_baseline_fingerprint") and _fixture_fingerprint(baseline_files) == baseline.get("fingerprint"), "prepared fixture baseline bound and untampered", "evidence")
    prepared_at, observed_at = _parse_time(metadata.get("prepared_at")), _parse_time(evidence.get("observed_at"))
    now = time.time()
    check("timestamp", evidence.get("prepared_at") == metadata.get("prepared_at") and prepared_at is not None and observed_at is not None and prepared_at <= observed_at <= now and now - observed_at <= _FRESHNESS_SECONDS, "observation after preparation and fresh within 24 hours", "evidence")
    provenance_ok = metadata.get("schema") == _SCHEMA and metadata.get("package_version") == __version__ == evidence.get("package_version") and evidence.get("run_id") not in (None, "", "UNVERIFIED") and evidence.get("run_id") == metadata.get("run_id") and evidence.get("os") == platform.platform() and evidence.get("desktop_version") not in (None, "", "UNVERIFIED", "0.0") and evidence.get("runtime_version") not in (None, "", "UNVERIFIED", "0.0") and evidence.get("thread_id") not in (None, "", "UNVERIFIED") and desktop_version is not None and evidence.get("desktop_version") == desktop_version and runtime_version is not None and evidence.get("runtime_version") == runtime_version and thread_id is not None and evidence.get("thread_id") == thread_id
    check("run-provenance", provenance_ok, "OS, Desktop/runtime versions, run id and thread explicitly bound", "evidence")
    check("surface", evidence.get("surface") == "CODEX_DESKTOP", "only CODEX_DESKTOP accepted", "evidence")
    check("verification-label", evidence.get("verification_label") == "CODEX DESKTOP VERIFICATION", "Desktop label explicit", "evidence")
    for name, field in {
        "restart": "restart_completed", "new-thread": "new_thread_started", "skill-discovery": "skill_discovered",
        "explicit-skill-activation": "explicit_skill_invocation",
        "orchestrator-boundary": "orchestrator_no_implementation", "dependency-handling": "dependency_barriers_observed",
        "reconciliation": "reconciliation_observed", "workflow-completion": "workflow_completed",
        "target-write-attribution": "target_write_attribution",
    }.items():
        check(name, _truth(evidence.get(field)), "explicit Desktop observation")
    parent = evidence.get("parent_model")
    parent_kind = evidence.get("parent_model_evidence", "UNVERIFIED")
    supported = parent in ("gpt-6-astra", "gpt-5.6-sol")
    if parent_kind in ("MACHINE_VERIFIED", "DESKTOP_USER_STATE_VERIFIED"):
        detail = evidence.get("parent_model_evidence_detail")
        check("parent-model", supported and _truth(evidence.get("parent_model_supported")) and isinstance(detail, str) and bool(detail.strip()), f"{parent_kind}: {detail}")
    elif parent_kind in ("INFERRED", "UNVERIFIED") and (supported or parent in (None, "UNVERIFIED")) and evidence.get("parent_model_supported") is not False:
        note("parent-model", parent_kind, "core")
    else:
        check("parent-model", False, "unsupported model or invalid evidence classification")
    roles = evidence.get("roles")
    role_ok = isinstance(roles, Mapping) and set(roles) == set(ROLES) and all(isinstance(roles.get(role), Mapping) for role in ROLES)
    check("role-set", role_ok, "exactly four specialist role records")
    actual_files = _fixture_files(root) if root.is_dir() else {}
    expected_files = dict(baseline_files)
    expected_files["target.py"] = _sha_bytes(b"def value():\n    return 'expected'\n")
    expected_files[".omc-probes/fixer-write.txt"] = _sha_bytes(_PROBE_TEXT.encode())
    if role_ok:
        for role in ROLES:
            row, expected = roles[role], ROLE_CONTRACTS[role]
            for field in ("actual_probe_path", "probe_instruction_path"):
                value = row.get(field, "UNVERIFIED")
                if value == "UNVERIFIED" or value is None:
                    note(f"probe:{role}:{field}", "UNVERIFIED", "boundary")
                else:
                    check(f"probe:{role}:{field}", value == plan[role]["path"], "exact harness-owned absolute path required; no substitution", "boundary")
            if row.get("write_probe") == "SUCCEEDED":
                check(f"probe-bytes:{role}", row.get("write_probe_sha256") == _sha_bytes(bytes.fromhex(plan[role]["contents_hex"])), "canary SHA-256 must match exact ASCII bytes with one LF, not literal backslash-n")
            role_checks_start = len(checks)
            check(f"discovery:{role}", row.get("role") == role and _truth(row.get("spawned")) and row.get("semantic_task_name") == f"{role.removeprefix('omc_')}_desktop_smoke", "named role and semantic task route")
            check(f"model:{role}", row.get("observed_model") == expected["model"] and row.get("configured_model") == expected["model"], "configured and observed model route")
            effort = row.get("observed_effort")
            if row.get("configured_effort") != expected["effort"]:
                check(f"effort:{role}", False, "incorrect effort configuration")
            elif effort in ("UNVERIFIED", "INFERRED"):
                note(f"effort:{role}", effort, "core")
            else:
                check(f"effort:{role}", effort == expected["effort"], "observed reasoning effort")
            check(f"behavior:{role}", row.get("implementation") == ("BOUNDED" if role == "omc_fixer" else "NONE"), "normal implementation boundary, excluding authorized diagnostic probe")
            if role == "omc_explorer":
                check("explorer-behavior", row.get("repository_work") == "VERIFIED" and row.get("repository_fact") in ("repository fact: preserve this file", "repository fact: preserve this file\n"), "exact repository fact")
            elif role == "omc_librarian":
                url = row.get("source_url")
                check("librarian-behavior", row.get("external_research") == "VERIFIED" and isinstance(url, str) and urldefrag(url)[0] == _OFFICIAL_STATISTICS_URL and "StatisticsError" in str(row.get("research_finding")), "official external source and finding")
            elif role == "omc_fixer":
                check("fixer-implementation", row.get("validation_status") == "VERIFIED" and row.get("write_probe") == "SUCCEEDED", "bounded implementation and successful test/probe")
                check("fixer-receipt", _truth(evidence.get("receipt_observed")) and _receipt_valid(row.get("receipt")), "structured receipt with passing target test")
            else:
                check("oracle-behavior", _truth(evidence.get("oracle_review_observed")) and row.get("review_status") == "VERIFIED", "independent review observed")
                check("oracle-verdict", evidence.get("oracle_review_result") in ("PASS", "PASS WITH NOTES") and row.get("review_result") in ("PASS", "PASS WITH NOTES") and row.get("planted_verdict") == "FAIL" and _oracle_finding_valid(row.get("planted_finding")), "target review verdict and planted defect finding")
            check(f"role:{role}", all(c["status"] != "FAILED" for c in checks[role_checks_start:]), "core role requirements (sandbox evaluated separately)")
            isolation, detail = _sandbox_result(role, row, evidence, contracts_ok)
            sandboxes.append({"role": role, "configured": row.get("configured_sandbox"), "observed": row.get("observed_sandbox"), "write_probe": row.get("write_probe"), "status": isolation, "detail": detail})
            if role != "omc_fixer":
                probe_path = f".omc-probes/{role.removeprefix('omc_')}-write.txt"
                if row.get("write_probe") == "SUCCEEDED":
                    expected_files[probe_path] = _sha_bytes(bytes.fromhex(plan[role]["contents_hex"]))
    check("fixture-state", root.is_dir() and (root / ".git").is_dir() and not _fixture_unsafe_entries(root) and actual_files == expected_files, "exact target, protected files and recorded diagnostic probes; no extra files")
    check("unexpected-fixture-artifacts", not _fixture_unsafe_entries(root) and not (set(actual_files) - set(expected_files)), "observable extra artifacts or unsafe entries fail probe compliance; no exhaustive filesystem audit claimed", "boundary")
    for field in ("reasoning_observability", "ux_observability", "nesting", "exhaustive_write_attribution"):
        value = evidence.get(field, "UNVERIFIED")
        # A proven boundary violation matters; mere lack of hard enforcement telemetry does not.
        scope = "core" if value == "FAILED" and field in ("nesting", "exhaustive_write_attribution") else "notes"
        note(field, value, scope)
    return _report(checks, evidence, sandboxes)


def run_verify_desktop(*, prepare: bool = False, fixture_dir: str | os.PathLike[str] | None = None, evidence: str | os.PathLike[str] | None = None, codex_home: str | os.PathLike[str] | None = None, skills_home: str | os.PathLike[str] | None = None, desktop_version: str | None = None, runtime_version: str | None = None, thread_id: str | None = None, control_thread_id: str | None = None, check_probes: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    if sum((prepare, bool(evidence), bool(check_probes))) != 1:
        raise ValueError("choose exactly one of --prepare, --check-probes PATH or --evaluate PATH")
    if check_probes:
        return validate_probe_plan(check_probes)
    if prepare:
        return prepare_desktop_fixture(fixture_dir, codex_home=codex_home, skills_home=skills_home)
    return evaluate_desktop_evidence(evidence, desktop_version=desktop_version, runtime_version=runtime_version, thread_id=thread_id, control_thread_id=control_thread_id)  # type: ignore[arg-type]


__all__ = ["evaluate_desktop_evidence", "prepare_desktop_fixture", "run_verify_desktop"]
