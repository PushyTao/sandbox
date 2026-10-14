import importlib.util
import pathlib
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


class WindowsProbeTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('sandbox_probe.windows'),
                             'Windows feasibility probe is missing')
        from sandbox_probe import windows
        return windows

    def test_unsupported_host_does_not_claim_job_success(self):
        module = self.module()
        with patch.object(module.sys, 'platform', 'linux'):
            observations = {item.id: item for item in module.probe()}
        self.assertEqual(observations['windows.job_lifecycle'].status, 'unavailable')
        self.assertFalse(any(item.status == 'pass' for item in observations.values()))

    @unittest.skipUnless(sys.platform == 'win32', 'requires native Windows')
    def test_native_job_kills_running_synthetic_child(self):
        observations = {item.id: item for item in self.module().probe()}
        job = observations['windows.job_lifecycle']
        self.assertEqual(job.status, 'pass', job.to_dict())
        self.assertTrue(job.details['running_before_close'])
        self.assertTrue(job.details['terminated_after_close'])
        self.assertTrue(job.details['assigned_before_resume'])
        self.assertGreater(job.details['pid'], 0)

    def test_job_never_claims_other_security_boundaries(self):
        observations = {item.id: item for item in self.module().probe()}
        for boundary in ('filesystem', 'token', 'network', 'ipc', 'descendants'):
            self.assertEqual(observations['windows.' + boundary].status, 'unverified')

    @unittest.skipUnless(sys.platform == 'win32', 'requires native Windows')
    def test_resume_failure_reaps_suspended_child(self):
        import ctypes
        from ctypes import wintypes

        module = self.module()
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        # Only the failing operation is simulated: Job, suspended process, cleanup
        # and the independent termination check all use native APIs.
        kernel.ResumeThread = Mock(return_value=0xFFFFFFFF)
        with patch.object(module.ctypes, 'WinDLL', return_value=kernel):
            job = module.probe()[0]
        self.assertEqual(job.status, 'fail', job.to_dict())
        self.assertNotIn('cleanup_errors', job.details)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        handle = kernel.OpenProcess(0x100000, False, job.details['pid'])
        if handle:
            try:
                self.assertEqual(kernel.WaitForSingleObject(handle, 0), 0,
                                 'suspended synthetic child survived cleanup')
            finally:
                kernel.CloseHandle(handle)
        else:
            self.assertEqual(ctypes.get_last_error(), 87,
                             'expected no such process, not an access failure')


if __name__ == '__main__':
    unittest.main()
