from __future__ import annotations

import contextlib
import io
import hashlib
import json
import platform
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from oh_my_codex.desktop import ROLES, evaluate_desktop_evidence, prepare_desktop_fixture


ROOT = Path(__file__).resolve().parents[1]


class DesktopVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="omc desktop test ")
        base = Path(self.temp.name)
        self.codex = base / "codex"
        self.skills = base / "skills"
        (self.codex / "agents").mkdir(parents=True)
        (self.skills / "oh-my-codex/agents").mkdir(parents=True)
        for role in ROLES:
            shutil.copy2(ROOT / f"oh_my_codex/assets/agents/{role}.toml", self.codex / f"agents/{role}.toml")
        shutil.copy2(ROOT / "oh_my_codex/assets/skills/oh-my-codex/SKILL.md", self.skills / "oh-my-codex/SKILL.md")
        shutil.copy2(ROOT / "oh_my_codex/assets/skills/oh-my-codex/agents/openai.yaml", self.skills / "oh-my-codex/agents/openai.yaml")
        prepared = prepare_desktop_fixture(base / "fixture", codex_home=self.codex, skills_home=self.skills)
        self.root = Path(prepared["fixture"])
        self.evidence_path = Path(prepared["evidence"])
        self.evidence = json.loads(self.evidence_path.read_text(encoding="utf-8"))
        self.metadata = json.loads((self.root / ".omc-desktop.json").read_text(encoding="utf-8"))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _complete(self) -> None:
        self.evidence.update({
            "surface": "CODEX_DESKTOP", "os": platform.platform(), "desktop_version": "26.908.40834",
            "runtime_version": "0.154.0-alpha.6.2", "observed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "run_id": self.metadata["run_id"], "thread_id": "desktop-thread-1", "restart_completed": True,
            "new_thread_started": True, "skill_discovered": True, "parent_model": "gpt-6-astra",
            "parent_model_evidence": "DESKTOP_USER_STATE_VERIFIED", "parent_model_evidence_detail": "Operator recorded Astra/high selected in Desktop",
            "explicit_skill_invocation": True, "normal_thread_without_skill": True,
            "dependency_barriers_observed": True, "workflow_completed": True, "target_write_attribution": "VERIFIED",
            "parent_model_supported": True, "orchestrator_no_implementation": True, "reconciliation_observed": True,
            "receipt_observed": True, "oracle_review_observed": True, "oracle_review_result": "PASS",
        })
        receipt = {"task": "update target", "status": "completed", "files": ["target.py"], "validation": [{"command": "python -B -m unittest -v test_target.py", "result": "PASS"}], "deviations": [], "unresolved_risks": []}
        finding = {"file": "review_target.py", "function": "average", "input": {"values": []}, "expected": 0, "observed": "ZeroDivisionError"}
        for role in ROLES:
            row = self.evidence["roles"][role]
            row.update({
                "role": role, "spawned": True, "semantic_task_name": f"{role.removeprefix('omc_')}_desktop_smoke", "observed_model": "gpt-5.6-sol" if role == "omc_oracle" else "gpt-5.6-luna",
                "observed_effort": "medium" if role == "omc_explorer" else "high", "observed_sandbox": "workspace-write" if role == "omc_fixer" else "read-only",
                "implementation": "BOUNDED" if role == "omc_fixer" else "NONE", "write_probe": "SUCCEEDED" if role == "omc_fixer" else "DENIED", "result": "VERIFIED",
            })
        self.evidence["roles"]["omc_explorer"].update({"repository_work": "VERIFIED", "repository_fact": "repository fact: preserve this file"})
        self.evidence["roles"]["omc_librarian"].update({"external_research": "VERIFIED", "source_url": "https://docs.python.org/3/library/statistics.html", "research_finding": "statistics.mean([]) raises StatisticsError"})
        self.evidence["roles"]["omc_fixer"].update({"validation_status": "VERIFIED", "receipt": receipt})
        self.evidence["roles"]["omc_oracle"].update({"review_status": "VERIFIED", "review_result": "PASS", "planted_verdict": "FAIL", "planted_finding": finding})
        self.evidence_path.write_text(json.dumps(self.evidence, indent=2), encoding="utf-8")
        (self.root / "target.py").write_text("def value():\n    return 'expected'\n", encoding="utf-8")
        (self.root / ".omc-probes/fixer-write.txt").write_text("OMC Desktop Fixer probe\n", encoding="utf-8")

    def _evaluate(self):
        return evaluate_desktop_evidence(self.evidence_path, desktop_version="26.908.40834", runtime_version="0.154.0-alpha.6.2", thread_id="desktop-thread-1")

    def test_prepare_is_fail_closed_and_positive_evaluation_is_pass_with_notes(self):
        self.assertEqual(self.evidence["overall"], "FAIL")
        self.assertEqual(self.evidence["strict_least_privilege"], "UNVERIFIED")
        self.assertTrue((self.root / ".git").is_dir())
        self._complete()
        report = self._evaluate()
        self.assertEqual(report["overall"], "PASS WITH NOTES")
        self.assertEqual(report["strict_least_privilege"], "READY")

    def test_old_timestamp_and_versions_fail(self):
        self._complete()
        old = (datetime.now(timezone.utc) - timedelta(days=2)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        self.evidence.update({"observed_at": old, "desktop_version": "0.0", "runtime_version": "0.0"})
        self.evidence_path.write_text(json.dumps(self.evidence), encoding="utf-8")
        report = evaluate_desktop_evidence(self.evidence_path, desktop_version="0.0", runtime_version="0.0", thread_id="desktop-thread-1")
        self.assertEqual(report["overall"], "FAIL")
        self.assertTrue(any(c["name"] == "timestamp" and c["status"] == "FAILED" for c in report["checks"]))

    def test_future_timestamp_fails(self):
        self._complete()
        future = (datetime.now(timezone.utc) + timedelta(minutes=5)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        self.evidence["observed_at"] = future
        self.evidence_path.write_text(json.dumps(self.evidence), encoding="utf-8")
        report = self._evaluate()
        self.assertEqual(report["overall"], "FAIL")
        self.assertTrue(any(c["name"] == "timestamp" and c["status"] == "FAILED" for c in report["checks"]))

    def test_low_level_surface_missing_required_context_and_wrong_thread_fail(self):
        self._complete()
        self.evidence.update({"surface": "CODEX_CLI_APPSERVER", "os": "old-os"})
        self.evidence_path.write_text(json.dumps(self.evidence), encoding="utf-8")
        report = evaluate_desktop_evidence(self.evidence_path, desktop_version="26.908.40834", runtime_version="0.154.0-alpha.6.2", thread_id="other-thread")
        self.assertEqual(report["overall"], "FAIL")
        failed = {c["name"] for c in report["checks"] if c["status"] == "FAILED"}
        self.assertTrue({"surface", "run-provenance"} <= failed)

    def test_permission_success_for_read_only_role_fails_gate(self):
        self._complete()
        self.evidence["roles"]["omc_explorer"]["write_probe"] = "SUCCEEDED"
        self.evidence_path.write_text(json.dumps(self.evidence), encoding="utf-8")
        report = self._evaluate()
        self.assertEqual(report["overall"], "FAIL")

    def test_failed_research_and_failed_nesting_fail(self):
        self._complete()
        self.evidence["roles"]["omc_librarian"]["external_research"] = "FAILED"
        self.evidence["nesting"] = "FAILED"
        self.evidence_path.write_text(json.dumps(self.evidence), encoding="utf-8")
        report = self._evaluate()
        self.assertEqual(report["overall"], "FAIL")

    def test_missing_installed_asset_or_changed_root_fails(self):
        self._complete()
        (self.skills / "oh-my-codex/SKILL.md").unlink()
        self.evidence_path.write_text(json.dumps(self.evidence), encoding="utf-8")
        report = self._evaluate()
        self.assertEqual(report["overall"], "FAIL")
        self.evidence["skills_home"] = str(self.root / "different-skills")
        self.evidence_path.write_text(json.dumps(self.evidence), encoding="utf-8")
        report = evaluate_desktop_evidence(self.evidence_path, desktop_version="26.908.40834", runtime_version="0.154.0-alpha.6.2", thread_id="desktop-thread-1")
        self.assertEqual(report["overall"], "FAIL")

    def test_protected_bytes_extra_nested_control_and_malformed_roles_fail(self):
        self._complete()
        (self.root / "review_target.py").write_text("tampered\n", encoding="utf-8")
        (self.root / ".omc-probes/nested-control.txt").write_text("extra\n", encoding="utf-8")
        self.evidence["roles"] = []
        self.evidence_path.write_text(json.dumps(self.evidence), encoding="utf-8")
        report = self._evaluate()
        self.assertEqual(report["overall"], "FAIL")
        failed = {c["name"] for c in report["checks"] if c["status"] == "FAILED"}
        self.assertTrue({"role-set", "fixture-state"} <= failed)

    def test_duplicate_control_basename_and_wrong_semantic_fact_fail(self):
        self._complete()
        (self.root / ".omc-probes/desktop-evidence.json").write_text("duplicate\n", encoding="utf-8")
        self.evidence["roles"]["omc_explorer"]["semantic_task_name"] = "explorer_other"
        self.evidence["roles"]["omc_explorer"]["repository_fact"] = "arbitrary fact"
        self.evidence_path.write_text(json.dumps(self.evidence), encoding="utf-8")
        report = self._evaluate()
        self.assertEqual(report["overall"], "FAIL")
        self.assertTrue(any(c["name"] == "fixture-state" and c["status"] == "FAILED" for c in report["checks"]))
        self.assertTrue(any(c["name"] == "role:omc_explorer" and c["status"] == "FAILED" for c in report["checks"]))

    def test_empty_or_failed_fixer_validation_fails(self):
        self._complete()
        self.evidence["roles"]["omc_fixer"]["receipt"]["validation"] = []
        self.evidence_path.write_text(json.dumps(self.evidence), encoding="utf-8")
        self.assertEqual(self._evaluate()["overall"], "FAIL")
        self._complete()
        self.evidence["roles"]["omc_fixer"]["receipt"]["validation"][0]["result"] = "FAIL"
        self.evidence_path.write_text(json.dumps(self.evidence), encoding="utf-8")
        self.assertEqual(self._evaluate()["overall"], "FAIL")

    def test_null_role_row_and_unhashable_effort_fail_without_traceback(self):
        self._complete()
        self.evidence["roles"]["omc_explorer"] = None
        self.evidence_path.write_text(json.dumps(self.evidence), encoding="utf-8")
        self.assertEqual(self._evaluate()["overall"], "FAIL")
        self.evidence["roles"]["omc_explorer"] = dict(self.evidence["roles"]["omc_librarian"])
        self.evidence["roles"]["omc_explorer"]["role"] = "omc_explorer"
        self.evidence["roles"]["omc_explorer"]["observed_effort"] = []
        self.evidence_path.write_text(json.dumps(self.evidence), encoding="utf-8")
        self.assertEqual(self._evaluate()["overall"], "FAIL")

    def _save(self):
        self.evidence_path.write_text(json.dumps(self.evidence), encoding="utf-8")

    def _host_limitation(self):
        self._complete()
        self.evidence.update({"parent_effective_sandbox": "danger-full-access", "supported_config_remedy": "NONE",
                              "host_limitation_detail": "Valid role override ignored by the tested host; supported configuration inspection found no remedy."})
        for role, row in self.evidence["roles"].items():
            row.update({"observed_sandbox": "danger-full-access", "write_probe": "SUCCEEDED", "host_override_evidence": "INHERITED_PARENT"})
            # Legacy aggregate failures from sandbox probes must not veto semantic checks.
            row["result"] = "FAILED"
            if role != "omc_fixer":
                data = f"{role} authorized canary\n".encode()
                (self.root / f".omc-probes/{role.removeprefix('omc_')}-write.txt").write_bytes(data)
                row["write_probe_sha256"] = hashlib.sha256(data).hexdigest()
        self._save()

    def test_core_pass_and_host_blocked_produces_daily_pass_with_host_limitation(self):
        self._host_limitation()
        report = self._evaluate()
        self.assertEqual(report["core_orchestration"], "PASS")
        self.assertEqual(report["behavioral_role_isolation"], "PASS")
        self.assertEqual(report["strict_sandbox_isolation"], "BLOCKED BY HOST")
        self.assertEqual(report["overall"], "PASS WITH HOST LIMITATION")
        self.assertTrue(report["warnings"])
        self.assertTrue(report["desktop_verified"])

    def test_wrong_model_for_every_role_fails_core_even_with_host_limitation(self):
        self._host_limitation()
        for role, row in self.evidence["roles"].items():
            with self.subTest(role=role):
                original = row["observed_model"]
                row["observed_model"] = "wrong-model"
                self._save()
                self.assertEqual(self._evaluate()["core_orchestration"], "FAIL")
                row["observed_model"] = original

    def test_critical_workflow_failures_still_fail_core(self):
        for field in ("orchestrator_no_implementation", "dependency_barriers_observed", "workflow_completed", "explicit_skill_invocation", "normal_thread_without_skill", "target_write_attribution"):
            with self.subTest(field=field):
                self._complete()
                self.evidence[field] = False
                self._save()
                self.assertEqual(self._evaluate()["core_orchestration"], "FAIL")
        self._complete()
        self.evidence["roles"]["omc_fixer"]["write_probe"] = "DENIED"
        self._save()
        self.assertEqual(self._evaluate()["core_orchestration"], "FAIL")
        self._complete()
        self.evidence["roles"]["omc_oracle"]["review_result"] = "UNVERIFIED"
        self._save()
        self.assertEqual(self._evaluate()["core_orchestration"], "FAIL")

    def test_wrong_project_sandbox_is_failure_for_every_role(self):
        self._host_limitation()
        for role, row in self.evidence["roles"].items():
            with self.subTest(role=role):
                old = row["configured_sandbox"]
                row["configured_sandbox"] = "danger-full-access"
                self._save()
                self.assertEqual(self._evaluate()["strict_sandbox_isolation"], "FAIL")
                row["configured_sandbox"] = old
        # Also catch actual source/installed misconfiguration, not only entered intent.
        path = self.codex / "agents/omc_explorer.toml"
        path.write_text(path.read_text().replace('sandbox_mode = "read-only"', 'sandbox_mode = "danger-full-access"'))
        self._save()
        report = self._evaluate()
        self.assertEqual(report["strict_sandbox_isolation"], "FAIL")
        self.assertEqual(report["core_orchestration"], "FAIL")

    def test_future_enforced_host_pass_has_no_host_warning(self):
        self._complete()
        report = self._evaluate()
        self.assertEqual(report["strict_sandbox_isolation"], "PASS")
        self.assertEqual(report["warnings"], [])

    def test_parent_metadata_observability_is_not_a_daily_use_blocker(self):
        for kind in ("DESKTOP_USER_STATE_VERIFIED", "INFERRED", "UNVERIFIED"):
            with self.subTest(kind=kind):
                self._host_limitation()
                self.evidence["parent_model_evidence"] = kind
                if kind == "UNVERIFIED":
                    self.evidence["parent_model"] = "UNVERIFIED"
                    self.evidence["parent_model_supported"] = "UNVERIFIED"
                self._save()
                report = self._evaluate()
                self.assertEqual(report["overall"], "PASS WITH HOST LIMITATION")
                self.assertEqual(report["parent_model_evidence"], kind)
        self.evidence["parent_model"] = "gpt-5.6-luna"
        self._save()
        self.assertEqual(self._evaluate()["core_orchestration"], "FAIL")

    def test_broader_permission_without_host_cause_or_supported_remedy_evidence_is_unverified(self):
        self._host_limitation()
        self.evidence["supported_config_remedy"] = "UNVERIFIED"
        self._save()
        report = self._evaluate()
        self.assertEqual(report["core_orchestration"], "PASS")
        self.assertEqual(report["strict_sandbox_isolation"], "UNVERIFIED")
        self.assertEqual(report["overall"], "FAIL")

    def test_stale_evaluator_fingerprint_and_legacy_schema_cannot_qualify(self):
        self._host_limitation()
        before = self.evidence_path.read_bytes()
        from oh_my_codex import desktop
        assets = desktop._asset_fingerprints(self.codex, self.skills)
        assets["package:desktop.py"] = "changed-evaluator"
        with mock.patch.object(desktop, "_asset_fingerprints", return_value=assets):
            report = self._evaluate()
        self.assertEqual(report["evidence_validity"], "FAIL")
        self.assertEqual(report["overall"], "FAIL")
        self.assertFalse(report["desktop_verified"])
        self.assertEqual(self.evidence_path.read_bytes(), before)
        self.evidence["schema"] = 2
        self._save()
        self.assertEqual(self._evaluate()["evidence_validity"], "FAIL")

    def test_config_change_invalidates_fingerprint(self):
        self._complete()
        (self.codex / "config.toml").write_text('model = "gpt-6-astra"\n')
        self.assertEqual(self._evaluate()["evidence_validity"], "FAIL")

    def test_probes_must_match_recorded_bytes_and_preserve_protected_files(self):
        self._host_limitation()
        (self.root / ".omc-probes/explorer-write.txt").write_text("unrecorded write")
        self.assertEqual(self._evaluate()["core_orchestration"], "FAIL")
        self._host_limitation()
        (self.root / "value.txt").write_text("unauthorized edit")
        self.assertEqual(self._evaluate()["core_orchestration"], "FAIL")

    def test_wrong_effort_fails_and_unobservable_effort_adds_notes(self):
        self._complete()
        self.evidence["roles"]["omc_oracle"]["observed_effort"] = "low"
        self._save()
        self.assertEqual(self._evaluate()["core_orchestration"], "FAIL")
        self.evidence["roles"]["omc_oracle"]["observed_effort"] = "UNVERIFIED"
        self._save()
        self.assertEqual(self._evaluate()["core_orchestration"], "PASS WITH NOTES")

    def test_deleted_git_fixture_and_unauthorized_behavior_are_not_accepted(self):
        self._complete()
        shutil.rmtree(self.root / ".git")
        report = self._evaluate()
        self.assertEqual(report["core_orchestration"], "FAIL")
        self.assertEqual(report["behavioral_role_isolation"], "FAIL")

    def test_real_source_misconfiguration_is_project_failure(self):
        from oh_my_codex import desktop
        self._host_limitation()
        source_path = ROOT / "oh_my_codex/assets/agents/omc_explorer.toml"
        installed_path = self.codex / "agents/omc_explorer.toml"
        wrong = source_path.read_text().replace('sandbox_mode = "read-only"', 'sandbox_mode = "danger-full-access"')
        original_read = Path.read_text
        def read(path, *args, **kwargs):
            return wrong if path in (source_path, installed_path) else original_read(path, *args, **kwargs)
        with mock.patch.object(Path, "read_text", read):
            self.assertFalse(desktop._installed_contracts(self.codex, self.skills)[0])
            report = self._evaluate()
        self.assertEqual(report["strict_sandbox_isolation"], "FAIL")
        self.assertEqual(report["core_orchestration"], "FAIL")

    def test_cli_human_status_and_exit_code_keep_host_warning_visible(self):
        from oh_my_codex.cli import main
        self._host_limitation()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["verify-desktop", "--evaluate", str(self.evidence_path),
                         "--desktop-version", "26.908.40834", "--runtime-version", "0.154.0-alpha.6.2",
                         "--thread-id", "desktop-thread-1"])
        self.assertEqual(code, 0)
        for text in ("PASS WITH HOST LIMITATION", "BLOCKED BY HOST", "danger-full-access", "not technical write prevention"):
            self.assertIn(text, output.getvalue())

    def test_missing_fixture_returns_complete_fail_closed_dimensions(self):
        shutil.rmtree(self.root)
        self.evidence_path = Path(self.temp.name) / "orphan.json"
        self._save()
        report = self._evaluate()
        self.assertEqual(report["daily_use_readiness"], "FAIL")
        self.assertEqual(report["strict_sandbox_isolation"], "UNVERIFIED")



if __name__ == "__main__":
    unittest.main()
