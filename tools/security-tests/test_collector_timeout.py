"""R1: original 60s timeout, real suspended descendant, independent exit handle.

Adapted from the architect's review_timeout_repro.py. Only the fixed security
test command is substituted; neither the M0 source nor its failure test changes.
The review guard always reaps its exact child handle, even against the old bug.
"""
import argparse
import contextlib
import ctypes
from ctypes import wintypes
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent


def kernel_api():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "GetCurrentProcess": ([], wintypes.HANDLE),
        "OpenProcess": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        "DuplicateHandle": ([wintypes.HANDLE, wintypes.HANDLE, wintypes.HANDLE,
                             ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD,
                             wintypes.BOOL, wintypes.DWORD], wintypes.BOOL),
        "WaitForSingleObject": ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        "TerminateProcess": ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
        "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
    }
    for name, (arguments, result) in signatures.items():
        getattr(kernel, name).argtypes = arguments
        getattr(kernel, name).restype = result
    return kernel


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def delayed_fixed_probe():
    target = load_module("original_review_tests", ROOT / "test_m0_review.py")
    kernel = kernel_api()
    duplicate = kernel.DuplicateHandle
    reviewer = kernel.OpenProcess(0x0040, False, int(os.environ["REVIEW_GUARD_PID"]))
    if not reviewer:
        raise ctypes.WinError(ctypes.get_last_error())

    def delay_duplicate(host, process, destination, retained, access, inherit, flags):
        succeeded = duplicate(host, process, destination, retained, access, inherit, flags)
        if not succeeded:
            return succeeded
        independent = wintypes.HANDLE()
        if not duplicate(kernel.GetCurrentProcess(), process, reviewer,
                         ctypes.byref(independent), 0, False, 2):
            raise ctypes.WinError(ctypes.get_last_error())
        Path(os.environ["REVIEW_GUARD_MARKER"]).write_text(str(independent.value), encoding="ascii")
        print("R1: paused with real suspended descendant before experimental Job assignment", flush=True)
        print("R1: stderr preserved across timeout", file=sys.stderr, flush=True)
        time.sleep(63)  # Original deadline stays 60; no reliance on this finally.
        return succeeded

    kernel.DuplicateHandle = delay_duplicate
    try:
        with patch.object(target.windows.ctypes, "WinDLL", return_value=kernel):
            test = target.WindowsInitializationFailures(
                "test_assignment_failure_never_resumes_and_reaps_exact_process")
            outcome = target.unittest.TestResult()
            test.run(outcome)
            if not outcome.wasSuccessful():
                raise AssertionError(outcome.errors + outcome.failures)
    finally:
        kernel.CloseHandle(reviewer)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("this regression requires native Windows")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    collector = load_module("collector_under_test", ROOT / "collect_review.py")
    kernel = kernel_api()
    # Compatibility with 70466f5 permits the same assertion to demonstrate red.
    owner = collector if hasattr(collector, "run_bounded") else collector.subprocess
    attribute = "run_bounded" if owner is collector else "run"
    original = getattr(owner, attribute)
    result = {"fault": "pause after DuplicateHandle before experimental Job assignment",
              "timeout_seconds": 60, "python": platform.python_version(),
              "platform": platform.platform(), "production_ready": False,
              "guard_emergency_termination": False, "collector_returncode": None,
              "collector_exception": None}
    with tempfile.TemporaryDirectory(prefix="r1-guard-", dir=str(output)) as temporary:
        marker = Path(temporary) / "exact-handle"

        def run_with_fault(command, **kwargs):
            if str(command[-1]).endswith("test_m0_review.py"):
                assert kwargs["timeout"] == 60
                env = dict(kwargs["env"])
                env.update(REVIEW_GUARD_PID=str(os.getpid()), REVIEW_GUARD_MARKER=str(marker))
                kwargs["env"] = env
                command = [sys.executable, "-I", "-S", str(Path(__file__).resolve()),
                           "--delayed-fixed-probe"]
            return original(command, **kwargs)

        retained = None
        started = time.monotonic()
        try:
            with patch.object(sys, "argv", [str(ROOT / "collect_review.py"), "--source",
                                           str(args.source.resolve()), "--output-dir",
                                           str(output / "collector")]), \
                    patch.object(owner, attribute, side_effect=run_with_fault), \
                    contextlib.redirect_stdout(io.StringIO()):
                try:
                    result["collector_returncode"] = collector.main()
                except Exception as error:
                    result["collector_exception"] = type(error).__name__
            result["elapsed_seconds"] = round(time.monotonic() - started, 3)
            if not marker.exists():
                raise AssertionError("fault never reached a real suspended descendant")
            retained = int(marker.read_text(encoding="ascii"))
            result["child_exit_confirmed_before_guard"] = kernel.WaitForSingleObject(retained, 0) == 0
            summary_path = output / "collector" / "summary.json"
            result["summary_written"] = summary_path.exists()
            if summary_path.exists():
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                security = next(run for run in summary["runs"] if run["name"] == "security-tests")
                result["collector_recorded_timeout"] = security.get("timed_out") is True
                result["collector_confirmed_cleanup"] = security.get("cleanup", {}).get("complete") is True
                cleanup = security.get("cleanup", {})
                handles = cleanup.get("process_handles", [])
                result["collector_waited_exact_descendant_handles"] = (
                    len(handles) >= 2 and all(item["exit_confirmed"] for item in handles)
                    and cleanup.get("active_after_cleanup") == 0)
                result["outer_guard_before_python_started"] = (
                    cleanup.get("configured_before_create") is True
                    and cleanup.get("assigned_before_resume") is True)
                result["original_60s_deadline_observed"] = security.get("elapsed_seconds", 0) >= 59.9
                result["temporary_fixture_removed"] = summary["temporary_fixture_removed"]
                result["probe_skipped_after_timeout"] = not any(r["name"] == "probe" for r in summary["runs"])
                result["stdout_preserved"] = "real suspended descendant" in (
                    output / "collector/security-tests.stdout.txt").read_text(encoding="utf-8")
                result["stderr_preserved"] = "stderr preserved" in (
                    output / "collector/security-tests.stderr.txt").read_text(encoding="utf-8")
        finally:
            if retained is None and marker.exists():
                retained = int(marker.read_text(encoding="ascii"))
            if retained:
                try:
                    if kernel.WaitForSingleObject(retained, 0) != 0:
                        result["guard_emergency_termination"] = True
                        kernel.TerminateProcess(retained, 1)
                    result["guard_confirmed_child_exit"] = kernel.WaitForSingleObject(retained, 5000) == 0
                    if not result["guard_confirmed_child_exit"]:
                        raise RuntimeError("review guard could not confirm exit")
                finally:
                    kernel.CloseHandle(retained)
    result["guard_fixture_removed"] = not Path(temporary).exists()
    required = ("child_exit_confirmed_before_guard", "summary_written", "collector_recorded_timeout",
                "collector_confirmed_cleanup", "temporary_fixture_removed", "probe_skipped_after_timeout",
                "stdout_preserved", "stderr_preserved", "guard_confirmed_child_exit", "guard_fixture_removed",
                "collector_waited_exact_descendant_handles", "outer_guard_before_python_started",
                "original_60s_deadline_observed")
    passed = (all(result.get(key) is True for key in required)
              and result["collector_returncode"] == 1 and result["collector_exception"] is None
              and not result["guard_emergency_termination"])
    result["regression_passed"] = passed
    (output / "regression.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    if sys.argv[1:] == ["--delayed-fixed-probe"]:
        delayed_fixed_probe()
    else:
        raise SystemExit(main())
