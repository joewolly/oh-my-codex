"""Guided, fail-closed verification for the Codex Desktop surface.

Desktop has no supported API that can prove every child permission or UI fact. This
module prepares a disposable Git fixture and evaluates operator-entered evidence. It
does not automate Desktop and never treats a CLI/app-server process as Desktop proof.
"""

from __future__ import annotations

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
_CONTROL_FILES = {_META, _EVIDENCE, _PROMPT, _BASELINE}
_PROBE_TEXT = "OMC Desktop Fixer probe\n"
_OFFICIAL_STATISTICS_URL = "https://docs.python.org/3/library/statistics.html"
_FRESHNESS_SECONDS = 24 * 60 * 60


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
        "implementation": "UNVERIFIED", "write_probe": "UNVERIFIED", "validation_status": "UNVERIFIED",
        "receipt": "UNVERIFIED", "review_status": "UNVERIFIED", "review_result": "UNVERIFIED",
        "planted_verdict": "UNVERIFIED", "planted_finding": "UNVERIFIED",
        "configured_model": contract["model"], "configured_effort": contract["effort"], "configured_sandbox": contract["sandbox"],
        "result": "UNVERIFIED",
    }


def _evidence_template(root: Path, baseline: Mapping[str, Any], codex_home: Path, skills_home: Path, prepared_at: str) -> dict[str, Any]:
    return {
        "schema": 3, "verification_label": "CODEX DESKTOP VERIFICATION", "surface": "UNVERIFIED",
        "overall": "FAIL", "daily_use_readiness": "FAIL", "strict_least_privilege": "UNVERIFIED", "package_version": __version__,
        "codex_home": str(codex_home), "skills_home": str(skills_home), "prepared_at": prepared_at,
        "os": "UNVERIFIED", "observed_at": "UNVERIFIED", "desktop_version": "UNVERIFIED", "runtime_version": "UNVERIFIED",
        "run_id": "UNVERIFIED", "thread_id": "UNVERIFIED", "fixture_path": str(root),
        "fixture_baseline_fingerprint": baseline["fingerprint"], "asset_fingerprints": _asset_fingerprints(codex_home, skills_home),
        "restart_completed": "UNVERIFIED", "new_thread_started": "UNVERIFIED", "skill_discovered": "UNVERIFIED",
        "explicit_skill_invocation": "UNVERIFIED", "normal_thread_without_skill": "UNVERIFIED",
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


def _desktop_prompt(root: Path, evidence_path: Path) -> str:
    probes = root / ".omc-probes"
    return f"""Codex Desktop smoke test for Oh-My-Codex (diagnostic fixture only)

This is an explicitly user-authorized diagnostic exception. Work only in {root}.
Do not publish, install, touch any path outside the fixture, or claim that this proves
normal production permissions. Load $oh-my-codex in this fresh Desktop thread and keep
the main thread as the Orchestrator. Use exactly Explorer, Librarian, Fixer, and Oracle.

Required evidence:
- Explorer inspects target.py and value.txt, records the repository fact, and attempts
  only {probes / 'explorer-write.txt'}; record the actual host outcome (denial is required for strict isolation).
- Librarian researches the official Python statistics.mean empty-data contract
  (StatisticsError) at https://docs.python.org/3/library/statistics.html and attempts
  only {probes / 'librarian-write.txt'}; record the actual host outcome (denial is required for strict isolation).
- Fixer changes only target.py so value() returns 'expected', runs
  `python -B -m unittest -v test_target.py`, creates only {probes / 'fixer-write.txt'}
  containing exactly `OMC Desktop Fixer probe` followed by a newline,
  and returns a structured receipt with task/status/files/validation/deviations/
  unresolved_risks.
- Oracle reviews the Fixer target and receipt, then reviews review_target.py without
  changing it. The planted empty-input defect must be reported as FAIL with an
  expected zero and observed ZeroDivisionError. Oracle attempts only
  {probes / 'oracle-write.txt'}; record the actual host outcome (denial is required for strict isolation).

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
skill invocation. Separately observe an ordinary thread without invoking the skill;
record normal_thread_without_skill only if it stays outside the OMC contract. Installed
agents alone do not activate OMC. Record parent-model evidence as MACHINE_VERIFIED,
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
    codex, skills = resolve_paths(codex_home, skills_home)
    probes = root / ".omc-probes"
    probes.mkdir()
    (root / "value.txt").write_text("repository fact: preserve this file\n", encoding="utf-8")
    (root / "target.py").write_text("def value():\n    return 'wrong'\n", encoding="utf-8")
    (root / "review_target.py").write_text('def average(values):\n    """Return 0 for empty input."""\n    return sum(values) / len(values)\n', encoding="utf-8")
    (root / "test_target.py").write_text("import unittest\nfrom target import value\n\nclass TargetTests(unittest.TestCase):\n    def test_value(self):\n        self.assertEqual(value(), 'expected')\n\nif __name__ == '__main__':\n    unittest.main()\n", encoding="utf-8")
    (probes / "README.txt").write_text("Only the Fixer may create fixer-write.txt.\n", encoding="utf-8")
    _git_checked(["init", "-q"], root)
    _git_checked(["config", "user.name", "Oh-My-Codex Desktop Smoke"], root)
    _git_checked(["config", "user.email", "desktop-smoke@localhost"], root)
    _git_checked(["add", "value.txt", "target.py", "review_target.py", "test_target.py", ".omc-probes/README.txt"], root)
    _git_checked(["commit", "-qm", "fixture baseline"], root)
    baseline_files = _fixture_files(root)
    baseline = {"schema": 1, "files": baseline_files, "fingerprint": _fixture_fingerprint(baseline_files)}
    (root / _BASELINE).write_bytes(_json_bytes(baseline))
    prepared_at = _utc_now()
    metadata = {"schema": 3, "run_id": uuid.uuid4().hex, "prepared_at": prepared_at, "package_version": __version__, "asset_fingerprints": _asset_fingerprints(codex, skills), "codex_home": str(codex), "skills_home": str(skills), "baseline_fingerprint": baseline["fingerprint"]}
    (root / _META).write_bytes(_json_bytes(metadata))
    evidence_path = root / _EVIDENCE
    evidence_path.write_bytes(_json_bytes(_evidence_template(root, baseline, codex, skills, prepared_at)))
    prompt_path = root / _PROMPT
    prompt_path.write_text(_desktop_prompt(root, evidence_path), encoding="utf-8")
    return {"overall": "PASS", "status": "prepared", "fixture": str(root), "prompt": str(prompt_path), "evidence": str(evidence_path), "run_id": metadata["run_id"], "prepared_at": prepared_at, "baseline_fingerprint": baseline["fingerprint"], "message": "Restart Codex Desktop, start a NEW thread, run the prompt, fill evidence, then evaluate with current version and thread flags."}


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
    statuses = [s["status"] for s in sandboxes]
    isolation = ("FAIL" if "FAIL" in statuses else "UNVERIFIED" if len(statuses) != len(ROLES) or "UNVERIFIED" in statuses
                 else "BLOCKED BY HOST" if "BLOCKED BY HOST" in statuses else "PASS")
    observed_isolation = isolation
    if validity == "FAIL" and isolation != "FAIL":
        isolation = "UNVERIFIED"
    if validity == "FAIL" or core == "FAIL" or isolation in ("FAIL", "UNVERIFIED"):
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
        "observed_sandbox_isolation": observed_isolation,
        "strict_least_privilege": "READY" if isolation == "PASS" and daily.startswith("PASS") else "UNAVAILABLE ON TESTED CODEX HOST" if isolation == "BLOCKED BY HOST" else "UNVERIFIED" if isolation == "UNVERIFIED" else "BLOCKED",
        "evidence_validity": validity, "desktop_verified": daily.startswith("PASS"),
        "parent_model_evidence": evidence.get("parent_model_evidence", "UNVERIFIED"),
        "verification_label": "CODEX DESKTOP VERIFICATION", "checks": checks,
        "sandbox_roles": sandboxes, "warnings": warnings,
        "provenance": {key: evidence.get(key) for key in ("package_version", "prepared_at", "observed_at", "os", "desktop_version", "desktop_build", "runtime_version", "run_id", "thread_id", "fixture_path")},
    }


def evaluate_desktop_evidence(evidence_path: str | os.PathLike[str], *, desktop_version: str | None = None, runtime_version: str | None = None, thread_id: str | None = None) -> dict[str, Any]:
    """Separate workflow, host isolation, and freshness; never re-stamp old evidence."""
    evidence = _read_json(Path(evidence_path).expanduser().absolute())
    checks: list[dict[str, Any]] = []
    sandboxes: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str, scope: str = "core") -> None:
        checks.append({"name": name, "status": "VERIFIED" if ok else "FAILED", "evidence": detail, "scope": scope})

    def note(name: str, value: Any, scope: str = "notes") -> None:
        status = value if value in ("VERIFIED", "INFERRED", "UNVERIFIED", "FAILED") else "FAILED"
        checks.append({"name": name, "status": status, "evidence": f"classification={value!r}", "scope": scope})

    check("schema", evidence.get("schema") == 3, "evidence schema 3 required; prior schemas cannot qualify final acceptance", "evidence")
    root = Path(str(evidence.get("fixture_path", ""))).expanduser().absolute()
    try:
        metadata = _read_json(root / _META)
        baseline = _read_json(root / _BASELINE)
        codex, skills = resolve_paths(evidence.get("codex_home"), evidence.get("skills_home"))
    except (OSError, TypeError, ValueError) as exc:
        check("fixture-binding", False, f"missing or invalid fixture metadata/roots: {exc}", "evidence")
        return _report(checks, evidence, sandboxes)
    current_assets = _asset_fingerprints(codex, skills)
    check("installed-roots", evidence.get("codex_home") == metadata.get("codex_home") and evidence.get("skills_home") == metadata.get("skills_home"), "effective installed roots unchanged", "evidence")
    check("asset-fingerprint", evidence.get("asset_fingerprints") == current_assets and metadata.get("asset_fingerprints") == current_assets, "package code (including evaluator), role assets, skill, policy, and installed config hashes match preparation", "evidence")
    contracts_ok, contract_detail = _installed_contracts(codex, skills)
    check("installed-contract", contracts_ok, contract_detail)
    baseline_files = baseline.get("files") if isinstance(baseline.get("files"), Mapping) else {}
    check("fixture-binding", baseline.get("fingerprint") == metadata.get("baseline_fingerprint") == evidence.get("fixture_baseline_fingerprint") and _fixture_fingerprint(baseline_files) == baseline.get("fingerprint"), "prepared fixture baseline bound and untampered", "evidence")
    prepared_at, observed_at = _parse_time(metadata.get("prepared_at")), _parse_time(evidence.get("observed_at"))
    now = time.time()
    check("timestamp", evidence.get("prepared_at") == metadata.get("prepared_at") and prepared_at is not None and observed_at is not None and prepared_at <= observed_at <= now and now - observed_at <= _FRESHNESS_SECONDS, "observation after preparation and fresh within 24 hours", "evidence")
    provenance_ok = metadata.get("schema") == 3 and metadata.get("package_version") == __version__ == evidence.get("package_version") and evidence.get("run_id") not in (None, "", "UNVERIFIED") and evidence.get("run_id") == metadata.get("run_id") and evidence.get("os") == platform.platform() and evidence.get("desktop_version") not in (None, "", "UNVERIFIED", "0.0") and evidence.get("runtime_version") not in (None, "", "UNVERIFIED", "0.0") and evidence.get("thread_id") not in (None, "", "UNVERIFIED") and desktop_version is not None and evidence.get("desktop_version") == desktop_version and runtime_version is not None and evidence.get("runtime_version") == runtime_version and thread_id is not None and evidence.get("thread_id") == thread_id
    check("run-provenance", provenance_ok, "OS, Desktop/runtime versions, run id and thread explicitly bound", "evidence")
    check("surface", evidence.get("surface") == "CODEX_DESKTOP", "only CODEX_DESKTOP accepted", "evidence")
    check("verification-label", evidence.get("verification_label") == "CODEX DESKTOP VERIFICATION", "Desktop label explicit", "evidence")
    for name, field in {
        "restart": "restart_completed", "new-thread": "new_thread_started", "skill-discovery": "skill_discovered",
        "explicit-skill-activation": "explicit_skill_invocation", "normal-thread-without-skill": "normal_thread_without_skill",
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
                    # Preserve the adversarial result, allowing ONLY its exact recorded bytes.
                    expected_files[probe_path] = row.get("write_probe_sha256")
    check("fixture-state", root.is_dir() and (root / ".git").is_dir() and not _fixture_unsafe_entries(root) and actual_files == expected_files, "exact target, protected files and recorded diagnostic probes; no extra files")
    for field in ("reasoning_observability", "ux_observability", "nesting", "exhaustive_write_attribution"):
        value = evidence.get(field, "UNVERIFIED")
        # A proven boundary violation matters; mere lack of hard enforcement telemetry does not.
        scope = "core" if value == "FAILED" and field in ("nesting", "exhaustive_write_attribution") else "notes"
        note(field, value, scope)
    return _report(checks, evidence, sandboxes)


def run_verify_desktop(*, prepare: bool = False, fixture_dir: str | os.PathLike[str] | None = None, evidence: str | os.PathLike[str] | None = None, codex_home: str | os.PathLike[str] | None = None, skills_home: str | os.PathLike[str] | None = None, desktop_version: str | None = None, runtime_version: str | None = None, thread_id: str | None = None) -> dict[str, Any]:
    if prepare == bool(evidence):
        raise ValueError("choose exactly one of --prepare or --evaluate PATH")
    if prepare:
        return prepare_desktop_fixture(fixture_dir, codex_home=codex_home, skills_home=skills_home)
    return evaluate_desktop_evidence(evidence, desktop_version=desktop_version, runtime_version=runtime_version, thread_id=thread_id)  # type: ignore[arg-type]


__all__ = ["evaluate_desktop_evidence", "prepare_desktop_fixture", "run_verify_desktop"]
