"""Protocol-level tests for the bounded app-server verification transport."""

from __future__ import annotations

import os
import contextlib
from pathlib import Path
import sys
import tempfile
import textwrap
import time
import unittest

from oh_my_codex.verify import _AppServer, _aggregate, _observation_from_event


FAKE_SERVER = textwrap.dedent(
    r"""
    import json
    import sys
    import time

    mode = sys.argv[1]

    def send(value):
        sys.stdout.write(json.dumps(value, separators=(",", ":")) + "\n")
        sys.stdout.flush()

    for raw in sys.stdin:
        request = json.loads(raw)
        request_id = request.get("id")
        method = request.get("method")
        if mode == "fragmented" and method == "initialize":
            response = json.dumps({"id": request_id, "result": {"userAgent": "fake"}}, separators=(",", ":"))
            notification = json.dumps({"method": "thread/started", "params": {"thread": {"id": "root", "agent_role": "omc_explorer"}}}, separators=(",", ":"))
            combined = response + "\n" + notification + "\n"
            midpoint = max(1, len(combined) // 2)
            sys.stdout.write(combined[:midpoint])
            sys.stdout.flush()
            time.sleep(0.01)
            sys.stdout.write(combined[midpoint:])
            sys.stdout.flush()
        elif mode == "root-terminal" and method == "turn/start":
            send({"id": request_id, "result": {}})
            send({"method": "turn/completed", "params": {"threadId": "child"}})
            time.sleep(0.01)
            send({"method": "turn/completed", "params": {"threadId": "root"}})
            send({"method": "after/root", "params": {}})
        elif mode == "malformed":
            sys.stdout.write("{malformed json\n")
            sys.stdout.flush()
            send({"id": request_id, "result": {"ok": True}})
        elif mode == "timeout":
            time.sleep(5)
        elif mode == "eof":
            break
        else:
            send({"id": request_id, "result": {}})
    """
)


class AppServerProtocolTests(unittest.TestCase):
    def _server(self, mode: str, seconds: float = 1.0):
        temp = tempfile.TemporaryDirectory(prefix="omc verify protocol ")
        script = Path(temp.name) / "fake_app_server.py"
        script.write_text(FAKE_SERVER, encoding="utf-8")
        server = _AppServer(
            [sys.executable, str(script), mode],
            os.environ.copy(),
            time.monotonic() + seconds,
        )
        return temp, server

    @staticmethod
    def _shutdown(temp, server):
        server.close()
        for stream in (server.process.stdin, server.process.stdout, server.process.stderr):
            with contextlib.suppress(Exception):
                if stream is not None:
                    stream.close()
        temp.cleanup()

    def test_fragmented_and_coalesced_messages_are_retained(self):
        temp, server = self._server("fragmented")
        try:
            response = server.request("initialize", {}, 1)
            self.assertEqual(response["result"]["userAgent"], "fake")
            followup = server.request("initialized", {}, 2)
            self.assertEqual(followup["result"], {})
            self.assertTrue(any(event.get("method") == "thread/started" for event in server.events))
            self.assertEqual(len(server.events), 3)
        finally:
            self._shutdown(temp, server)

    def test_collect_turn_waits_for_root_terminal_after_child_terminal(self):
        temp, server = self._server("root-terminal")
        try:
            server.root_thread_id = "root"
            self.assertIsNotNone(server.request("turn/start", {}, 1))
            server.collect_turn()
            terminal_ids = [
                event["params"]["threadId"]
                for event in server.events
                if event.get("method") == "turn/completed"
            ]
            self.assertEqual(terminal_ids, ["child", "root"])
            self.assertNotIn("after/root", [event.get("method") for event in server.events])
        finally:
            self._shutdown(temp, server)

    def test_malformed_line_is_bounded_and_reported(self):
        temp, server = self._server("malformed")
        try:
            response = server.request("initialize", {}, 1)
            self.assertEqual(response["result"]["ok"], True)
            malformed = [event for event in server.events if "_malformed" in event]
            self.assertEqual(len(malformed), 1)
        finally:
            self._shutdown(temp, server)

    def test_early_eof_returns_without_hanging(self):
        temp, server = self._server("eof", seconds=0.5)
        started = time.monotonic()
        try:
            self.assertIsNone(server.request("initialize", {}, 1))
            self.assertLess(time.monotonic() - started, 1.0)
        finally:
            self._shutdown(temp, server)

    def test_timeout_is_bounded_and_close_reaps_process(self):
        temp, server = self._server("timeout", seconds=0.15)
        started = time.monotonic()
        try:
            self.assertIsNone(server.request("initialize", {}, 1))
            self.assertLess(time.monotonic() - started, 1.0)
        finally:
            self._shutdown(temp, server)
            self.assertIsNotNone(server.process.poll())

    def test_self_reported_model_without_spawn_source_cannot_pass_routing(self):
        event = {
            "method": "thread/started",
            "params": {
                "thread": {
                    "id": "child",
                    "agent_role": "omc_explorer",
                    "model": "gpt-5.6-luna",
                    "effort": "medium",
                    "sandbox": "read-only",
                    "parentThreadId": "root",
                    "text": "OMC_ROLE_EXPLORER_V1",
                }
            },
        }
        observation = _observation_from_event(event, {"root", "child"})
        self.assertIsNotNone(observation)
        assert observation is not None
        overall, checks = _aggregate(
            [], [observation], fixture_changed=False, malformed=False, root_thread_id="root"
        )
        self.assertEqual(overall, "FAIL")
        self.assertTrue(
            any(
                check["name"] == "runtime:omc_explorer" and check["status"] == "FAILED"
                for check in checks
            )
        )


if __name__ == "__main__":
    unittest.main()
