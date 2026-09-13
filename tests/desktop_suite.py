from __future__ import annotations

import contextlib
import base64
import io
import hashlib
import json
import platform
import os
import re
import shlex
import subprocess
import sys
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from oh_my_codex import desktop_core
from oh_my_codex.desktop import contained_target, validate_probe_plan, ROLES, evaluate_desktop_evidence, prepare_desktop_fixture


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
        (self.codex / "config.toml").write_text('model = "gpt-6-astra"\n')
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
            "explicit_skill_invocation": True, "probe_preflight": "VERIFIED",
            "observed_probe_paths": [row["path"] for row in self.metadata["probe_plan"].values()],
            "dependency_barriers_observed": True, "workflow_completed": True, "target_write_attribution": "VERIFIED",
            "parent_model_supported": True, "orchestrator_no_implementation": True, "reconciliation_observed": True,
            "receipt_observed": True, "oracle_review_observed": True, "oracle_review_result": "PASS",
        })
        self.control_path = self.root / "control-evidence.json"
        self.control = json.loads(self.control_path.read_text())
        self.control.update({key: self.evidence[key] for key in ("surface", "os", "desktop_version", "runtime_version", "observed_at")})
        self.control.update({"thread_id": "control-thread-1", "new_thread_started": True,
            "skill_invoked": False, "activation_marker_observed": False, "policy_loaded": False,
            "instructed_omc_orchestrator": False, "omc_workflow_forced": False,
            "source_modifications_observed": False, "transcript_reviewed": True, "observation_basis": "DESKTOP_OPERATOR_REVIEW",
            "evidence_reference": "Synthetic unit fixture: operator transcript observation", "response": "42. No mandatory role workflow.",
            "activation_control_result": "PASS"})
        self.control_path.write_text(json.dumps(self.control))
        receipt = {"task": "update target", "status": "completed", "files": ["target.py"], "validation": [{"command": "python -B -m unittest -v test_target.py", "result": "PASS"}], "deviations": [], "unresolved_risks": []}
        finding = {"file": "review_target.py", "function": "average", "input": {"values": []}, "expected": 0, "observed": "ZeroDivisionError"}
        for role in ROLES:
            row = self.evidence["roles"][role]
            row.update({"actual_probe_path": self.metadata["probe_plan"][role]["path"],
                        "probe_instruction_path": self.metadata["probe_plan"][role]["path"],
                        "write_probe_sha256": hashlib.sha256(bytes.fromhex(self.metadata["probe_plan"][role]["contents_hex"])).hexdigest()})
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
        (self.root / "target.py").write_bytes(b"def value():\n    return 'expected'\n")
        (self.root / ".omc-probes/fixer-write.txt").write_bytes(b"OMC Desktop Fixer probe\n")

    def _evaluate(self):
        return evaluate_desktop_evidence(self.evidence_path, desktop_version="26.908.40834", runtime_version="0.154.0-alpha.6.2", thread_id="desktop-thread-1", control_thread_id="control-thread-1")

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
        report = evaluate_desktop_evidence(self.evidence_path, desktop_version="0.0", runtime_version="0.0", thread_id="desktop-thread-1", control_thread_id="control-thread-1")
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
        report = evaluate_desktop_evidence(self.evidence_path, desktop_version="26.908.40834", runtime_version="0.154.0-alpha.6.2", thread_id="desktop-thread-1", control_thread_id="control-thread-1")
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
                data = bytes.fromhex(self.metadata["probe_plan"][role]["contents_hex"])
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
        for field in ("orchestrator_no_implementation", "dependency_barriers_observed", "workflow_completed", "explicit_skill_invocation", "target_write_attribution"):
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
        (self.codex / "config.toml").write_text('model = "gpt-6-astra"\n# changed\n')
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
        (self.root / ".git").rename(self.root.parent / "removed-git")
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
                         "--thread-id", "desktop-thread-1", "--control-thread-id", "control-thread-1"])
        self.assertEqual(code, 0)
        for text in ("PASS WITH HOST LIMITATION", "BLOCKED BY HOST", "danger-full-access", "not technical write prevention"):
            self.assertIn(text, output.getvalue())

    def test_missing_fixture_returns_complete_fail_closed_dimensions(self):
        self.root.rename(self.root.parent / "removed-fixture")
        self.evidence_path = Path(self.temp.name) / "orphan.json"
        self._save()
        report = self._evaluate()
        self.assertEqual(report["daily_use_readiness"], "FAIL")
        self.assertEqual(report["strict_sandbox_isolation"], "UNVERIFIED")


    def test_all_harness_targets_are_canonical_children_with_spaces(self):
        plan = validate_probe_plan(self.root)
        self.assertIn(" ", str(self.root))
        for role in ROLES:
            with self.subTest(role=role):
                target = Path(plan["probe_plan"][role]["path"])
                self.assertEqual(target.parent, self.root / ".omc-probes")
                self.assertTrue(target.is_relative_to(self.root))
                self.assertIn(json.dumps(str(target)), (self.root / "desktop-prompt.txt").read_text())
        self.assertEqual(plan["fixer_target"], str(self.root / "target.py"))

    def test_absolute_outside_target_rejected(self):
        with self.assertRaises(ValueError):
            contained_target(self.root, self.root.parent / "outside.txt")

    def test_dotdot_escape_rejected(self):
        for candidate in ("../outside.txt", ".omc-probes/../../outside.txt"):
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                contained_target(self.root, candidate)

    def test_sibling_prefix_escape_rejected(self):
        with self.assertRaises(ValueError):
            contained_target(self.root, Path(str(self.root) + "-sibling") / "probe.txt")

    def test_parent_traversal_even_inside_fixture_rejected(self):
        with self.assertRaises(ValueError):
            contained_target(self.root, ".omc-probes/../target.py")

    def test_symlink_escape_and_dangling_link_rejected(self):
        for destination in (self.root.parent, self.root.parent / "missing"):
            link = self.root / ".omc-probes/link"
            link.symlink_to(destination)
            with self.assertRaises(ValueError):
                contained_target(self.root, link / "probe.txt")
            link.unlink()

    def test_symlink_loop_and_internal_link_rejected(self):
        link = self.root / ".omc-probes/link"
        for destination in (link, self.root / "value.txt"):
            link.symlink_to(destination)
            with self.assertRaises(ValueError):
                contained_target(self.root, link)
            link.unlink()

    def test_canonical_temporary_root_alias(self):
        alias = self.root.parent / "root alias"
        alias.symlink_to(self.root, target_is_directory=True)
        self.assertEqual(contained_target(alias, ".omc-probes/new.txt"), self.root / ".omc-probes/new.txt")
        prepared = prepare_desktop_fixture(self.root.parent / "new fixture", codex_home=self.codex, skills_home=self.skills)
        self.assertEqual(prepared["fixture"], str(Path(prepared["fixture"]).resolve(strict=True)))

    def test_root_and_non_directory_parent_rejected(self):
        for candidate in (self.root, self.root / "value.txt/probe"):
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                contained_target(self.root, candidate)

    def test_hardlink_target_rejected(self):
        target = self.root / ".omc-probes/explorer-write.txt"
        target.hardlink_to(self.root / "value.txt")
        with self.assertRaises(ValueError):
            validate_probe_plan(self.root)

    def test_preflight_rejects_changed_manifest_before_paths_returned(self):
        for candidate in (str(self.root.parent / "outside.txt"), "../outside.txt", str(self.root / ".omc-probes/alternate.txt")):
            self.metadata["probe_plan"]["omc_librarian"]["path"] = candidate
            (self.root / ".omc-desktop.json").write_text(json.dumps(self.metadata))
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                validate_probe_plan(self.root)

    def test_preflight_rejects_symlink_replacement_after_preparation(self):
        shutil.rmtree(self.root / ".omc-probes")
        (self.root / ".omc-probes").symlink_to(self.root.parent, target_is_directory=True)
        with self.assertRaises(ValueError):
            validate_probe_plan(self.root)
        self.assertFalse((self.root.parent / "librarian-write.txt").exists())

    def test_preflight_rejects_modified_authorization_prompt(self):
        self._complete()
        with (self.root / "desktop-prompt.txt").open("a") as stream:
            stream.write("Use ../outside.txt instead")
        with self.assertRaises(ValueError):
            validate_probe_plan(self.root)
        self.assertEqual(self._evaluate()["probe_boundary_compliance"], "FAIL")

    def test_alternate_path_inside_fixture_fails_for_every_specialist(self):
        self._complete()
        for role in ROLES:
            row = self.evidence["roles"][role]
            for field in ("actual_probe_path", "probe_instruction_path"):
                original = row[field]
                row[field] = str(self.root / ".omc-probes/alternate.txt")
                self._save()
                with self.subTest(role=role, field=field):
                    self.assertEqual(self._evaluate()["probe_boundary_compliance"], "FAIL")
                row[field] = original

    def test_outside_recorded_probe_fails_even_with_host_limitation(self):
        self._host_limitation()
        self.evidence["observed_probe_paths"].append(str(self.root.parent / ".omc-probes/librarian-write.txt"))
        self._save()
        report = self._evaluate()
        self.assertEqual(report["overall"], "FAIL")
        self.assertEqual(report["probe_path_compliance"], "FAILED")
        self.assertEqual(report["strict_sandbox_isolation"], "BLOCKED BY HOST")

    def test_missing_probe_path_evidence_is_unverified(self):
        self._complete()
        del self.evidence["observed_probe_paths"]
        self._save()
        report = self._evaluate()
        self.assertEqual(report["probe_path_compliance"], "UNVERIFIED")
        self.assertEqual(report["overall"], "FAIL")

    def test_literal_backslash_n_fails_even_when_hash_is_accurately_recorded(self):
        self._host_limitation()
        data = b"OMC Desktop Explorer probe\\n"
        path = self.root / ".omc-probes/explorer-write.txt"
        path.write_bytes(data)
        self.evidence["roles"]["omc_explorer"]["write_probe_sha256"] = hashlib.sha256(data).hexdigest()
        self._save()
        report = self._evaluate()
        self.assertEqual(report["overall"], "FAIL")
        self.assertTrue(any(c["name"] == "probe-bytes:omc_explorer" and c["status"] == "FAILED" for c in report["checks"]))
        self.assertEqual(path.read_bytes(), data)

    def test_missing_control_is_unverified_even_with_legacy_boolean(self):
        self._complete()
        self.control_path.unlink()
        self.evidence["normal_thread_without_skill"] = True
        self._save()
        report = self._evaluate()
        self.assertEqual(report["explicit_activation_control"], "UNVERIFIED")
        self.assertEqual(report["overall"], "FAIL")
        self.assertEqual(report["core_orchestration"], "PASS")

    def test_automatic_omc_activation_fails_control(self):
        for field in ("activation_marker_observed", "policy_loaded", "instructed_omc_orchestrator", "omc_workflow_forced"):
            self._complete()
            self.control[field] = True
            self.control_path.write_text(json.dumps(self.control))
            with self.subTest(field=field):
                self.assertEqual(self._evaluate()["explicit_activation_control"], "FAIL")
                self.assertEqual(self._evaluate()["overall"], "FAIL")

    def test_ordinary_subagent_capability_does_not_mean_omc_activation(self):
        self._complete()
        self.control["ordinary_subagents_used"] = True
        self.control_path.write_text(json.dumps(self.control))
        self.assertEqual(self._evaluate()["explicit_activation_control"], "PASS")

    def test_stale_control_timestamp_or_fingerprint_cannot_pass(self):
        for field, value in (("observed_at", "2000-01-01T00:00:00Z"), ("asset_fingerprints", {}), ("schema", 3), ("run_id", "old-run")):
            self._complete()
            self.control[field] = value
            self.control_path.write_text(json.dumps(self.control))
            with self.subTest(field=field):
                self.assertEqual(self._evaluate()["explicit_activation_control"], "UNVERIFIED")
                self.assertEqual(self._evaluate()["overall"], "FAIL")

    def test_reused_activated_thread_or_invoked_control_is_unverified(self):
        for field, value in (("thread_id", "desktop-thread-1"), ("skill_invoked", True), ("new_thread_started", False), ("observation_basis", "MODEL_SELF_CLAIM"), ("evidence_reference", "")):
            self._complete()
            self.control[field] = value
            self.control_path.write_text(json.dumps(self.control))
            with self.subTest(field=field):
                self.assertEqual(self._evaluate()["explicit_activation_control"], "UNVERIFIED")

    def test_control_prompt_does_not_load_or_invoke_policy(self):
        prompt = (self.root / "control-prompt.txt").read_text()
        for token in ("$oh-my-codex", "OMC_ORCHESTRATOR_V1", "SKILL.md"):
            self.assertNotIn(token, prompt)
        self.assertNotIn("OMC_ORCHESTRATOR_V1", (self.root / "desktop-prompt.txt").read_text())

    def test_preflight_cli_returns_only_validated_paths_and_fails_closed(self):
        from oh_my_codex.cli import main
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["verify-desktop", "--check-probes", str(self.root), "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["probe_plan"], self.metadata["probe_plan"])
        self.metadata["fixer_target"] = str(self.root.parent / "outside.py")
        (self.root / ".omc-desktop.json").write_text(json.dumps(self.metadata))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["verify-desktop", "--check-probes", str(self.root), "--json"]), 2)

    def _gate_command(self):
        prompt = (self.root / "desktop-prompt.txt").read_text()
        return shlex.split(next(line for line in prompt.splitlines() if line.startswith("python3 -I -S -c ")))

    def _run_gate(self, command=None):
        command = list(command or self._gate_command())
        command[0] = sys.executable
        return subprocess.run(command, cwd=self.root.parent, env={"PATH": os.defpath, "PYTHONPATH": ""},
                              capture_output=True, text=True)

    def test_self_contained_preflight_without_package_outside_checkout_and_with_spaces(self):
        # The same interpreter, flags, environment and outside cwd must reject the
        # package import and still execute the exact generated launcher/helper.
        unavailable = self._run_gate([sys.executable, "-I", "-S", "-c", "import oh_my_codex"])
        self.assertNotEqual(unavailable.returncode, 0)
        self.assertIn("No module named 'oh_my_codex'", unavailable.stderr)
        self.assertIn(" ", str(self.root))
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        result = self._run_gate()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(json.loads(result.stdout)["overall"], "PASS")
        direct = self._run_gate([sys.executable, "-I", "-S", str(self.root / ".omc-probe-preflight.py")])
        self.assertEqual(direct.returncode, 0, direct.stderr + direct.stdout)
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def _retained_prompt_command(self):
        prepared = prepare_desktop_fixture(self.root.parent / "final_fixture with spaces",
                                           codex_home=self.codex, skills_home=self.skills)
        # Retain the actual generated artifact outside the writable fixture, as
        # in final acceptance. Never reconstruct the command from API fields.
        artifact = self.root.parent / "activated-prompt.txt"
        artifact.write_bytes(Path(prepared["prompt"]).read_bytes())
        lines = [line for line in artifact.read_text().splitlines()
                 if line.startswith("python3 -I -S -c ")]
        self.assertEqual(len(lines), 1)
        return prepared, lines[0]

    def _run_prompt_command(self, command):
        # Decode the known shlex serialization, preserving every semantic
        # argument. Use the running Python without requiring a shell or alias.
        args = shlex.split(command)
        self.assertEqual(args[:4], ["python3", "-I", "-S", "-c"])
        return subprocess.run([sys.executable, *args[1:]], cwd=self.root.parent,
                              capture_output=True, text=True)

    def test_exact_retained_prompt_command_no_import_outside_checkout_with_spaces(self):
        prepared, command = self._retained_prompt_command()
        unavailable = self._run_prompt_command("python3 -I -S -c 'import oh_my_codex'")
        self.assertNotEqual(unavailable.returncode, 0)
        self.assertIn("No module named 'oh_my_codex'", unavailable.stderr)
        self.assertFalse(self.root.parent.is_relative_to(ROOT))
        self.assertIn(" ", str(self.root.parent))
        args = shlex.split(command)
        self.assertEqual(args[:4], ["python3", "-I", "-S", "-c"])
        self.assertEqual(args[5:], [prepared["preflight"], prepared["preflight_sha256"]])
        self.assertIn(" ", args[5])
        self.assertEqual(args[6], hashlib.sha256(Path(args[5]).read_bytes()).hexdigest())
        fixture = Path(prepared["fixture"])
        before = {p.relative_to(fixture): p.read_bytes() for p in fixture.rglob("*") if p.is_file()}
        result = self._run_prompt_command(command)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(json.loads(result.stdout)["overall"], "PASS")
        self.assertEqual(before, {p.relative_to(fixture): p.read_bytes() for p in fixture.rglob("*") if p.is_file()})

    def test_retained_prompt_uses_standard_base64_without_raw_launcher_source(self):
        prepared, command = self._retained_prompt_command()
        wrapper = (desktop_core._preflight_argv(Path(prepared["fixture"]), prepared["preflight_sha256"])[4]
                   if os.name == "nt" else shlex.split(command)[4])
        match = re.fullmatch(r'import base64;exec\(base64\.b64decode\("([A-Za-z0-9+/=]+)"\)\)', wrapper)
        self.assertIsNotNone(match)
        encoded = match.group(1)
        self.assertNotIn("_", encoded)
        self.assertNotIn("_", wrapper)
        launcher = base64.b64decode(encoded, validate=True).decode("utf-8")
        self.assertEqual(base64.b64encode(launcher.encode()).decode("ascii"), encoded)
        for token in ("read_bytes", "__name__", "__file__", "st_nlink", "hashlib.sha256", "exec(compile"):
            self.assertIn(token, launcher)
            self.assertNotIn(token, command)

    def test_retained_prompt_python_payload_survives_underscore_escaping(self):
        prepared, command = self._retained_prompt_command()
        wrapper = (desktop_core._preflight_argv(Path(prepared["fixture"]), prepared["preflight_sha256"])[4]
                   if os.name == "nt" else shlex.split(command)[4])
        # Model the observed escaping of Python source in the -c payload only.
        # Helper paths are separate data arguments (including an underscore here);
        # this does not claim immunity to arbitrary mutation of paths or prose.
        escaped = wrapper.replace("_", "\\_")
        quoted_wrapper = (desktop_core._powershell_quote(wrapper) if os.name == "nt" else shlex.quote(wrapper))
        quoted_escaped = (desktop_core._powershell_quote(escaped) if os.name == "nt" else shlex.quote(escaped))
        transformed = command.replace(quoted_wrapper, quoted_escaped, 1)
        self.assertEqual(transformed, command)
        result = self._run_prompt_command(transformed)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(json.loads(result.stdout)["overall"], "PASS")
        # Establish that this transformation reproduces the old source failure.
        launcher = base64.b64decode(wrapper.split('"')[1]).decode("utf-8")
        with self.assertRaises(SyntaxError):
            compile(launcher.replace("_", "\\_"), "escaped launcher", "exec")

    def test_retained_prompt_wrong_sha_fails_closed(self):
        prepared, command = self._retained_prompt_command()
        digest = prepared["preflight_sha256"]
        wrong = ("0" if digest[0] != "0" else "1") + digest[1:]
        if os.name == "nt":
            changed = command.replace(desktop_core._powershell_quote(digest),
                                      desktop_core._powershell_quote(wrong), 1)
        else:
            changed = command.removesuffix(digest) + wrong
        result = self._run_prompt_command(changed)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("helper identity mismatch", result.stderr)
        self.assertNotIn("PASS", result.stdout)

    def test_retained_prompt_helper_replacement_symlink_hardlink_fail_closed(self):
        prepared, command = self._retained_prompt_command()
        helper = Path(prepared["preflight"])
        retained = self.root.parent / "retained helper with spaces.py"
        helper.rename(retained)
        marker = self.root.parent / "tampered-helper-executed"
        for mutation in ("symlink", "hardlink", "replacement"):
            with self.subTest(mutation=mutation):
                helper.unlink(missing_ok=True)
                if mutation == "symlink":
                    helper.symlink_to(retained)
                elif mutation == "hardlink":
                    helper.hardlink_to(retained)
                else:
                    helper.write_text("from pathlib import Path\nPath(" + repr(str(marker)) + ").touch()\n")
                result = self._run_prompt_command(command)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("helper identity mismatch" if mutation == "replacement" else
                              "canonical single-link regular file", result.stderr)
                self.assertFalse(marker.exists())
                self.assertNotIn("PASS", result.stdout)
                helper.unlink()
        helper.write_bytes(retained.read_bytes())
        self.assertEqual(self._run_prompt_command(command).returncode, 0)

    def test_helper_generated_contained_fingerprinted_and_deterministic(self):
        from oh_my_codex import desktop
        helper = contained_target(self.root, ".omc-probe-preflight.py")
        digest = hashlib.sha256(helper.read_bytes()).hexdigest()
        self.assertEqual(digest, self.metadata["preflight_sha256"])
        self.assertEqual(digest, self.evidence["preflight_sha256"])
        baseline = json.loads((self.root / "fixture-baseline.json").read_text())
        self.assertEqual(helper.read_bytes(), desktop._helper_bytes(self.root, self.metadata, baseline))
        self.assertNotIn(helper.name, baseline["files"])
        self.assertNotIn("import oh_my_codex", helper.read_text())
        self.assertNotIn("from oh_my_codex", helper.read_text())

    def test_activated_prompt_uses_only_pinned_fixture_gate(self):
        prompt = (self.root / "desktop-prompt.txt").read_text()
        self.assertIn("python3 -I -S -c", prompt)
        self.assertIn(str(self.root / ".omc-probe-preflight.py"), prompt)
        self.assertIn(self.metadata["preflight_sha256"], prompt)
        self.assertNotIn("-m oh_my_codex", prompt)
        self.assertIn("Do not improvise an alternate gate", prompt)
        self.assertIn("pip install, modify the Python environment, or fall back to importing oh_my_codex", prompt)

    def test_malicious_helper_never_executes_and_evaluation_fails(self):
        self._complete()
        marker = self.root / "malicious-executed"
        (self.root / ".omc-probe-preflight.py").write_text(
            "from pathlib import Path\nPath(" + repr(str(marker)) + ").touch()\nprint('PASS')\n")
        result = self._run_gate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("helper identity mismatch", result.stderr)
        self.assertFalse(marker.exists())
        self.assertEqual(self._evaluate()["evidence_validity"], "FAIL")

    def test_helper_and_local_hash_tampering_cannot_replace_retained_anchor(self):
        command = self._gate_command()
        helper = self.root / ".omc-probe-preflight.py"
        helper.write_text("print('PASS')\n")
        changed = hashlib.sha256(helper.read_bytes()).hexdigest()
        self.metadata["preflight_sha256"] = changed
        (self.root / ".omc-desktop.json").write_text(json.dumps(self.metadata))
        prompt = self.root / "desktop-prompt.txt"
        prompt.write_text(prompt.read_text().replace(command[-1], changed))
        result = self._run_gate(command)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("PASS", result.stdout)
        with self.assertRaises(ValueError):
            validate_probe_plan(self.root)

    def test_standalone_metadata_tampering_fails(self):
        metadata_path = self.root / ".omc-desktop.json"
        original = metadata_path.read_bytes()
        for field, value in (("schema", 3), ("fixture_path", str(self.root.parent)),
                             ("run_id", "forged"), ("asset_fingerprints", {}),
                             ("preflight_contract", 0), ("directory_identity", {})):
            changed = dict(self.metadata, **{field: value})
            metadata_path.write_text(json.dumps(changed))
            with self.subTest(field=field):
                result = self._run_gate()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("metadata changed", result.stdout)
            metadata_path.write_bytes(original)

    def test_standalone_probe_plan_tampering_fails(self):
        self.metadata["probe_plan"]["omc_explorer"]["path"] = str(self.root.parent / "escape")
        (self.root / ".omc-desktop.json").write_text(json.dumps(self.metadata))
        result = self._run_gate()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root.parent / "escape").exists())

    def test_standalone_every_installed_asset_changed_or_missing_fails(self):
        from oh_my_codex import desktop
        for name, path in desktop._asset_paths(self.codex, self.skills).items():
            if not name.startswith("installed"):
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

    def test_standalone_missing_asset_at_preparation_still_fails(self):
        (self.codex / "config.toml").unlink()
        prepared = prepare_desktop_fixture(self.root.parent / "missing asset fixture", codex_home=self.codex, skills_home=self.skills)
        result = self._run_gate(shlex.split(prepared["preflight_command"]))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("installed-config", result.stdout)

    def test_standalone_control_integrity_and_source_tampering_fails(self):
        for name in ("fixture-baseline.json", "desktop-prompt.txt", "control-prompt.txt", "value.txt", "test_target.py", "review_target.py"):
            path = self.root / name
            original = path.read_bytes()
            path.write_bytes(original + b" ")
            with self.subTest(name=name):
                self.assertNotEqual(self._run_gate().returncode, 0)
            path.write_bytes(original)
        (self.root / "extra.txt").write_text("extra")
        self.assertNotEqual(self._run_gate().returncode, 0)

    def test_standalone_parent_replacement_fails(self):
        probes = self.root / ".omc-probes"
        # Keep the previous inode alive so reuse cannot mask the replacement.
        probes.rename(self.root.parent / "old probes")
        shutil.copytree(self.root.parent / "old probes", probes)
        result = self._run_gate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("parent identity changed", result.stdout)

    def test_standalone_symlink_and_hardlink_fail(self):
        probe = self.root / ".omc-probes/explorer-write.txt"
        probe.symlink_to(self.root / "value.txt")
        self.assertNotEqual(self._run_gate().returncode, 0)
        probe.unlink()
        probe.hardlink_to(self.root / "value.txt")
        self.assertNotEqual(self._run_gate().returncode, 0)
        probe.unlink()
        helper = self.root / ".omc-probe-preflight.py"
        copied = self.root.parent / "helper copy"
        helper.rename(copied)
        helper.symlink_to(copied)
        self.assertNotEqual(self._run_gate().returncode, 0)
        helper.unlink()
        helper.hardlink_to(copied)
        self.assertNotEqual(self._run_gate().returncode, 0)

    def test_standalone_accepts_only_exact_authorized_changes_between_dispatches(self):
        self._complete()
        for row in self.metadata["probe_plan"].values():
            Path(row["path"]).write_bytes(bytes.fromhex(row["contents_hex"]))
        self.assertEqual(self._run_gate().returncode, 0)
        probe = self.root / ".omc-probes/librarian-write.txt"
        probe.write_bytes(b"OMC Desktop Librarian probe\\n")
        self.assertNotEqual(self._run_gate().returncode, 0)

    def test_standalone_copied_helper_cannot_validate_original_fixture(self):
        copied = self.root.parent / "copied helper.py"
        shutil.copy2(self.root / ".omc-probe-preflight.py", copied)
        result = self._run_gate([sys.executable, "-I", "-S", str(copied)])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outside its prepared fixture", result.stdout)

    def test_prompt_digest_placeholder_in_fixture_name_is_literal(self):
        prepared = prepare_desktop_fixture(self.root.parent / "__OMC_PREFLIGHT_SHA256__ fixture's name", codex_home=self.codex, skills_home=self.skills)
        command = desktop_core._preflight_argv(
            Path(prepared["fixture"]), prepared["preflight_sha256"],
            executable=str(Path(sys.executable).expanduser().absolute()),
        )
        result = self._run_gate(command)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_stale_helper_evidence_is_rejected(self):
        self._complete()
        self.evidence["preflight_sha256"] = "stale"
        self._save()
        self.assertEqual(self._evaluate()["evidence_validity"], "FAIL")


if __name__ == "__main__":
    unittest.main()
