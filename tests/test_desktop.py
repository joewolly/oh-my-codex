"""Desktop verification regressions with mutable user-owned config semantics."""
from __future__ import annotations

import shlex

from desktop_suite import DesktopVerificationTests as _DesktopVerificationTests
from oh_my_codex.desktop import _asset_paths, prepare_desktop_fixture


class DesktopVerificationTests(_DesktopVerificationTests):
    # These legacy expectations treated user-owned config.toml as an immutable
    # OMC asset. Hide them and replace them with the ownership-correct contract.
    test_config_change_invalidates_fingerprint = None
    test_standalone_missing_asset_at_preparation_still_fails = None
    test_standalone_every_installed_asset_changed_or_missing_fails = None

    def test_benign_config_rewrite_does_not_invalidate_acceptance(self) -> None:
        self._complete()
        (self.codex / "config.toml").write_text(
            'model = "gpt-6-astra"\n# benign Desktop rewrite\n', encoding="utf-8"
        )
        self.assertEqual(self._evaluate()["evidence_validity"], "PASS")
        gate = self._run_gate()
        self.assertEqual(gate.returncode, 0, gate.stdout + gate.stderr)

    def test_missing_user_config_is_allowed(self) -> None:
        (self.codex / "config.toml").unlink()
        prepared = prepare_desktop_fixture(
            self.root.parent / "missing config fixture",
            codex_home=self.codex,
            skills_home=self.skills,
        )
        result = self._run_gate(shlex.split(prepared["preflight_command"]))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_malformed_user_config_fails_preflight(self) -> None:
        (self.codex / "config.toml").write_text('[agents\n', encoding="utf-8")
        result = self._run_gate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("effective config.toml is invalid", result.stdout)

    def test_agent_discovery_disabled_in_user_config_fails_preflight(self) -> None:
        (self.codex / "config.toml").write_text('[agents]\nenabled = false\n', encoding="utf-8")
        result = self._run_gate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("agents.enabled=false", result.stdout)

    def test_conflicting_omc_role_in_user_config_fails_preflight(self) -> None:
        (self.codex / "config.toml").write_text(
            '[agents.omc_explorer]\nmodel = "gpt-5.6-luna"\n', encoding="utf-8"
        )
        result = self._run_gate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("conflicting OMC roles", result.stdout)

    def test_managed_installed_assets_remain_byte_pinned(self) -> None:
        for name, path in _asset_paths(self.codex, self.skills).items():
            if not name.startswith("installed") or name == "installed-config":
                continue
            original = path.read_bytes()
            for mutation in ("changed", "missing"):
                if mutation == "changed":
                    path.write_bytes(original + b"\n# changed\n")
                else:
                    path.unlink()
                with self.subTest(asset=name, mutation=mutation):
                    result = self._run_gate()
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(name, result.stdout)
                path.write_bytes(original)


del _DesktopVerificationTests
