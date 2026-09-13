from __future__ import annotations

import os
import json
import shlex
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from oh_my_codex.verify import (
    _aggregate,
    _configured_checks,
    _diagnostic_outputs,
    _event_thread_ids,
    _fixture_snapshot,
    _fixture_unsafe_entries,
    _git_checked,
    _normalise_sandbox,
    _oracle_finding_matches,
    _observation_from_event,
    _parent_prompt,
    _role_write_evidence,
    _role_completion_evidence,
    _librarian_source_evidence,
    _nesting_violations,
    _returned_paths,
    _skill_read_evidence,
    _trace_observations,
    _terminate_process,
)


class VerifyEvidenceTests(unittest.TestCase):
    def _observations(self):
        return [
            {
                "thread_id": f"child-{role}",
                "role": role,
                "source": "subAgentThreadSpawn",
                "model": "gpt-5.6-sol" if role == "omc_oracle" else "gpt-5.6-luna",
                "effort": "medium" if role == "omc_explorer" else "high",
                "sandbox": "workspace-write" if role == "omc_fixer" else "read-only",
                "parent_thread_id": "root",
            }
            for role in ("omc_explorer", "omc_librarian", "omc_fixer", "omc_oracle")
        ]

    def test_complete_host_correlated_roles_verify(self):
        overall, checks = _aggregate([], self._observations(), fixture_changed=False, malformed=False)
        self.assertEqual(overall, "PASS WITH NOTES")  # nesting remains deliberately unverified
        runtime = {item["name"]: item["status"] for item in checks if item["name"].startswith("runtime:")}
        self.assertEqual(set(runtime.values()), {"VERIFIED"})

    def test_complete_core_evidence_can_pass_with_nesting_note(self):
        role_ids = {row["role"]: {row["thread_id"]} for row in self._observations()}
        overall, checks = _aggregate(
            [],
            self._observations(),
            fixture_changed=False,
            malformed=False,
            target_ok=True,
            role_text={role: "" for role in role_ids},
            root_thread_id="root",
            role_write_evidence={
                "omc_explorer": False,
                "omc_librarian": False,
                "omc_fixer": True,
                "omc_oracle": False,
                "__observed__": True,
                "__root__": False,
            },
            completion_evidence={role: True for role in role_ids},
            terminal_status={role: "completed" for role in role_ids},
            diagnostics={
                "omc_explorer": {"paths": ["target.py"], "findings": ["fixture"], "uncertainties": [], "no_files_modified": True},
                "omc_fixer": {"receipt": {"task": "verify", "status": "completed", "files": ["target.py"], "summary": "updated", "validation": [{"command": "python", "result": "pass"}], "deviations": [], "unresolved_risks": []}},
                "omc_librarian": {"research_status": "unavailable", "source_url": "unavailable"},
                "omc_oracle": {"review_target": "review_target.py", "review_target_found": True, "verdict": "FAIL", "findings": [{"file": "review_target.py", "function": "average", "input": {"values": []}, "expected": 0, "observed": "ZeroDivisionError"}]},
            },
            skill_read=True,
        )
        self.assertEqual(overall, "PASS WITH NOTES")
        self.assertFalse(any(item["status"] in {"FAILED", "UNVERIFIED"} and item["name"] != "nesting" for item in checks))

    def test_missing_role_and_wrong_effective_model_fail(self):
        observations = self._observations()[:-1]
        observations[0] = dict(observations[0], model="gpt-5.6-sol")
        overall, checks = _aggregate([], observations, fixture_changed=False, malformed=False)
        self.assertEqual(overall, "FAIL")
        self.assertTrue(any(item["status"] == "FAILED" and item["name"] == "runtime:omc_explorer" for item in checks))
        self.assertTrue(any(item["status"] == "UNVERIFIED" and item["name"] == "runtime:omc_oracle" for item in checks))

    def test_capability_b_is_only_positive_parent_inheritance_evidence(self):
        row = dict(self._observations()[0], model="gpt-5.6-sol", effort="high", sandbox="workspace-write")
        _, checks = _aggregate([], [row], False, False, parent_metadata={"model": "gpt-5.6-sol", "effort": "high", "sandbox": "workspace-write"})
        self.assertTrue(any(c["name"] == "capability:B-spawn-config" for c in checks))

    def test_capability_d_requires_observed_contradiction(self):
        row = dict(self._observations()[0], model="gpt-4.1")
        _, checks = _aggregate([], [row], False, False, config_present=True)
        self.assertTrue(any(c["name"] == "capability:D-config-contradicted" for c in checks))

    def test_capability_sandbox_only_mismatch_is_d_not_b(self):
        row = dict(self._observations()[-1], sandbox="workspace-write")
        _, checks = _aggregate(
            [], [row], False, False,
            parent_metadata={"model": "gpt-5.6-sol", "effort": "high", "sandbox": "workspace-write"},
            config_present=True,
        )
        self.assertTrue(any(c["name"] == "capability:D-config-contradicted" for c in checks))
        self.assertFalse(any(c["name"] == "capability:B-spawn-config" for c in checks))

    def test_capability_unknown_is_used_for_missing_effective_metadata(self):
        row = dict(self._observations()[0], model=None, effort=None, sandbox=None)
        _, checks = _aggregate([], [row], False, False)
        self.assertTrue(any(c["name"] == "capability:UNKNOWN" for c in checks))

    def test_capability_c_is_used_without_spawn(self):
        _, checks = _aggregate([], [], False, False)
        self.assertTrue(any(c["name"] == "capability:C-no-usable-spawn" for c in checks))

    def test_malformed_or_parent_edit_is_failure(self):
        overall, checks = _aggregate([], self._observations(), fixture_changed=True, malformed=True)
        self.assertEqual(overall, "FAIL")
        self.assertEqual({item["name"] for item in checks if item["status"] == "FAILED"} & {"protocol-integrity", "parent-boundary"}, {"protocol-integrity", "parent-boundary"})

    def test_nested_thread_shape_and_sandbox_aliases(self):
        event = {"method": "thread/started", "params": {"thread": {"id": "child", "agentRole": "omc_fixer", "threadSource": "subAgent", "model": "gpt-5.6-luna", "reasoningEffort": "high", "sandbox": {"type": "workspaceWrite"}, "parentThreadId": "root"}}}
        observation = _observation_from_event(event, {"root", "child"})
        self.assertIsNotNone(observation)
        assert observation is not None
        self.assertEqual(observation["role"], "omc_fixer")
        self.assertEqual(observation["sandbox"], "workspace-write")
        self.assertEqual(_normalise_sandbox({"type": "readOnly"}), "read-only")

    def test_unrelated_thread_event_is_ignored(self):
        event = {"params": {"thread": {"id": "other", "agentRole": "omc_fixer", "model": "gpt-5.6-luna"}}}
        self.assertIsNone(_observation_from_event(event, {"root", "child"}))

    def test_host_returned_legacy_trace_is_consumed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "rollout.jsonl"
            path.write_text(
                '\n'.join(
                    [
                        '{"type":"session_meta","payload":{"id":"child","agent_role":"omc_fixer","source":"subAgentThreadSpawn","parentThreadId":"root"}}',
                        '{"type":"turn_context","payload":{"model":"gpt-5.6-luna","effort":"high","sandbox_policy":{"type":"workspaceWrite"}}}',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            rows, malformed = _trace_observations({"child": str(path)}, {"root", "child"})
            self.assertFalse(malformed)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["role"], "omc_fixer")
            self.assertEqual(rows[1]["model"], "gpt-5.6-luna")

    def test_unrelated_trace_path_is_not_read(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "rollout.jsonl"
            path.write_text('{"type":"session_meta","payload":{"agent_role":"omc_fixer"}}\n', encoding="utf-8")
            rows, malformed = _trace_observations({"other": str(path)}, {"root", "child"})
            self.assertEqual((rows, malformed), ([], False))

    def test_read_command_is_not_write_authorship(self):
        events = [{"method": "item/completed", "params": {"threadId": "child", "item": {"type": "commandExecution", "command": "cat target.py"}}}]
        evidence = _role_write_evidence(events, {"omc_fixer": {"child"}}, root_thread_id="root")
        self.assertFalse(evidence["omc_fixer"])
        self.assertFalse(evidence["__observed__"])

    def test_parent_typed_write_is_not_fixer_authorship(self):
        events = [{
            "method": "item/completed",
            "params": {"threadId": "root", "item": {"type": "fileChange", "path": "target.py"}},
        }]
        evidence = _role_write_evidence(events, {"omc_fixer": {"child"}}, root_thread_id="root")
        self.assertTrue(evidence["__root__"])
        self.assertFalse(evidence["omc_fixer"])

    def test_opaque_command_marks_readonly_behavior_unknown(self):
        events = [{
            "method": "item/completed",
            "params": {"threadId": "child", "item": {"type": "commandExecution", "command": "cat target.py", "status": "completed"}},
        }]
        evidence = _role_write_evidence(events, {"omc_explorer": {"child"}}, root_thread_id="root")
        self.assertTrue(evidence["__unknown__:omc_explorer"])
        self.assertFalse(evidence["omc_explorer"])

    def test_failed_child_is_not_successful_completion(self):
        events = [{"method": "turn/failed", "params": {"threadId": "child", "turn": {"status": "failed"}}}]
        self.assertFalse(_role_completion_evidence(events, {"omc_explorer": {"child"}})["omc_explorer"])

    def test_structured_diagnostic_uses_final_child_item(self):
        role_ids = {"omc_oracle": {"child"}}
        events = [{
            "method": "turn/completed",
            "params": {"threadId": "child", "turn": {"items": [{"phase": "final_answer", "text": "OMC_DIAGNOSTIC_JSON {\"role\":\"omc_oracle\",\"verdict\":\"FAIL\"}"}]}},
        }]
        self.assertEqual(_diagnostic_outputs(events, role_ids)["omc_oracle"]["verdict"], "FAIL")

    def test_oracle_semantic_forms_reach_aggregation(self):
        payload = {
            "role": "omc_oracle",
            "review_target": "review_target.py",
            "review_target_found": True,
            "verdict": "FAIL",
            "findings": [{
                "file": "review_target.py",
                "function": "average",
                "input": {"values": []},
                "expected": "return 0",
                "observed": {"exception": "ZeroDivisionError", "message": "division by zero"},
            }],
        }
        events = [{"method": "turn/completed", "params": {"threadId": "child", "turn": {"items": [{"phase": "final_answer", "text": "OMC_DIAGNOSTIC_JSON:" + json.dumps(payload)}]}}}]
        diagnostics = _diagnostic_outputs(events, {"omc_oracle": {"child"}})
        _, checks = _aggregate([], self._observations(), False, False, role_text={role: "" for role in ("omc_explorer", "omc_librarian", "omc_fixer", "omc_oracle")}, diagnostics=diagnostics)
        self.assertEqual(next(item["status"] for item in checks if item["name"] == "oracle-verdict"), "INFERRED")

    def test_oracle_finding_rejects_boolean_zero_and_negated_exception_tokens(self):
        base = {
            "file": "review_target.py",
            "function": "average",
            "input": {"values": []},
            "expected": 0,
            "observed": "raised ZeroDivisionError: division by zero",
        }
        self.assertTrue(_oracle_finding_matches(base))

        boolean_zero = dict(base, expected=False)
        self.assertFalse(_oracle_finding_matches(boolean_zero))
        for observed in ("NoZeroDivisionError", "NotZeroDivisionError"):
            self.assertFalse(_oracle_finding_matches(dict(base, observed=observed)))

    def test_oracle_finding_accepts_supported_structured_exception_forms(self):
        base = {
            "file": "review_target.py",
            "function": "average",
            "input": {"values": []},
            "expected": "return 0",
        }
        self.assertTrue(_oracle_finding_matches(dict(base, observed={"exception": "ZeroDivisionError"})))
        self.assertTrue(_oracle_finding_matches(dict(base, observed={"exception": "builtins.ZeroDivisionError"})))
        self.assertFalse(_oracle_finding_matches(dict(base, observed={"exception": "other.ZeroDivisionError"})))
        for malformed in ([], {}, None):
            self.assertFalse(_oracle_finding_matches(dict(base, observed={"exception": malformed})))

    def test_typed_librarian_websearch_source_is_correlated(self):
        events = [{
            "method": "item/completed",
            "params": {"threadId": "child", "item": {"type": "webSearch", "results": [{"type": "text_result", "url": "https://docs.example.test/page#section"}]}},
        }]
        evidence = _librarian_source_evidence(events, {"omc_librarian": {"child"}})
        self.assertEqual(evidence["omc_librarian"], {"https://docs.example.test/page"})

    def test_child_agent_management_is_a_nesting_failure(self):
        child = {"thread_id": "child", "parent_thread_id": "root"}
        event = {"method": "item/completed", "params": {"threadId": "child", "item": {"type": "subAgentActivity", "agentThreadId": "grandchild"}}}
        violations = _nesting_violations([event], [child], "root")
        self.assertTrue(violations)
        overall, checks = _aggregate([], self._observations(), False, False, nesting_violations=violations)
        self.assertEqual(overall, "FAIL")
        self.assertTrue(any(item["name"] == "nesting" and item["status"] == "FAILED" for item in checks))

    def test_root_is_not_counted_as_nested_child(self):
        observations = [{"thread_id": "root", "parent_thread_id": None}] + self._observations()
        root_spawn = {"method": "item/completed", "params": {"threadId": "root", "item": {"type": "collabAgentToolCall", "tool": "spawnAgent", "status": "completed", "receiverThreadIds": ["child"]}}}
        self.assertEqual(_nesting_violations([root_spawn], observations, "root"), [])

    def test_nested_source_provides_role_and_parent(self):
        event = {"method": "thread/started", "params": {"thread": {"id": "child", "source": {"subagent": {"thread_spawn": {"agent_role": "omc_explorer", "parent_thread_id": "root"}}}, "model": "gpt-5.6-luna", "reasoningEffort": "medium", "sandbox": "read-only"}}}
        observation = _observation_from_event(event, {"root", "child"})
        self.assertEqual(observation["role"], "omc_explorer")
        self.assertEqual(observation["parent_thread_id"], "root")
        self.assertEqual(observation["source"], "subAgentThreadSpawn")

    def test_thread_read_path_uses_bare_thread_id(self):
        events = [{
            "method": "thread/read",
            "params": {"result": {"thread": {"id": "child", "path": "/tmp/child.jsonl"}}},
        }]
        self.assertEqual(_returned_paths(events, {"child"}), {"child": "/tmp/child.jsonl"})

    def test_trace_binding_uses_child_id_over_shared_session_id(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "rollout.jsonl"
            path.write_text(
                '{"type":"session_meta","payload":{"id":"child","session_id":"root","agent_role":"omc_explorer","source":{"subagent":{"thread_spawn":{"parent_thread_id":"root","agent_role":"omc_explorer"}}}}}\n'
                '{"type":"turn_context","payload":{"model":"gpt-5.6-luna","effort":"medium","sandbox_policy":{"type":"readOnly"},"multi_agent_version":"v2"}}\n',
                encoding="utf-8",
            )
            rows, malformed = _trace_observations({"child": str(path)}, {"root", "child"})
            self.assertFalse(malformed)
            self.assertTrue(rows)
            self.assertEqual(rows[0]["role"], "omc_explorer")

    def test_activity_task_name_cannot_assign_role(self):
        event = {
            "method": "item/started",
            "params": {
                "threadId": "root",
                "item": {"type": "subAgentActivity", "agentThreadId": "child", "agentPath": "/tmp/explorer_verify"},
            },
        }
        observation = _observation_from_event(event, {"root", "child"})
        self.assertIsNotNone(observation)
        self.assertIsNone(observation["role"])

    def test_v1_completed_spawn_discovers_receiver_before_terminal(self):
        event = {
            "method": "item/completed",
            "params": {"threadId": "root", "item": {
                "type": "collabAgentToolCall", "tool": "spawnAgent", "status": "completed",
                "senderThreadId": "root", "receiverThreadIds": ["child-v1"],
            }},
        }
        self.assertEqual(_event_thread_ids([event]), {"child-v1"})

    def test_v1_failed_spawn_does_not_discover_receiver(self):
        event = {
            "method": "item/completed",
            "params": {"threadId": "root", "item": {
                "type": "collabAgentToolCall", "tool": "spawnAgent", "status": "failed",
                "senderThreadId": "root", "receiverThreadIds": [],
            }},
        }
        self.assertEqual(_event_thread_ids([event]), set())

    def test_skill_request_or_missing_parent_marker_is_not_runtime_load(self):
        with tempfile.TemporaryDirectory() as temp:
            skill = Path(temp) / "SKILL.md"
            skill.write_text("installed skill content\nOMC_ORCHESTRATOR_V1\n", encoding="utf-8")
            accepted = [{
                "method": "item/started",
                "params": {"threadId": "root", "item": {"type": "skill", "path": str(skill)}},
            }]
            self.assertFalse(_skill_read_evidence(accepted, str(skill), root_thread_id="root"))

    def test_deleted_final_target_fails_effect_check(self):
        overall, checks = _aggregate([], self._observations(), False, False, target_ok=False)
        self.assertEqual(overall, "FAIL")
        self.assertTrue(any(item["name"] == "fixer-effect" and item["status"] == "FAILED" for item in checks))

    def test_prompt_uses_explicit_native_role_triples(self):
        prompt = _parent_prompt(Path("/tmp/fixture"), Path("/tmp/skills"), "v2")
        self.assertNotIn("omc_role", prompt)
        self.assertIn("agent_type='omc_explorer', task_name='explorer_verify', fork_turns='none'", prompt)
        self.assertIn("agent_type='omc_oracle', task_name='oracle_verify', fork_turns='none'", prompt)
        self.assertIn("task (a nonempty objective)", prompt)
        self.assertIn("an input object mapping each function parameter name", prompt)

    def test_fixture_snapshot_does_not_follow_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            outside = root / "outside.txt"
            outside.write_text("secret", encoding="utf-8")
            fixture = root / "fixture"
            fixture.mkdir()
            (fixture / "link.txt").symlink_to(outside)
            self.assertNotIn("link.txt", _fixture_snapshot(fixture))
            self.assertEqual(_fixture_unsafe_entries(fixture), ["link.txt"])

    def test_fixture_git_overrides_global_hooks_and_signing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture = root / "fixture"
            fixture.mkdir()
            sentinel = root / "outside-sentinel"
            hook_dir = root / "global-hooks"
            hook_dir.mkdir()
            hook = hook_dir / "pre-commit"
            hook.write_bytes(f"#!/bin/sh\ntouch {shlex.quote(sentinel.as_posix())}\n".encode("utf-8"))
            hook.chmod(0o755)
            global_config = root / "gitconfig"
            _git_checked(["config", "--file", str(global_config), "core.hooksPath", str(hook_dir)], fixture)
            _git_checked(["config", "--file", str(global_config), "commit.gpgSign", "true"], fixture)
            with mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(global_config), "GIT_CONFIG_NOSYSTEM": "1"}):
                _git_checked(["init", "-q"], fixture)
                _git_checked(["config", "user.name", "Verifier"], fixture)
                _git_checked(["config", "user.email", "verify@localhost"], fixture)
                (fixture / "value.txt").write_text("ok\n", encoding="utf-8")
                _git_checked(["add", "value.txt"], fixture)
                _git_checked(["commit", "-qm", "fixture"], fixture)
            self.assertFalse(sentinel.exists())


class VerifyConfigurationTests(unittest.TestCase):
    def test_configuration_is_intent_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            codex = root / "codex"
            skills = root / "skills/oh-my-codex"
            (codex / "agents").mkdir(parents=True)
            skills.mkdir(parents=True)
            (skills / "SKILL.md").write_text("OMC_ORCHESTRATOR_V1\n", encoding="utf-8")
            for role in ("explorer", "librarian", "fixer", "oracle"):
                model = "gpt-5.6-sol" if role == "oracle" else "gpt-5.6-luna"
                effort = "medium" if role == "explorer" else "high"
                sandbox = "workspace-write" if role == "fixer" else "read-only"
                (codex / "agents" / f"omc_{role}.toml").write_text(
                    f'model = "{model}"\nmodel_reasoning_effort = "{effort}"\nsandbox_mode = "{sandbox}"\ndeveloper_instructions = "OMC_ROLE_{role.upper()}_V1"\n[agents]\nenabled = false\n',
                    encoding="utf-8",
                )
            checks, _ = _configured_checks(codex, root / "skills")
            self.assertTrue(any(c["name"] == "skill-load" and c["status"] == "INFERRED" for c in checks))
            self.assertFalse(any(c["status"] == "FAILED" for c in checks))


class ProcessCleanupTests(unittest.TestCase):
    def test_terminate_process_is_idempotent_for_finished_process(self):
        process = mock.Mock()
        process.poll.return_value = 0
        _terminate_process(process)
        process.terminate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
