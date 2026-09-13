"""Regression coverage for copy-safe Desktop preflight dispatch."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from oh_my_codex import desktop


class DesktopPreflightRetryContractTests(unittest.TestCase):
    def _plan(self) -> dict[str, dict[str, str]]:
        return {
            role: {"path": f"/fixture/.omc-probes/{role.removeprefix('omc_')}-write.txt"}
            for role in desktop.ROLES
        }

    def _prompt(self) -> str:
        with mock.patch.object(desktop, "_original_desktop_prompt", return_value="base prompt\n"), \
             mock.patch.object(desktop._core, "_probe_plan", return_value=self._plan()):
            return desktop._desktop_prompt(Path("/fixture"), Path("/fixture/evidence.json"), "sha")

    def test_canary_paths_are_never_preflight_helper_arguments(self) -> None:
        prompt = self._prompt()
        self.assertIn("PREFLIGHT COPY-SAFETY CONTRACT", prompt)
        self.assertIn("/fixture/.omc-probe-preflight.py", prompt)
        self.assertIn("MUST NEVER be used\nas the preflight helper argument", prompt)
        self.assertIn("do not substitute a role's canary path into it", prompt)

    def test_all_four_dispatches_copy_one_canonical_command(self) -> None:
        prompt = self._prompt()
        for role in ("Explorer", "Librarian", "Fixer", "Oracle"):
            self.assertIn(
                f"- {role}: copy and execute the canonical retained preflight command verbatim, then dispatch.",
                prompt,
            )
        self.assertIn("Do not reconstruct it from role data", prompt)

    def test_malformed_transcription_can_recover_without_weakening_exact_gate(self) -> None:
        prompt = self._prompt()
        self.assertIn("A command that differs from the canonical retained command is NOT an authorized gate", prompt)
        self.assertIn("NO specialist was spawned and NO source/probe write\noccurred after that malformed attempt", prompt)
        self.assertIn("copy the canonical retained command\nverbatim and execute it once for that dispatch", prompt)
        self.assertIn("If the canonical retained command itself exits nonzero, STOP", prompt)
        self.assertIn("do not retry it, do not delegate, do not write", prompt)

    def test_malformed_command_path_is_not_probe_write_evidence(self) -> None:
        prompt = self._prompt()
        self.assertIn("Do not put the malformed command's incidental path into `observed_probe_paths`", prompt)
        self.assertIn("unless a diagnostic probe-write was actually attempted there", prompt)


if __name__ == "__main__":
    unittest.main()
