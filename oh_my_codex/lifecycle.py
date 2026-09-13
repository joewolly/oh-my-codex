"""Conservative, additive installation lifecycle for Oh-My-Codex.

The installer owns only the files listed in :data:`ASSETS` and records their
content hashes.  It never edits Codex configuration or repository policy files.
"""

from __future__ import annotations

import hashlib
import base64
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

from . import __version__

MANAGED_DIR = "oh-my-codex"
MANIFEST_NAME = "manifest.json"
JOURNAL_NAME = "journal.json"
SCHEMA = 1
AGENT_NAMES = ("explorer", "librarian", "fixer", "oracle")
ASSETS = {
    "agents/omc_explorer.toml": "assets/agents/omc_explorer.toml",
    "agents/omc_librarian.toml": "assets/agents/omc_librarian.toml",
    "agents/omc_fixer.toml": "assets/agents/omc_fixer.toml",
    "agents/omc_oracle.toml": "assets/agents/omc_oracle.toml",
    "skill/oh-my-codex/SKILL.md": "assets/skills/oh-my-codex/SKILL.md",
    "skill/oh-my-codex/agents/openai.yaml": "assets/skills/oh-my-codex/agents/openai.yaml",
}
_HASH = re.compile(r"^[0-9a-f]{64}$")
_KNOWN_SYSTEM_ALIASES = {Path("/var"): Path("/private/var"), Path("/tmp"): Path("/private/tmp")}
_ALLOWED_PAIRS = {("codex", key) for key in ASSETS if not key.startswith("skill/")} | {("skills", key.removeprefix("skill/")) for key in ASSETS if key.startswith("skill/")}
_UNSET = object()
_LOCK_CONTENT = b"oh-my-codex lifecycle lock v1\n"


class LifecycleError(RuntimeError):
    """A fail-closed lifecycle operation error."""


def resolve_paths(codex_home: str | os.PathLike[str] | None = None,
                  skills_home: str | os.PathLike[str] | None = None) -> tuple[Path, Path]:
    """Resolve user roots without creating or touching them."""
    codex = Path(codex_home) if codex_home is not None else Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    skills = Path(skills_home) if skills_home is not None else Path.home() / ".agents" / "skills"
    return codex.expanduser().absolute(), skills.expanduser().absolute()


def _file_signature(path: Path) -> tuple[int, int, int, str] | None:
    """Return identity, type, and content hash for a regular file."""
    _safe_target(path)
    if not path.exists():
        return None
    if path.is_symlink():
        raise LifecycleError(f"refusing symlink target: {path}")
    first = path.lstat()
    if not stat.S_ISREG(first.st_mode):
        raise LifecycleError(f"refusing non-regular file: {path}")
    data = path.read_bytes()
    last = path.lstat()
    identity = (first.st_dev, first.st_ino, stat.S_IFMT(first.st_mode))
    if identity != (last.st_dev, last.st_ino, stat.S_IFMT(last.st_mode)):
        raise LifecycleError(f"file changed while being read: {path}")
    return (*identity, _sha(data))


def _atomic_write(path: Path, data: bytes, *, expected: object = _UNSET) -> None:
    """Write one file atomically and durably, refusing symlink targets."""
    _safe_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.is_symlink():
        raise LifecycleError(f"refusing symlink target: {path}")
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if expected is not _UNSET and _file_signature(path) != expected:
            raise LifecycleError(f"file changed during lifecycle write: {path}")
        os.replace(tmp, path)
        try:
            fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError:
            pass
    finally:
        if tmp.exists() or tmp.is_symlink():
            tmp.unlink(missing_ok=True)


# Kept as a public-ish seam for focused failure-injection tests.
atomic_write = _atomic_write


def _safe_target(path: Path) -> None:
    """Reject symlinked ancestors and unsafe existing path components."""
    path = Path(path)
    current = path
    while True:
        if current.is_symlink():
            # macOS exposes these stable system aliases; user supplied links
            # anywhere else remain a fail-closed path hazard.
            if current not in _KNOWN_SYSTEM_ALIASES or current.resolve() != _KNOWN_SYSTEM_ALIASES[current]:
                raise LifecycleError(f"refusing symlink path component: {current}")
        parent = current.parent
        if parent == current:
            break
        current = parent


def _ensure_root(root: Path) -> None:
    _safe_target(root)
    if root.exists() and not root.is_dir():
        raise LifecycleError(f"install root is not a directory: {root}")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(path: Path) -> dict[str, Any] | None:
    if path.is_symlink():
        raise LifecycleError(f"refusing symlink metadata file: {path}")
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LifecycleError(f"invalid lifecycle metadata {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LifecycleError(f"invalid lifecycle metadata object: {path}")
    return value


def _manifest_path(codex_home: Path) -> Path:
    return codex_home / MANAGED_DIR / MANIFEST_NAME


def _journal_path(codex_home: Path) -> Path:
    return codex_home / MANAGED_DIR / JOURNAL_NAME


def _validate_rel(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise LifecycleError("tampered manifest contains an invalid path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise LifecycleError("tampered manifest contains a traversal path")
    return path.as_posix()


def _load_manifest(codex_home: Path, skills_home: Path | None = None) -> dict[str, Any] | None:
    manifest = _read_json(_manifest_path(codex_home))
    if manifest is None:
        return None
    if manifest.get("schema") != SCHEMA or not isinstance(manifest.get("files"), list):
        raise LifecycleError("tampered or unsupported ownership manifest")
    if skills_home is not None:
        roots = manifest.get("roots")
        expected_roots = {"codex": str(codex_home), "skills": str(skills_home)}
        if roots != expected_roots:
            raise LifecycleError("ownership manifest roots do not match requested homes")
    seen: set[tuple[str, str]] = set()
    for item in manifest["files"]:
        if not isinstance(item, dict) or item.get("root") not in ("codex", "skills"):
            raise LifecycleError("tampered ownership manifest entry")
        rel = _validate_rel(item.get("path"))
        if (item["root"], rel) in seen or (item["root"], rel) not in _ALLOWED_PAIRS:
            raise LifecycleError("tampered ownership manifest allowlist")
        if not isinstance(item.get("sha256"), str) or not _HASH.fullmatch(item["sha256"]):
            raise LifecycleError("tampered ownership manifest hash")
        seen.add((item["root"], rel))
    if len(seen) != len(ASSETS):
        # Older/partial manifests are still useful for uninstall, but may not
        # silently grant ownership to files that are outside the allowlist.
        if not seen.issubset({("codex", x) for x in ASSETS} | {("skills", x.removeprefix("skill/")) for x in ASSETS if x.startswith("skill/")}):
            raise LifecycleError("tampered ownership manifest entries")
    return manifest


def _source_root(source_root: Path | None) -> Path:
    return source_root or Path(__file__).resolve().parent


def _asset_sources(source_root: Path) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for destination, relative in ASSETS.items():
        source = source_root / relative
        _safe_target(source)
        if not source.is_file():
            raise LifecycleError(f"bundled asset is missing: {relative}")
        result[destination] = source.read_bytes()
    return result


def _validate_bundle(sources: dict[str, bytes]) -> None:
    """Validate the shipped contract before lifecycle writes begin."""
    import tomllib
    for name in AGENT_NAMES:
        logical = f"agents/omc_{name}.toml"
        try:
            data = tomllib.loads(sources[logical].decode("utf-8"))
        except (KeyError, UnicodeError, ValueError) as exc:
            raise LifecycleError(f"bundled role is malformed: {logical}: {exc}") from exc
        expected_model = "gpt-5.6-sol" if name == "oracle" else "gpt-5.6-luna"
        expected_effort = "medium" if name == "explorer" else "high"
        expected_sandbox = "workspace-write" if name == "fixer" else "read-only"
        required = ("name", "description", "developer_instructions", "model", "model_reasoning_effort", "sandbox_mode")
        if any(not isinstance(data.get(field), str) or not data.get(field).strip() for field in required):
            raise LifecycleError(f"bundled role is missing required fields: {logical}")
        if data["name"] != f"omc_{name}" or data["model"] != expected_model or data["model_reasoning_effort"] != expected_effort or data["sandbox_mode"] != expected_sandbox:
            raise LifecycleError(f"bundled role contract mismatch: {logical}")
        if not isinstance(data.get("agents"), dict) or data["agents"].get("enabled") is not False:
            raise LifecycleError(f"bundled role must set agents.enabled=false: {logical}")
    try:
        policy = sources["skill/oh-my-codex/agents/openai.yaml"].decode("utf-8")
    except (KeyError, UnicodeError) as exc:
        raise LifecycleError(f"bundled skill policy is malformed: {exc}") from exc
    if "allow_implicit_invocation: false" not in policy:
        raise LifecycleError("bundled skill policy must disable implicit invocation")


def _destination(root: Path, logical: str) -> Path:
    if logical.startswith("skill/"):
        return root[1] / logical.removeprefix("skill/")
    return root[0] / logical


def _manifest_entries(manifest: dict[str, Any] | None) -> dict[tuple[str, str], str]:
    if not manifest:
        return {}
    return {(i["root"], i["path"]): i["sha256"] for i in manifest["files"]}


def _roots(codex: Path, skills: Path) -> tuple[Path, Path]:
    return codex, skills


def _preflight_config(codex_home: Path) -> list[str]:
    config = codex_home / "config.toml"
    _safe_target(config)
    if not config.exists():
        return []
    try:
        import tomllib
        data = tomllib.loads(config.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise LifecycleError(f"existing config.toml is malformed: {exc}") from exc
    warnings: list[str] = []
    agents = data.get("agents") if isinstance(data, dict) else None
    if isinstance(agents, dict) and agents.get("enabled") is False:
        warnings.append("config.toml sets agents.enabled=false; runtime worker discovery may be disabled")
    def has_danger(value: Any) -> bool:
        if isinstance(value, str):
            return value == "danger-full-access"
        if isinstance(value, dict):
            return any(has_danger(child) for child in value.values())
        if isinstance(value, list):
            return any(has_danger(child) for child in value)
        return False
    if has_danger(data):
        warnings.append("config.toml requests danger-full-access sandbox; static checks cannot prove effective containment")
    if isinstance(agents, dict):
        declared = {str(key).removeprefix("omc_") for key in agents if str(key).startswith("omc_") and str(key).removeprefix("omc_") in AGENT_NAMES}
        if declared:
            raise LifecycleError("role conflict: config.toml declares " + ", ".join(sorted(declared)))
    return warnings


def _role_name(path: Path, data: dict[str, Any] | None = None) -> str | None:
    if data and isinstance(data.get("name"), str):
        value = data["name"]
        if value.startswith("omc_") and value.removeprefix("omc_") in AGENT_NAMES:
            return value.removeprefix("omc_")
        return None
    stem = path.stem
    return stem.removeprefix("omc_") if stem.startswith("omc_") and stem.removeprefix("omc_") in AGENT_NAMES else None


def _scan_role_files(codex_home: Path) -> list[tuple[Path, str]]:
    locations: list[Path] = []
    location_keys: set[str] = set()
    agents = codex_home / "agents"
    if agents.is_symlink():
        raise LifecycleError(f"role directory is a symlink: {agents}")
    if agents.exists() and agents.is_dir() and not agents.is_symlink():
        locations.append(agents)
        location_keys.add(str(agents.resolve()))
    cwd = Path.cwd().resolve()
    for ancestor in (cwd, *cwd.parents):
        candidate = ancestor / ".codex" / "agents"
        if candidate.is_symlink():
            raise LifecycleError(f"project role directory is a symlink: {candidate}")
        if candidate.exists() and candidate.is_dir() and not candidate.is_symlink():
            key = str(candidate.resolve())
            if key not in location_keys:
                locations.append(candidate)
                location_keys.add(key)
    config_locations: list[Path] = []
    config_keys: set[str] = set()
    for ancestor in (cwd, *cwd.parents):
        config = ancestor / ".codex" / "config.toml"
        if config.is_symlink():
            raise LifecycleError(f"project config is a symlink: {config}")
        if config.exists() and not config.is_symlink():
            key = str(config.resolve())
            if key not in config_keys:
                config_locations.append(config)
                config_keys.add(key)
    found: list[tuple[Path, str]] = []
    found_keys: set[tuple[str, str]] = set()
    import tomllib
    for directory in locations:
        pending = [directory]
        while pending:
            current_directory = pending.pop()
            try:
                children = sorted(current_directory.iterdir())
            except OSError as exc:
                raise LifecycleError(f"cannot scan role declarations: {current_directory}: {exc}") from exc
            for path in children:
                if path.is_symlink():
                    raise LifecycleError(f"role declaration path is a symlink: {path}")
                if path.is_dir():
                    pending.append(path)
                    continue
                if path.suffix != ".toml":
                    continue
                try:
                    data = tomllib.loads(path.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, ValueError) as exc:
                    raise LifecycleError(f"role declaration is malformed: {path}: {exc}") from exc
                role = _role_name(path, data)
                if role in AGENT_NAMES:
                    key = (str(path.resolve()), role)
                    if key not in found_keys:
                        found.append((path, role))
                        found_keys.add(key)
                role_table = data.get("agents") if isinstance(data, dict) else None
                if isinstance(role_table, dict):
                    for key in role_table:
                        candidate = str(key).removeprefix("omc_")
                        if str(key).startswith("omc_") and candidate in AGENT_NAMES:
                            found_key = (str(path.resolve()), candidate)
                            if found_key not in found_keys:
                                found.append((path, candidate))
                                found_keys.add(found_key)
    for path in config_locations:
        if not path.exists():
            continue
        _safe_target(path)
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as exc:
            raise LifecycleError(f"project config is malformed: {path}: {exc}") from exc
        role_table = data.get("agents") if isinstance(data, dict) else None
        if isinstance(role_table, dict):
            for key in role_table:
                candidate = str(key).removeprefix("omc_")
                if str(key).startswith("omc_") and candidate in AGENT_NAMES:
                    found_key = (str(path.resolve()), candidate)
                    if found_key not in found_keys:
                        found.append((path, candidate))
                        found_keys.add(found_key)
    return found


def _role_conflicts(codex_home: Path, owned: dict[tuple[str, str], str]) -> list[str]:
    conflicts: list[str] = []
    expected = {codex_home / "agents" / f"omc_{n}.toml" for n in AGENT_NAMES}
    for path, role in _scan_role_files(codex_home):
        if path not in expected:
            conflicts.append(f"role {role} declared by {path}")
    # A destination file is safe only if this manifest already owns it.
    for name in AGENT_NAMES:
        path = codex_home / "agents" / f"omc_{name}.toml"
        key = ("codex", f"agents/omc_{name}.toml")
        if path.exists() and key not in owned:
            conflicts.append(f"unowned destination collision: {path}")
    return conflicts


def _recover(codex_home: Path, skills_home: Path) -> None:
    journal = _read_json(_journal_path(codex_home))
    if journal is None:
        return
    if journal.get("schema") != SCHEMA or not isinstance(journal.get("changed"), list):
        raise LifecycleError("tampered lifecycle journal")
    if journal.get("roots") != {"codex": str(codex_home), "skills": str(skills_home)}:
        raise LifecycleError("lifecycle journal roots do not match requested homes")
    for field in ("manifest_before_b64", "manifest_after_b64", "manifest_before_sha256", "manifest_after_sha256"):
        if not isinstance(journal.get(field), str):
            raise LifecycleError("tampered lifecycle journal manifest record")
    try:
        manifest_before = base64.b64decode(journal["manifest_before_b64"], validate=True)
        manifest_after = base64.b64decode(journal["manifest_after_b64"], validate=True)
    except (ValueError, TypeError) as exc:
        raise LifecycleError("tampered lifecycle journal manifest bytes") from exc
    if _sha(manifest_before) != journal["manifest_before_sha256"] or _sha(manifest_after) != journal["manifest_after_sha256"]:
        raise LifecycleError("tampered lifecycle journal manifest hash")
    manifest_path = _manifest_path(codex_home)
    _safe_target(manifest_path)
    current_manifest = manifest_path.read_bytes() if manifest_path.exists() else None
    current_manifest_hash = _sha(current_manifest) if current_manifest is not None else None
    expected_before_hash = journal["manifest_before_sha256"] if manifest_before else None
    expected_after_hash = journal["manifest_after_sha256"]
    if current_manifest_hash not in (expected_before_hash, expected_after_hash):
        raise LifecycleError("refusing recovery after unexpected manifest change")
    roots = _roots(codex_home, skills_home)
    records: list[tuple[dict[str, Any], Path, Path | None, tuple[int, int, int, str] | None]] = []
    # Validate every record and its current state before restoring any file.
    for item in journal["changed"]:
        if not isinstance(item, dict) or item.get("root") not in ("codex", "skills"):
            raise LifecycleError("tampered lifecycle journal entry")
        rel = _validate_rel(item.get("path"))
        logical = rel if item["root"] == "codex" else "skill/" + rel
        allowed = (("codex", rel) if item["root"] == "codex" else ("skills", rel))
        if allowed not in _ALLOWED_PAIRS:
            raise LifecycleError("tampered lifecycle journal allowlist")
        target = _destination(roots, logical)
        _safe_target(target)
        before = item.get("before_sha256")
        after = item.get("after_sha256")
        if before is not None and (not isinstance(before, str) or not _HASH.fullmatch(before)):
            raise LifecycleError("tampered lifecycle journal before hash")
        if not isinstance(after, str) or not _HASH.fullmatch(after):
            raise LifecycleError("tampered lifecycle journal after hash")
        backup = item.get("backup")
        backup_path: Path | None = None
        if backup:
            backup_path = codex_home / MANAGED_DIR / "backups" / _validate_rel(backup)
            _safe_target(backup_path)
            if not backup_path.exists() or backup_path.is_symlink():
                raise LifecycleError("lifecycle journal backup is missing or unsafe")
            backup_data = backup_path.read_bytes()
            if item.get("backup_sha256") != _sha(backup_data):
                raise LifecycleError("lifecycle journal backup hash mismatch")
        current_signature = _file_signature(target)
        current = current_signature[3] if current_signature is not None else None
        if current not in (before, after):
            raise LifecycleError(f"refusing recovery after unexpected user change: {target}")
        records.append((item, target, backup_path, current_signature))
    all_after = current_manifest_hash == expected_after_hash
    all_before = current_manifest_hash == expected_before_hash
    for item, target, _, _ in records:
        current_signature = _file_signature(target)
        current = current_signature[3] if current_signature is not None else None
        all_after = all_after and current == item["after_sha256"]
        all_before = all_before and current == item.get("before_sha256")
    if all_after:
        # The manifest and every file reached the commit point; a crash after
        # the manifest replace is therefore a completed transaction.
        _journal_path(codex_home).unlink(missing_ok=True)
        return
    if all_before:
        _journal_path(codex_home).unlink(missing_ok=True)
        return
    # At this point every record has been validated and all current hashes are
    # known to be either before or after. Restore the pre-transaction state.
    for item, target, backup_path, validated_signature in reversed(records):
        before = item.get("before_sha256")
        current_signature = _file_signature(target)
        if current_signature != validated_signature:
            raise LifecycleError(f"refusing recovery after concurrent edit: {target}")
        if current_signature is None or current_signature[3] == before:
            continue
        if current_signature[3] != item.get("after_sha256"):
            raise LifecycleError(f"refusing recovery after unexpected state: {target}")
        if backup_path is not None:
            atomic_write(target, backup_path.read_bytes(), expected=validated_signature)
        elif target.exists() and not target.is_symlink():
            if _file_signature(target) != validated_signature:
                raise LifecycleError(f"refusing recovery after concurrent edit: {target}")
            target.unlink()
    if current_manifest_hash == expected_after_hash:
        manifest_signature = _file_signature(manifest_path)
        if manifest_signature is None or manifest_signature[3] != expected_after_hash:
            raise LifecycleError("refusing recovery after concurrent manifest edit")
        if manifest_before:
            atomic_write(manifest_path, manifest_before, expected=manifest_signature)
        elif manifest_path.exists() and not manifest_path.is_symlink():
            if _file_signature(manifest_path) != manifest_signature:
                raise LifecycleError("refusing recovery after concurrent manifest edit")
            manifest_path.unlink()
    _journal_path(codex_home).unlink(missing_ok=True)


@contextmanager
def _lifecycle_lock(path: Path):
    """Serialize lifecycle writers while allowing lock cleanup on normal exit."""
    lock_path = path
    _safe_target(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path.exists():
        if lock_path.is_symlink() or not lock_path.is_file():
            raise LifecycleError(f"refusing unsafe lifecycle lock path: {lock_path}")
        try:
            stream = lock_path.open("r+b")
        except OSError as exc:
            raise LifecycleError(f"cannot open lifecycle lock: {lock_path}") from exc
    else:
        try:
            fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise LifecycleError(f"another lifecycle operation is initializing: {lock_path}")
        stream = os.fdopen(fd, "r+b")
        stream.write(_LOCK_CONTENT)
        stream.flush()
        os.fsync(stream.fileno())
    locked = False
    try:
        try:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except ImportError:
            import msvcrt
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                locked = True
            except OSError as exc:
                raise LifecycleError("another lifecycle operation is in progress") from exc
        except OSError as exc:
            raise LifecycleError("another lifecycle operation is in progress") from exc
        # Windows byte-range locks deny reads by contenders. Validate only
        # after acquiring the lock, using the same descriptor that owns it.
        stream.seek(0)
        if stream.read() != _LOCK_CONTENT:
            raise LifecycleError(f"refusing unrecognized lifecycle lock file: {lock_path}")
        yield
    finally:
        if locked:
            try:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            except ImportError:
                import msvcrt
                stream.seek(0)
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            except OSError:
                pass
        stream.close()


@contextmanager
def _lifecycle_locks(codex_home: Path, skills_home: Path):
    """Hold both root locks in deterministic order."""
    paths = [codex_home / MANAGED_DIR / ".lock", skills_home / ".oh-my-codex.lock"]
    paths.sort(key=lambda path: str(path))
    with _lifecycle_lock(paths[0]):
        with _lifecycle_lock(paths[1]):
            yield


def _lock_paths(codex_home: Path, skills_home: Path) -> list[str]:
    return [str(codex_home / MANAGED_DIR / ".lock"), str(skills_home / ".oh-my-codex.lock")]


def _write_journal(codex_home: Path, skills_home: Path, changed: list[dict[str, Any]], *, manifest_before: bytes, manifest_after: bytes) -> None:
    payload = {"schema": SCHEMA, "state": "installing", "roots": {"codex": str(codex_home), "skills": str(skills_home)},
              "manifest_before_b64": base64.b64encode(manifest_before).decode("ascii"),
              "manifest_after_b64": base64.b64encode(manifest_after).decode("ascii"),
              "manifest_before_sha256": _sha(manifest_before), "manifest_after_sha256": _sha(manifest_after), "changed": changed}
    atomic_write(_journal_path(codex_home), json.dumps(payload, sort_keys=True, indent=2).encode())


def _manifest_bytes(codex_home: Path, skills_home: Path, hashes: dict[str, str]) -> bytes:
    entries = []
    for logical in ASSETS:
        root = "skills" if logical.startswith("skill/") else "codex"
        path = logical.removeprefix("skill/") if root == "skills" else logical
        entries.append({"root": root, "path": path, "sha256": hashes[logical]})
    payload = {"schema": SCHEMA, "version": __version__, "roots": {"codex": str(codex_home), "skills": str(skills_home)}, "files": entries}
    return json.dumps(payload, sort_keys=True, indent=2).encode()


def _write_manifest(codex_home: Path, skills_home: Path, hashes: dict[str, str]) -> None:
    atomic_write(_manifest_path(codex_home), _manifest_bytes(codex_home, skills_home, hashes))


def install(codex_home: str | os.PathLike[str] | None = None,
            skills_home: str | os.PathLike[str] | None = None,
            *, source_root: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    codex, skills = resolve_paths(codex_home, skills_home)
    _validate_bundle(_asset_sources(_source_root(Path(source_root) if source_root is not None else None)))
    _ensure_root(codex)
    _ensure_root(skills)
    managed = codex / MANAGED_DIR
    if managed.exists() and managed.is_symlink():
        raise LifecycleError(f"refusing symlink managed directory: {managed}")
    managed.mkdir(parents=True, exist_ok=True)
    skills.mkdir(parents=True, exist_ok=True)
    with _lifecycle_locks(codex, skills):
        return _install_impl(codex_home, skills_home, source_root=source_root)


def _install_impl(codex_home: str | os.PathLike[str] | None = None,
            skills_home: str | os.PathLike[str] | None = None,
            *, source_root: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Install or reconcile the bundled files with fail-closed ownership."""
    codex, skills = resolve_paths(codex_home, skills_home)
    _ensure_root(codex)
    _ensure_root(skills)
    managed = codex / MANAGED_DIR
    if managed.exists() and managed.is_symlink():
        raise LifecycleError(f"refusing symlink managed directory: {managed}")
    managed.mkdir(parents=True, exist_ok=True)
    _recover(codex, skills)
    manifest = _load_manifest(codex, skills)
    manifest_path = _manifest_path(codex)
    _safe_target(manifest_path)
    manifest_before = manifest_path.read_bytes() if manifest_path.exists() else b""
    old = _manifest_entries(manifest)
    warnings = _preflight_config(codex)
    conflicts = _role_conflicts(codex, old)
    if conflicts:
        raise LifecycleError("role conflict: " + "; ".join(conflicts))
    sources = _asset_sources(_source_root(Path(source_root) if source_root is not None else None))
    _validate_bundle(sources)
    roots = _roots(codex, skills)
    planned: list[tuple[str, Path, bytes, str, str | None, tuple[int, int, int, str] | None]] = []
    hashes = {logical: _sha(data) for logical, data in sources.items()}
    for logical, data in sources.items():
        root_name = "skills" if logical.startswith("skill/") else "codex"
        rel = logical.removeprefix("skill/") if root_name == "skills" else logical
        target = _destination(roots, logical)
        _safe_target(target)
        owned_hash = old.get((root_name, rel))
        expected_signature = _file_signature(target)
        if target.exists():
            if target.is_symlink():
                raise LifecycleError(f"refusing symlink target: {target}")
            current = expected_signature[3] if expected_signature is not None else None
            if owned_hash is None:
                raise LifecycleError(f"unowned destination collision: {target}")
            if current != owned_hash:
                raise LifecycleError(f"owned file was modified: {target}")
            if current == hashes[logical]:
                continue
        elif owned_hash is not None and owned_hash != hashes[logical]:
            # Missing files are safe to recreate only when the old ownership is
            # still a valid allowlisted entry.
            pass
        backup_name: str | None = None
        if target.exists():
            backup_name = f"{int(time.time())}-{uuid.uuid4().hex}-{root_name}-{Path(rel).name}"
        planned.append((logical, target, data, root_name, backup_name, expected_signature))
    changed: list[dict[str, Any]] = []
    manifest_after = _manifest_bytes(codex, skills, hashes)
    _write_journal(codex, skills, changed, manifest_before=manifest_before, manifest_after=manifest_after)
    installed: list[str] = []
    backups: list[str] = []
    try:
        for logical, target, data, root_name, backup_name, expected_signature in planned:
            if _file_signature(target) != expected_signature:
                raise LifecycleError(f"owned target changed during install preflight: {target}")
            entry = {"root": root_name, "path": logical.removeprefix("skill/") if root_name == "skills" else logical,
                     "before_sha256": expected_signature[3] if expected_signature is not None else None, "after_sha256": _sha(data)}
            if backup_name:
                backup_dir = managed / "backups"
                _safe_target(backup_dir)
                backup_dir.mkdir(parents=True, exist_ok=True)
                backup_path = backup_dir / backup_name
                if _file_signature(target) != expected_signature:
                    raise LifecycleError(f"owned target changed before backup: {target}")
                backup_data = target.read_bytes()
                atomic_write(backup_path, backup_data)
                entry["backup"] = backup_name
                entry["backup_sha256"] = _sha(backup_data)
                backups.append(str(backup_path))
            changed.append(entry)
            _write_journal(codex, skills, changed, manifest_before=manifest_before, manifest_after=manifest_after)
            atomic_write(target, data, expected=expected_signature)
            installed.append(logical)
        _write_manifest(codex, skills, hashes)
    except Exception:
        # Recovery validates all records and restores only files still carrying
        # the journal's after hash.
        _recover(codex, skills)
        raise
    _journal_path(codex).unlink(missing_ok=True)
    restart_note = "Codex Desktop restart required; start a NEW Desktop thread before invoking $oh-my-codex (no hot reload assumed)"
    model_note = "Select Astra (gpt-6-astra) or Sol (gpt-5.6-sol) as the main-thread model"
    return {"overall": "PASS", "version": __version__, "installed": installed, "backups": backups, "warnings": warnings,
            "restart_required": True, "new_thread_required": True, "restart_guidance": restart_note,
            "main_model_guidance": model_note,
            "activation_required": "$oh-my-codex", "globally_activated": False,
            "lock_paths": _lock_paths(codex, skills)}


def uninstall(codex_home: str | os.PathLike[str] | None = None,
              skills_home: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    codex, skills = resolve_paths(codex_home, skills_home)
    _ensure_root(codex)
    managed = codex / MANAGED_DIR
    if managed.exists() and managed.is_symlink():
        raise LifecycleError(f"refusing symlink managed directory: {managed}")
    if managed.exists():
        _ensure_root(skills)
        skills.mkdir(parents=True, exist_ok=True)
        with _lifecycle_locks(codex, skills):
            return _uninstall_impl(codex_home, skills_home)
    return _uninstall_impl(codex_home, skills_home)


def _uninstall_impl(codex_home: str | os.PathLike[str] | None = None,
              skills_home: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Remove only unchanged files recorded in the ownership manifest."""
    codex, skills = resolve_paths(codex_home, skills_home)
    _ensure_root(codex)
    _ensure_root(skills)
    _recover(codex, skills)
    manifest = _load_manifest(codex, skills)
    if manifest is None:
        return {"overall": "PASS", "removed": [], "preserved": [], "warnings": ["not installed"], "lock_paths": _lock_paths(codex, skills)}
    roots = _roots(codex, skills)
    removed: list[str] = []
    preserved: list[str] = []
    actions: list[tuple[str, Path, tuple[int, int, int, str]]] = []
    for item in manifest["files"]:
        logical = item["path"] if item["root"] == "codex" else "skill/" + item["path"]
        target = _destination(roots, logical)
        _safe_target(target)
        if target.is_symlink():
            preserved.append(f"{logical} (symlink)")
            continue
        expected_signature = _file_signature(target)
        if expected_signature is None:
            continue
        if expected_signature[3] != item["sha256"]:
            preserved.append(f"{logical} (modified)")
            continue
        actions.append((logical, target, expected_signature))
    # Every target has been checked before the first unlink, so a late
    # collision cannot leave a half-completed uninstall.
    for logical, target, expected_signature in actions:
        current = _file_signature(target)
        if current != expected_signature:
            preserved.append(f"{logical} (modified during uninstall)")
            continue
        target.unlink()
        removed.append(logical)
    # Empty directories owned solely by this package may be tidied safely.
    for directory in (codex / "agents", skills / "oh-my-codex"):
        if directory.exists() and directory.is_dir() and not directory.is_symlink():
            try:
                directory.rmdir()
            except OSError:
                pass
    manifest_removed = False
    manifest_path = _manifest_path(codex)
    if not preserved:
        _safe_target(manifest_path)
        if manifest_path.exists() and not manifest_path.is_symlink():
            manifest_path.unlink()
            manifest_removed = True
    return {"overall": "PASS" if not preserved else "PASS WITH NOTES", "removed": removed, "preserved": preserved,
            "manifest": str(manifest_path), "manifest_removed": manifest_removed,
            "backups_retained": (codex / MANAGED_DIR / "backups").exists(),
            "resume": "safe to rerun after interruption; removal is hash guarded and idempotent",
            "lock_paths": _lock_paths(codex, skills)}


def _check(name: str, status: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


def doctor(codex_home: str | os.PathLike[str] | None = None,
           skills_home: str | os.PathLike[str] | None = None,
           *, platform_name: str | None = None,
           codex_bin: str = "codex") -> dict[str, Any]:
    """Perform static, read-only lifecycle and environment diagnostics."""
    codex, skills = resolve_paths(codex_home, skills_home)
    checks: list[dict[str, str]] = []
    warnings: list[str] = []
    platform_value = platform_name or sys.platform
    supported = platform_value.startswith(("darwin", "linux", "win"))
    checks.append(_check("platform", "PASS" if supported else "FAIL", platform_value))
    py_ok = sys.version_info >= (3, 11)
    checks.append(_check("python", "PASS" if py_ok else "FAIL", ".".join(map(str, sys.version_info[:3]))))
    executable = shutil.which(codex_bin)
    if executable:
        try:
            completed = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=5, check=False)
            detail = (completed.stdout or completed.stderr).strip()[:200]
            checks.append(_check("codex", "PASS" if completed.returncode == 0 else "PASS WITH NOTES", detail or executable))
            if completed.returncode != 0:
                warnings.append("Codex version command returned nonzero")
        except (OSError, subprocess.TimeoutExpired) as exc:
            checks.append(_check("codex", "PASS WITH NOTES", f"could not query version: {exc}"))
            warnings.append("Codex version was not observable")
    else:
        checks.append(_check("codex", "PASS WITH NOTES", f"executable not found: {codex_bin}"))
        warnings.append("Codex executable was not found; runtime availability is unverified")
    try:
        config_warnings = _preflight_config(codex)
        warnings.extend(config_warnings)
        checks.append(_check("config.toml", "PASS", "absent or valid TOML; no file was changed"))
    except LifecycleError as exc:
        checks.append(_check("config.toml", "FAIL", str(exc)))
    try:
        manifest = _load_manifest(codex, skills)
        if manifest is None:
            checks.append(_check("ownership manifest", "FAIL", "not installed"))
        else:
            entries = _manifest_entries(manifest)
            hashes_ok = True
            for (root_name, rel), expected in entries.items():
                logical = rel if root_name == "codex" else "skill/" + rel
                target = _destination(_roots(codex, skills), logical)
                if not target.exists() or target.is_symlink() or _sha(target.read_bytes()) != expected:
                    hashes_ok = False
                    break
            checks.append(_check("ownership manifest", "PASS" if hashes_ok else "FAIL", "allowlisted files match" if hashes_ok else "owned file hash mismatch"))
            template_failures: list[str] = []
            import tomllib
            for name in AGENT_NAMES:
                path = codex / "agents" / f"omc_{name}.toml"
                if not path.exists():
                    template_failures.append(f"missing {path.name}")
                    continue
                try:
                    data = tomllib.loads(path.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, ValueError) as exc:
                    template_failures.append(f"{path.name}: {exc}")
                    continue
                expected_model = "gpt-5.6-sol" if name == "oracle" else "gpt-5.6-luna"
                expected_effort = "medium" if name == "explorer" else "high"
                if not isinstance(data.get("name"), str) or data.get("name") != f"omc_{name}":
                    template_failures.append(f"{path.name}: name")
                for field in ("description", "developer_instructions"):
                    if not isinstance(data.get(field), str) or not data.get(field).strip():
                        template_failures.append(f"{path.name}: {field}")
                if data.get("model") != expected_model:
                    template_failures.append(f"{path.name}: model")
                if data.get("model_reasoning_effort") != expected_effort:
                    template_failures.append(f"{path.name}: model_reasoning_effort")
                role_agents = data.get("agents")
                if not isinstance(role_agents, dict) or role_agents.get("enabled") is not False:
                    template_failures.append(f"{path.name}: agents.enabled")
                expected_sandbox = "workspace-write" if name == "fixer" else "read-only"
                if data.get("sandbox_mode") != expected_sandbox:
                    template_failures.append(f"{path.name}: sandbox_mode")
            skill_file = skills / "oh-my-codex" / "SKILL.md"
            if not skill_file.exists():
                template_failures.append("missing skill SKILL.md")
            else:
                try:
                    skill_file.read_text(encoding="utf-8")
                except (OSError, UnicodeError) as exc:
                    template_failures.append(f"SKILL.md: {exc}")
            policy_file = skills / "oh-my-codex" / "agents" / "openai.yaml"
            if not policy_file.exists():
                template_failures.append("missing openai.yaml")
            else:
                try:
                    policy_text = policy_file.read_text(encoding="utf-8")
                    if "allow_implicit_invocation: false" not in policy_text:
                        template_failures.append("openai.yaml: explicit invocation policy")
                except (OSError, UnicodeError) as exc:
                    template_failures.append(f"openai.yaml: {exc}")
            checks.append(_check("role templates", "FAIL" if template_failures else "PASS", "; ".join(template_failures) if template_failures else "four expected templates have bounded model, effort, sandbox, and agent settings"))
    except LifecycleError as exc:
        checks.append(_check("ownership manifest", "FAIL", str(exc)))
    try:
        roles = _scan_role_files(codex)
        by_role: dict[str, list[str]] = {}
        for path, role in roles:
            by_role.setdefault(role, []).append(str(path))
        duplicates = [f"{role}: {', '.join(paths)}" for role, paths in by_role.items() if len(paths) > 1]
        checks.append(_check("role declarations", "FAIL" if duplicates else "PASS", "; ".join(duplicates) if duplicates else "no duplicate expected role declarations"))
        warnings.extend(duplicates)
    except (OSError, ValueError, LifecycleError) as exc:
        checks.append(_check("role declarations", "FAIL", f"static scan failed closed: {exc}"))
    # These are implementation limitations of current Codex role discovery,
    # not failures of correctly formed package templates.
    checks.append(_check("Codex role capability notes", "PASS WITH NOTES", "Known tested Desktop hosts have ignored valid per-role sandbox requests; behavioral compliance is not technical isolation. Retest effective permissions on future hosts; static configuration remains valid."))
    checks.append(_check("Desktop verification", "PASS WITH NOTES", "STATIC ONLY: Codex Desktop discovery, effective permissions, and behavior are unverified; restart and a NEW Desktop thread are required after installation"))
    warnings.append("static doctor does not verify provider availability or live role discovery")
    warnings.append("Desktop behavior is unverified; run `oh-my-codex verify-desktop --prepare` and complete the guided smoke test")
    has_fail = any(item["status"] == "FAIL" for item in checks)
    overall = "FAIL" if has_fail else ("PASS WITH NOTES" if warnings or any(item["status"] == "PASS WITH NOTES" for item in checks) else "PASS")
    return {"overall": overall, "checks": checks, "warnings": warnings, "lock_paths": _lock_paths(codex, skills)}
