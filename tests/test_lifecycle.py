from __future__ import annotations

import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from oh_my_codex import lifecycle


def make_assets(root: Path) -> Path:
    (root / "assets/agents").mkdir(parents=True)
    (root / "assets/skills/oh-my-codex/agents").mkdir(parents=True)
    for name in lifecycle.AGENT_NAMES:
        model = "gpt-5.6-sol" if name == "oracle" else "gpt-5.6-luna"
        effort = "medium" if name == "explorer" else "high"
        (root / f"assets/agents/omc_{name}.toml").write_text(
            f'name = "omc_{name}"\ndescription = "{name} role"\ndeveloper_instructions = "Never subdelegate."\nmodel = "{model}"\nmodel_reasoning_effort = "{effort}"\nsandbox_mode = "{("workspace-write" if name == "fixer" else "read-only")}"\n[agents]\nenabled = false\n',
            encoding="utf-8",
        )
    (root / "assets/skills/oh-my-codex/SKILL.md").write_text("# skill\nagents.enabled = false\n", encoding="utf-8")
    (root / "assets/skills/oh-my-codex/agents/openai.yaml").write_text("allow_implicit_invocation: false\n", encoding="utf-8")
    return root


class LifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="omc lifecycle ")
        self.base = Path(self.temp.name)
        self.source = make_assets(self.base / "source")
        self.codex = self.base / "codex home with spaces"
        self.skills = self.base / "skills home with spaces"
        self.project = self.base / "isolated project/deep"
        self.project.mkdir(parents=True)
        self.home = self.base / "isolated home"
        self.home.mkdir()
        self.env_patch = mock.patch.dict(
            os.environ,
            {"HOME": str(self.home), "USERPROFILE": str(self.home), "CODEX_HOME": str(self.home / ".codex")},
            clear=False,
        )
        self.env_patch.start()
        self.cwd_patch = mock.patch.object(Path, "cwd", return_value=self.project)
        self.cwd_patch.start()

    def tearDown(self) -> None:
        self.cwd_patch.stop()
        self.env_patch.stop()
        self.temp.cleanup()

    def test_fresh_and_idempotent_install(self) -> None:
        first = lifecycle.install(self.codex, self.skills, source_root=self.source)
        second = lifecycle.install(self.codex, self.skills, source_root=self.source)
        self.assertEqual(first["overall"], "PASS")
        self.assertTrue(first["restart_required"])
        self.assertTrue(first["new_thread_required"])
        self.assertIn("Astra", first["main_model_guidance"])
        self.assertEqual(second["installed"], [])
        self.assertTrue((self.codex / "oh-my-codex/manifest.json").exists())

    def test_install_adds_capability_without_global_activation(self) -> None:
        self.codex.mkdir(parents=True)
        config = self.codex / "config.toml"
        global_instructions = self.codex / "AGENTS.md"
        config.write_text('model = "gpt-6-astra"\n', encoding="utf-8")
        global_instructions.write_text("Ordinary Codex instructions.\n", encoding="utf-8")
        before = {p: p.read_bytes() for p in (config, global_instructions)}
        report = lifecycle.install(self.codex, self.skills)
        self.assertFalse(report["globally_activated"])
        self.assertEqual(report["activation_required"], "$oh-my-codex")
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        policy = (self.skills / "oh-my-codex/agents/openai.yaml").read_text()
        self.assertIn("allow_implicit_invocation: false", policy)
        lifecycle.uninstall(self.codex, self.skills)
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_resolve_paths_environment_precedence_and_unicode(self) -> None:
        env_codex = self.base / "env home – 用户" / ".codex"
        with mock.patch.dict(os.environ, {"CODEX_HOME": str(env_codex), "HOME": str(self.home), "USERPROFILE": str(self.home)}, clear=False):
            resolved_codex, resolved_skills = lifecycle.resolve_paths()
            expected_skills = (Path.home() / ".agents/skills").absolute()
            explicit_codex, explicit_skills = lifecycle.resolve_paths(self.base / "explicit – codex", self.base / "explicit – skills")
        self.assertEqual(resolved_codex, env_codex.absolute())
        self.assertEqual(resolved_skills, expected_skills)
        self.assertEqual(explicit_codex, (self.base / "explicit – codex").absolute())
        self.assertEqual(explicit_skills, (self.base / "explicit – skills").absolute())

    def test_posix_lock_branch_is_exclusive(self) -> None:
        lock_dir = self.base / "lock root"
        lock_dir.mkdir()
        with lifecycle._lifecycle_lock(lock_dir / ".oh-my-codex.lock"):
            with self.assertRaises(lifecycle.LifecycleError):
                with lifecycle._lifecycle_lock(lock_dir / ".oh-my-codex.lock"):
                    pass

    def test_windows_msvcrt_lock_branch_simulation(self) -> None:
        fake_msvcrt = types.SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2, calls=[])

        def locking(fd, mode, size):
            fake_msvcrt.calls.append((fd, mode, size))

        fake_msvcrt.locking = locking
        lock_path = self.base / "windows lock – 用户" / ".oh-my-codex.lock"
        lock_path.parent.mkdir(parents=True)
        with mock.patch.dict(sys.modules, {"fcntl": None, "msvcrt": fake_msvcrt}):
            with lifecycle._lifecycle_lock(lock_path):
                self.assertTrue(lock_path.exists())
        self.assertEqual([call[1] for call in fake_msvcrt.calls], [1, 2])

    def test_bundled_assets_install_doctor_and_reinstall(self) -> None:
        lifecycle.install(self.codex, self.skills)
        report = lifecycle.doctor(self.codex, self.skills, codex_bin="definitely-not-installed")
        self.assertIn(report["overall"], ("PASS", "PASS WITH NOTES"))
        lifecycle.uninstall(self.codex, self.skills)
        lifecycle.install(self.codex, self.skills)
        self.assertTrue((self.skills / "oh-my-codex/agents/openai.yaml").exists())

    def test_upgrade_backs_up_owned_file(self) -> None:
        lifecycle.install(self.codex, self.skills, source_root=self.source)
        asset = self.source / "assets/agents/omc_explorer.toml"
        asset.write_text(asset.read_text() + "description = 'updated'\n", encoding="utf-8")
        result = lifecycle.install(self.codex, self.skills, source_root=self.source)
        self.assertIn("agents/omc_explorer.toml", result["installed"])
        self.assertTrue(result["backups"])

    def test_uninstall_preserves_modified_and_is_repeatable(self) -> None:
        lifecycle.install(self.codex, self.skills, source_root=self.source)
        target = self.codex / "agents/omc_fixer.toml"
        target.write_text(target.read_text() + "# user change\n", encoding="utf-8")
        result = lifecycle.uninstall(self.codex, self.skills)
        self.assertTrue(result["preserved"])
        self.assertTrue(target.exists())
        again = lifecycle.uninstall(self.codex, self.skills)
        self.assertEqual(again["removed"], [])

    def test_clean_uninstall_removes_manifest_and_keeps_unrelated_file(self) -> None:
        lifecycle.install(self.codex, self.skills, source_root=self.source)
        unrelated = self.codex / "agents/custom.toml"
        unrelated.write_text('name = "custom"\n', encoding="utf-8")
        result = lifecycle.uninstall(self.codex, self.skills)
        self.assertTrue(result["manifest_removed"])
        self.assertFalse((self.codex / "oh-my-codex/manifest.json").exists())
        self.assertTrue(unrelated.exists())

    def test_malformed_config_is_fail_closed(self) -> None:
        self.codex.mkdir(parents=True)
        (self.codex / "config.toml").write_text("[broken\n", encoding="utf-8")
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.install(self.codex, self.skills, source_root=self.source)
        self.assertFalse((self.codex / "agents").exists())

    def test_config_and_unrelated_agent_are_byte_preserved(self) -> None:
        self.codex.mkdir(parents=True)
        config_bytes = b"[agents]\nenabled = true\n"
        (self.codex / "config.toml").write_bytes(config_bytes)
        agents = self.codex / "agents"
        agents.mkdir()
        unrelated = agents / "custom.toml"
        unrelated_bytes = b'name = "custom"\ndescription = "user role"\n'
        unrelated.write_bytes(unrelated_bytes)
        lifecycle.install(self.codex, self.skills, source_root=self.source)
        self.assertEqual((self.codex / "config.toml").read_bytes(), config_bytes)
        self.assertEqual(unrelated.read_bytes(), unrelated_bytes)

    def test_collision_manifest_tamper_and_symlink_refuse(self) -> None:
        (self.codex / "agents").mkdir(parents=True)
        target = self.codex / "agents/omc_explorer.toml"
        target.write_text("user-owned", encoding="utf-8")
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.install(self.codex, self.skills, source_root=self.source)
        target.unlink()
        lifecycle.install(self.codex, self.skills, source_root=self.source)
        manifest = self.codex / "oh-my-codex/manifest.json"
        data = json.loads(manifest.read_text())
        data["files"][0]["path"] = "../outside"
        manifest.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.uninstall(self.codex, self.skills)

        manifest.unlink()
        try:
            manifest.symlink_to(self.source / "assets/agents/omc_explorer.toml")
        except OSError:
            self.skipTest("symlinks unavailable")
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.uninstall(self.codex, self.skills)

    def test_project_shadowing_is_a_conflict(self) -> None:
        project = self.base / "project"
        agents = project / ".codex/agents"
        agents.mkdir(parents=True)
        (agents / "custom.toml").write_text('name = "omc_explorer"\n', encoding="utf-8")
        with mock.patch.object(Path, "cwd", return_value=project):
            with self.assertRaises(lifecycle.LifecycleError):
                lifecycle.install(self.codex, self.skills, source_root=self.source)

    def test_nested_role_shadowing_is_a_conflict(self) -> None:
        nested = self.codex / "agents/nested"
        nested.mkdir(parents=True)
        (nested / "shadow.toml").write_text('name = "omc_explorer"\n', encoding="utf-8")
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.install(self.codex, self.skills, source_root=self.source)

    def test_project_config_shadowing_is_a_conflict(self) -> None:
        project = self.base / "project-config"
        config_dir = project / ".codex"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text('[agents.omc_explorer]\nmodel = "user"\n', encoding="utf-8")
        with mock.patch.object(Path, "cwd", return_value=project):
            with self.assertRaises(lifecycle.LifecycleError):
                lifecycle.install(self.codex, self.skills, source_root=self.source)

    def test_manifest_binds_both_roots(self) -> None:
        lifecycle.install(self.codex, self.skills, source_root=self.source)
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.uninstall(self.codex, self.base / "different skills")
        self.assertTrue((self.skills / "oh-my-codex/SKILL.md").exists())

    def test_shared_skills_root_is_locked(self) -> None:
        first_codex = self.base / "first codex"
        second_codex = self.base / "second codex"
        lifecycle.install(first_codex, self.skills, source_root=self.source)
        with lifecycle._lifecycle_locks(first_codex, self.skills):
            with self.assertRaises(lifecycle.LifecycleError):
                lifecycle.install(second_codex, self.skills, source_root=self.source)

    def test_malformed_existing_role_is_fail_closed(self) -> None:
        agents = self.codex / "agents"
        agents.mkdir(parents=True)
        (agents / "custom.toml").write_text("[broken\n", encoding="utf-8")
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.install(self.codex, self.skills, source_root=self.source)

    def test_rollback_on_write_failure(self) -> None:
        lifecycle.install(self.codex, self.skills, source_root=self.source)
        target = self.codex / "agents/omc_librarian.toml"
        old_target = target.read_bytes()
        source_target = self.source / "assets/agents/omc_librarian.toml"
        source_target.write_text(source_target.read_text() + "# upgrade\n", encoding="utf-8")
        original = lifecycle.atomic_write

        def fail_librarian(path, data, **kwargs):
            if Path(path) == target:
                raise OSError("injected")
            return original(path, data)

        with mock.patch.object(lifecycle, "atomic_write", side_effect=fail_librarian):
            with self.assertRaises(OSError):
                lifecycle.install(self.codex, self.skills, source_root=self.source)
        self.assertTrue((self.codex / "agents/omc_explorer.toml").exists())
        self.assertEqual((self.codex / "agents/omc_explorer.toml").read_bytes(), (self.source / "assets/agents/omc_explorer.toml").read_bytes())
        self.assertEqual(target.read_bytes(), old_target)
        self.assertTrue((self.codex / "oh-my-codex/manifest.json").exists())

    def test_rollback_mixed_existing_upgrade_keeps_before_record(self) -> None:
        lifecycle.install(self.codex, self.skills, source_root=self.source)
        first_source = self.source / "assets/agents/omc_explorer.toml"
        second_source = self.source / "assets/agents/omc_librarian.toml"
        first_source.write_text(first_source.read_text() + "# upgrade\n", encoding="utf-8")
        second_source.write_text(second_source.read_text() + "# upgrade\n", encoding="utf-8")
        first_target = self.codex / "agents/omc_explorer.toml"
        second_target = self.codex / "agents/omc_librarian.toml"
        old_first = first_target.read_bytes()
        old_second = second_target.read_bytes()
        original = lifecycle.atomic_write

        def fail_second(path, data, **kwargs):
            if Path(path) == second_target:
                raise OSError("injected second replace failure")
            return original(path, data, **kwargs)

        with mock.patch.object(lifecycle, "atomic_write", side_effect=fail_second):
            with self.assertRaises(OSError):
                lifecycle.install(self.codex, self.skills, source_root=self.source)
        self.assertEqual(first_target.read_bytes(), old_first)
        self.assertEqual(second_target.read_bytes(), old_second)
        self.assertFalse((self.codex / "oh-my-codex/journal.json").exists())

    def test_install_rechecks_second_target_after_first_write(self) -> None:
        lifecycle.install(self.codex, self.skills, source_root=self.source)
        explorer = self.source / "assets/agents/omc_explorer.toml"
        explorer.write_text(explorer.read_text() + "# upgrade\n", encoding="utf-8")
        librarian = self.source / "assets/agents/omc_librarian.toml"
        librarian.write_text(librarian.read_text() + "# upgrade\n", encoding="utf-8")
        first_target = self.codex / "agents/omc_explorer.toml"
        second_target = self.codex / "agents/omc_librarian.toml"
        old_first = first_target.read_bytes()
        user_edit = b'user edit during install\n'
        original = lifecycle.atomic_write

        def race(path, data, **kwargs):
            if Path(path) == first_target:
                second_target.write_bytes(user_edit)
            return original(path, data, **kwargs)

        with mock.patch.object(lifecycle, "atomic_write", side_effect=race):
            with self.assertRaises(lifecycle.LifecycleError):
                lifecycle.install(self.codex, self.skills, source_root=self.source)
        self.assertEqual(first_target.read_bytes(), old_first)
        self.assertEqual(second_target.read_bytes(), user_edit)

    def test_uninstall_rechecks_target_before_unlink(self) -> None:
        lifecycle.install(self.codex, self.skills, source_root=self.source)
        first_target = self.codex / "agents/omc_explorer.toml"
        second_target = self.codex / "agents/omc_librarian.toml"
        user_edit = b'user edit during uninstall\n'
        original_unlink = Path.unlink
        unlink_targets = [first_target, self.codex / "agents/omc_fixer.toml", self.codex / "agents/omc_oracle.toml"]
        unlink_targets.extend([self.skills / "oh-my-codex/SKILL.md", self.skills / "oh-my-codex/agents/openai.yaml", self.codex / "oh-my-codex/manifest.json"])
        calls = [0]

        def race_unlink(*args, **kwargs):
            path = unlink_targets[calls[0]]
            calls[0] += 1
            if path == first_target:
                second_target.write_bytes(user_edit)
            return original_unlink(path, *args, **kwargs)

        with mock.patch.object(Path, "unlink", side_effect=race_unlink):
            result = lifecycle.uninstall(self.codex, self.skills)
        self.assertIn("agents/omc_librarian.toml (modified during uninstall)", result["preserved"])
        self.assertEqual(second_target.read_bytes(), user_edit)

    def test_crash_after_manifest_is_committed_and_partial_crash_rolls_back(self) -> None:
        lifecycle.install(self.codex, self.skills, source_root=self.source)
        asset = self.source / "assets/agents/omc_explorer.toml"
        asset.write_text(asset.read_text() + "# upgrade\n", encoding="utf-8")
        original_manifest = lifecycle._write_manifest

        def crash_after_manifest(*args, **kwargs):
            original_manifest(*args, **kwargs)
            raise SystemExit("power loss")

        with mock.patch.object(lifecycle, "_write_manifest", side_effect=crash_after_manifest):
            with self.assertRaises(SystemExit):
                lifecycle.install(self.codex, self.skills, source_root=self.source)
        self.assertTrue((self.codex / "oh-my-codex/journal.json").exists())
        result = lifecycle.install(self.codex, self.skills, source_root=self.source)
        self.assertEqual(result["installed"], [])
        self.assertFalse((self.codex / "oh-my-codex/journal.json").exists())

    def test_recovery_preserves_edit_during_guarded_restore(self) -> None:
        lifecycle.install(self.codex, self.skills, source_root=self.source)
        asset = self.source / "assets/agents/omc_explorer.toml"
        asset.write_text(asset.read_text() + "# upgrade\n", encoding="utf-8")
        original_manifest = lifecycle._write_manifest

        def crash_before_manifest(*args, **kwargs):
            raise SystemExit("power loss")

        with mock.patch.object(lifecycle, "_write_manifest", side_effect=crash_before_manifest):
            with self.assertRaises(SystemExit):
                lifecycle.install(self.codex, self.skills, source_root=self.source)
        target = self.codex / "agents/omc_explorer.toml"
        user_edit = b"user edit during recovery\n"
        original_write = lifecycle.atomic_write
        injected = [False]

        def edit_during_restore(path, data, **kwargs):
            if Path(path) == target and not injected[0]:
                injected[0] = True
                target.write_bytes(user_edit)
            return original_write(path, data, **kwargs)

        with mock.patch.object(lifecycle, "atomic_write", side_effect=edit_during_restore):
            with self.assertRaises(lifecycle.LifecycleError):
                lifecycle.install(self.codex, self.skills, source_root=self.source)
        self.assertEqual(target.read_bytes(), user_edit)
        self.assertTrue((self.codex / "oh-my-codex/journal.json").exists())

    def test_arbitrary_shared_lock_file_or_directory_is_refused(self) -> None:
        self.skills.mkdir(parents=True)
        lock_path = self.skills / ".oh-my-codex.lock"
        lock_path.write_bytes(b"user-owned lock\n")
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.install(self.codex, self.skills, source_root=self.source)
        lock_path.unlink()
        lock_path.mkdir()
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.install(self.codex, self.skills, source_root=self.source)

    def test_nested_home_does_not_duplicate_role_scan(self) -> None:
        home = self.base / "isolated home"
        codex = home / ".codex"
        project = home / "project/deep"
        project.mkdir(parents=True)
        with mock.patch.object(Path, "cwd", return_value=project), mock.patch.dict(os.environ, {"HOME": str(home), "CODEX_HOME": str(codex)}):
            lifecycle.install(codex, home / ".agents/skills", source_root=self.source)
            result = lifecycle.doctor(codex, home / ".agents/skills", codex_bin="definitely-not-installed")
        declarations = next(c for c in result["checks"] if c["name"] == "role declarations")
        self.assertEqual(declarations["status"], "PASS")

    def test_parent_home_install_does_not_contaminate_alternate_home(self) -> None:
        parent_home = self.base / "parent home"
        parent_project = parent_home / "project/deep"
        parent_project.mkdir(parents=True)
        with mock.patch.object(Path, "cwd", return_value=parent_project):
            lifecycle.install(parent_home / ".codex", parent_home / ".agents/skills", source_root=self.source)

        alternate_home = self.base / "alternate home"
        alternate_project = alternate_home / "project/deep"
        alternate_project.mkdir(parents=True)
        with mock.patch.object(Path, "cwd", return_value=alternate_project):
            lifecycle.install(alternate_home / ".codex", alternate_home / ".agents/skills", source_root=self.source)
            result = lifecycle.doctor(alternate_home / ".codex", alternate_home / ".agents/skills", codex_bin="definitely-not-installed")
        declarations = next(c for c in result["checks"] if c["name"] == "role declarations")
        self.assertEqual(declarations["status"], "PASS")

    def test_doctor_duplicate_role_is_failure(self) -> None:
        lifecycle.install(self.codex, self.skills, source_root=self.source)
        (self.codex / "agents/custom.toml").write_text('name = "omc_explorer"\n', encoding="utf-8")
        result = lifecycle.doctor(self.codex, self.skills, codex_bin="definitely-not-installed")
        declarations = next(c for c in result["checks"] if c["name"] == "role declarations")
        self.assertEqual(declarations["status"], "FAIL")
        self.assertEqual(result["overall"], "FAIL")

    def test_doctor_platform_and_shadowing_diagnostic(self) -> None:
        lifecycle.install(self.codex, self.skills, source_root=self.source)
        result = lifecycle.doctor(self.codex, self.skills, platform_name="win32", codex_bin="definitely-not-installed")
        self.assertIn(result["overall"], ("PASS", "PASS WITH NOTES"))
        self.assertTrue(any(c["name"] == "platform" and c["status"] == "PASS" for c in result["checks"]))


if __name__ == "__main__":
    unittest.main()
