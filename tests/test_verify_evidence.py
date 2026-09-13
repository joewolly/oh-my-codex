from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from oh_my_codex import verify as verify_module
from oh_my_codex.verify import (
    _aggregate,
    _diagnostic_outputs,
    _event_thread_ids,
    _observation_from_event,
    _role_write_evidence,
    _skill_read_evidence,
    run_verify,
)


class AdversarialVerifierEvidenceTests(unittest.TestCase):
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

    def _aggregate_checks(self, *, diagnostics=None, role_write_evidence=None):
        role_text = {role: "" for role in ("omc_explorer", "omc_librarian", "omc_fixer", "omc_oracle")}
        _, checks = _aggregate(
            [],
            self._observations(),
            fixture_changed=False,
            malformed=False,
            target_ok=True,
            role_text=role_text,
            root_thread_id="root",
            role_write_evidence=role_write_evidence,
            completion_evidence={role: True for role in role_text},
            terminal_status={role: "completed" for role in role_text},
            diagnostics=diagnostics,
            skill_read=True,
        )
        return {check["name"]: check for check in checks}

    def test_agent_path_task_name_without_typed_role_does_not_prove_role(self):
        event = {
            "method": "item/completed",
            "params": {
                "threadId": "root",
                "item": {
                    "type": "subAgentActivity",
                    "agentThreadId": "child",
                    "agentPath": "omc_explorer",
                    "taskName": "explorer_verify",
                    "kind": "completed",
                },
            },
        }
        known_ids = {"root"} | _event_thread_ids([event])
        observation = _observation_from_event(event, known_ids)
        self.assertIsNotNone(observation)
        assert observation is not None
        self.assertIsNone(observation["role"])
        self.assertIsNone(observation["source"])
        self.assertIsNone(observation["model"])

    def test_trace_session_id_parent_does_not_replace_child_identity(self):
        from oh_my_codex.verify import _trace_observations

        with tempfile.TemporaryDirectory() as temp:
            trace = Path(temp) / "child.jsonl"
            trace.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "type": "session_meta",
                                "payload": {
                                    "id": "child",
                                    "session_id": "root",
                                    "source": {
                                        "subagent": {
                                            "thread_spawn": {
                                                "parent_thread_id": "root",
                                                "agent_role": "omc_explorer",
                                            }
                                        }
                                    },
                                },
                            }
                        ),
                        json.dumps(
                            {
                                "type": "turn_context",
                                "payload": {
                                    "model": "gpt-5.6-luna",
                                    "effort": "medium",
                                    "sandbox_policy": {"type": "workspace-write"},
                                },
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            rows, malformed = _trace_observations({"child": str(trace)}, {"root", "child"})
            self.assertFalse(malformed)
            self.assertTrue(rows)
            self.assertTrue(any(row.get("thread_id") == "child" and row.get("role") == "omc_explorer" for row in rows))
            self.assertTrue(any(row.get("parent_thread_id") == "root" for row in rows))

    def test_rpc_thread_result_with_bare_id_populates_returned_path(self):
        child_path = "/tmp/omc-child-rollout.jsonl"
        with tempfile.TemporaryDirectory() as temp:
            server = Path(temp) / "fake_app_server.py"
            server.write_text(
                "import json, sys\n"
                f"child_path = {json.dumps(child_path)}\n"
                "for line in sys.stdin:\n"
                "    request = json.loads(line)\n"
                "    if request.get('method') == 'thread/read':\n"
                "        result = {'thread': {'id': 'child', 'path': child_path, 'agentRole': 'omc_explorer'}}\n"
                "    else:\n"
                "        result = {}\n"
                "    print(json.dumps({'id': request.get('id'), 'result': result}), flush=True)\n",
                encoding="utf-8",
            )
            process = verify_module._AppServer([sys.executable, str(server)], {}, time.monotonic() + 2)
            try:
                response = process.request("thread/read", {"threadId": "child"}, 1)
                self.assertIsNotNone(response)
                self.assertEqual(process.returned_paths.get("child"), child_path)
            finally:
                process.close()
                for stream in (process.process.stdin, process.process.stdout, process.process.stderr):
                    if stream is not None:
                        stream.close()

    def test_skill_request_or_unmarked_parent_input_does_not_prove_skill_load(self):
        with tempfile.TemporaryDirectory() as temp:
            skill = Path(temp) / "SKILL.md"
            skill.write_text("A real installed skill instruction line.\n", encoding="utf-8")
            outbound_skill = {
                "method": "turn/start",
                "params": {
                    "threadId": "root",
                    "input": [{"type": "skill", "path": str(skill)}],
                },
            }
            self.assertFalse(_skill_read_evidence([outbound_skill], str(skill), root_thread_id="root"))

            host_input_without_marker = {
                "method": "item/completed",
                "params": {
                    "threadId": "root",
                    "item": {"type": "skill", "path": str(skill), "text": "skill accepted"},
                },
            }
            self.assertFalse(_skill_read_evidence([host_input_without_marker], str(skill), root_thread_id="root"))

    def test_shell_write_by_readonly_child_or_root_is_not_readonly_evidence(self):
        child_write = {
            "method": "item/completed",
            "params": {
                "threadId": "child-omc_explorer",
                "item": {
                    "type": "commandExecution",
                    "command": "sh -c 'printf hacked > target.py'",
                    "status": "completed",
                    "exitCode": 0,
                },
            },
        }
        child_evidence = _role_write_evidence(
            [child_write], {"omc_explorer": {"child-omc_explorer"}}, root_thread_id="root"
        )
        checks = self._aggregate_checks(role_write_evidence=child_evidence)
        self.assertIn(checks["readonly-behavior"]["status"], {"FAILED", "UNVERIFIED"})

        root_write = {
            "method": "item/completed",
            "params": {
                "threadId": "root",
                "item": {
                    "type": "commandExecution",
                    "command": "sh -c 'printf hacked > target.py'",
                    "status": "completed",
                    "exitCode": 0,
                },
            },
        }
        root_evidence = _role_write_evidence(
            [root_write], {"omc_explorer": {"child-omc_explorer"}}, root_thread_id="root"
        )
        root_checks = self._aggregate_checks(role_write_evidence=root_evidence)
        if "parent-authorship" in root_checks:
            self.assertIn(root_checks["parent-authorship"]["status"], {"FAILED", "UNVERIFIED"})

        typed_root_write = {
            "method": "item/completed",
            "params": {"threadId": "root", "item": {"type": "fileChange", "path": "target.py"}},
        }
        typed_root_evidence = _role_write_evidence(
            [typed_root_write], {"omc_explorer": {"child-omc_explorer"}}, root_thread_id="root"
        )
        self.assertTrue(typed_root_evidence["__root__"])
        typed_root_checks = self._aggregate_checks(role_write_evidence=typed_root_evidence)
        self.assertEqual(typed_root_checks["parent-authorship"]["status"], "FAILED")

    def test_fixer_receipt_true_without_required_fields_is_not_valid_receipt(self):
        events = [
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "child-omc_fixer",
                    "turn": {
                        "items": [
                            {
                                "phase": "final_answer",
                                "text": 'OMC_DIAGNOSTIC_JSON:{"role":"omc_fixer","receipt":true}',
                            }
                        ]
                    },
                },
            }
        ]
        diagnostics = _diagnostic_outputs(events, {"omc_fixer": {"child-omc_fixer"}})
        self.assertEqual(diagnostics["omc_fixer"], {"role": "omc_fixer", "receipt": True})
        checks = self._aggregate_checks(diagnostics=diagnostics)
        self.assertIn(checks["fixer-receipt"]["status"], {"FAILED", "UNVERIFIED"})

    def test_oracle_empty_or_pass_without_finding_does_not_pass_planted_defect(self):
        payloads = [
            {"role": "omc_oracle"},
            {
                "role": "omc_oracle",
                "review_target": "review_target.py",
                "review_target_found": True,
                "verdict": "PASS",
            },
        ]
        for payload in payloads:
            with self.subTest(payload=payload):
                events = [
                    {
                        "method": "turn/completed",
                        "params": {
                            "threadId": "child-omc_oracle",
                            "turn": {
                                "items": [
                                    {
                                        "phase": "final_answer",
                                        "text": "OMC_DIAGNOSTIC_JSON:" + json.dumps(payload),
                                    }
                                ]
                            },
                        },
                    }
                ]
                diagnostics = _diagnostic_outputs(events, {"omc_oracle": {"child-omc_oracle"}})
                checks = self._aggregate_checks(diagnostics=diagnostics)
                self.assertIn(checks["oracle-verdict"]["status"], {"FAILED", "UNVERIFIED"})

    def test_run_verify_retained_fixture_reflects_deleted_target(self):
        class FakeAppServer:
            def __init__(self, argv, env, deadline):
                self.events = []
                self.returned_paths = {}
                self.root_thread_id = None
                self.stderr = bytearray()
                self.fixture = None

            def request(self, method, params, request_id):
                if method == "initialize":
                    return {"id": request_id, "result": {"userAgent": "fake-app-server"}}
                if method == "thread/start":
                    self.root_thread_id = "root"
                    self.fixture = Path(params["cwd"])
                    return {
                        "id": request_id,
                        "result": {
                            "thread": {
                                "id": "root",
                                "model": "gpt-5.6-sol",
                                "reasoningEffort": "high",
                                "sandbox": "workspace-write",
                            }
                        },
                    }
                if method == "turn/start":
                    assert self.fixture is not None
                    (self.fixture / "target.py").unlink()
                    self.events.append(
                        {"method": "turn/completed", "params": {"threadId": "root", "turn": {"status": "completed"}}}
                    )
                    return {"id": request_id, "result": {}}
                return {"id": request_id, "result": {}}

            def collect_turn(self):
                return None

            def close(self):
                return None

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            artifact_home = root / "codex home"
            skills_home = root / "skills home"
            with mock.patch.object(verify_module, "_AppServer", FakeAppServer):
                report = run_verify(
                    artifact_home,
                    skills_home,
                    codex_bin="fake-codex",
                    timeout=2,
                    keep_artifacts=True,
                )
            artifact_dir = Path(report["provenance"]["artifact_dir"])
            try:
                self.assertFalse(report["fixture"]["target_corrected"])
                self.assertFalse((artifact_dir / "fixture" / "target.py").exists())
            finally:
                shutil.rmtree(artifact_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
