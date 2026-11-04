"""Inject one Windows API failure per case; observe real native child cleanup.

Only fixed c19b235 probes run. No host policy or runtime implementation changes.
This is mixed fault injection/native testing, not an end-to-end sandbox test.
"""

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
from unittest.mock import Mock, patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Requires native Windows")
    source = args.source.resolve()
    baseline = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(source)).decode().strip()
    if baseline != "c19b23585d64d20869adb9654cfbc1f013584d40":
        parser.error("Requires unchanged c19b235 source")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=str(source)).strip():
        parser.error("Source checkout must be clean")
    if args.output.exists():
        parser.error("Refusing to overwrite evidence")
    sys.path.insert(0, str(source / "tools/m0"))
    from sandbox_probe import windows

    args.output.parent.mkdir(parents=True, exist_ok=True)
    checks = []
    # Verify reported native PID disappearance independently of probe booleans.
    observer = ctypes.WinDLL("kernel32", use_last_error=True)
    observer.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    observer.OpenProcess.restype = wintypes.HANDLE
    observer.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    observer.WaitForSingleObject.restype = wintypes.DWORD
    observer.CloseHandle.argtypes = [wintypes.HANDLE]
    observer.CloseHandle.restype = wintypes.BOOL

    with tempfile.TemporaryDirectory(prefix="qa-job-", dir=str(args.output.parent)) as scratch:
        with patch.object(tempfile, "tempdir", scratch):
            for operation, failure in (("CreateProcessW", 0),
                                       ("AssignProcessToJobObject", 0),
                                       ("ResumeThread", 0xFFFFFFFF)):
                kernel = ctypes.WinDLL("kernel32", use_last_error=True)

                def deny(*unused, value=failure):
                    ctypes.set_last_error(5)
                    return value

                setattr(kernel, operation, Mock(side_effect=deny))
                with patch.object(windows.ctypes, "WinDLL", return_value=kernel):
                    observation = windows._job_lifecycle()
                pid = observation.details.get("pid")
                independently_gone = None
                last_error = None
                if pid:
                    handle = observer.OpenProcess(0x100000, False, pid)
                    if handle:
                        try:
                            independently_gone = observer.WaitForSingleObject(handle, 0) == 0
                        finally:
                            if not observer.CloseHandle(handle):
                                raise RuntimeError("Observer handle close failed")
                    else:
                        last_error = ctypes.get_last_error()
                        independently_gone = last_error == 87
                expected = "unavailable" if operation == "CreateProcessW" else "fail"
                correct = (observation.status == expected and
                           "cleanup_errors" not in observation.details and
                           (pid is None or independently_gone is True))
                checks.append(dict(operation=operation, injected_error=5, expected=expected,
                                   observation=observation.to_dict(), pid_gone=independently_gone,
                                   open_process_error=last_error, assertion_passed=correct))
            remnants = [p.name for p in Path(scratch).iterdir()]
    result = dict(baseline=baseline, utc=datetime.now(timezone.utc).isoformat(),
                  python=platform.python_version(), platform=platform.platform(),
                  command=sys.argv, checks=checks, scratch_remnants=remnants,
                  scratch_root_removed=not Path(scratch).exists(),
                  testing_level="mock one API operation; real process/Job/cleanup/observer")
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if all(c["assertion_passed"] for c in checks) and not remnants else 1


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
