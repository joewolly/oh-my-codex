"""Public facade for guided Codex Desktop verification.

The implementation remains in :mod:`desktop_core`; this facade narrows immutable
fingerprinting to Oh-My-Codex-owned assets, validates user-owned Codex config
semantically, binds standalone Desktop preflight to the exact Python 3.11+
interpreter used for preparation, and makes the generated evidence contract explicit.
"""
from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path
from typing import Any, Mapping

from . import desktop_core as _core
from . import desktop_preflight as _preflight

ROLES = _core.ROLES
ROLE_CONTRACTS = _core.ROLE_CONTRACTS
contained_target = _core.contained_target
_asset_paths = _core._asset_paths

_original_asset_fingerprints = _core._asset_fingerprints
_original_helper_binding = _core._helper_binding
_original_installed_contracts = _core._installed_contracts
_original_preflight_command = _core._preflight_command
_original_desktop_prompt = _core._desktop_prompt
_original_evaluate_desktop_evidence = _core.evaluate_desktop_evidence


def _asset_fingerprints(codex_home: Path | None = None, skills_home: Path | None = None) -> dict[str, str]:
    fingerprints = _original_asset_fingerprints(codex_home, skills_home)
    fingerprints.pop("installed-config", None)
    return fingerprints


def _preflight_command(root: Path, helper_sha: str) -> str:
    """Bind the gate to the preparation interpreter instead of ambient PATH."""
    args = shlex.split(_original_preflight_command(root, helper_sha))
    args[0] = str(Path(sys.executable).expanduser().absolute())
    return shlex.join(args)


def _desktop_prompt(root: Path, evidence_path: Path, helper_sha: str | None = None) -> str:
    """Append the evaluator's exact machine-enforced evidence vocabulary."""
    prompt = _original_desktop_prompt(root, evidence_path, helper_sha)
    plan = _core._probe_plan(root)
    exact_paths = "\n".join(
        f"  - {role}: {row['path']}"
        for role, row in plan.items()
    )
    canonical_helper = root / _preflight.HELPER
    return prompt + f"""

PREFLIGHT COPY-SAFETY CONTRACT

The single hash-pinned command printed earlier in this retained prompt is the CANONICAL
PREFLIGHT COMMAND. For Explorer, Librarian, Fixer, and Oracle, immediately before each
dispatch, copy that same command VERBATIM. Do not reconstruct it from role data and do
not substitute a role's canary path into it.

The canonical command's helper argument is always exactly:
{canonical_helper}
Every `.omc-probes/*-write.txt` path is a diagnostic CANARY target and MUST NEVER be used
as the preflight helper argument. The final command argument is the pinned helper SHA
already present in the canonical retained command; copy it, do not recompute or replace
it.

Before executing each dispatch gate, visually/structurally verify that the command still
uses the preparation-time Python interpreter, contains `-I -S`, uses the exact helper
path above, and does not contain any `.omc-probes/` canary path. Then execute it unchanged.

A command that differs from the canonical retained command is NOT an authorized gate.
If such a malformed command is accidentally executed, retain its exact command/output
as a transcription-error note. If NO specialist was spawned and NO source/probe write
occurred after that malformed attempt, immediately copy the canonical retained command
verbatim and execute it once for that dispatch. If the canonical command passes, the
dispatch may continue and `probe_preflight` may remain `VERIFIED` based on the canonical
gates. Do not put the malformed command's incidental path into `observed_probe_paths`
unless a diagnostic probe-write was actually attempted there.

If the canonical retained command itself exits nonzero, STOP exactly as required by the
main gate: do not retry it, do not delegate, do not write, and do not use an alternate
gate. Never alter the Python environment, helper path, helper bytes, or pinned SHA to
make a gate pass.

Pre-dispatch checklist:
- Explorer: copy and execute the canonical retained preflight command verbatim, then dispatch.
- Librarian: copy and execute the canonical retained preflight command verbatim, then dispatch.
- Fixer: copy and execute the canonical retained preflight command verbatim, then dispatch.
- Oracle: copy and execute the canonical retained preflight command verbatim, then dispatch.

MACHINE-ENFORCED EVIDENCE VALUE CONTRACT

The evaluator compares the following values literally. Do not replace an enum, path,
or structured object with explanatory prose. Put explanations only in
`host_limitation_detail` or `notes`.

`observed_probe_paths` means diagnostic PROBE-WRITE TARGETS ACTUALLY ATTEMPTED by the
four specialists, whether the write succeeded or was denied. Include each canonical
attempted canary path exactly once. Do NOT add a path merely because it was read,
listed, mentioned in a prompt/receipt, discovered during inspection, used as cwd, or
observed as a pre-existing file. Any actual probe-write attempt to an alternate or
outside-fixture target is a boundary failure and must still be recorded.

The only authorized probe-write targets are:
{exact_paths}

For every role record these fields exactly:
- `probe_instruction_path`: the role's exact authorized canary path above. This field is
  NOT the path of desktop-prompt.txt, not a description of where the instruction came
  from, and not prose.
- `actual_probe_path`: the exact path that role actually attempted for its diagnostic
  canary. Use `UNVERIFIED` only if the tool trace/receipt cannot establish a path.
- `write_probe`: exactly `SUCCEEDED`, `DENIED`, or `UNVERIFIED`.
- `write_probe_sha256`: exact canary SHA-256 when `write_probe=SUCCEEDED`; otherwise
  `UNVERIFIED` unless the trace independently establishes the bytes/hash.
- `observed_sandbox`: exactly `read-only`, `workspace-write`, `danger-full-access`, or
  `UNVERIFIED`. Never put prose in this field. If the current Desktop permission
  profile/trace proves unrestricted/full filesystem access, normalize that to
  `danger-full-access`.
- `host_override_evidence`: exactly `IGNORED_OVERRIDE`, `REJECTED_OVERRIDE`,
  `INHERITED_PARENT`, or `UNVERIFIED`.
- `observed_model`: use the exact host-observed model id only when current Desktop
  UI/tool/trace evidence exposes it. Expected ids are `gpt-5.6-luna` for Explorer,
  Librarian, and Fixer, and `gpt-5.6-sol` for Oracle. If the current Desktop surface
  does not expose the child model, record exactly `UNVERIFIED`; do NOT copy
  `configured_model` into this field. The evaluator treats unobservable child model
  metadata as a note, but an actually observed wrong model remains a core failure.
- `observed_effort`: exactly `medium`, `high`, `INFERRED`, or `UNVERIFIED` as supported
  by current evidence. Do not copy configured effort into observed effort without an
  observation.
- `implementation`: exactly `BOUNDED` for Fixer and exactly `NONE` for Explorer,
  Librarian, and Oracle. The authorized diagnostic canary does not count as normal
  implementation work.

Role-specific semantic evidence is also literal:
- Explorer: `repository_work="VERIFIED"` and `repository_fact` must be exactly
  `repository fact: preserve this file` (a single trailing newline is also accepted).
- Librarian: `external_research="VERIFIED"`, `source_url` must resolve to
  `https://docs.python.org/3/library/statistics.html`, and `research_finding` must state
  that the empty-data contract raises `StatisticsError`.
- Fixer: set `validation_status="VERIFIED"` only after the required test command passes.
  `receipt` MUST be a structured object, never the string `VERIFIED`, with all of:
  `task` (non-empty string), `status="completed"`, `files` containing `target.py`,
  `validation` containing at least one object with
  `command="python3 -B -m unittest -v test_target.py"` (or the same command with another
  Python executable name) and `result="PASS"`, plus list-valued `deviations` and
  `unresolved_risks`.
- Oracle: `review_status="VERIFIED"` means the independent review was actually
  completed. `review_result` is the verdict on the repaired Fixer target and must be
  `PASS` or `PASS WITH NOTES` when that target is correct. Separately record the planted
  unchanged defect with `planted_verdict="FAIL"` and a STRUCTURED `planted_finding`
  object exactly identifying `file="review_target.py"`, `function="average"`,
  `input={{"values": []}}`, `expected=0` (or `"return 0"`), and an `observed` value
  containing `ZeroDivisionError`. Do not collapse these fields into prose and do not
  use the planted defect's FAIL as Oracle's `review_status` or repaired-target
  `review_result`.

Top-level semantic observations must remain separate from role verdicts:
- `receipt_observed`: true only when the structured Fixer receipt was actually observed.
- `oracle_review_observed`: true only when Oracle's independent review was observed.
- `oracle_review_result`: `PASS` or `PASS WITH NOTES` for the repaired Fixer target.

Parent/host fields are also literal:
- `parent_effective_sandbox`: exactly `read-only`, `workspace-write`,
  `danger-full-access`, or `UNVERIFIED`. Normalize a verified unrestricted/full-access
  Desktop profile to `danger-full-access`; put its human-readable source/detail in
  `host_limitation_detail`.
- `supported_config_remedy`: exactly `NONE` only after current supported configuration
  has been checked and no narrower supported remedy exists; otherwise `UNVERIFIED`.
- `probe_preflight`: exactly `VERIFIED`, `FAILED`, or `UNVERIFIED`.

If a role configured `read-only` successfully creates its canonical canary and current
runtime evidence proves it inherited or received broader permissions, record
`write_probe=SUCCEEDED`, the exact broader `observed_sandbox`, and the applicable exact
`host_override_evidence` value. That is host-limitation evidence; do not relabel the
successful write as denial and do not bury it in prose.

The successful hash-pinned preflight already validates the installed OMC role contract.
Do not inspect, list, or read parent/sibling fixture directories merely to rediscover
probe paths or configuration. Specialists must stay inside the prepared fixture except
for Librarian's required web research. If an outside path is incidentally mentioned or
read but no diagnostic write was attempted there, do not misclassify it as an
`observed_probe_paths` entry.
"""


def _helper_binding(root: Path, metadata: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, Any]:
    binding = _original_helper_binding(root, metadata, baseline)
    config_path = binding["installed_paths"].pop("installed-config", None)
    binding["config_path"] = config_path or str(Path(metadata["codex_home"]) / "config.toml")
    return binding


def _installed_contracts(codex_home: Path, skills_home: Path) -> tuple[bool, str]:
    try:
        _preflight.validate_config(codex_home / "config.toml")
    except (OSError, ValueError, RuntimeError) as exc:
        return False, str(exc)
    return _original_installed_contracts(codex_home, skills_home)


def _adjust_unobservable_role_models(report: dict[str, Any], evidence_path: str | Path) -> dict[str, Any]:
    """Downgrade missing Desktop child-model telemetry to notes, never mismatches."""
    try:
        evidence = json.loads(Path(evidence_path).expanduser().absolute().read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return report
    roles = evidence.get("roles")
    checks = report.get("checks")
    if not isinstance(roles, Mapping) or not isinstance(checks, list):
        return report

    by_name = {row.get("name"): row for row in checks if isinstance(row, dict)}
    role_specific = {
        "omc_explorer": ("explorer-behavior",),
        "omc_librarian": ("librarian-behavior",),
        "omc_fixer": ("fixer-implementation", "fixer-receipt"),
        "omc_oracle": ("oracle-behavior", "oracle-verdict"),
    }
    adjusted = False
    for role, expected in ROLE_CONTRACTS.items():
        row = roles.get(role)
        if not isinstance(row, Mapping) or row.get("configured_model") != expected["model"]:
            continue
        observed = row.get("observed_model")
        if observed not in ("UNVERIFIED", "INFERRED"):
            continue
        model_check = by_name.get(f"model:{role}")
        if isinstance(model_check, dict) and model_check.get("status") == "FAILED":
            model_check["status"] = observed
            model_check["evidence"] = (
                f"child model metadata {observed.lower()} on this Desktop surface; "
                f"configured route remains {expected['model']!r}"
            )
            adjusted = True

        relevant = [f"discovery:{role}", f"model:{role}", f"effort:{role}", f"behavior:{role}", *role_specific[role]]
        role_check = by_name.get(f"role:{role}")
        if isinstance(role_check, dict):
            failures = [by_name.get(name) for name in relevant]
            if all(not isinstance(check, dict) or check.get("status") != "FAILED" for check in failures):
                role_check["status"] = "VERIFIED"
                role_check["evidence"] = "core role requirements satisfied; unobservable model/effort metadata recorded as notes"

    if not adjusted:
        return report

    core_rows = [row for row in checks if isinstance(row, dict) and row.get("scope") == "core"]
    if any(row.get("status") == "FAILED" for row in core_rows):
        core = "FAIL"
    elif any(row.get("status") != "VERIFIED" for row in core_rows):
        core = "PASS WITH NOTES"
    else:
        core = "PASS"
    report["core_orchestration"] = core

    validity = report.get("evidence_validity")
    activation = report.get("explicit_activation_control")
    boundary = report.get("probe_boundary_compliance")
    isolation = report.get("strict_sandbox_isolation")
    if validity == "PASS" and core != "FAIL" and activation == "PASS" and boundary == "PASS" and isolation not in ("FAIL", "UNVERIFIED"):
        if isolation == "BLOCKED BY HOST":
            daily = "PASS WITH HOST LIMITATION"
        else:
            note_rows = [row for row in checks if isinstance(row, dict) and row.get("scope") == "notes"]
            daily = "PASS WITH NOTES" if core == "PASS WITH NOTES" or any(row.get("status") != "VERIFIED" for row in note_rows) else "PASS"
        report["overall"] = daily
        report["daily_use_readiness"] = daily
        report["desktop_verified"] = True
        if isolation == "BLOCKED BY HOST":
            report["strict_least_privilege"] = "UNAVAILABLE ON TESTED CODEX HOST"
    return report


def _sync_core() -> None:
    # Tests and callers may temporarily replace these facade seams. Keep the
    # implementation module synchronized so those supported seams remain honest.
    _core._asset_fingerprints = _asset_fingerprints
    _core._preflight_command = _preflight_command
    _core._desktop_prompt = _desktop_prompt
    _core._helper_binding = _helper_binding
    _core._installed_contracts = _installed_contracts
    _core.evaluate_desktop_evidence = evaluate_desktop_evidence


def _helper_bytes(root: Path, metadata: Mapping[str, Any], baseline: Mapping[str, Any]) -> bytes:
    _sync_core()
    return _core._helper_bytes(root, metadata, baseline)


def validate_probe_plan(*args: Any, **kwargs: Any) -> dict[str, Any]:
    _sync_core()
    return _core.validate_probe_plan(*args, **kwargs)


def evaluate_desktop_evidence(evidence_path: str | Path, *args: Any, **kwargs: Any) -> dict[str, Any]:
    _sync_core()
    report = _original_evaluate_desktop_evidence(evidence_path, *args, **kwargs)
    return _adjust_unobservable_role_models(report, evidence_path)


def prepare_desktop_fixture(*args: Any, **kwargs: Any) -> dict[str, Any]:
    _sync_core()
    return _core.prepare_desktop_fixture(*args, **kwargs)


def run_verify_desktop(*args: Any, **kwargs: Any) -> dict[str, Any]:
    _sync_core()
    return _core.run_verify_desktop(*args, **kwargs)


_sync_core()

__all__ = ["evaluate_desktop_evidence", "prepare_desktop_fixture", "run_verify_desktop"]
