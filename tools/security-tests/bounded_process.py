"""Lifecycle guard for trusted fixed review commands, not a sandbox backend.

Windows requires CPython's _winapi CreateProcess binding (tested on 3.8.5)
so the primary thread handle remains available until Job assignment succeeds.
Only stdin/stdout/stderr are inherited; the controlling Job handle is not.
"""
import ctypes
from ctypes import wintypes
import os
import subprocess
import sys
import tempfile
import time


class BasicLimits(ctypes.Structure):
    _fields_ = [("ProcessTime", ctypes.c_int64), ("JobTime", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD), ("MinWorkingSet", ctypes.c_size_t),
                ("MaxWorkingSet", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD)]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [("Basic", BasicLimits), ("IoCounters", ctypes.c_uint64 * 6),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


def _kernel():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "CreateJobObjectW": ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
        "SetInformationJobObject": ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                     wintypes.DWORD], wintypes.BOOL),
        "QueryInformationJobObject": ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                       wintypes.DWORD, ctypes.c_void_p], wintypes.BOOL),
        "AssignProcessToJobObject": ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
        "IsProcessInJob": ([wintypes.HANDLE, wintypes.HANDLE,
                            ctypes.POINTER(wintypes.BOOL)], wintypes.BOOL),
        "OpenProcess": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        "ResumeThread": ([wintypes.HANDLE], wintypes.DWORD),
        "WaitForSingleObject": ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        "TerminateJobObject": ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
        "TerminateProcess": ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
        "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
    }
    for name, (arguments, result) in signatures.items():
        getattr(kernel, name).argtypes = arguments
        getattr(kernel, name).restype = result
    return kernel


def _check(value, operation):
    if not value:
        raise OSError(ctypes.get_last_error(), operation)
    return value


def _members(kernel, job):
    # Includes nested-job members. Never act on these PIDs without opening and
    # verifying the handle's membership; a PID alone is not an identity.
    capacity = 64
    while capacity <= 65536:
        class ProcessList(ctypes.Structure):
            _fields_ = [("assigned", wintypes.DWORD), ("count", wintypes.DWORD),
                        ("pids", ctypes.c_size_t * capacity)]
        listing = ProcessList()
        ok = kernel.QueryInformationJobObject(job, 3, ctypes.byref(listing), ctypes.sizeof(listing), None)
        if ok and listing.count >= listing.assigned:
            return list(listing.pids[:listing.count])
        if not ok and ctypes.get_last_error() != 234:  # ERROR_MORE_DATA
            _check(ok, "QueryInformationJobObject")
        capacity *= 2
    raise OSError("Job membership exceeded fixed review guard capacity")


def _run_windows(command, cwd, env, timeout):
    import _winapi
    import msvcrt

    kernel = _kernel()
    cleanup = {"scope": "outer-windows-job", "configured_before_create": False,
               "assigned_before_resume": False, "process_handles": [], "errors": []}
    result = {"exit_code": None, "timed_out": False, "timeout_seconds": timeout,
              "error": None, "cleanup": cleanup}
    errors = cleanup["errors"]
    job = process = thread = None
    retained = []
    assigned = False
    started = time.monotonic()
    with open(os.devnull, "rb") as stdin, \
            tempfile.TemporaryFile(dir=env["TEMP"]) as stdout, \
            tempfile.TemporaryFile(dir=env["TEMP"]) as stderr:
        try:
            job = _check(kernel.CreateJobObjectW(None, None), "CreateJobObjectW")
            limits = ExtendedLimits()
            limits.Basic.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE; neither breakaway flag.
            _check(kernel.SetInformationJobObject(job, 9, ctypes.byref(limits),
                                                 ctypes.sizeof(limits)), "SetInformationJobObject")
            cleanup["configured_before_create"] = True
            startup = subprocess.STARTUPINFO()
            startup.dwFlags = subprocess.STARTF_USESTDHANDLES
            handles = [msvcrt.get_osfhandle(stream.fileno()) for stream in (stdin, stdout, stderr)]
            startup.hStdInput, startup.hStdOutput, startup.hStdError = handles
            startup.lpAttributeList = {"handle_list": handles}
            try:
                for handle in handles:
                    os.set_handle_inheritable(handle, True)
                process, thread, pid, _ = _winapi.CreateProcess(
                    command[0], subprocess.list2cmdline(command), None, None, True,
                    0x4 | 0x08000000, env, str(cwd), startup)  # SUSPENDED | NO_WINDOW
                retained.append((pid, process))
            finally:
                for handle in handles:
                    os.set_handle_inheritable(handle, False)
            _check(kernel.AssignProcessToJobObject(job, process), "AssignProcessToJobObject")
            assigned = True
            cleanup["assigned_before_resume"] = True
            if kernel.ResumeThread(thread) == 0xFFFFFFFF:
                raise OSError(ctypes.get_last_error(), "ResumeThread")
            wait = kernel.WaitForSingleObject(process, max(0, int((timeout - (time.monotonic() - started)) * 1000)))
            if wait == 258:
                result["timed_out"] = True
            elif wait != 0:
                raise OSError(ctypes.get_last_error(), "WaitForSingleObject(root)")
            else:
                result["exit_code"] = _winapi.GetExitCodeProcess(process)
        except Exception as error:
            result["error"] = {"type": type(error).__name__, "code": getattr(error, "errno", None)}
        finally:
            # This supervisor is outside the new Job and survives the test's death.
            # Pin current descendants BEFORE termination, including suspended ones.
            if job:
                try:
                    members = _members(kernel, job)
                    cleanup["active_before_cleanup"] = len(members)
                    for pid in members:
                        if any(pid == known for known, _ in retained):
                            continue
                        handle = _check(kernel.OpenProcess(0x100000 | 0x1000, False, pid), "OpenProcess(member)")
                        member = wintypes.BOOL()
                        try:
                            _check(kernel.IsProcessInJob(handle, job, ctypes.byref(member)), "IsProcessInJob")
                            if not member.value:
                                raise OSError("member changed before handle acquisition")
                        except Exception:
                            kernel.CloseHandle(handle)
                            raise
                        retained.append((pid, handle))
                except Exception as error:
                    errors.append("pin-members: {}".format(type(error).__name__))
                if not kernel.TerminateJobObject(job, 1):
                    errors.append("TerminateJobObject")
                    # Closing our non-inherited handle is an independent fallback.
                    if not kernel.CloseHandle(job):
                        errors.append("CloseHandle(job fallback)")
                    job = None
            if process and not assigned:
                # Even failed outer assignment never resumes Python. Reap its
                # exact CreateProcess handle; it is not yet owned by the Job.
                kernel.TerminateProcess(process, 1)
            deadline = time.monotonic() + 5
            for pid, handle in retained:
                exited = kernel.WaitForSingleObject(handle, max(0, int((deadline - time.monotonic()) * 1000))) == 0
                cleanup["process_handles"].append({"pid": pid, "exit_confirmed": exited})
                if not exited:
                    errors.append("process exit not confirmed: {}".format(pid))
            if job:
                try:
                    active = _members(kernel, job)
                    while active and time.monotonic() < deadline:
                        time.sleep(0.01)
                        active = _members(kernel, job)
                    cleanup["active_after_cleanup"] = len(active)
                    if active:
                        errors.append("Job still has active processes")
                except Exception as error:
                    errors.append("query-cleanup: {}".format(type(error).__name__))
            if process and all(item["exit_confirmed"] for item in cleanup["process_handles"]):
                result["exit_code"] = _winapi.GetExitCodeProcess(process)
            for _, handle in retained:
                if not kernel.CloseHandle(handle):
                    errors.append("CloseHandle(process)")
            for label, handle in (("thread", thread), ("job", job)):
                if handle and not kernel.CloseHandle(handle):
                    errors.append("CloseHandle({})".format(label))
            cleanup["complete"] = not errors
        stdout.seek(0)
        stderr.seek(0)
        result["stdout"], result["stderr"] = stdout.read(), stderr.read()
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return result


def run_bounded(command, *, cwd, env, timeout):
    if sys.platform == "win32":
        return _run_windows(command, cwd, env, timeout)
    # Linux's existing fixed M0 probes own their process-tree experiments. This
    # direct-child timeout does NOT claim to prove descendant cleanup on Linux.
    started = time.monotonic()
    try:
        child = subprocess.run(command, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
                               capture_output=True, timeout=timeout)
        result = {"exit_code": child.returncode, "stdout": child.stdout, "stderr": child.stderr,
                  "timed_out": False, "error": None,
                  "cleanup": {"scope": "direct-child-only", "complete": True,
                              "descendant_cleanup_verified": False}}
    except subprocess.TimeoutExpired as error:
        result = {"exit_code": None, "stdout": error.output or b"", "stderr": error.stderr or b"",
                  "timed_out": True, "error": {"type": "TimeoutExpired"},
                  "cleanup": {"scope": "direct-child-only", "complete": False,
                              "descendant_cleanup_verified": False}}
    result.update(timeout_seconds=timeout, elapsed_seconds=round(time.monotonic() - started, 3))
    return result
