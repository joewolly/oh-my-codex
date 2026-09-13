"""Regression coverage for the generated Desktop evidence vocabulary."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from oh_my_codex import desktop, desktop_core


class DesktopEvidencePromptContractTests(unittest.TestCase):
    def _plan(self) -> dict[str, dict[str, str]]:
        return {
            role: {"path": f"/fixture/.omc-probes/{role.removeprefix('omc_')}-write.txt"}
            for role in desktop.ROLES
        }

    def test_prompt_distinguishes_probe_write_attempts_from_incidental_reads(self) -> None:
        with mock.patch.object(desktop, "_original_desktop_prompt", return_value="base prompt\n"), \
             mock.patch.object(desktop._core, "_probe_plan", return_value=self._plan()):
            prompt = desktop._desktop_prompt(Path("/fixture"), Path("/fixture/evidence.json"), "sha")

        self.assertIn("diagnostic PROBE-WRITE TARGETS ACTUALLY ATTEMPTED", prompt)
        self.assertIn("Do NOT add a path merely because it was read", prompt)
        self.assertIn("no diagnostic write was attempted there", prompt)
        self.assertIn("`observed_probe_paths` entry", prompt)
        self.assertIn("/fixture/.omc-probes/fixer-write.txt", prompt)

    def test_prompt_pins_machine_enforced_enums_and_path_meaning(self) -> None:
        with mock.patch.object(desktop, "_original_desktop_prompt", return_value="base prompt\n"), \
             mock.patch.object(desktop._core, "_probe_plan", return_value=self._plan()):
            prompt = desktop._desktop_prompt(Path("/fixture"), Path("/fixture/evidence.json"), "sha")

        self.assertIn("`write_probe`: exactly `SUCCEEDED`, `DENIED`, or `UNVERIFIED`", prompt)
        self.assertIn("`observed_sandbox`: exactly `read-only`, `workspace-write`, `danger-full-access`, or", prompt)
        self.assertIn("`host_override_evidence`: exactly `IGNORED_OVERRIDE`, `REJECTED_OVERRIDE`,", prompt)
        self.assertIn("`parent_effective_sandbox`: exactly `read-only`, `workspace-write`,", prompt)
        self.assertIn("`supported_config_remedy`: exactly `NONE`", prompt)
        self.assertIn("This field is\n  NOT the path of desktop-prompt.txt", prompt)

    def test_prompt_pins_role_semantics_and_structured_receipts(self) -> None:
        with mock.patch.object(desktop, "_original_desktop_prompt", return_value="base prompt\n"), \
             mock.patch.object(desktop._core, "_probe_plan", return_value=self._plan()):
            prompt = desktop._desktop_prompt(Path("/fixture"), Path("/fixture/evidence.json"), "sha")

        self.assertIn("`observed_model`: use the exact host-observed model id", prompt)
        self.assertIn("do NOT copy\n  `configured_model`", prompt)
        self.assertIn("`implementation`: exactly `BOUNDED` for Fixer", prompt)
        self.assertIn("`validation_status=\"VERIFIED\"`", prompt)
        self.assertIn("`receipt` MUST be a structured object, never the string `VERIFIED`", prompt)
        self.assertIn("`review_status=\"VERIFIED\"`", prompt)
        self.assertIn("`planted_verdict=\"FAIL\"`", prompt)
        self.assertIn("STRUCTURED `planted_finding`", prompt)

    def test_unobservable_child_model_is_note_but_wrong_observed_model_stays_failure(self) -> None:
        evidence = {
            "roles": {
                role: {"configured_model": contract["model"], "observed_model": "UNVERIFIED"}
                for role, contract in desktop.ROLE_CONTRACTS.items()
            }
        }
        checks = []
        for role in desktop.ROLES:
            checks.extend([
                {"name": f"discovery:{role}", "status": "VERIFIED", "scope": "core", "evidence": ""},
                {"name": f"model:{role}", "status": "FAILED", "scope": "core", "evidence": ""},
                {"name": f"effort:{role}", "status": "UNVERIFIED", "scope": "core", "evidence": ""},
                {"name": f"behavior:{role}", "status": "VERIFIED", "scope": "core", "evidence": ""},
                {"name": f"role:{role}", "status": "FAILED", "scope": "core", "evidence": ""},
            ])
        checks.extend([
            {"name": "orchestrator-boundary", "status": "VERIFIED", "scope": "core", "evidence": ""},
            {"name": "fixture-state", "status": "VERIFIED", "scope": "core", "evidence": ""},
        ])
        report = {
            "checks": checks,
            "core_orchestration": "FAIL",
            "overall": "FAIL",
            "daily_use_readiness": "FAIL",
            "desktop_verified": False,
            "evidence_validity": "PASS",
            "explicit_activation_control": "PASS",
            "probe_boundary_compliance": "PASS",
            "strict_sandbox_isolation": "BLOCKED BY HOST",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.json"
            path.write_text(json.dumps(evidence), encoding="utf-8")
            adjusted = desktop._adjust_unobservable_role_models(report, path)

        self.assertEqual(adjusted["core_orchestration"], "PASS WITH NOTES")
        self.assertEqual(adjusted["overall"], "PASS WITH HOST LIMITATION")
        self.assertTrue(adjusted["desktop_verified"])
        self.assertTrue(all(
            next(c for c in adjusted["checks"] if c["name"] == f"model:{role}")["status"] == "UNVERIFIED"
            for role in desktop.ROLES
        ))

        evidence["roles"]["omc_explorer"]["observed_model"] = "wrong-model"
        wrong_report = json.loads(json.dumps(report))
        wrong_report["checks"] = json.loads(json.dumps(checks))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.json"
            path.write_text(json.dumps(evidence), encoding="utf-8")
            unchanged = desktop._adjust_unobservable_role_models(wrong_report, path)
        explorer = next(c for c in unchanged["checks"] if c["name"] == "model:omc_explorer")
        self.assertEqual(explorer["status"], "FAILED")

    def test_sync_core_installs_prompt_and_evaluator_contract_seams(self) -> None:
        desktop._sync_core()
        self.assertIs(desktop_core._desktop_prompt, desktop._desktop_prompt)
        self.assertIs(desktop_core.evaluate_desktop_evidence, desktop.evaluate_desktop_evidence)


if __name__ == "__main__":
    unittest.main()
