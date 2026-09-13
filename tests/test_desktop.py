"""Desktop verification regressions with mutable config and pinned Python semantics."""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
import shutil
import unittest
from pathlib import Path

from desktop_suite import DesktopVerificationTests as _DesktopVerificationTests
from oh_my_codex import desktop_core
from oh_my_codex.desktop import _asset_paths, prepare_desktop_fixture


class DesktopVerificationTests(_DesktopVerificationTests):
    # These legacy expectations treated user-owned config.toml as an immutable
    # OMC asset or assumed ambient `python3` was the prepared Python 3.11+.
    test_config_change_invalidates_fingerprint = None
    test_standalone_missing_asset_at_preparation_still_fails = None
    test_standalone_every_installed_asset_changed_or_missing_fails = None
    test_exact_retained_prompt_command_no_import_outside_checkout_with_spaces = None
    test_activated_prompt_uses_only_pinned_fixture_gate = None

    def _gate_command(self):
        prompt = (self.root / "desktop-prompt.txt").read_text()
        expected = desktop_core._preflight_argv(
            self.root,
            self.metadata["preflight_sha256"],
            executable=str(Path(sys.executable).expanduser().absolute()),
        )
        literal = desktop_core._serialize_shell_argv(expected)
        self.assertEqual(prompt.count(literal), 1)
        if os.name == "nt":
            return expected
        expected_helper = expected[-2]
        matches = []
        for line in prompt.splitlines():
            try:
                args = shlex.split(line)
            except ValueError:
                continue
            if len(args) >= 7 and args[1:4] == ["-I", "-S", "-c"] and args[-2] == expected_helper:
                matches.append(args)
        self.assertEqual(len(matches), 1)
        return matches[0]

    def _run_gate(self, command=None):
        command = list(command or self._gate_command())
        return subprocess.run(command, cwd=self.root.parent, env={"PATH": os.defpath, "PYTHONPATH": ""},
                              capture_output=True, text=True)

    def _retained_prompt_command(self):
        prepared = prepare_desktop_fixture(self.root.parent / "final_fixture with spaces",
                                           codex_home=self.codex, skills_home=self.skills)
        artifact = self.root.parent / "activated-prompt.txt"
        artifact.write_bytes(Path(prepared["prompt"]).read_bytes())
        lines = [line for line in artifact.read_text().splitlines()
                 if line == prepared["preflight_command"]]
        self.assertEqual(len(lines), 1)
        return prepared, lines[0]

    def _run_prompt_command(self, command):
        if os.name == "nt":
            powershell = shutil.which("pwsh") or shutil.which("powershell")
            self.assertIsNotNone(powershell)
            return subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-Command", command],
                                  cwd=self.root.parent, capture_output=True, text=True)
        args = shlex.split(command)
        self.assertEqual(args[1:4], ["-I", "-S", "-c"])
        return subprocess.run(args, cwd=self.root.parent, capture_output=True, text=True)

    def test_generated_preflight_binds_preparation_interpreter(self) -> None:
        args = self._gate_command()
        self.assertTrue(Path(args[0]).is_absolute())
        self.assertEqual(Path(args[0]), Path(sys.executable).expanduser().absolute())
        self.assertEqual(args[1:4], ["-I", "-S", "-c"])
        self.assertEqual(args[-2], str(self.root / ".omc-probe-preflight.py"))
        self.assertEqual(self._run_gate().returncode, 0)

    def test_exact_retained_prompt_uses_bound_interpreter_without_package_import(self) -> None:
        prepared, command = self._retained_prompt_command()
        unavailable = subprocess.run([sys.executable, "-I", "-S", "-c", "import oh_my_codex"],
                                     cwd=self.root.parent, capture_output=True, text=True)
        self.assertNotEqual(unavailable.returncode, 0)
        self.assertIn("No module named 'oh_my_codex'", unavailable.stderr)
        args = desktop_core._preflight_argv(
            Path(prepared["fixture"]),
            prepared["preflight_sha256"],
            executable=str(Path(sys.executable).expanduser().absolute()),
        ) if os.name == "nt" else shlex.split(command)
        self.assertEqual(Path(args[0]), Path(sys.executable).expanduser().absolute())
        self.assertEqual(args[1:4], ["-I", "-S", "-c"])
        self.assertEqual(args[5:], [prepared["preflight"], prepared["preflight_sha256"]])
        self.assertIn(" ", args[5])
        result = self._run_prompt_command(command)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_activated_prompt_uses_only_bound_pinned_fixture_gate(self) -> None:
        prompt = (self.root / "desktop-prompt.txt").read_text()
        args = self._gate_command()
        self.assertEqual(Path(args[0]), Path(sys.executable).expanduser().absolute())
        self.assertEqual(args[1:4], ["-I", "-S", "-c"])
        self.assertIn(str(self.root / ".omc-probe-preflight.py"), prompt)
        self.assertIn(self.metadata["preflight_sha256"], prompt)
        self.assertNotIn("-m oh_my_codex", prompt)
        self.assertIn("Do not improvise an alternate gate", prompt)
        self.assertIn("pip install, modify the Python environment, or fall back to importing oh_my_codex", prompt)

    def test_benign_config_rewrite_does_not_invalidate_acceptance(self) -> None:
        self._complete()
        (self.codex / "config.toml").write_text(
            'model = "gpt-6-astra"\n# benign Desktop rewrite\n', encoding="utf-8"
        )
        self.assertEqual(self._evaluate()["evidence_validity"], "PASS")
        gate = self._run_gate()
        self.assertEqual(gate.returncode, 0, gate.stdout + gate.stderr)

    def test_missing_user_config_is_allowed(self) -> None:
        (self.codex / "config.toml").unlink()
        prepared = prepare_desktop_fixture(
            self.root.parent / "missing config fixture",
            codex_home=self.codex,
            skills_home=self.skills,
        )
        result = self._run_gate(desktop_core._preflight_argv(
            Path(prepared["fixture"]), prepared["preflight_sha256"],
            executable=str(Path(sys.executable).expanduser().absolute()),
        ))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_direct_core_prepared_fixture_preflight_is_compatible(self) -> None:
        prepared = desktop_core.prepare_desktop_fixture(
            self.root.parent / "direct core fixture",
            codex_home=self.codex,
            skills_home=self.skills,
        )
        # Direct core callers retain the legacy ambient-python command contract;
        # the public Desktop facade used by the CLI binds the preparation Python.
        args = desktop_core._preflight_argv(
            Path(prepared["fixture"]), prepared["preflight_sha256"], executable=sys.executable
        )
        result = subprocess.run(args,
                                cwd=self.root.parent, env={"PATH": os.defpath, "PYTHONPATH": ""},
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_posix_preflight_serialization_is_unchanged(self) -> None:
        args = ["/tmp/Python Tool/python", "-I", "-S", "-c", "print('ok')", "/tmp/helper path", "abc123"]
        self.assertEqual(desktop_core._serialize_shell_argv(args, windows=False), shlex.join(args))

    def test_powershell_serializer_escapes_spaces_and_apostrophes(self) -> None:
        args = [r"C:\Users\Test User\O'Brien\python.exe", "-I", "-S", "-c", "print('ok')",
                r"C:\Users\Test User\O'Brien\.omc-probe-preflight.py", "abc123"]
        command = desktop_core._serialize_shell_argv(args, windows=True)
        self.assertEqual(
            command,
            "& 'C:\\Users\\Test User\\O''Brien\\python.exe' '-I' '-S' '-c' "
            "'print(''ok'')' 'C:\\Users\\Test User\\O''Brien\\.omc-probe-preflight.py' 'abc123'",
        )

    @unittest.skipUnless(os.name == "nt", "literal retained PowerShell execution is Windows-only")
    def test_exact_retained_command_executes_through_powershell_unchanged(self) -> None:
        prepared, command = self._retained_prompt_command()
        self.assertTrue(command.startswith("& '"))
        self.assertIn(" '-I' '-S' '-c' ", command)
        result = self._run_prompt_command(command)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(prepared["preflight"], str(Path(prepared["fixture"]) / ".omc-probe-preflight.py"))

    @unittest.skipUnless(os.name == "nt", "PowerShell argv execution is Windows-only")
    def test_powershell_apostrophe_argument_round_trips(self) -> None:
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        self.assertIsNotNone(powershell)
        marker = r"C:\Users\Test User\O'Brien\fixture"
        command = desktop_core._serialize_shell_argv(
            [sys.executable, "-I", "-S", "-c", "import sys;print(sys.argv[1])", marker],
            windows=True,
        )
        result = subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-Command", command],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(result.stdout.strip(), marker)

    def test_malformed_user_config_fails_preflight(self) -> None:
        (self.codex / "config.toml").write_text('[agents\n', encoding="utf-8")
        result = self._run_gate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("effective config.toml is invalid", result.stdout)

    def test_agent_discovery_disabled_in_user_config_fails_preflight(self) -> None:
        (self.codex / "config.toml").write_text('[agents]\nenabled = false\n', encoding="utf-8")
        result = self._run_gate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("agents.enabled=false", result.stdout)

    def test_conflicting_omc_role_in_user_config_fails_preflight(self) -> None:
        (self.codex / "config.toml").write_text(
            '[agents.omc_explorer]\nmodel = "gpt-5.6-luna"\n', encoding="utf-8"
        )
        result = self._run_gate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("conflicting OMC roles", result.stdout)

    def test_managed_installed_assets_remain_byte_pinned(self) -> None:
        for name, path in _asset_paths(self.codex, self.skills).items():
            if not name.startswith("installed") or name == "installed-config":
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


del _DesktopVerificationTests
