"""Regression coverage for the generated Desktop evidence vocabulary."""
from __future__ import annotations

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
        self.assertIn("do not misclassify it as an `observed_probe_paths` entry", prompt)
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

    def test_sync_core_installs_prompt_contract_seam(self) -> None:
        desktop._sync_core()
        self.assertIs(desktop_core._desktop_prompt, desktop._desktop_prompt)


if __name__ == "__main__":
    unittest.main()
