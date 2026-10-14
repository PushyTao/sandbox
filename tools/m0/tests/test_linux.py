import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sandbox_probe import linux


class LinuxProbeTests(unittest.TestCase):
    def test_platform_mismatch_is_unverified(self):
        with patch.object(linux.sys, "platform", "win32"):
            results = linux.probe()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "unverified")

    def test_missing_bwrap_does_not_run_a_workload(self):
        with patch.object(linux.sys, "platform", "linux"), patch.object(
            linux, "_trusted_bwrap", return_value=None
        ), patch.object(linux.subprocess, "run") as run:
            results = linux.probe()
        self.assertEqual(results[0].status, "unavailable")
        run.assert_not_called()

    def test_plan_uses_namespaces_clear_environment_and_no_host_root(self):
        plan = linux._plan("/usr/bin/bwrap", "/tmp/m0-workspace")
        for flag in ("--unshare-pid", "--unshare-net", "--unshare-ipc",
                     "--unshare-user", "--clearenv", "--die-with-parent",
                     "--new-session", "--cap-drop"):
            self.assertIn(flag, plan)
        mounts = [plan[i + 1:i + 3] for i, value in enumerate(plan)
                  if value in ("--bind", "--ro-bind")]
        self.assertNotIn(["/", "/"], mounts)
        self.assertNotIn([str(Path.home()), str(Path.home())], mounts)
        self.assertIn(["/tmp/m0-workspace", "/workspace"], mounts)

    def test_single_counterexample_is_not_reported_as_protection(self):
        result = linux._counterexample("FS-4.alias", "hardlink write", True)
        self.assertEqual(result.status, "fail")
        result = linux._counterexample("FS-4.alias", "hardlink write", False)
        self.assertEqual(result.status, "unverified")

    @unittest.skipUnless(sys.platform == "linux" and os.environ.get("SBX_M0_INTEGRATION") == "1",
                         "opt-in real Linux test; no platform guarantee from a skip")
    def test_probe_output_is_bounded_during_collection(self):
        with self.assertRaisesRegex(RuntimeError, "oversized"):
            linux._run(["/usr/bin/env"], "import time; print('x' * 20000, flush=True); time.sleep(30)")

    @unittest.skipUnless(sys.platform == "linux" and os.environ.get("SBX_M0_INTEGRATION") == "1",
                         "opt-in real Linux test; no platform guarantee from a skip")
    def test_real_probe_exercises_positive_and_negative_cases(self):
        results = {item.id: item for item in linux.probe()}
        self.assertEqual(results["LINUX.setup"].status, "pass")
        self.assertEqual(results["FS-1.workspace"].status, "pass")
        self.assertEqual(results["FS-2.symlink"].status, "pass")
        self.assertEqual(results["FS-3.existing"].status, "pass")
        self.assertEqual(results["NET-1.ipv4-tcp"].status, "pass")
        self.assertEqual(results["NET-1.abstract-unix"].status, "pass")
        self.assertEqual(results["PR-1.root-exit"].status, "pass")
        # These intentional counterexamples block this candidate, rather than
        # treating a ro-bind mount as the design's complete policy compiler.
        self.assertEqual(results["FS-4.hardlink"].status, "fail")
        self.assertEqual(results["FS-4.future-name"].status, "fail")


if __name__ == "__main__":
    unittest.main()
