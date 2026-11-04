"""Regression controls for the QA fixture, not product compatibility tests.

Run with --source <clean c19b235 checkout> --output <new directory>.
With --case, run one control and propagate the audit's exit code unchanged.
Without --case, verify all control exit codes and retain their raw reports.
"""

import argparse
import ctypes
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import subprocess
import sys
from unittest.mock import Mock, patch

import audit_windows_failures as audit


# Literal expectations derived from the three API failure stages.
MUTATIONS = {
    "wrong-operation": ("ResumeThread", "error", {"operation": "OtherAPI", "code": 5}),
    "wrong-code": ("ResumeThread", "error", {"operation": "ResumeThread", "code": 6}),
    "assign-missing-pid": ("AssignProcessToJobObject", "pid", None),
    "resume-missing-pid": ("ResumeThread", "pid", None),
    "resume-invalid-pid": ("ResumeThread", "pid", 0),
    "assign-wrong-stage": ("AssignProcessToJobObject", "assigned_before_resume", True),
    "resume-wrong-stage": ("ResumeThread", "assigned_before_resume", False),
    "resume-missing-stage": ("ResumeThread", "assigned_before_resume", None),
    "cleanup-error": ("ResumeThread", "cleanup_errors", ["synthetic cleanup error"]),
}
CASES = ("normal", "early-assign") + tuple(MUTATIONS)


def run_case(args):
    sys.path.insert(0, str(args.source.resolve() / "tools/m0"))
    from sandbox_probe import windows

    real_dll = ctypes.WinDLL
    real_lifecycle = windows._job_lifecycle
    kernels = []

    def deny_assign(*unused):
        ctypes.set_last_error(5)
        return 0

    def kernel_factory(*positional, **keywords):
        kernel = real_dll(*positional, **keywords)
        kernels.append(kernel)
        # The audit constructs its observer, then one kernel per fixed case.
        if args.case == "early-assign" and len(kernels) == 4:
            kernel.AssignProcessToJobObject = Mock(side_effect=deny_assign)
        return kernel

    def lifecycle():
        observation = real_lifecycle()
        # Alter only the returned evidence AFTER real native cleanup.
        # These controls test rejection of incomplete/inconsistent evidence.
        if args.case in MUTATIONS:
            operation, field, value = MUTATIONS[args.case]
            if observation.details.get("error", {}).get("operation") == operation:
                if value is None:
                    observation.details.pop(field, None)
                else:
                    observation.details[field] = value
        return observation

    argv = [str(Path(audit.__file__).resolve()), "--source", str(args.source.resolve()),
            "--output", str(args.output.resolve())]
    with patch.object(sys, "argv", argv), \
            patch.object(ctypes, "WinDLL", side_effect=kernel_factory), \
            patch.object(windows, "_job_lifecycle", side_effect=lifecycle):
        code = audit.main()
    # Ensure the early-failure control itself actually reached the intended setup.
    if args.case == "early-assign":
        if (len(kernels) != 4 or kernels[3].AssignProcessToJobObject.call_count != 1
                or kernels[3].ResumeThread.call_count != 0):
            raise RuntimeError("Early-assignment control did not exercise its intended path")
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", choices=CASES)
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Requires native Windows")
    # Validate before importing any code from the requested source checkout.
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(args.source))
    clean = subprocess.check_output(["git", "status", "--porcelain"], cwd=str(args.source))
    if revision.decode().strip() != "c19b23585d64d20869adb9654cfbc1f013584d40" or clean.strip():
        parser.error("Requires clean c19b235 source")
    if args.case:
        return run_case(args)

    args.output.mkdir(parents=True, exist_ok=False)
    results = []
    for name in CASES:
        output = args.output / (name + ".json")
        command = [sys.executable, "-B", str(Path(__file__).resolve()), "--source",
                   str(args.source.resolve()), "--output", str(output.resolve()),
                   "--case", name]
        started = datetime.now(timezone.utc).isoformat()
        # Do not kill the audit supervisor on an outer timeout: it may own a
        # suspended child that still needs its native finally cleanup.
        child = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (args.output / (name + ".stdout.txt")).write_bytes(child.stdout)
        (args.output / (name + ".stderr.txt")).write_bytes(child.stderr)
        report = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}
        checks = report.get("checks", [])
        wanted = [True, True, True] if name == "normal" else [True, True, False]
        if name.startswith("assign-"):
            wanted = [True, False, True]
        expected_exit = 0 if name == "normal" else 1
        actual = [c["assertion_passed"] for c in checks]
        passed = (child.returncode == expected_exit and actual == wanted
                  and report.get("scratch_remnants") == []
                  and report.get("scratch_root_removed") is True)
        if name == "early-assign" and len(checks) == 3:
            details = checks[2]["observation"]["details"]
            passed = (passed and details.get("error") == {
                "operation": "AssignProcessToJobObject", "code": 5}
                and checks[2].get("pid_gone") is True)
        results.append(dict(case=name, argv=command, cwd=str(Path.cwd()),
                            started_utc=started, exit_code=child.returncode,
                            expected_exit_code=expected_exit, assertion_passed=actual,
                            expected_assertion_passed=wanted, regression_passed=passed))
    summary = dict(python=platform.python_version(), platform=platform.platform(),
                   machine=platform.machine(), command=sys.argv, results=results,
                   testing_level="QA regression controls with native fixed probe cleanup; "
                                 "returned metadata mutated in named negative cases")
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n",
                                              encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if all(r["regression_passed"] for r in results) else 1


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
