"""Public facade for guided Codex Desktop verification.

The implementation remains in :mod:`desktop_core`; this facade narrows immutable
fingerprinting to Oh-My-Codex-owned assets and validates user-owned Codex config
semantically so benign Desktop rewrites do not invalidate acceptance.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from . import desktop_core as _core
from . import desktop_preflight as _preflight

ROLES = _core.ROLES
ROLE_CONTRACTS = _core.ROLE_CONTRACTS
contained_target = _core.contained_target

_original_asset_fingerprints = _core._asset_fingerprints
_original_helper_binding = _core._helper_binding
_original_installed_contracts = _core._installed_contracts


def _asset_fingerprints(codex_home: Path | None = None, skills_home: Path | None = None) -> dict[str, str]:
    fingerprints = _original_asset_fingerprints(codex_home, skills_home)
    fingerprints.pop("installed-config", None)
    return fingerprints


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


# The core functions resolve these private helpers through their own module globals.
# Patch those seams once at import so preparation, standalone preflight regeneration,
# control binding, and final evaluation all use the same ownership model.
_core._asset_fingerprints = _asset_fingerprints
_core._helper_binding = _helper_binding
_core._installed_contracts = _installed_contracts

validate_probe_plan = _core.validate_probe_plan
evaluate_desktop_evidence = _core.evaluate_desktop_evidence
prepare_desktop_fixture = _core.prepare_desktop_fixture
run_verify_desktop = _core.run_verify_desktop

__all__ = ["evaluate_desktop_evidence", "prepare_desktop_fixture", "run_verify_desktop"]
