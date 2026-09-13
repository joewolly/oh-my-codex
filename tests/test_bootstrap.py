from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_PATH = ROOT / "scripts/bootstrap.py"
SPEC = importlib.util.spec_from_file_location("omc_bootstrap", BOOTSTRAP_PATH)
assert SPEC is not None and SPEC.loader is not None
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


class BootstrapInstallerTests(unittest.TestCase):
    def test_bootstrap_help_is_side_effect_free(self) -> None:
        result = subprocess.run(
            [sys.executable, str(BOOTSTRAP_PATH), "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("private tooling venv", result.stdout)

    def test_default_venv_and_python_are_platform_native(self) -> None:
        venv_dir = bootstrap.default_venv_dir()
        self.assertTrue(venv_dir.is_absolute())
        python = bootstrap.venv_python(venv_dir)
        if os.name == "nt":
            self.assertEqual(python.name, "python.exe")
            self.assertEqual(python.parent.name, "Scripts")
        else:
            self.assertEqual(python.name, "python")
            self.assertEqual(python.parent.name, "bin")

    def test_venv_builder_matches_platform_cli_symlink_behavior(self) -> None:
        builder = bootstrap.new_venv_builder()
        self.assertTrue(builder.with_pip)
        self.assertEqual(builder.symlinks, os.name != "nt")

    def test_venv_reuse_requires_working_pip(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            python = Path(temp) / ("python.exe" if os.name == "nt" else "python")
            python.write_text("placeholder", encoding="utf-8")
            version_ok = subprocess.CompletedProcess([], 0)
            pip_missing = subprocess.CompletedProcess([], 1)
            with mock.patch.object(
                bootstrap.subprocess,
                "run",
                side_effect=[version_ok, pip_missing],
            ) as run_mock:
                self.assertFalse(bootstrap.venv_is_usable(python))

        self.assertEqual(
            run_mock.call_args_list[1].args[0],
            [str(python), "-m", "pip", "--version"],
        )

    def test_incomplete_venv_is_removed_and_recreated(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            venv_dir = Path(temp) / "tooling venv"
            old_python = bootstrap.venv_python(venv_dir)
            old_python.parent.mkdir(parents=True)
            old_python.write_text("old", encoding="utf-8")
            stale_marker = venv_dir / "partial-ensurepip.txt"
            stale_marker.write_text("stale", encoding="utf-8")

            def create_replacement(path: Path) -> None:
                replacement = bootstrap.venv_python(Path(path))
                replacement.parent.mkdir(parents=True, exist_ok=True)
                replacement.write_text("new", encoding="utf-8")

            with mock.patch.object(
                bootstrap,
                "venv_is_usable",
                side_effect=[False, True],
            ), mock.patch.object(bootstrap, "new_venv_builder") as builder_factory:
                builder_factory.return_value.create.side_effect = create_replacement
                result = bootstrap.ensure_venv(venv_dir)

            self.assertEqual(result, bootstrap.venv_python(venv_dir))
            self.assertEqual(result.read_text(encoding="utf-8"), "new")
            self.assertFalse(stale_marker.exists())
            builder_factory.return_value.create.assert_called_once_with(venv_dir)

    def test_failed_venv_creation_cleans_partial_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            venv_dir = Path(temp) / "tooling venv"

            def fail_after_partial_create(path: Path) -> None:
                partial = Path(path) / "partial-ensurepip.txt"
                partial.parent.mkdir(parents=True, exist_ok=True)
                partial.write_text("partial", encoding="utf-8")
                raise subprocess.CalledProcessError(1, ["python", "-m", "ensurepip"])

            with mock.patch.object(
                bootstrap,
                "venv_is_usable",
                return_value=False,
            ), mock.patch.object(bootstrap, "new_venv_builder") as builder_factory:
                builder_factory.return_value.create.side_effect = fail_after_partial_create
                with self.assertRaises(subprocess.CalledProcessError):
                    bootstrap.ensure_venv(venv_dir)

            self.assertFalse(venv_dir.exists())

    def test_lifecycle_command_preserves_optional_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            python = base / ("python.exe" if os.name == "nt" else "python")
            codex = base / "codex home with spaces"
            skills = base / "skills home with spaces"
            command = bootstrap.lifecycle_command(
                python,
                "install",
                codex_home=codex,
                skills_home=skills,
            )
        self.assertEqual(command[:4], [str(python), "-m", "oh_my_codex", "install"])
        self.assertEqual(command[4:], ["--codex-home", str(codex), "--skills-home", str(skills)])

    def test_bootstrap_private_install_disables_pip_cache(self) -> None:
        tooling_python = Path("C:/private tooling/python.exe" if os.name == "nt" else "/private tooling/python")
        with mock.patch.object(bootstrap, "ensure_supported_python"), \
                mock.patch.object(bootstrap, "ensure_venv", return_value=tooling_python), \
                mock.patch.object(bootstrap, "run") as run_mock:
            self.assertEqual(bootstrap.main(["--skip-doctor"]), 0)

        pip_args = run_mock.call_args_list[0].args[0]
        self.assertEqual(pip_args[:4], [str(tooling_python), "-m", "pip", "install"])
        self.assertIn("--no-cache-dir", pip_args)
        self.assertIn("--no-deps", pip_args)
        self.assertIn("--force-reinstall", pip_args)

    def test_wrappers_delegate_to_bootstrap_without_global_activation(self) -> None:
        shell = (ROOT / "install.sh").read_text(encoding="utf-8")
        powershell = (ROOT / "install.ps1").read_text(encoding="utf-8")
        bootstrap_source = BOOTSTRAP_PATH.read_text(encoding="utf-8")
        for source in (shell, powershell, bootstrap_source):
            self.assertNotIn("OMC_ORCHESTRATOR_V1", source)
        self.assertIn("scripts/bootstrap.py", shell)
        self.assertIn("scripts/bootstrap.py", powershell)
        self.assertIn('"install"', bootstrap_source)
        self.assertIn('"doctor"', bootstrap_source)
        self.assertIn("NOT globally activated", bootstrap_source)
        self.assertIn("verify-desktop.ps1", bootstrap_source)
        desktop_wrapper = (ROOT / "verify-desktop.ps1").read_text(encoding="utf-8")
        self.assertIn("verify-desktop-state.json", desktop_wrapper)
        self.assertIn("Set-Clipboard", desktop_wrapper)
        self.assertIn("--evaluate", desktop_wrapper)
        self.assertIn("--control-thread-id", desktop_wrapper)

    @unittest.skipUnless(shutil.which("bash"), "bash is not available")
    def test_install_sh_parses(self) -> None:
        result = subprocess.run(
            [shutil.which("bash"), "-n", str(ROOT / "install.sh")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not available")
    def test_install_ps1_parses(self) -> None:
        script = str(ROOT / "install.ps1").replace("'", "''")
        command = (
            "$tokens=$null;$errors=$null;"
            f"[System.Management.Automation.Language.Parser]::ParseFile('{script}',[ref]$tokens,[ref]$errors)>$null;"
            "if($errors.Count){$errors | ForEach-Object { Write-Error $_.Message }; exit 1}"
        )
        result = subprocess.run(
            [shutil.which("pwsh"), "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not available")
    def test_verify_desktop_ps1_parses(self) -> None:
        script = str(ROOT / "verify-desktop.ps1").replace("'", "''")
        command = (
            "$tokens=$null;$errors=$null;"
            f"[System.Management.Automation.Language.Parser]::ParseFile('{script}',[ref]$tokens,[ref]$errors)>$null;"
            "if($errors.Count){$errors | ForEach-Object { Write-Error $_.Message }; exit 1}"
        )
        result = subprocess.run(
            [shutil.which("pwsh"), "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
