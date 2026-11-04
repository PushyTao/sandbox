"""PUSH-4: fixed synthetic checks, not a sandbox or a product acceptance suite.

SBX_REVIEW_M0_ROOT selects the trusted source tree being reviewed. Tests never
accept a workload, contact external endpoints, or change host security settings.
"""

import contextlib
import ctypes
import io
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


M0_ROOT = Path(os.environ.get(
    "SBX_REVIEW_M0_ROOT", str(Path(__file__).resolve().parents[1] / "m0")
)).resolve(strict=True)
sys.path.insert(0, str(M0_ROOT))
from sandbox_probe import report, windows  # noqa: E402


class PublicBoundaryTests(unittest.TestCase):
    def test_cli_rejects_workload_workspace_and_platform_overrides(self):
        for args in (["--command", "synthetic-only"], ["--workspace", "."],
                     ["--platform", "win32"], ["--", "synthetic-only"]):
            with self.subTest(args=args), patch.object(report, "collect_observations") as collect:
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                    report.main(args, stdout=io.StringIO())
                self.assertEqual(error.exception.code, 2)
                collect.assert_not_called()


class FilesystemCounterexamples(unittest.TestCase):
    """Passing tests reproduce unsafe shortcuts; they do not test a backend."""

    def test_hardlink_bypasses_name_filter_and_copy_can_disclose_content(self):
        with tempfile.TemporaryDirectory(prefix="push4-alias-") as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            protected = source / "protected"
            protected.mkdir()
            secret = protected / "synthetic-secret"
            secret.write_bytes(b"PUSH4-SYNTHETIC-ONLY")
            alias = source / "ordinary"
            try:
                os.link(str(secret), str(alias))
            except OSError as error:
                self.skipTest("fixture filesystem cannot hardlink: errno={}".format(error.errno))
            self.assertTrue(os.path.samefile(str(secret), str(alias)))
            self.assertNotEqual(secret.resolve(), alias.resolve())
            copied = root / "copied"
            # Deliberately unsafe example: filtering names alone misses aliases.
            shutil.copytree(str(source), str(copied), ignore=shutil.ignore_patterns("protected"))
            self.assertFalse((copied / "protected").exists())
            self.assertEqual((copied / "ordinary").read_bytes(), b"PUSH4-SYNTHETIC-ONLY")
            self.assertFalse(os.path.samefile(str(copied / "ordinary"), str(secret)))
            (copied / "ordinary").write_bytes(b"copy-only")
            self.assertEqual(secret.read_bytes(), b"PUSH4-SYNTHETIC-ONLY")
            alias.write_bytes(b"alias-write")
            self.assertEqual(secret.read_bytes(), b"alias-write")

    def test_resolved_path_does_not_pin_parent_identity(self):
        with tempfile.TemporaryDirectory(prefix="push4-parent-") as temporary:
            root = Path(temporary)
            parent = root / "parent"
            parent.mkdir()
            (parent / "data").write_bytes(b"approved-object")
            checked = (parent / "data").resolve(strict=True)
            parent.rename(root / "original-parent")
            parent.mkdir()
            (parent / "data").write_bytes(b"replacement-object")
            self.assertEqual(checked.read_bytes(), b"replacement-object")
            self.assertEqual((root / "original-parent" / "data").read_bytes(), b"approved-object")

    def test_existing_name_scan_does_not_reserve_future_name(self):
        with tempfile.TemporaryDirectory(prefix="push4-future-") as temporary:
            root = Path(temporary)
            protected_names = {".agents", ".git", "sandbox.toml"}
            existing = {item.name for item in root.iterdir()} & protected_names
            self.assertEqual(existing, set())
            (root / ".agents").mkdir()
            (root / ".agents" / "config").write_bytes(b"synthetic-only")
            self.assertTrue((root / ".agents" / "config").is_file())


class TemporaryCleanupTests(unittest.TestCase):
    def test_directory_symlink_cleanup_preserves_external_synthetic_sentinel(self):
        # "External" is a sibling synthetic directory inside our own fixture.
        with tempfile.TemporaryDirectory(prefix="push4-cleanup-") as temporary:
            root = Path(temporary)
            outside = root / "outside"
            outside.mkdir()
            sentinel = outside / "sentinel"
            sentinel.write_bytes(b"must-survive-inner-cleanup")
            with tempfile.TemporaryDirectory(prefix="inner-", dir=str(root)) as inner:
                try:
                    os.symlink(str(outside), str(Path(inner) / "link"), target_is_directory=True)
                except OSError as error:
                    self.skipTest("directory symlink unavailable: errno={}".format(error.errno))
            self.assertFalse(Path(inner).exists())
            self.assertEqual(sentinel.read_bytes(), b"must-survive-inner-cleanup")


@unittest.skipUnless(sys.platform == "win32", "requires native Windows APIs")
class WindowsInitializationFailures(unittest.TestCase):
    def test_job_configuration_failure_never_creates_process(self):
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.SetInformationJobObject = Mock(return_value=0)
        kernel.CreateProcessW = Mock()
        kernel.ResumeThread = Mock()
        with patch.object(windows.ctypes, "WinDLL", return_value=kernel):
            observation = windows._job_lifecycle()
        self.assertEqual(observation.status, "unavailable", observation.to_dict())
        kernel.CreateProcessW.assert_not_called()
        kernel.ResumeThread.assert_not_called()
        self.assertNotIn("cleanup_errors", observation.details)

    def test_assignment_failure_never_resumes_and_reaps_exact_process(self):
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.DuplicateHandle.argtypes = [wintypes.HANDLE, wintypes.HANDLE, wintypes.HANDLE,
                                          ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD,
                                          wintypes.BOOL, wintypes.DWORD]
        kernel.DuplicateHandle.restype = wintypes.BOOL
        retained = wintypes.HANDLE()
        host_process = kernel.GetCurrentProcess()

        def fail_assignment(job, process):
            # Retain an independent handle: never infer cleanup from PID reuse.
            if not kernel.DuplicateHandle(host_process, process, host_process,
                                          ctypes.byref(retained), 0, False, 2):
                raise ctypes.WinError(ctypes.get_last_error())
            ctypes.set_last_error(5)
            return 0

        kernel.AssignProcessToJobObject = Mock(side_effect=fail_assignment)
        kernel.ResumeThread = Mock()
        try:
            with patch.object(windows.ctypes, "WinDLL", return_value=kernel):
                observation = windows._job_lifecycle()
            self.assertTrue(retained.value, "failure injection never reached a real process")
            self.assertEqual(observation.status, "fail", observation.to_dict())
            self.assertFalse(observation.details["assigned_before_resume"])
            kernel.ResumeThread.assert_not_called()
            self.assertEqual(kernel.WaitForSingleObject(retained, 0), 0,
                             "probe returned before its suspended child terminated")
            self.assertNotIn("cleanup_errors", observation.details)
        finally:
            # Emergency cleanup uses only the exact handle created by this test.
            if retained.value:
                try:
                    if kernel.WaitForSingleObject(retained, 0) != 0:
                        kernel.TerminateProcess(retained, 1)
                        self.assertEqual(kernel.WaitForSingleObject(retained, 5000), 0)
                finally:
                    kernel.CloseHandle(retained)


if __name__ == "__main__":
    unittest.main(verbosity=2)
