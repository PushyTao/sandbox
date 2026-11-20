"""Fixed, disposable native Job lifecycle experiment; not a sandbox runner."""

import ctypes
from ctypes import wintypes
import pathlib
import subprocess
import sys
import tempfile
import time

from .report import Observation


# Fixed synthetic payload only. Both processes self-expire; neither inherits the
# controlling Job handle. Publish the PID atomically after the descendant runs.
_DESCENDANT_CODE = """
import os, pathlib, time
pathlib.Path('descendant-ready.tmp').write_text(str(os.getpid()))
pathlib.Path('descendant-ready.tmp').replace('descendant-ready')
time.sleep(20)
"""
_CHILD_CODE = """
import pathlib, subprocess, sys, time
child = subprocess.Popen([sys.executable, '-I', '-S', '-c', {descendant!r}],
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    close_fds=True, creationflags=0x08000000)
pathlib.Path('ready').write_text('ready')
try:
    child.wait(timeout=20)
finally:
    if child.poll() is None:
        child.kill()
    child.wait(timeout=5)
""".format(descendant=_DESCENDANT_CODE)


def _job_lifecycle():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    size_t = ctypes.c_size_t

    class BasicLimits(ctypes.Structure):
        _fields_ = [('ProcessTime', ctypes.c_int64), ('JobTime', ctypes.c_int64),
                    ('LimitFlags', wintypes.DWORD), ('MinWorkingSet', size_t),
                    ('MaxWorkingSet', size_t), ('ActiveProcessLimit', wintypes.DWORD),
                    ('Affinity', size_t), ('PriorityClass', wintypes.DWORD),
                    ('SchedulingClass', wintypes.DWORD)]

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in
                    ('ReadOps', 'WriteOps', 'OtherOps', 'ReadBytes', 'WriteBytes', 'OtherBytes')]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [('BasicLimitInformation', BasicLimits), ('IoInfo', IoCounters),
                    ('ProcessMemoryLimit', size_t), ('JobMemoryLimit', size_t),
                    ('PeakProcessMemoryUsed', size_t), ('PeakJobMemoryUsed', size_t)]

    class StartupInfo(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('reserved', wintypes.LPWSTR),
                    ('desktop', wintypes.LPWSTR), ('title', wintypes.LPWSTR),
                    ('x', wintypes.DWORD), ('y', wintypes.DWORD),
                    ('xsize', wintypes.DWORD), ('ysize', wintypes.DWORD),
                    ('xchars', wintypes.DWORD), ('ychars', wintypes.DWORD),
                    ('fill', wintypes.DWORD), ('flags', wintypes.DWORD),
                    ('show', wintypes.WORD), ('reserved_size', wintypes.WORD),
                    ('reserved_data', ctypes.POINTER(ctypes.c_byte)),
                    ('stdin', wintypes.HANDLE), ('stdout', wintypes.HANDLE),
                    ('stderr', wintypes.HANDLE)]

    class ProcessInfo(ctypes.Structure):
        _fields_ = [('process', wintypes.HANDLE), ('thread', wintypes.HANDLE),
                    ('pid', wintypes.DWORD), ('tid', wintypes.DWORD)]

    signatures = {
        'CreateJobObjectW': ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
        'SetInformationJobObject': ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                     wintypes.DWORD], wintypes.BOOL),
        'CreateProcessW': ([wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p,
                            ctypes.c_void_p, wintypes.BOOL, wintypes.DWORD,
                            ctypes.c_void_p, wintypes.LPCWSTR,
                            ctypes.POINTER(StartupInfo), ctypes.POINTER(ProcessInfo)], wintypes.BOOL),
        'AssignProcessToJobObject': ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
        'ResumeThread': ([wintypes.HANDLE], wintypes.DWORD),
        'WaitForSingleObject': ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        'TerminateProcess': ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
        'OpenProcess': ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        'IsProcessInJob': ([wintypes.HANDLE, wintypes.HANDLE,
                            ctypes.POINTER(wintypes.BOOL)], wintypes.BOOL),
        'GetExitCodeProcess': ([wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
        'CloseHandle': ([wintypes.HANDLE], wintypes.BOOL),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(kernel, name)
        function.argtypes, function.restype = arguments, result

    def check(value, operation):
        if not value:
            raise OSError(ctypes.get_last_error(), operation)
        return value

    job = None
    temporary = None
    descendant = None
    process = ProcessInfo()
    details = {'assigned_before_resume': False, 'running_before_close': False,
               'terminated_after_close': False, 'descendant_in_job': False,
               'descendant_running_before_close': False,
               'descendant_terminated_after_close': False,
               'descendant_cleanup_confirmed': False}
    status, summary = 'fail', 'Job lifecycle experiment did not complete.'
    cleanup_errors = []
    try:
        job = check(kernel.CreateJobObjectW(None, None), 'CreateJobObjectW')
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE, no breakaway
        check(kernel.SetInformationJobObject(job, 9, ctypes.byref(limits),
                                            ctypes.sizeof(limits)), 'SetInformationJobObject')
        temporary = tempfile.TemporaryDirectory(prefix='m0-job-')
        directory = temporary.name
        marker = pathlib.Path(directory) / 'ready'
        descendant_marker = pathlib.Path(directory) / 'descendant-ready'
        # No workload input; -I -S disables user startup code.
        command = ctypes.create_unicode_buffer(subprocess.list2cmdline(
            [sys.executable, '-I', '-S', '-c', _CHILD_CODE]))
        startup = StartupInfo()
        startup.cb = ctypes.sizeof(startup)
        check(kernel.CreateProcessW(sys.executable, command, None, None, False,
                                    0x4 | 0x08000000, None, directory,
                                    ctypes.byref(startup), ctypes.byref(process)), 'CreateProcessW')
        details['pid'] = process.pid
        check(kernel.AssignProcessToJobObject(job, process.process), 'AssignProcessToJobObject')
        details['assigned_before_resume'] = True
        if kernel.ResumeThread(process.thread) == 0xFFFFFFFF:
            raise OSError(ctypes.get_last_error(), 'ResumeThread')
        deadline = time.monotonic() + 5
        while not (marker.exists() and descendant_marker.exists()) and time.monotonic() < deadline:
            if kernel.WaitForSingleObject(process.process, 0) != 258:
                break
            time.sleep(0.02)
        details['running_before_close'] = (
            marker.exists() and kernel.WaitForSingleObject(process.process, 0) == 258)
        if not descendant_marker.exists():
            raise OSError(0, 'descendant readiness timeout')
        # This PID comes from our fixed payload in its disposable directory.
        # Pin the process before closing the Job; a later PID lookup is not exit
        # evidence. Membership is checked against THIS Job, not any ambient Job.
        details['descendant_pid'] = int(descendant_marker.read_text())
        descendant = check(kernel.OpenProcess(0x100000 | 0x1000 | 0x1, False,
            details['descendant_pid']), 'OpenProcess(descendant)')
        member = wintypes.BOOL()
        check(kernel.IsProcessInJob(descendant, job, ctypes.byref(member)),
              'IsProcessInJob(descendant)')
        details['descendant_in_job'] = bool(member.value)
        details['descendant_running_before_close'] = kernel.WaitForSingleObject(descendant, 0) == 258
        check(kernel.CloseHandle(job), 'CloseHandle(job)')
        job = None
        details['terminated_after_close'] = kernel.WaitForSingleObject(process.process, 5000) == 0
        details['descendant_terminated_after_close'] = kernel.WaitForSingleObject(descendant, 5000) == 0
        if details['descendant_terminated_after_close']:
            exit_code = wintypes.DWORD()
            check(kernel.GetExitCodeProcess(descendant, ctypes.byref(exit_code)),
                  'GetExitCodeProcess(descendant)')
            details['descendant_exit_code'] = exit_code.value
        if all(details[key] for key in ('running_before_close', 'terminated_after_close',
                'descendant_in_job', 'descendant_running_before_close',
                'descendant_terminated_after_close')):
            status = 'pass'
            summary = 'Fixed child and its observed descendant ran in the Job and terminated on Job close.'
    except OSError as error:
        # Record operation and code only, never inherited environment or arbitrary output.
        details['error'] = {'operation': error.strerror, 'code': error.errno}
        if not process.process:
            status = 'unavailable'
    finally:
        if job and not kernel.CloseHandle(job):
            cleanup_errors.append('CloseHandle(job)')
        if process.process:
            if kernel.WaitForSingleObject(process.process, 0) != 0:
                # Job close may already be terminating the child. TerminateProcess
                # can then report access denied; the subsequent wait is decisive.
                terminated = kernel.TerminateProcess(process.process, 1)
                if kernel.WaitForSingleObject(process.process, 5000) != 0:
                    if not terminated:
                        cleanup_errors.append('TerminateProcess')
                    cleanup_errors.append('termination not confirmed')
            if not kernel.CloseHandle(process.process):
                cleanup_errors.append('CloseHandle(process)')
        if process.thread and not kernel.CloseHandle(process.thread):
            cleanup_errors.append('CloseHandle(thread)')
        if descendant:
            if kernel.WaitForSingleObject(descendant, 0) != 0 and details['descendant_in_job']:
                # Only terminate the exact handle whose membership was verified.
                kernel.TerminateProcess(descendant, 1)
            details['descendant_cleanup_confirmed'] = kernel.WaitForSingleObject(descendant, 5000) == 0
            if not details['descendant_cleanup_confirmed']:
                cleanup_errors.append('descendant termination not confirmed')
            if not kernel.CloseHandle(descendant):
                cleanup_errors.append('CloseHandle(descendant)')
        if temporary is not None:
            try:
                temporary.cleanup()
            except OSError:
                cleanup_errors.append('temporary directory cleanup')
    if cleanup_errors:
        status = 'fail'
        summary = 'Job lifecycle cleanup failed; inspect cleanup evidence.'
        details['cleanup_errors'] = cleanup_errors
    return Observation('windows.job_lifecycle', status, summary, details)


def probe():
    observations = []
    if sys.platform != 'win32':
        observations.append(Observation('windows.job_lifecycle', 'unavailable',
                                        'Native Windows is required; WSL is not native Windows.'))
    else:
        observations.append(_job_lifecycle())
    for boundary, summary in (
        ('filesystem', 'No ACL or filesystem isolation is installed or tested.'),
        ('token', 'Child uses the current identity; restricted tokens are not tested.'),
        ('network', 'No network deny policy is installed or tested.'),
        ('ipc', 'No host IPC isolation is installed or tested.'),
        ('descendants', 'Only one fixed CreateProcess descendant is tested; general containment, '
                        'host-agent escape and supervisor crash remain unverified.'),
    ):
        observations.append(Observation('windows.' + boundary, 'unverified', summary))
    return observations
