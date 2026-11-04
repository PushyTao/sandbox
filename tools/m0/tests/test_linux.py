import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

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
    def test_lifecycle_setup_failure_collects_observed_child_before_return(self):
        # Inject a launcher that exited before readiness, while a real bounded
        # child remains. A separate reaper owns wait(), just as PID 1 does for
        # descendants of a real namespace launcher.
        child = subprocess.Popen([sys.executable, "-I", "-c",
            "import time; print('ready', flush=True); time.sleep(.4)"], stdout=subprocess.PIPE)
        reaper = threading.Thread(target=child.wait)
        try:
            self.assertEqual(child.stdout.readline().strip(), b"ready")
            self.assertIsNone(child.poll())
            reaper.start()
            launcher = Mock(pid=os.getpid())
            launcher.poll.return_value = 0
            with tempfile.TemporaryDirectory() as temporary, patch.object(
                    linux.subprocess, "Popen", return_value=launcher):
                with self.assertRaisesRegex(RuntimeError, "ready"):
                    linux._lifecycle([], Path(temporary))
            self.assertIsNotNone(child.poll(), "probe returned while its observed synthetic child was alive")
            launcher.kill.assert_not_called()
        finally:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=3)
            if reaper.ident is not None:
                reaper.join(timeout=3)
            child.stdout.close()

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
        for identifier in ("ENV.private", "NET-1.ipv4-tcp", "NET-1.ipv4-udp",
                           "NET-1.ipv6-tcp", "NET-1.ipv6-udp", "NET-1.abstract-unix"):
            self.assertEqual(results[identifier].status, "pass", identifier)
        self.assertEqual(results["PR-1.root-exit"].status, "pass")
        # These intentional counterexamples block this candidate, rather than
        # treating a ro-bind mount as the design's complete policy compiler.
        self.assertEqual(results["FS-4.hardlink"].status, "fail")
        self.assertEqual(results["FS-4.future-name"].status, "fail")


if __name__ == "__main__":
    unittest.main()
