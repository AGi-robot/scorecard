"""Check protocol isolation without model requests or upstream dependencies."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / "eqbench"
SPEC = importlib.util.spec_from_file_location("eqbench_launcher", ROOT / "eqbench_run.py")
LAUNCHER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LAUNCHER)
PROTOCOLS = json.loads((ROOT / "protocols.json").read_text())


class LauncherTests(unittest.TestCase):
    def test_changed_revision_and_modified_source_never_execute(self):
        for revision, dirty in [("0" * 40, ""),
                                (PROTOCOLS["eqbench-v4"]["revision"], " M eqbench4.py")]:
            with self.subTest(revision=revision, dirty=dirty), \
                 patch.object(LAUNCHER.subprocess, "check_output", side_effect=[revision, dirty]), \
                 patch.object(LAUNCHER.subprocess, "call") as execute, \
                 contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    LAUNCHER.main(["--suite", "eqbench-v4", "--checkout", "/tmp", "--", "--help"])
                execute.assert_not_called()

    def test_dry_run_and_official_arguments_for_both_suites(self):
        for suite, protocol in PROTOCOLS.items():
            with self.subTest(suite=suite), tempfile.TemporaryDirectory() as tmp:
                entry = Path(tmp) / protocol["entrypoint"]
                entry.touch()
                options = ["--suite", suite, "--checkout", tmp, "--python", "/official/python"]
                forwarded = ["--run-id", "grace test", "--help"]
                with patch.object(LAUNCHER.subprocess, "check_output",
                                  side_effect=[protocol["revision"], ""]), \
                     patch.object(LAUNCHER.subprocess, "call") as execute, \
                     contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(LAUNCHER.main(options + ["--dry-run", "--"] + forwarded), 0)
                    execute.assert_not_called()
                with patch.object(LAUNCHER.subprocess, "check_output",
                                  side_effect=[protocol["revision"], ""]), \
                     patch.object(LAUNCHER.subprocess, "call", return_value=7) as execute, \
                     contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(LAUNCHER.main(options + ["--"] + forwarded), 7)
                    execute.assert_called_once_with(
                        ["/official/python", str(entry), *forwarded], cwd=Path(tmp))


if __name__ == "__main__":
    unittest.main()
