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

    @unittest.skipUnless(sys.platform == 'win32', 'requires native Windows')
    def test_job_close_reaps_running_descendant(self):
        # Removing descendant creation, membership verification or the wait must
        # prevent a passing lifecycle observation. The probe pins a real handle.
        job = self.module()._job_lifecycle()
        self.assertEqual(job.status, 'pass', job.to_dict())
        self.assertTrue(job.details.get('descendant_in_job'), job.to_dict())
        self.assertTrue(job.details['descendant_running_before_close'])
        self.assertTrue(job.details['descendant_terminated_after_close'])
        self.assertTrue(job.details['descendant_cleanup_confirmed'])
        self.assertIsInstance(job.details['descendant_exit_code'], int)
        self.assertNotEqual(job.details['descendant_pid'], job.details['pid'])

    @unittest.skipUnless(sys.platform == 'win32', 'requires native Windows')
    def test_descendant_query_failure_is_not_success_and_reaps_tree(self):
        import ctypes
        from ctypes import wintypes

        module = self.module()
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.DuplicateHandle.argtypes = [wintypes.HANDLE, wintypes.HANDLE,
            wintypes.HANDLE, ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD,
            wintypes.BOOL, wintypes.DWORD]
        kernel.DuplicateHandle.restype = wintypes.BOOL
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        retained = wintypes.HANDLE()

        def fail_query(process, job, result):
            # Keep an independent handle BEFORE cleanup, avoiding a reused PID
            # or a later OpenProcess failure masquerading as proof of exit.
            current = kernel.GetCurrentProcess()
            self.assertTrue(kernel.DuplicateHandle(current, process, current,
                ctypes.byref(retained), 0, False, 2))
            ctypes.set_last_error(5)
            return False

        kernel.IsProcessInJob = Mock(side_effect=fail_query)
        try:
            with patch.object(module.ctypes, 'WinDLL', return_value=kernel):
                job = module._job_lifecycle()
            self.assertEqual(job.status, 'fail', job.to_dict())
            self.assertEqual(job.details['error']['operation'], 'IsProcessInJob(descendant)')
            self.assertTrue(retained.value, 'descendant must exist before injected failure')
            self.assertEqual(kernel.WaitForSingleObject(retained, 0), 0,
                             'probe returned before descendant cleanup')
            self.assertNotIn('cleanup_errors', job.details)
        finally:
            if retained.value:
                kernel.CloseHandle(retained)

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
