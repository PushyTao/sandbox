"""Fail-closed checks for the independent Windows collector guard."""
import contextlib
import ctypes
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import bounded_process
import collect_review


@unittest.skipUnless(sys.platform == "win32", "requires native Windows APIs")
class CollectorGuardTests(unittest.TestCase):
    def check_start_failure(self, operation, expected_handles):
        kernel = bounded_process._kernel()
        setattr(kernel, operation, Mock(return_value=0))
        with tempfile.TemporaryDirectory(prefix="r1-start-") as temporary:
            marker = Path(temporary) / "python-started"
            env = dict(os.environ, TEMP=temporary)
            with patch.object(bounded_process, "_kernel", return_value=kernel):
                run = bounded_process.run_bounded(
                    [sys.executable, "-I", "-S", "-c",
                     "from pathlib import Path; Path('python-started').write_text('started')"],
                    cwd=temporary, env=env, timeout=5)
            self.assertFalse(marker.exists(), "test Python ran without outer containment")
            self.assertIsNotNone(run["error"])
            self.assertFalse(run["cleanup"]["assigned_before_resume"])
            self.assertTrue(run["cleanup"]["complete"], run)
            handles = run["cleanup"]["process_handles"]
            self.assertEqual(len(handles), expected_handles)
            self.assertTrue(all(item["exit_confirmed"] for item in handles), run)

    def test_outer_configuration_failure_never_starts_python(self):
        self.check_start_failure("SetInformationJobObject", 0)

    def test_outer_assignment_failure_reaps_unresumed_python(self):
        self.check_start_failure("AssignProcessToJobObject", 1)

    def test_incomplete_cleanup_cannot_report_success_or_continue(self):
        source = Path(os.environ["SBX_REVIEW_M0_ROOT"]).resolve().parents[1]
        kernel = bounded_process._kernel()
        original_close = kernel.CloseHandle
        reported_failure = []

        def close_then_report_failure(handle):
            # Release the real resource; simulate a failed cleanup receipt only.
            closed = original_close(handle)
            if not reported_failure:
                reported_failure.append(True)
                ctypes.set_last_error(6)
                return 0
            return closed

        kernel.CloseHandle = close_then_report_failure
        with tempfile.TemporaryDirectory(prefix="r1-incomplete-") as temporary:
            output = Path(temporary) / "evidence"
            with patch.object(bounded_process, "_kernel", return_value=kernel), \
                    patch.object(sys, "argv", ["collect_review.py", "--source", str(source),
                                               "--output-dir", str(output)]), \
                    contextlib.redirect_stdout(io.StringIO()):
                code = collect_review.main()
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(code, 1)
            self.assertEqual(summary["collector_exit_code"], 1)
            self.assertEqual(len(summary["runs"]), 1, "continued after incomplete cleanup")
            run = summary["runs"][0]
            self.assertEqual(run["exit_code"], 0, "fault must be cleanup, not baseline failure")
            self.assertFalse(run["cleanup"]["complete"])
            self.assertTrue(run["cleanup"]["errors"])
            self.assertTrue(all(item["exit_confirmed"] for item in run["cleanup"]["process_handles"]))
            self.assertTrue(summary["temporary_fixture_removed"])
            self.assertTrue((output / "baseline-tests.stderr.txt").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
