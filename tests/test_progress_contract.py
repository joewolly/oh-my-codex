from __future__ import annotations

import unittest
from pathlib import Path

import oh_my_codex


class ProgressContractTests(unittest.TestCase):
    def setUp(self) -> None:
        package_root = Path(oh_my_codex.__file__).resolve().parent
        self.skill = (package_root / "assets/skills/oh-my-codex/SKILL.md").read_text(encoding="utf-8")

    def test_orchestrator_owns_one_canonical_overall_progress_plan(self) -> None:
        self.assertIn("## Overall plan progress", self.skill)
        self.assertIn("one canonical\nuser-visible progress plan", self.skill)
        self.assertIn("Specialists never create, replace, or maintain a competing top-level plan", self.skill)

    def test_progress_plan_uses_codex_update_plan_when_available(self) -> None:
        self.assertIn("When the Codex `update_plan` tool is available, the Orchestrator MUST use it", self.skill)
        self.assertIn("If `update_plan` is unavailable on\nthe current host, orchestration may continue", self.skill)

    def test_progress_items_report_current_overall_step_and_total(self) -> None:
        self.assertIn("Number every milestone as\n`N/TOTAL`", self.skill)
        self.assertIn("Exactly one milestone is `in_progress` while active work remains", self.skill)
        self.assertIn("The current\n`in_progress` milestone MUST identify the major overall-plan step presently being\nexecuted", self.skill)

    def test_specialist_activity_rolls_up_under_overall_milestones(self) -> None:
        self.assertIn("Explorer, Librarian, Fixer, and Oracle activity rolls up underneath the applicable overall\nmilestone", self.skill)
        self.assertIn("Their dispatches, retries, receipts, or substeps do not become separate\nuser-facing progress items", self.skill)


if __name__ == "__main__":
    unittest.main()
