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
_asset_paths = _core._asset_paths

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


def _sync_core() -> None:
    # Tests and callers may temporarily replace these facade seams. Keep the
    # implementation module synchronized so those supported seams remain honest.
    _core._asset_fingerprints = _asset_fingerprints
    _core._helper_binding = _helper_binding
    _core._installed_contracts = _installed_contracts


def _helper_bytes(root: Path, metadata: Mapping[str, Any], baseline: Mapping[str, Any]) -> bytes:
    _sync_core()
    return _core._helper_bytes(root, metadata, baseline)


def validate_probe_plan(*args: Any, **kwargs: Any) -> dict[str, Any]:
    _sync_core()
    return _core.validate_probe_plan(*args, **kwargs)


def evaluate_desktop_evidence(*args: Any, **kwargs: Any) -> dict[str, Any]:
    _sync_core()
    return _core.evaluate_desktop_evidence(*args, **kwargs)


def prepare_desktop_fixture(*args: Any, **kwargs: Any) -> dict[str, Any]:
    _sync_core()
    return _core.prepare_desktop_fixture(*args, **kwargs)


def run_verify_desktop(*args: Any, **kwargs: Any) -> dict[str, Any]:
    _sync_core()
    return _core.run_verify_desktop(*args, **kwargs)


_sync_core()

__all__ = ["evaluate_desktop_evidence", "prepare_desktop_fixture", "run_verify_desktop"]
