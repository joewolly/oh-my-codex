"""Live, bounded verification of an installed Oh-My-Codex role set.

The verifier deliberately keeps its evidence model conservative.  A role TOML
file or a model's final prose can establish configuration intent, but cannot by
itself establish that the app-server ran that role.  Execution evidence must
be connected to a thread id returned by the server (and, where available, its
returned legacy rollout path).
"""

from __future__ import annotations

import contextlib
import json
import os
import queue
import re
import signal
import subprocess
import tempfile
import threading
import time
import tomllib
import platform
from urllib.parse import urldefrag
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import __version__


_ROLES: dict[str, dict[str, str]] = {
    "omc_explorer": {"model": "gpt-5.6-luna", "effort": "medium", "sandbox": "read-only"},
    "omc_librarian": {"model": "gpt-5.6-luna", "effort": "high", "sandbox": "read-only"},
    "omc_fixer": {"model": "gpt-5.6-luna", "effort": "high", "sandbox": "workspace-write"},
    "omc_oracle": {"model": "gpt-5.6-sol", "effort": "high", "sandbox": "read-only"},
}
_MARKERS = {
    "omc_explorer": "OMC_ROLE_EXPLORER_V1",
    "omc_librarian": "OMC_ROLE_LIBRARIAN_V1",
    "omc_fixer": "OMC_ROLE_FIXER_V1",
    "omc_oracle": "OMC_ROLE_ORACLE_V1",
}
_PARENT_MARKER = "OMC_ORCHESTRATOR_V1"
_TERMINAL_METHODS = {"turn/completed", "turn/failed", "turn/cancelled", "turn/stopped"}
_SENSITIVE_KEYS = {"token", "access_token", "refresh_token", "api_key", "authorization", "password", "secret"}


def _check(name: str, status: str, evidence: str) -> dict[str, str]:
    return {"name": name, "status": status, "evidence": evidence}


def _sanitise(value: Any, key: str = "") -> Any:
    if key.lower() in _SENSITIVE_KEYS or any(part in key.lower() for part in ("token", "credential", "authorization")):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(k): _sanitise(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitise(item) for item in value]
    return value


def _flatten_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        result: list[str] = []
        for child in value.values():
            result.extend(_flatten_strings(child))
        return result
    if isinstance(value, (list, tuple)):
        result = []
        for child in value:
            result.extend(_flatten_strings(child))
        return result
    return []


def _first(value: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in value:
            return value[key]
    return None


def _normalise_sandbox(value: Any) -> str | None:
    if isinstance(value, Mapping):
        value = _first(value, "mode", "sandboxMode", "sandbox_mode", "type")
    if value is None:
        return None
    text = str(value).lower().replace("_", "-")
    if text in {"read-only", "readonly", "ro"}:
        return "read-only"
    if text in {"workspace-write", "workspacewrite"}:
        return "workspace-write"
    return text


def _source_details(value: Any) -> tuple[str | None, str | None, str | None]:
    """Normalize legacy source tags, including nested subagent/thread_spawn."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key).lower().replace("_", "")
            if key_text == "subagent":
                nested_source, nested_role, nested_parent = _source_details(child)
                return nested_source or "subAgent", nested_role, nested_parent
            if key_text in {"threadspawn", "subagentthreadspawn"}:
                nested_role = child.get("agent_role", child.get("agentRole")) if isinstance(child, Mapping) else None
                nested_parent = child.get("parent_thread_id", child.get("parentThreadId")) if isinstance(child, Mapping) else None
                return "subAgentThreadSpawn", str(nested_role) if nested_role else None, str(nested_parent) if nested_parent else None
        return None, None, None
    if value is None:
        return None, None, None
    text = str(value)
    lowered = text.lower().replace("_", "")
    if lowered in {"subagent", "subagentspawn"}:
        return "subAgent", None, None
    if lowered in {"subagentthreadspawn", "threadspawn"}:
        return "subAgentThreadSpawn", None, None
    return text, None, None


def _iter_dicts(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_dicts(child)


def _thread_id(value: Mapping[str, Any]) -> str | None:
    candidate = _first(value, "threadId", "thread_id")
    if isinstance(candidate, str) and candidate:
        return candidate
    thread = value.get("thread")
    if isinstance(thread, Mapping):
        candidate = _first(thread, "id", "threadId", "thread_id")
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


def _event_thread_ids(events: Iterable[Mapping[str, Any]]) -> set[str]:
    ids: set[str] = set()
    for event in events:
        method = event.get("method")
        params = event.get("params")
        if not isinstance(params, Mapping):
            continue
        item = params.get("item")
        if isinstance(item, Mapping) and item.get("type") == "subAgentActivity":
            child_id = item.get("agentThreadId")
            if isinstance(child_id, str) and child_id:
                ids.add(child_id)
        # V1 reports native spawning as a completed collaboration tool item;
        # failed calls have no usable receiver and must not create children.
        if (
            isinstance(item, Mapping)
            and item.get("type") == "collabAgentToolCall"
            and item.get("tool") == "spawnAgent"
            and item.get("status") == "completed"
        ):
            receivers = item.get("receiverThreadIds")
            if isinstance(receivers, list):
                ids.update(child for child in receivers if isinstance(child, str) and child)
        if method in _TERMINAL_METHODS:
            candidate = _thread_id(params)
            if candidate:
                ids.add(candidate)
        if method not in {"thread/started", "thread/updated", "thread/read", "thread/forked"}:
            continue
        for item in (params, params.get("thread"), params.get("result")):
            if isinstance(item, Mapping):
                candidate = _thread_id(item)
                if candidate:
                    ids.add(candidate)
    return ids


def _observation_from_event(event: Mapping[str, Any], known_ids: set[str]) -> dict[str, Any] | None:
    """Extract one role observation without accepting uncorrelated prose."""
    method = event.get("method")
    if method in {"item/started", "item/completed"}:
        params = event.get("params")
        if not isinstance(params, Mapping) or not isinstance(params.get("item"), Mapping):
            return None
        item = params["item"]
        if item.get("type") != "subAgentActivity":
            return None
        child_id = item.get("agentThreadId")
        parent_id = params.get("threadId")
        if not isinstance(child_id, str) or child_id not in known_ids or not isinstance(parent_id, str):
            return None
        # Activity records prove that a child id was created.  Their
        # agentPath/task name is display metadata and is not authoritative
        # role identity; role comes from the typed child thread or its bound
        # session_meta record.
        return {"thread_id": child_id, "role": None, "source": None, "model": None, "effort": None, "sandbox": None, "multi_agent_version": None, "parent_thread_id": parent_id, "path": None, "text": "", "completed": item.get("kind") == "completed"}
    if method not in {"thread/started", "thread/updated", "thread/read", "thread/forked"}:
        return None
    params = event.get("params")
    if not isinstance(params, Mapping):
        return None
    candidates = [params]
    for key in ("thread", "result"):
        child = params.get(key)
        if isinstance(child, Mapping):
            candidates.append(child)
    for item in candidates:
        tid = _thread_id(item)
        if not tid or tid not in known_ids:
            continue
        # Thread metadata is commonly nested below ``thread`` while legacy
        # records put the same fields beside the id.  Merge only that child,
        # retaining the host-correlated id requirement above.
        data = dict(item)
        if isinstance(item.get("thread"), Mapping):
            data.update(item["thread"])
        role = _first(data, "agent_role", "agentRole")
        source_value = _first(data, "source", "threadSource", "thread_source", "sourceKind")
        source, source_role, source_parent = _source_details(source_value)
        if role is None:
            role = source_role
        model = _first(data, "model", "modelId", "model_id")
        effort = _first(data, "effort", "reasoningEffort", "reasoning_effort")
        sandbox = _first(data, "sandbox", "sandboxPolicy", "sandbox_policy")
        multi_agent_version = _first(data, "multi_agent_version", "multiAgentVersion")
        parent = _first(data, "forkedFromId", "parentThreadId", "parent_thread_id") or source_parent
        path = _first(data, "path", "rolloutPath", "rollout_path")
        text = " ".join(_flatten_strings(data))
        if any(x is not None for x in (role, source, model, effort, sandbox, parent, path)):
            return {
                "thread_id": tid,
                "role": str(role) if role is not None else None,
                "source": str(source) if source is not None else None,
                "model": str(model) if model is not None else None,
                "effort": str(effort) if effort is not None else None,
                "sandbox": _normalise_sandbox(sandbox),
                "multi_agent_version": str(multi_agent_version) if multi_agent_version is not None else None,
                "parent_thread_id": str(parent) if parent is not None else None,
                "path": str(path) if path is not None else None,
                "text": text,
            }
    return None


def _trace_observation(record: Mapping[str, Any], thread_id: str) -> dict[str, Any] | None:
    """Read only typed legacy rollout records from a host-returned path."""
    record_type = record.get("type")
    if record_type not in {"session_meta", "turn_context", "response_item", "event_msg"}:
        return None
    payload = record.get("payload")
    if not isinstance(payload, Mapping):
        payload = record
    # ``id`` identifies this rollout thread; ``session_id`` is the shared
    # session group and may legitimately identify the parent.
    record_id = _first(payload, "id", "thread_id", "threadId")
    if record_type == "session_meta" and record_id is not None and str(record_id) != thread_id:
        return None
    role = _first(payload, "agent_role", "agentRole")
    source_value = _first(payload, "source", "threadSource", "thread_source", "sourceKind")
    source, source_role, source_parent = _source_details(source_value)
    if role is None:
        role = source_role
    model = _first(payload, "model", "modelId", "model_id")
    effort = _first(payload, "effort", "reasoningEffort", "reasoning_effort")
    sandbox = _first(payload, "sandbox", "sandboxPolicy", "sandbox_policy")
    multi_agent_version = _first(payload, "multi_agent_version", "multiAgentVersion")
    parent = _first(payload, "forkedFromId", "parentThreadId", "parent_thread_id") or source_parent
    if all(value is None for value in (role, source, model, effort, sandbox, parent, multi_agent_version)):
        event_name = str(_first(payload, "event", "name", "method") or "").lower()
        if record_type != "event_msg" or "completed" not in event_name:
            return None
        return {"thread_id": thread_id, "role": None, "source": None, "model": None, "effort": None, "sandbox": None, "multi_agent_version": None, "parent_thread_id": None, "path": None, "text": "", "completed": True}
    return {
        "thread_id": thread_id,
        "role": str(role) if role is not None else None,
        "source": str(source) if source is not None else None,
        "model": str(model) if model is not None else None,
        "effort": str(effort) if effort is not None else None,
        "sandbox": _normalise_sandbox(sandbox),
        "multi_agent_version": str(multi_agent_version) if multi_agent_version is not None else None,
        "parent_thread_id": str(parent) if parent is not None else None,
        "path": None,
        "text": "",
        "completed": record_type == "event_msg" and "completed" in str(_first(payload, "event", "name", "method") or "").lower(),
    }


def _trace_observations(paths: Mapping[str, str], known_ids: set[str]) -> tuple[list[dict[str, Any]], bool]:
    """Parse only paths explicitly returned for known threads."""
    observations: list[dict[str, Any]] = []
    malformed = False
    seen_paths: dict[str, str] = {}
    for thread_id, raw_path in paths.items():
        if thread_id not in known_ids:
            continue
        path = Path(raw_path)
        canonical_path = str(path.resolve())
        previous_id = seen_paths.get(canonical_path)
        if previous_id is not None and previous_id != thread_id:
            malformed = True
            continue
        seen_paths[canonical_path] = thread_id
        if not path.is_absolute() or not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        path_rows: list[dict[str, Any]] = []
        matching_session = False
        conflicting_session = False
        for line in lines:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                malformed = True
                continue
            if isinstance(record, Mapping):
                if record.get("type") == "session_meta":
                    payload = record.get("payload") if isinstance(record.get("payload"), Mapping) else record
                    record_id = _first(payload, "id", "thread_id", "threadId")
                    if record_id is None or str(record_id) != thread_id:
                        conflicting_session = True
                    else:
                        matching_session = True
                row = _trace_observation(record, thread_id)
                if row:
                    path_rows.append(row)
        # A rollout path is usable only when its typed session metadata binds
        # it to the host-returned thread id.  Missing binding is unknown; a
        # conflicting binding is stale/untrusted evidence.
        if conflicting_session or not matching_session:
            continue
        for row in path_rows:
            row["path"] = raw_path
            if row not in observations:
                observations.append(row)
    return observations, malformed


def _returned_paths(events: Iterable[Mapping[str, Any]], known_ids: set[str]) -> dict[str, str]:
    paths: dict[str, str] = {}
    for event in events:
        if event.get("method") not in {"thread/started", "thread/updated", "thread/read", "thread/forked"}:
            continue
        params = event.get("params")
        if not isinstance(params, Mapping):
            continue
        for item in _iter_dicts(params):
            thread_id = item.get("id") if isinstance(item.get("id"), str) else _thread_id(item)
            path = item.get("path")
            if thread_id in known_ids and isinstance(path, str) and path:
                paths[thread_id] = path
    return paths


def _configured_checks(codex_home: Path, skills_home: Path) -> tuple[list[dict[str, str]], dict[str, Any]]:
    checks: list[dict[str, str]] = []
    config: dict[str, Any] = {}
    skill_path = skills_home / "oh-my-codex" / "SKILL.md"
    if skill_path.is_file():
        try:
            skill_text = skill_path.read_text(encoding="utf-8")
        except OSError as exc:
            checks.append(_check("skill-load", "FAILED", f"cannot read {skill_path}: {exc}"))
        else:
            if _PARENT_MARKER in skill_text:
                checks.append(_check("skill-load", "INFERRED", f"skill exists and contains {_PARENT_MARKER}"))
            else:
                checks.append(_check("skill-load", "FAILED", "skill exists but parent marker is missing"))
    else:
        checks.append(_check("skill-load", "FAILED", f"missing {skill_path}"))

    for role, expected in _ROLES.items():
        path = codex_home / "agents" / f"{role}.toml"
        if not path.is_file():
            checks.append(_check(f"config:{role}", "FAILED", f"missing {path}"))
            continue
        try:
            with path.open("rb") as handle:
                data = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            checks.append(_check(f"config:{role}", "FAILED", f"invalid TOML: {exc}"))
            continue
        config[role] = data
        strings = _flatten_strings(data)
        marker = _MARKERS[role]
        if not any(marker in text for text in strings):
            checks.append(_check(f"config:{role}", "FAILED", f"missing {marker}"))
            continue
        checks.append(_check(f"config:{role}", "INFERRED", f"role file and {marker} present"))
        agents = data.get("agents")
        if not isinstance(agents, Mapping) or agents.get("enabled") is not False:
            checks.append(_check(f"config:{role}:agents", "FAILED", "role config must set agents.enabled=false"))
        actual = {
            "model": data.get("model"),
            "effort": data.get("model_reasoning_effort", data.get("reasoning_effort")),
            "sandbox": _normalise_sandbox(data.get("sandbox_mode", data.get("sandbox"))),
        }
        for field, value in expected.items():
            if actual[field] is None:
                checks.append(_check(f"config:{role}:{field}", "UNVERIFIED", f"config omits required {field}"))
            elif str(actual[field]) != value:
                checks.append(_check(f"config:{role}:{field}", "FAILED", f"expected {field}={value!r}, got {actual[field]!r}"))
    return checks, config


def _fixture_snapshot(root: Path) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            continue
        if path.is_file() and ".git" not in path.relative_to(root).parts:
            result[str(path.relative_to(root))] = path.read_bytes()
    return result


def _fixture_unsafe_entries(root: Path) -> list[str]:
    """Find links and non-regular files without dereferencing them."""
    unsafe: list[str] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if ".git" in relative.parts:
            continue
        try:
            if path.is_symlink():
                unsafe.append(str(relative))
            elif not path.is_dir() and not path.is_file():
                unsafe.append(str(relative))
        except OSError:
            unsafe.append(str(relative))
    return unsafe


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    # Every fixture Git operation gets an explicit empty hooks directory and
    # signing disablement.  This overrides user/global Git configuration
    # without mutating it or executing hooks outside the disposable fixture.
    hooks = cwd / ".omc-empty-hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        ["git", "-c", f"core.hooksPath={hooks}", "-c", "commit.gpgSign=false", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def _git_checked(args: list[str], cwd: Path) -> None:
    result = _git(args, cwd)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail or result.returncode}")


class _AppServer:
    def __init__(self, argv: list[str], env: Mapping[str, str], deadline: float):
        self.deadline = deadline
        kwargs: dict[str, Any] = {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "env": dict(env),
            "text": False,
            "bufsize": 0,
        }
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            kwargs["start_new_session"] = True
        self.process = subprocess.Popen(argv, **kwargs)
        assert self.process.stdout is not None and self.process.stderr is not None
        self.queue: queue.Queue[tuple[str, bytes | None]] = queue.Queue()
        self._readers = [
            threading.Thread(target=self._reader, args=(self.process.stdout, "stdout"), daemon=True),
            threading.Thread(target=self._reader, args=(self.process.stderr, "stderr"), daemon=True),
        ]
        for reader in self._readers:
            reader.start()
        self.events: list[dict[str, Any]] = []
        self.requests: list[dict[str, Any]] = []
        self.stderr = bytearray()
        self._stdout_buffer = bytearray()
        self.root_thread_id: str | None = None
        self.returned_paths: dict[str, str] = {}

    def _reader(self, stream: Any, kind: str) -> None:
        try:
            while True:
                line = stream.readline()
                if not line:
                    break
                self.queue.put((kind, line))
        except (OSError, ValueError):
            pass
        finally:
            self.queue.put((kind, None))

    def _read(self, timeout: float) -> tuple[str, bytes] | None:
        end = time.monotonic() + max(0.0, timeout)
        while True:
            try:
                kind, line = self.queue.get(timeout=max(0.0, end - time.monotonic()))
            except queue.Empty:
                return None
            if kind == "stderr":
                if line:
                    self.stderr.extend(line)
                continue
            if line is None:
                return None
            return kind, line

    def send(self, method: str, params: Mapping[str, Any], request_id: int) -> None:
        if self.process.stdin is None:
            raise RuntimeError("app-server stdin is closed")
        payload = json.dumps({"method": method, "id": request_id, "params": params}, separators=(",", ":"))
        self.requests.append({"method": method, "id": request_id, "params": dict(params)})
        self.process.stdin.write((payload + "\n").encode())
        self.process.stdin.flush()

    def _json_lines(self, chunk: bytes) -> Iterable[bytes]:
        """Yield complete JSONL records while retaining a split record."""
        self._stdout_buffer.extend(chunk)
        while True:
            try:
                end = self._stdout_buffer.index(b"\n")
            except ValueError:
                return
            line = bytes(self._stdout_buffer[:end]).rstrip(b"\r")
            del self._stdout_buffer[: end + 1]
            if line:
                yield line

    def request(self, method: str, params: Mapping[str, Any], request_id: int) -> dict[str, Any] | None:
        self.send(method, params, request_id)
        while time.monotonic() < self.deadline:
            item = self._read(self.deadline - time.monotonic())
            if item is None:
                break
            _, chunk = item
            response: dict[str, Any] | None = None
            for line in self._json_lines(chunk):
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    self.events.append({"_malformed": line.decode("utf-8", "replace")})
                    continue
                if not isinstance(message, dict):
                    continue
                self.events.append(message)
                self._answer_server_request(message)
                if message.get("id") == request_id:
                    if method == "thread/start" and isinstance(message.get("result"), Mapping):
                        self.root_thread_id = _thread_id(message["result"])
                    if isinstance(message.get("result"), Mapping):
                        for thread in _iter_dicts(message["result"]):
                            path = thread.get("path")
                            thread_id = thread.get("id") if isinstance(thread.get("id"), str) else _thread_id(thread)
                            requested = params.get("threadId") if method == "thread/read" else None
                            if isinstance(requested, str) and thread_id != requested:
                                continue
                            if isinstance(path, str) and path and thread_id:
                                self.returned_paths[thread_id] = path
                    response = message
            if response is not None:
                return response
        return None

    def collect_turn(self) -> None:
        while time.monotonic() < self.deadline:
            item = self._read(self.deadline - time.monotonic())
            if item is None:
                break
            _, chunk = item
            saw_root_terminal = False
            for line in self._json_lines(chunk):
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    self.events.append({"_malformed": line.decode("utf-8", "replace")})
                    continue
                if not isinstance(message, dict):
                    continue
                self.events.append(message)
                self._answer_server_request(message)
                if message.get("method") in _TERMINAL_METHODS:
                    thread_id = _thread_id(message.get("params", {})) if isinstance(message.get("params"), Mapping) else None
                    if self.root_thread_id is None or thread_id in {None, self.root_thread_id}:
                        saw_root_terminal = True
            if saw_root_terminal:
                return

    def _answer_server_request(self, message: Mapping[str, Any]) -> None:
        # approvalPolicy=never should prevent these.  Rejecting an unexpected
        # request keeps the bounded smoke from hanging or approving side effects.
        if "method" not in message or "id" not in message or self.process.stdin is None:
            return
        method = str(message.get("method"))
        self.events.append({"_unexpected_request": method})
        reply = {"id": message["id"], "error": {"code": -32001, "message": "verification rejects server requests"}}
        with contextlib.suppress(OSError, BrokenPipeError):
            self.process.stdin.write((json.dumps(reply) + "\n").encode())
            self.process.stdin.flush()

    def close(self) -> None:
        _terminate_process(self.process)


def _terminate_process(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.terminate()
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        with contextlib.suppress(OSError):
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
        with contextlib.suppress(Exception):
            process.wait(timeout=2)


def _message_text(events: Iterable[Mapping[str, Any]]) -> str:
    chunks: list[str] = []
    for event in events:
        for item in _iter_dicts(event):
            for key in ("text", "delta", "message", "content"):
                value = item.get(key)
                if isinstance(value, str):
                    chunks.append(value)
    return "\n".join(chunks)


def _role_text(events: Iterable[Mapping[str, Any]], role_ids: Mapping[str, set[str]]) -> dict[str, str]:
    """Collect text only from typed item events carrying a known child id."""
    by_id = {thread_id: role for role, ids in role_ids.items() for thread_id in ids}
    result = {role: [] for role in role_ids}
    for event in events:
        if event.get("method") not in {"item/agentMessage/delta", "item/completed", "turn/completed"}:
            continue
        params = event.get("params")
        if not isinstance(params, Mapping):
            continue
        thread_id = _thread_id(params)
        role = by_id.get(thread_id)
        if role:
            result[role].append(_message_text([params]))
    return {role: "\n".join(chunks) for role, chunks in result.items()}


def _diagnostic_outputs(events: Iterable[Mapping[str, Any]], role_ids: Mapping[str, set[str]]) -> dict[str, dict[str, Any]]:
    """Parse only a child's structured final diagnostic object."""
    by_id = {thread_id: role for role, ids in role_ids.items() for thread_id in ids}
    outputs: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.get("method") != "turn/completed":
            continue
        params = event.get("params")
        if not isinstance(params, Mapping):
            continue
        role = by_id.get(_thread_id(params))
        turn = params.get("turn")
        if not role or not isinstance(turn, Mapping) or not isinstance(turn.get("items"), list):
            continue
        for item in turn["items"]:
            if not isinstance(item, Mapping) or item.get("phase") != "final_answer" or not isinstance(item.get("text"), str):
                continue
            text = item["text"]
            marker = "OMC_DIAGNOSTIC_JSON"
            if marker not in text:
                continue
            fragment = text.split(marker, 1)[1].lstrip()
            if fragment.startswith(":"):
                fragment = fragment[1:].lstrip()
            fragment = fragment.removeprefix("```").lstrip()
            try:
                value, end = json.JSONDecoder().raw_decode(fragment)
            except json.JSONDecodeError:
                continue
            trailing = fragment[end:].strip().strip("`").strip()
            if trailing:
                continue
            if isinstance(value, Mapping) and value.get("role") == role:
                if role in outputs and outputs[role] != dict(value):
                    outputs[role] = {"conflict": True}
                else:
                    outputs[role] = dict(value)
    return outputs


def _librarian_source_evidence(events: Iterable[Mapping[str, Any]], role_ids: Mapping[str, set[str]]) -> dict[str, set[str]]:
    """Collect URLs from typed web-search result items for known children."""
    by_id = {thread_id: role for role, ids in role_ids.items() for thread_id in ids}
    result = {role: set() for role in role_ids}
    for event in events:
        if event.get("method") not in {"item/started", "item/completed"}:
            continue
        params = event.get("params")
        if not isinstance(params, Mapping):
            continue
        role = by_id.get(_thread_id(params))
        item = params.get("item")
        if not role or not isinstance(item, Mapping) or str(item.get("type", "")).lower() != "websearch":
            continue
        for candidate in _iter_dicts(item):
            url = candidate.get("url")
            if isinstance(url, str) and url.startswith(("https://", "http://")):
                result[role].add(urldefrag(url).url)
    return result


def _nesting_violations(events: Iterable[Mapping[str, Any]], observations: Iterable[Mapping[str, Any]], root_thread_id: str | None) -> list[str]:
    """Detect agent-management operations issued by a known child."""
    if not root_thread_id:
        return []
    known_children = {
        str(row.get("thread_id"))
        for row in observations
        if row.get("thread_id") and row.get("thread_id") != root_thread_id
    }
    for event in events:
        params = event.get("params")
        if not isinstance(params, Mapping):
            continue
        item = params.get("item")
        if not isinstance(item, Mapping):
            continue
        parent_id = params.get("threadId")
        item_type = item.get("type")
        if item_type == "collabAgentToolCall" and isinstance(parent_id, str) and parent_id in known_children:
            return [f"V1 agent-management call from child {parent_id}"]
        if item_type == "subAgentActivity" and isinstance(parent_id, str) and parent_id in known_children:
            return [f"V2 agent-management activity from child {parent_id}"]
    for row in observations:
        parent_id = row.get("parent_thread_id")
        if isinstance(parent_id, str) and parent_id != root_thread_id and parent_id in known_children:
            return [f"descendant thread {row.get('thread_id')} links to child {parent_id}"]
    return []


def _oracle_finding_matches(finding: Mapping[str, Any]) -> bool:
    expected = finding.get("expected")
    expected_ok = (
        (isinstance(expected, (int, float)) and not isinstance(expected, bool) and expected == 0)
        or (isinstance(expected, str) and expected.strip().lower() == "return 0")
    )
    observed = finding.get("observed")
    if isinstance(observed, Mapping):
        exception = observed.get("exception")
        observed_ok = isinstance(exception, str) and exception in {
            "ZeroDivisionError",
            "builtins.ZeroDivisionError",
        }
    else:
        observed_ok = isinstance(observed, str) and bool(re.search(r"(?<![A-Za-z0-9_])ZeroDivisionError(?![A-Za-z0-9_])", observed))
    return (
        finding.get("file") == "review_target.py"
        and finding.get("function") == "average"
        and finding.get("input") == {"values": []}
        and expected_ok
        and observed_ok
    )


def _skill_read_evidence(events: Iterable[Mapping[str, Any]], skill_path: str, root_thread_id: str | None = None) -> bool:
    """Require host-emitted skill acceptance plus unseeded root evidence."""
    accepted = False
    root_marker = False
    command_loaded = False
    try:
        skill_text = Path(skill_path).read_text(encoding="utf-8")
    except OSError:
        skill_text = ""
    content_lines = [line.strip() for line in skill_text.splitlines() if len(line.strip()) >= 16 and line.strip() != _PARENT_MARKER]
    for event in events:
        params = event.get("params")
        if not isinstance(params, Mapping):
            continue
        event_thread = _thread_id(params)
        if root_thread_id is not None and event_thread != root_thread_id:
            continue
        for candidate in _iter_dicts(params):
            if candidate.get("type") == "skill" and candidate.get("path") == skill_path:
                accepted = True
            if candidate.get("type") == "commandExecution":
                command = str(candidate.get("command", ""))
                output = " ".join(_flatten_strings(_first(candidate, "output", "stdout", "aggregatedOutput", "result")))
                if (
                    skill_path in command
                    and candidate.get("status") in {"completed", "success"}
                    and candidate.get("exitCode", 0) == 0
                    and content_lines
                    and any(line in output for line in content_lines)
                ):
                    command_loaded = True
        if event.get("method") in {"item/completed", "item/agentMessage/delta", "turn/completed"}:
            text = _message_text([params])
            if _PARENT_MARKER in text:
                root_marker = True
    return command_loaded or (accepted and root_marker)


def _role_write_evidence(events: Iterable[Mapping[str, Any]], role_ids: Mapping[str, set[str]], root_thread_id: str | None = None) -> dict[str, bool]:
    """Detect typed writes and fail closed on opaque mutation-capable items."""
    by_id = {thread_id: role for role, ids in role_ids.items() for thread_id in ids}
    result = {role: False for role in role_ids}
    result["__observed__"] = False
    result["__root__"] = False
    result["__unknown__"] = False
    result["__unknown_root__"] = False
    result["__typed_root__"] = False
    for role in role_ids:
        result[f"__write__:{role}"] = False
        result[f"__unknown__:{role}"] = False
    for event in events:
        if event.get("method") not in {"item/completed", "item/started", "item/commandExecution/outputDelta"}:
            continue
        params = event.get("params")
        if not isinstance(params, Mapping):
            continue
        thread_id = _thread_id(params)
        role = by_id.get(thread_id)
        if not role and thread_id != root_thread_id:
            continue
        item = params.get("item")
        item_type = str(item.get("type", "")) if isinstance(item, Mapping) else ""
        paths = [
            str(candidate["path"])
            for candidate in _iter_dicts(params)
            if isinstance(candidate.get("path"), str)
        ]
        normalized_type = item_type.lower().replace("_", "")
        typed_write = any(tag in normalized_type for tag in ("filechange", "patchapplyend"))
        opaque = (
            event.get("method") == "item/commandExecution/outputDelta"
            or (
                normalized_type != "collabagenttoolcall"
                and any(tag in normalized_type for tag in ("commandexecution", "shell", "toolcall", "mcptool", "computertool", "functioncall", "tooluse", "browser", "applypatch"))
            )
        )
        command = str(item.get("command", "")) if isinstance(item, Mapping) else ""
        successful = event.get("method") == "item/completed" and (not isinstance(item, Mapping) or item.get("status") not in {"failed", "cancelled", "stopped"})
        shell_target_write = successful and bool(re.search(r">\s*[^;&|\n]*?(?:target\.py|value\.txt)\b", command))
        if opaque:
            result["__unknown__"] = True
            if role:
                result[f"__unknown__:{role}"] = True
            elif thread_id == root_thread_id:
                result["__unknown_root__"] = True
            if shell_target_write:
                result["__observed__"] = True
                if role:
                    result[role] = True
                    result[f"__write__:{role}"] = True
                elif thread_id == root_thread_id:
                    result["__root__"] = True
            continue
        if typed_write and successful:
            result["__observed__"] = True
            if role:
                result[f"__write__:{role}"] = True
                if any(path.lower().endswith("target.py") for path in paths):
                    result[role] = True
            elif thread_id == root_thread_id:
                result["__root__"] = True
                result["__typed_root__"] = True
    return result


def _role_completion_evidence(events: Iterable[Mapping[str, Any]], role_ids: Mapping[str, set[str]]) -> dict[str, bool]:
    by_id = {thread_id: role for role, ids in role_ids.items() for thread_id in ids}
    result = {role: False for role in role_ids}
    for event in events:
        if event.get("method") not in _TERMINAL_METHODS:
            continue
        params = event.get("params")
        if isinstance(params, Mapping):
            role = by_id.get(_thread_id(params))
            if role and _terminal_status(events, _thread_id(params) or "") == "completed":
                result[role] = True
    return result


def _terminal_status(events: Iterable[Mapping[str, Any]], thread_id: str) -> str | None:
    for event in events:
        if event.get("method") not in _TERMINAL_METHODS:
            continue
        params = event.get("params")
        if not isinstance(params, Mapping) or _thread_id(params) != thread_id:
            continue
        turn = params.get("turn")
        if isinstance(turn, Mapping) and isinstance(turn.get("status"), str):
            return turn["status"].lower()
        return str(event["method"]).rsplit("/", 1)[-1].lower()
    return None


def _aggregate(
    checks: list[dict[str, str]],
    observations: list[dict[str, Any]],
    fixture_changed: bool,
    malformed: bool,
    target_ok: bool | None = None,
    role_text: Mapping[str, str] | None = None,
    root_thread_id: str | None = None,
    role_write_evidence: Mapping[str, bool] | None = None,
    parent_metadata: Mapping[str, str] | None = None,
    config_present: bool = False,
    completion_evidence: Mapping[str, bool] | None = None,
    terminal_status: Mapping[str, str | None] | None = None,
    diagnostics: Mapping[str, Mapping[str, Any]] | None = None,
    skill_read: bool | None = None,
    runtime: str | None = None,
    source_evidence: Mapping[str, set[str]] | None = None,
    nesting_violations: Iterable[str] | None = None,
) -> tuple[str, list[dict[str, str]]]:
    """Apply pessimistic role and behavior gates to host observations."""
    if malformed:
        checks.append(_check("protocol-integrity", "FAILED", "malformed app-server event observed"))
    if fixture_changed:
        checks.append(_check("parent-boundary", "FAILED", "fixture contains changes outside the Fixer target"))
    if target_ok is False:
        checks.append(_check("fixer-effect", "FAILED", "target.py is absent or does not contain the exact expected correction"))
    elif target_ok is True:
        checks.append(_check("fixer-effect", "VERIFIED", "target.py contains the exact expected correction"))
    role_seen: dict[str, list[dict[str, Any]]] = {role: [] for role in _ROLES}
    for observation in observations:
        role = observation.get("role")
        if role in role_seen:
            role_seen[role].append(observation)
    for role, expected in _ROLES.items():
        rows = role_seen[role]
        if not rows:
            checks.append(_check(f"runtime:{role}", "UNVERIFIED", "no host-correlated execution observation"))
            continue
        if len(rows) != 1:
            checks.append(_check(f"runtime:{role}", "FAILED", f"expected one observation, found {len(rows)}"))
            continue
        row = rows[0]
        mismatches = []
        missing = []
        if row.get("conflict"):
            mismatches.append("conflicting host observations")
        if row.get("model") is None:
            missing.append("model")
        elif row.get("model") != expected["model"]:
            mismatches.append(f"model={row.get('model')!r}")
        if row.get("effort") is None:
            missing.append("effort")
        elif row.get("effort") != expected["effort"]:
            mismatches.append(f"effort={row.get('effort')!r}")
        if row.get("sandbox") is None:
            missing.append("sandbox")
        elif row.get("sandbox") != expected["sandbox"]:
            mismatches.append(f"sandbox={row.get('sandbox')!r}")
        if runtime is not None and row.get("multi_agent_version") is None:
            missing.append("multi_agent_version")
        elif runtime is not None and row.get("multi_agent_version") != runtime:
            mismatches.append(f"multi_agent_version={row.get('multi_agent_version')!r}")
        if row.get("source") is None:
            mismatches.append("spawn source=None")
        elif row.get("source") not in {"subAgent", "subAgentThreadSpawn", "thread_spawn", "agent"}:
            mismatches.append(f"source={row.get('source')!r}")
        if mismatches:
            checks.append(_check(f"runtime:{role}", "FAILED", "; ".join(mismatches)))
        elif missing:
            checks.append(_check(f"runtime:{role}", "UNVERIFIED", "host omitted " + ", ".join(missing)))
        else:
            checks.append(_check(f"runtime:{role}", "VERIFIED", f"thread {row.get('thread_id')} carries role, model, effort, sandbox and spawn source"))
        parent = row.get("parent_thread_id")
        if not parent:
            checks.append(_check(f"routing:{role}", "UNVERIFIED", "host event does not identify the parent thread"))
        elif root_thread_id is not None and parent != root_thread_id:
            checks.append(_check(f"routing:{role}", "FAILED", f"thread {row.get('thread_id')} links to {parent}, expected root {root_thread_id}"))
        else:
            checks.append(_check(f"routing:{role}", "VERIFIED", f"thread {row.get('thread_id')} is forked from {parent}"))
    exact_roles = all(
        len(role_seen[role]) == 1
        and role_seen[role][0].get("source") in {"subAgent", "subAgentThreadSpawn", "thread_spawn", "agent"}
        and role_seen[role][0].get("model") == expected["model"]
        and role_seen[role][0].get("effort") == expected["effort"]
        and role_seen[role][0].get("sandbox") == expected["sandbox"]
        and (runtime is None or role_seen[role][0].get("multi_agent_version") == runtime)
        for role, expected in _ROLES.items()
    )
    if not observations:
        checks.append(_check("capability:C-no-usable-spawn", "FAILED", "no native child execution observations were returned"))
    elif exact_roles:
        checks.append(_check("capability:A-named-route", "VERIFIED", "all four named roles were host-correlated"))
    else:
        inherited = False
        contradicted = False
        for role, rows in role_seen.items():
            if len(rows) != 1:
                continue
            row = rows[0]
            expected = _ROLES[role]
            observed_fields = {field: row.get(field) for field in ("model", "effort", "sandbox")}
            inherited_fields = ("model", "effort")
            if parent_metadata and all(observed_fields[field] is not None and observed_fields[field] == parent_metadata.get(field) for field in inherited_fields):
                if any(observed_fields[field] != expected[field] for field in inherited_fields):
                    inherited = True
            if any(observed_fields[field] is not None and observed_fields[field] != expected[field] for field in observed_fields):
                contradicted = True
        if inherited:
            checks.append(_check("capability:B-spawn-config", "FAILED", "named child spawn is observed with the parent effective configuration"))
        elif contradicted and config_present:
            checks.append(_check("capability:D-config-contradicted", "FAILED", "named role configuration exists but effective child metadata contradicts it"))
        elif any(row.get("role") in _ROLES for row in observations):
            checks.append(_check("capability:UNKNOWN", "UNVERIFIED", "native child exists but effective metadata is incomplete"))
        else:
            checks.append(_check("capability:UNKNOWN", "UNVERIFIED", "host did not expose enough metadata to classify role routing"))
    violations = list(nesting_violations or [])
    if violations:
        checks.append(_check("nesting", "FAILED", "; ".join(violations)))
    else:
        checks.append(_check("nesting", "UNVERIFIED", "native trace does not expose a complete child-of-child graph"))
    if role_text is not None:
        # Role markers are owned by the installed skill and are useful only as
        # corroboration.  The smoke prompt must not seed them, and their
        # absence cannot turn an otherwise host-correlated role into a fake
        # routing failure.  Identity comes from typed activity plus rollout
        # metadata below.
        for role in _ROLES:
            text = role_text.get(role, "").lower()
            marker = _MARKERS[role].lower()
            if marker in text:
                checks.append(_check(f"skill-marker:{role}", "INFERRED", "installed-skill role marker appeared in a child final event"))
        fixer_diag = diagnostics.get("omc_fixer") if diagnostics else None
        receipt = fixer_diag.get("receipt") if fixer_diag else None
        valid_receipt = (
            isinstance(receipt, Mapping)
            and receipt.get("status") == "completed"
            and isinstance(receipt.get("task"), str) and bool(receipt["task"].strip())
            and isinstance(receipt.get("summary"), str) and bool(receipt["summary"].strip())
            and isinstance(receipt.get("files"), list) and "target.py" in receipt["files"]
            and isinstance(receipt.get("validation"), list)
            and bool(receipt["validation"])
            and all(isinstance(item, Mapping) and isinstance(item.get("command"), str) and isinstance(item.get("result"), str) for item in receipt["validation"])
            and all(item["command"].strip() and item["result"].strip() for item in receipt["validation"])
            and isinstance(receipt.get("deviations"), list)
            and isinstance(receipt.get("unresolved_risks"), list)
        )
        if fixer_diag and not fixer_diag.get("conflict") and valid_receipt:
            checks.append(_check("fixer-receipt", "INFERRED", "Fixer terminal event contains the required structured receipt object"))
        else:
            checks.append(_check("fixer-receipt", "UNVERIFIED", "Fixer terminal event lacks the required structured receipt object"))
        explorer_diag = diagnostics.get("omc_explorer") if diagnostics else None
        valid_explorer = (
            explorer_diag
            and not explorer_diag.get("conflict")
            and isinstance(explorer_diag.get("paths"), list)
            and isinstance(explorer_diag.get("findings"), list)
            and isinstance(explorer_diag.get("uncertainties"), list)
            and any(isinstance(item, str) and item.strip() for item in explorer_diag["paths"])
            and any(isinstance(item, str) and item.strip() for item in explorer_diag["findings"])
            and explorer_diag.get("no_files_modified") is True
        )
        if valid_explorer:
            checks.append(_check("explorer-evidence", "INFERRED", "Explorer supplied structured paths, findings, uncertainties, and no_files_modified=true"))
        else:
            checks.append(_check("explorer-evidence", "UNVERIFIED", "Explorer terminal event lacks the required structured evidence"))
        librarian_diag = diagnostics.get("omc_librarian") if diagnostics else None
        research_status = librarian_diag.get("research_status") if librarian_diag else None
        source_url = librarian_diag.get("source_url") if librarian_diag else None
        valid_source = isinstance(source_url, str) and bool(source_url.strip()) and (
            research_status in {"unavailable", "unsupported"} or source_url.startswith(("https://", "http://"))
        )
        if research_status in {"available", "unavailable", "unsupported"} and valid_source:
            observed_sources = source_evidence.get("omc_librarian", set()) if source_evidence else set()
            if isinstance(source_url, str) and urldefrag(source_url).url in observed_sources:
                checks.append(_check("librarian-research", "VERIFIED", f"child-reported source outcome {research_status!r} is correlated to typed web-search result {source_url!r}"))
            else:
                checks.append(_check("librarian-research", "INFERRED", f"child-reported source outcome {research_status!r} with source {source_url!r}; native network proof is unverified"))
        else:
            checks.append(_check("librarian-research", "UNVERIFIED", "Librarian terminal event lacks a concrete source URL and available/unavailable/unsupported outcome"))
        oracle_diag = diagnostics.get("omc_oracle") if diagnostics else None
        if (
            oracle_diag
            and not oracle_diag.get("conflict")
            and oracle_diag.get("verdict") == "FAIL"
            and oracle_diag.get("review_target") == "review_target.py"
            and oracle_diag.get("review_target_found") is True
            and isinstance(oracle_diag.get("findings"), list)
            and any(
                isinstance(finding, Mapping) and _oracle_finding_matches(finding)
                for finding in oracle_diag["findings"]
            )
        ):
            checks.append(_check("oracle-verdict", "INFERRED", "Oracle terminal event contains structured verdict for review_target.py"))
        else:
            checks.append(_check("oracle-verdict", "UNVERIFIED", "Oracle terminal event lacks an unambiguous review_target.py bug verdict"))
        if skill_read:
            checks.append(_check("skill-runtime:parent", "VERIFIED", "host-emitted skill acceptance/root marker or verified command output loaded the requested SKILL.md"))
        else:
            checks.append(_check("skill-runtime:parent", "UNVERIFIED", "host-emitted skill acceptance plus root marker or verified SKILL.md command output was not observed"))
    if role_write_evidence is not None:
        if role_write_evidence.get("__typed_root__"):
            checks.append(_check("parent-authorship", "FAILED", "a typed target write is correlated to the root parent"))
        elif role_write_evidence.get("__unknown_root__"):
            checks.append(_check("parent-authorship", "UNVERIFIED", "root emitted an opaque mutation-capable operation"))
        if role_write_evidence.get("omc_fixer"):
            checks.append(_check("fixer-authorship", "VERIFIED", "a successful typed target.py patch is attributed to the Fixer thread; exclusivity is checked separately"))
        else:
            checks.append(_check("fixer-authorship", "UNVERIFIED", "host did not correlate a target.py write event to the Fixer thread"))
        readonly_roles = [role for role in _ROLES if role != "omc_fixer"]
        unknown_readonly = [role for role in readonly_roles if role_write_evidence.get(f"__unknown__:{role}")]
        wrote_readonly = [role for role in readonly_roles if role_write_evidence.get(f"__write__:{role}")]
        if wrote_readonly:
            checks.append(_check("readonly-behavior", "FAILED", "successful typed write from read-only role(s): " + ", ".join(wrote_readonly)))
        elif unknown_readonly:
            checks.append(_check("readonly-behavior", "UNVERIFIED", "opaque operation(s) from read-only role(s): " + ", ".join(unknown_readonly)))
        elif not role_write_evidence.get("__observed__"):
            checks.append(_check("readonly-behavior", "UNVERIFIED", "host exposed no typed file-change events for child attribution"))
        elif all(not role_write_evidence.get(f"__write__:{role}", role_write_evidence.get(role, False)) for role in readonly_roles):
            checks.append(_check("readonly-behavior", "VERIFIED", "no typed write event is correlated to a read-only role"))
    if completion_evidence is not None:
        for role in _ROLES:
            if completion_evidence.get(role):
                checks.append(_check(f"completion:{role}", "VERIFIED", "child turn terminal event is correlated to the role thread"))
            else:
                checks.append(_check(f"completion:{role}", "UNVERIFIED", "child turn terminal event is not correlated to the role thread"))
    if terminal_status is not None:
        for role in _ROLES:
            status = terminal_status.get(role)
            if status == "completed":
                checks.append(_check(f"terminal:{role}", "VERIFIED", "child turn completed successfully"))
            elif status in {"failed", "cancelled", "stopped"}:
                checks.append(_check(f"terminal:{role}", "FAILED", f"child turn ended with status {status}"))
            else:
                checks.append(_check(f"terminal:{role}", "UNVERIFIED", "child terminal status was not observed"))
    required = {"FAILED", "UNVERIFIED"}
    hard_fail = any(
        item["status"] in required
        and not (item["name"] == "nesting" and item["status"] == "UNVERIFIED")
        for item in checks
    )
    notes = any(item["status"] in {"INFERRED", "UNVERIFIED"} for item in checks if item["name"] == "nesting")
    overall = "FAIL" if hard_fail else ("PASS WITH NOTES" if notes else "PASS")
    return overall, checks


def run_verify(
    codex_home: Path,
    skills_home: Path,
    codex_bin: str = "codex",
    timeout: float = 300,
    runtime: str = "v2",
    keep_artifacts: bool = False,
) -> dict:
    """Run the installed parent and all four configured roles in a disposable fixture."""
    codex_home = Path(codex_home).expanduser()
    skills_home = Path(skills_home).expanduser()
    if runtime not in {"v1", "v2"}:
        raise ValueError("runtime must be v1 or v2")
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    if not codex_bin:
        raise ValueError("codex_bin must not be empty")
    checks, configured_roles = _configured_checks(codex_home, skills_home)
    artifact_dir: Path | None = None
    deadline = time.monotonic() + timeout
    events: list[dict[str, Any]] = []
    process: _AppServer | None = None
    fixture_changed = False
    target_ok = False
    transport_ok = False
    fixture_path = ""
    final_files: dict[str, bytes] = {}
    unsafe_entries: list[str] = []
    host_version = "unknown"
    host_stderr = ""
    parent_metadata: dict[str, str] = {}
    root_thread_id: str | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="omc-verify-") as temp_name:
            root = Path(temp_name)
            fixture = root / "fixture"
            fixture.mkdir()
            (fixture / "value.txt").write_text("original\n", encoding="utf-8")
            (fixture / "target.py").write_text("def value():\n    return 'wrong'\n", encoding="utf-8")
            # Oracle has a separate, deliberately retained defect to review;
            # Fixer is explicitly forbidden from changing this file.
            (fixture / "review_target.py").write_text(
                'def average(values):\n    """Return the arithmetic mean, or 0 for empty input."""\n    return sum(values) / len(values)\n',
                encoding="utf-8",
            )
            _git_checked(["init", "-q"], fixture)
            _git_checked(["config", "user.name", "Oh-My-Codex Verify"], fixture)
            _git_checked(["config", "user.email", "verify@localhost"], fixture)
            _git_checked(["add", "value.txt", "target.py", "review_target.py"], fixture)
            _git_checked(["commit", "-qm", "fixture"], fixture)
            baseline = _fixture_snapshot(fixture)
            fixture_path = str(fixture)

            if keep_artifacts:
                artifact_dir = Path(tempfile.mkdtemp(prefix="omc-verify-artifacts-"))
                (artifact_dir / "fixture").mkdir()
            feature = "multi_agent_v2" if runtime == "v2" else "multi_agent"
            argv = [
                codex_bin,
                "app-server",
                "--stdio",
                "--enable",
                feature,
                "--disable",
                "hooks",
                "--disable",
                "apps",
                "--disable",
                "plugins",
                "-c",
                "mcp_servers={}",
                "-c",
                "mcp_servers.node_repl.enabled=false",
                "-c",
                "mcp_servers.codegraph.enabled=false",
                "-c",
                "mcp_servers.blender.enabled=false",
                "-c",
                "mcp_servers.computer-use.enabled=false",
                "-c",
                "model_reasoning_effort=\"high\"",
            ]
            if runtime == "v1":
                argv[5:5] = ["--disable", "multi_agent_v2"]
            env = os.environ.copy()
            env["CODEX_HOME"] = str(codex_home)
            process = _AppServer(argv, env, deadline)
            init = process.request("initialize", {"clientInfo": {"name": "oh-my-codex-verify", "version": "1.0.0"}, "capabilities": {"experimentalApi": True}}, 1)
            if init and isinstance(init.get("result"), Mapping):
                host_version = str(init["result"].get("userAgent", "unknown"))
            start_params = {"cwd": str(fixture), "model": "gpt-5.6-sol", "approvalPolicy": "never", "sandbox": "workspace-write", "ephemeral": False, "historyMode": "legacy"}
            started = process.request("thread/start", start_params, 2)
            if started and isinstance(started.get("result"), Mapping):
                root_thread_id = _thread_id(started["result"])
                parent_result = started["result"]
                parent_model = parent_result.get("model")
                parent_effort = parent_result.get("reasoningEffort", parent_result.get("effort"))
                parent_sandbox = _normalise_sandbox(parent_result.get("sandbox"))
                parent_metadata = {
                    field: str(value)
                    for field, value in (("model", parent_model), ("effort", parent_effort), ("sandbox", parent_sandbox))
                    if value is not None
                }
                if parent_model == "gpt-5.6-sol" and parent_effort == "high" and parent_sandbox == "workspace-write":
                    checks.append(_check("runtime:orchestrator", "VERIFIED", "root thread reports Sol, high effort, and workspace-write"))
                elif any(value is None for value in (parent_model, parent_effort, parent_sandbox)):
                    checks.append(_check("runtime:orchestrator", "UNVERIFIED", "root thread omitted model, effort, or sandbox metadata"))
                else:
                    checks.append(_check("runtime:orchestrator", "FAILED", f"root thread reports model={parent_model!r}, effort={parent_effort!r}, sandbox={parent_sandbox!r}"))
                if root_thread_id and process.returned_paths.get(root_thread_id):
                    checks.append(_check("handshake:root-path", "VERIFIED", "thread/start returned the root legacy rollout path"))
                else:
                    checks.append(_check("handshake:root-path", "UNVERIFIED", "thread/start did not return a root rollout path"))
            prompt = _parent_prompt(fixture, skills_home, runtime)
            turn_started = None
            if init and init.get("result") is not None and started and started.get("result") is not None and root_thread_id:
                process.root_thread_id = root_thread_id
                turn_started = process.request("turn/start", {"threadId": root_thread_id, "input": [{"type": "skill", "name": "oh-my-codex", "path": str(skills_home / "oh-my-codex" / "SKILL.md")}, {"type": "text", "text": prompt}], "effort": "high", "model": "gpt-5.6-sol", "sandboxPolicy": {"type": "workspaceWrite", "writableRoots": [str(fixture)]}}, 3)
                transport_ok = turn_started is not None
            if turn_started is not None:
                process.collect_turn()
            # Child activity events expose the child id but not its persisted
            # rollout path.  A metadata-only read is safe and lets us consume
            # only the host-returned path for each child.
            child_ids = sorted(_event_thread_ids(process.events) - ({root_thread_id} if root_thread_id else set()))
            for offset, child_id in enumerate(child_ids[:8], start=100):
                if time.monotonic() >= deadline:
                    break
                process.request("thread/read", {"threadId": child_id, "includeTurns": False}, offset)
            events = list(process.events)
            final = _fixture_snapshot(fixture)
            final_files = final
            unsafe_entries = _fixture_unsafe_entries(fixture)
            expected_target = b"def value():\n    return 'expected'\n"
            target_ok = final.get("target.py") == expected_target
            fixture_changed = any(
                path != "target.py" and (path not in baseline or value != baseline[path])
                for path, value in final.items()
            ) or any(path not in final for path in baseline if path != "target.py")
            if unsafe_entries:
                checks.append(_check("fixture-integrity", "FAILED", "unsafe fixture entries: " + ", ".join(unsafe_entries[:8])))
    except RuntimeError as exc:
        checks.append(_check("fixture-setup", "FAILED", str(exc)))
    except (OSError, subprocess.SubprocessError) as exc:
        checks.append(_check("app-server", "FAILED", str(exc)))
    finally:
        if process is not None:
            host_stderr = bytes(process.stderr).decode("utf-8", "replace")[-2000:]
            process.close()
        if artifact_dir is not None:
            for relative, contents in final_files.items():
                destination = artifact_dir / "fixture" / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                with contextlib.suppress(OSError):
                    destination.write_bytes(contents)

    known_ids = {root_thread_id} if root_thread_id else set()
    known_ids |= _event_thread_ids(events)
    observations: list[dict[str, Any]] = []

    def add_observation(row: dict[str, Any]) -> None:
        for existing in observations:
            if existing.get("thread_id") != row.get("thread_id"):
                continue
            for field in ("role", "source", "model", "effort", "sandbox", "multi_agent_version", "parent_thread_id", "path"):
                old, new = existing.get(field), row.get(field)
                if old is None and new is not None:
                    existing[field] = new
                elif old is not None and new is not None and old != new:
                    existing["conflict"] = True
            existing["completed"] = bool(existing.get("completed")) or bool(row.get("completed"))
            return
        observations.append(row)

    for event in events:
        if "_malformed" in event:
            continue
        observation = _observation_from_event(event, known_ids)
        if observation:
            add_observation(observation)
    returned_paths = _returned_paths(events, known_ids)
    if process is not None:
        returned_paths.update(process.returned_paths)
    trace_rows, trace_malformed = _trace_observations(returned_paths, known_ids)
    for observation in trace_rows:
        add_observation(observation)
    nesting_violations = _nesting_violations(events, observations, root_thread_id)
    malformed = any("_malformed" in event or "_unexpected_request" in event for event in events)
    malformed = malformed or trace_malformed
    protocol_errors = [event.get("error") for event in events if isinstance(event.get("error"), Mapping)]
    if protocol_errors:
        checks.append(_check("app-server", "FAILED", f"host returned {len(protocol_errors)} protocol error(s)"))
    if not transport_ok:
        checks.append(_check("app-server", "FAILED", "initialize/thread-start/turn-start did not complete"))
    role_ids = {role: {row["thread_id"] for row in observations if row.get("role") == role and row.get("thread_id")} for role in _ROLES}
    role_text = _role_text(events, role_ids)
    diagnostics = _diagnostic_outputs(events, role_ids)
    source_evidence = _librarian_source_evidence(events, role_ids)
    skill_read = _skill_read_evidence(
        events,
        str(skills_home / "oh-my-codex" / "SKILL.md"),
        root_thread_id=root_thread_id,
    )
    write_evidence = _role_write_evidence(events, role_ids, root_thread_id=root_thread_id)
    completion_evidence = _role_completion_evidence(events, role_ids)
    terminal_status = {
        role: next((_terminal_status(events, thread_id) for thread_id in ids if _terminal_status(events, thread_id)), None)
        for role, ids in role_ids.items()
    }
    for observation in observations:
        observed_status = _terminal_status(events, str(observation.get("thread_id", "")))
        if observed_status is not None:
            observation["completed"] = observed_status == "completed"
    if root_thread_id:
        root_status = _terminal_status(events, root_thread_id)
        if root_status == "completed":
            checks.append(_check("terminal:orchestrator", "VERIFIED", "root turn completed successfully"))
        elif root_status in {"failed", "cancelled", "stopped"}:
            checks.append(_check("terminal:orchestrator", "FAILED", f"root turn ended with status {root_status}"))
        else:
            checks.append(_check("terminal:orchestrator", "UNVERIFIED", "root turn terminal status was not observed"))
            if time.monotonic() >= deadline:
                checks.append(_check("timeout", "FAILED", "verification deadline expired before root completion"))
    overall, checks = _aggregate(
        checks,
        observations,
        fixture_changed,
        malformed,
        target_ok=target_ok,
        role_text=role_text,
        root_thread_id=root_thread_id,
        role_write_evidence=write_evidence,
        parent_metadata=parent_metadata,
        config_present=bool(configured_roles),
        completion_evidence=completion_evidence,
        terminal_status=terminal_status,
        diagnostics=diagnostics,
        skill_read=skill_read,
        runtime=runtime,
        source_evidence=source_evidence,
        nesting_violations=nesting_violations,
    )
    report = {
        "overall": overall,
        "verification_label": "LOW-LEVEL RUNTIME VERIFICATION",
        "surface": "CODEX_CLI_APPSERVER",
        "desktop_verified": False,
        "package_version": __version__,
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "checks": checks,
        "provenance": {
            "host": host_version,
            "os": platform.platform(),
            "stderr": host_stderr,
            "runtime": runtime,
            "root_thread_id": root_thread_id,
            "thread_ids": sorted(known_ids),
            "artifact_dir": str(artifact_dir) if artifact_dir else None,
        },
        "fixture": {"path": fixture_path, "changed": fixture_changed, "target_corrected": target_ok},
        "runtime_evidence": {
            "skill_input_or_read": skill_read,
            "diagnostics": _sanitise(diagnostics),
            "source_evidence": {role: sorted(urls) for role, urls in source_evidence.items()},
            "typed_writes": _sanitise(write_evidence),
            "terminal_status": terminal_status,
        },
        "role_observations": [
            {key: row.get(key) for key in ("thread_id", "role", "source", "model", "effort", "sandbox", "multi_agent_version", "parent_thread_id", "path", "completed", "conflict")}
            for row in observations
        ],
        "limits": ["nesting is unverified when the host does not expose a complete child graph", "this separate app-server process is not Codex Desktop verification"],
    }
    if artifact_dir is not None:
        with contextlib.suppress(OSError):
            (artifact_dir / "events.jsonl").write_text(
                "".join(json.dumps(_sanitise(event), sort_keys=True) + "\n" for event in events),
                encoding="utf-8",
            )
            (artifact_dir / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def _parent_prompt(fixture: Path, skills_home: Path, runtime: str) -> str:
    if runtime == "v2":
        dispatch = (
            "agent_type='omc_explorer', task_name='explorer_verify', fork_turns='none'; "
            "agent_type='omc_librarian', task_name='librarian_verify', fork_turns='none'; "
            "agent_type='omc_fixer', task_name='fixer_verify', fork_turns='none'; "
            "agent_type='omc_oracle', task_name='oracle_verify', fork_turns='none'"
        )
    else:
        dispatch = (
            "agent_type='omc_explorer', fork_context=false; "
            "agent_type='omc_librarian', fork_context=false; "
            "agent_type='omc_fixer', fork_context=false; "
            "agent_type='omc_oracle', fork_context=false"
        )
    expected_lines = "def value():\n    return 'expected'"
    return f"""You are the Oh-My-Codex v1 verification parent. Work only in {fixture} and do not publish, install, or modify any path outside that fixture. This is diagnostic fixture mode: continue through production gate mismatches only inside this disposable fixture to collect evidence. Load the installed skill from {skills_home / 'oh-my-codex' / 'SKILL.md'} using the normal skill input/path mechanism before acting; do not recreate its instructions in your prompt. Then dispatch the four configured standalone agents sequentially by exact names omc_explorer, omc_librarian, omc_fixer, and omc_oracle through native multi-agent routing ({dispatch}); do not use a direct CLI specialist. Specialists must not call agent-management tools or delegate further; ordinary assigned inspection and edit tools are allowed. Each child must follow its configured role instructions and report its assigned tool outcomes; role diagnostic markers must come from those role instructions. Explorer must inspect only and append one final OMC_DIAGNOSTIC_JSON: object with role omc_explorer, paths (list), findings (list), uncertainties (list), and no_files_modified=true. Librarian must inspect only, attempt one official external source when available, report actual success or unavailability, and append one final OMC_DIAGNOSTIC_JSON: object with role omc_librarian, source_url, and research_status set to available, unavailable, or unsupported. Only Fixer may edit target.py. Its final file must contain exactly these three lines:\n{expected_lines}\nFixer must provide the required structured implementation receipt with task (a nonempty objective), status completed, summary, files (including target.py), validation (list entries each with command and result), deviations (list), and unresolved_risks (list), then append one final OMC_DIAGNOSTIC_JSON: object with role omc_fixer and that receipt object. Oracle must inspect the separate deliberately defective review_target.py contract and implementation, report its bug verdict while preserving that file, then append one final OMC_DIAGNOSTIC_JSON: object with role omc_oracle, review_target='review_target.py', review_target_found=true, findings (each including file, function, an input object mapping each function parameter name to its supplied value, expected, and observed), and verdict. Preserve value.txt exactly and preserve review_target.py exactly. Prose claims do not establish routing, effective model/effort/sandbox, authorship, or read-only behavior. Finish with concise JSON evidence including role observations, routing ids, nesting result, receipt/verdict presence, and final fixture state."""


__all__ = ["run_verify"]
