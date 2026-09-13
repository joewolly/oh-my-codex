"""Regression coverage for copy-safe Desktop preflight dispatch."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from oh_my_codex import desktop


class DesktopPreflightRetryContractTests(unittest.TestCase):
    def _plan(self) -> dict[str, dict[str, str]]:
        """Return deterministic probe paths for prompt-contract tests."""
        return {
            role: {"path": f"/fixture/.omc-probes/{role.removeprefix('omc_')}-write.txt"}
            for role in desktop.ROLES
        }

    def _prompt(self, base: str = "base prompt\n") -> str:
        """Render the public Desktop prompt against deterministic fixture paths."""
        with mock.patch.object(desktop, "_original_desktop_prompt", return_value=base), \
             mock.patch.object(desktop._core, "_probe_plan", return_value=self._plan()):
            return desktop._desktop_prompt(Path("/fixture"), Path("/fixture/evidence.json"), "sha")

    @staticmethod
    def _flat(value: str) -> str:
        """Normalize wrapping so tests assert semantics rather than formatting."""
        return " ".join(value.split())

    def test_canary_paths_are_never_preflight_helper_arguments(self) -> None:
        """Keep helper and canary path roles unambiguous in the generated prompt."""
        prompt = self._prompt()
        flat = self._flat(prompt)
        expected_helper = str(Path("/fixture") / ".omc-probe-preflight.py")
        self.assertIn("PREFLIGHT COPY-SAFETY CONTRACT", prompt)
        self.assertIn(expected_helper, prompt)
        self.assertIn("MUST NEVER be used as the preflight helper argument", flat)
        self.assertIn("do not substitute a role's canary path into it", flat)

    def test_all_four_dispatches_copy_one_canonical_command(self) -> None:
        """Require every specialist dispatch to reuse one canonical gate command."""
        prompt = self._prompt()
        for role in ("Explorer", "Librarian", "Fixer", "Oracle"):
            self.assertIn(
                f"- {role}: copy and execute the canonical retained preflight command verbatim, then dispatch.",
                prompt,
            )
        self.assertIn("Do not reconstruct it from role data", prompt)

    def test_only_narrow_canary_helper_transcription_can_recover(self) -> None:
        """Allow recovery only for the exact helper-path/canary transcription class."""
        flat = self._flat(self._prompt())
        self.assertIn("ONLY recoverable noncanonical form", flat)
        self.assertIn("identical to the canonical command in every token except the helper-path argument", flat)
        self.assertIn("one of the four exact canonical canary paths", flat)
        self.assertIn("interpreter, `-I -S`, Base64 launcher, and pinned SHA must be unchanged", flat)
        self.assertIn("Any other command difference is fatal", flat)

    def test_malformed_transcription_requires_zero_write_contamination(self) -> None:
        """Forbid recovery if a malformed attempt or its aftermath performed a write."""
        flat = self._flat(self._prompt())
        self.assertIn(
            "NO specialist was spawned, and NO source/probe write occurred during or after that malformed attempt",
            flat,
        )
        self.assertIn("copy the canonical retained command verbatim and execute it once for that dispatch", flat)
        self.assertIn("If the canonical retained command itself exits nonzero, STOP", flat)
        self.assertIn("do not retry it, do not delegate, do not write", flat)

    def test_malformed_command_path_is_not_probe_write_evidence(self) -> None:
        """Do not confuse an incidental malformed-command path with a probe write."""
        flat = self._flat(self._prompt())
        self.assertIn("Do not put the malformed command's incidental path into `observed_probe_paths`", flat)
        self.assertIn("unless a diagnostic probe-write was actually attempted there", flat)

    def test_legacy_core_ambiguities_are_rewritten(self) -> None:
        """Eliminate stale core wording before the copy-safety contract is appended."""
        legacy = (
            "base prompt\n"
            "If it exits nonzero, STOP before spawning any specialist or writing probes/source.\n"
            "Record observed_probe_paths as a list of all probe paths seen in tool traces/receipts,\n"
            "including alternate/outside paths. Any alternate path fails this run even if later\n"
            "corrected.\n"
        )
        prompt = self._prompt(legacy)
        self.assertNotIn("If it exits nonzero, STOP before", prompt)
        self.assertIn("CANONICAL retained preflight command exits nonzero", prompt)
        self.assertNotIn("list of all probe paths seen", prompt)
        self.assertIn("diagnostic probe-write TARGET paths actually attempted", prompt)


if __name__ == "__main__":
    unittest.main()
