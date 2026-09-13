"""Execution regression for recoverable noncanonical Desktop preflight transcription."""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import oh_my_codex
from oh_my_codex.desktop import prepare_desktop_fixture


class DesktopPreflightRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="omc preflight recovery ")
        base = Path(self.temp.name)
        self.codex = base / "codex"
        self.skills = base / "skills"
        (self.codex / "agents").mkdir(parents=True)
        (self.skills / "oh-my-codex/agents").mkdir(parents=True)

        package = Path(oh_my_codex.__file__).resolve().parent
        for role in ("omc_explorer", "omc_librarian", "omc_fixer", "omc_oracle"):
            shutil.copy2(package / f"assets/agents/{role}.toml", self.codex / f"agents/{role}.toml")
        shutil.copy2(package / "assets/skills/oh-my-codex/SKILL.md", self.skills / "oh-my-codex/SKILL.md")
        shutil.copy2(
            package / "assets/skills/oh-my-codex/agents/openai.yaml",
            self.skills / "oh-my-codex/agents/openai.yaml",
        )
        (self.codex / "config.toml").write_text('model = "gpt-6-astra"\n', encoding="utf-8")

        self.prepared = prepare_desktop_fixture(
            base / "fixture with spaces",
            codex_home=self.codex,
            skills_home=self.skills,
        )
        self.root = Path(self.prepared["fixture"])
        self.canonical = shlex.split(self.prepared["preflight_command"])

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            cwd=self.root.parent,
            env={"PATH": os.defpath, "PYTHONPATH": ""},
            capture_output=True,
            text=True,
        )

    def test_prepared_prompt_has_no_legacy_ambiguities(self) -> None:
        prompt = (self.root / "desktop-prompt.txt").read_text(encoding="utf-8")
        self.assertNotIn("If it exits nonzero, STOP before spawning", prompt)
        self.assertNotIn("list of all probe paths seen", prompt)
        self.assertIn("CANONICAL retained preflight command exits nonzero", prompt)
        self.assertIn("diagnostic probe-write TARGET paths actually attempted", prompt)

    def test_noncanonical_oracle_canary_typo_does_not_poison_canonical_retry(self) -> None:
        first = self._run(self.canonical)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)

        target_before = (self.root / "target.py").read_bytes()
        oracle_canary = self.root / ".omc-probes/oracle-write.txt"
        malformed = list(self.canonical)
        malformed[-2] = str(oracle_canary)

        typo = self._run(malformed)
        self.assertNotEqual(typo.returncode, 0)
        self.assertFalse(oracle_canary.exists())
        self.assertEqual((self.root / "target.py").read_bytes(), target_before)

        retry = self._run(self.canonical)
        self.assertEqual(retry.returncode, 0, retry.stdout + retry.stderr)
        self.assertFalse(oracle_canary.exists())
        self.assertEqual((self.root / "target.py").read_bytes(), target_before)
        self.assertEqual(Path(self.canonical[0]), Path(sys.executable).expanduser().absolute())


if __name__ == "__main__":
    unittest.main()
