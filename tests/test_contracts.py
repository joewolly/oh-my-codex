"""Small contract checks for the shipped role and skill assets."""

from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "oh_my_codex" / "assets" / "agents"
ROLE_NAMES = {
    "omc_explorer": ("gpt-5.6-luna", "medium", "read-only"),
    "omc_librarian": ("gpt-5.6-luna", "high", "read-only"),
    "omc_fixer": ("gpt-5.6-luna", "high", "workspace-write"),
    "omc_oracle": ("gpt-5.6-sol", "high", "read-only"),
}
REQUIRED = {
    "name",
    "description",
    "developer_instructions",
    "model",
    "model_reasoning_effort",
    "sandbox_mode",
}


class ContractTests(unittest.TestCase):
    def test_exactly_four_custom_roles_have_required_fields(self):
        paths = sorted(AGENT_DIR.glob("*.toml"))
        self.assertEqual({path.stem for path in paths}, set(ROLE_NAMES))
        for path in paths:
            with self.subTest(path=path.name):
                data = tomllib.loads(path.read_text(encoding="utf-8"))
                self.assertTrue(REQUIRED <= data.keys())
                self.assertEqual(data["name"], path.stem)
                self.assertEqual(data["model"], ROLE_NAMES[path.stem][0])
                self.assertEqual(
                    data["model_reasoning_effort"], ROLE_NAMES[path.stem][1]
                )
                self.assertEqual(data["sandbox_mode"], ROLE_NAMES[path.stem][2])
                self.assertIs(data["agents"]["enabled"], False)

    def test_role_prompts_preserve_role_boundaries_and_markers(self):
        prompts = {
            name: tomllib.loads(
                (AGENT_DIR / f"{name}.toml").read_text(encoding="utf-8")
            )["developer_instructions"]
            for name in ROLE_NAMES
        }
        for name, prompt in prompts.items():
            self.assertIn("never subdelegate", prompt.lower())
            self.assertIn(f"OMC_ROLE_{name.removeprefix('omc_').upper()}_V1", prompt)
        self.assertIn("no files modified", prompts["omc_explorer"].lower())
        self.assertIn("no files modified", prompts["omc_librarian"].lower())
        self.assertIn("no files modified", prompts["omc_oracle"].lower())
        self.assertIn("structured implementation receipt", prompts["omc_fixer"].lower())

    def test_skill_is_explicit_only_and_mentions_barriers(self):
        skill = (ROOT / "oh_my_codex/assets/skills/oh-my-codex/SKILL.md").read_text(encoding="utf-8")
        manifest = (ROOT / "oh_my_codex/assets/skills/oh-my-codex/agents/openai.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("$oh-my-codex", skill)
        self.assertIn("hard barrier", skill)
        self.assertIn("exclusive", skill)
        self.assertIn("allow_implicit_invocation: false", manifest)

    def test_skill_distinguishes_parent_observability_and_daily_readiness(self):
        skill = (ROOT / "oh_my_codex/assets/skills/oh-my-codex/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("gpt-6-astra", skill)
        self.assertIn("gpt-5.6-sol", skill)
        self.assertIn("DESKTOP", skill.upper())
        self.assertIn("Desktop/user-state verified", skill)
        self.assertIn("PASS WITH HOST LIMITATION", skill)
        self.assertIn("known unsupported model", skill)
        self.assertIn("Do not auto-switch", skill)
        self.assertIn("do not create an Orchestrator child", skill)
        self.assertIn("model's self-claim", skill)
        self.assertIn("diagnostic", skill.lower())

    def test_orchestrator_marker_is_diagnostic_only(self):
        skill = (ROOT / "oh_my_codex/assets/skills/oh-my-codex/SKILL.md").read_text(encoding="utf-8")
        normalized = " ".join(skill.split())
        self.assertIn("OMC_ORCHESTRATOR_V1", skill)
        self.assertIn("disposable diagnostic fixture only", normalized)
        self.assertIn("never report that marker in a normal response", normalized)
        self.assertIn("place the marker value in the smoke prompt", normalized)


if __name__ == "__main__":
    unittest.main()
