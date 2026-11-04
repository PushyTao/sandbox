"""Collect bounded, fixed M0 review evidence for a trusted source snapshot."""

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    tests = Path(__file__).resolve().parent
    files = sorted((source / "tools" / "m0").rglob("*.py"))
    evidence = {
        "platform": platform.platform(), "machine": platform.machine(),
        "python": platform.python_version(), "sys_platform": sys.platform,
        "euid": os.geteuid() if hasattr(os, "geteuid") else None,
        "production_ready": False,
        "source_sha256": {p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in files},
        "runs": [],
    }
    # Linux fixtures use /tmp rather than the Windows source mount. On Windows,
    # keep temp writes under this task's evidence directory. No host data is used.
    scratch_parent = "/tmp" if sys.platform == "linux" else str(output)
    evidence["scratch_location"] = "/tmp" if sys.platform == "linux" else "<evidence>"
    with tempfile.TemporaryDirectory(prefix="push4-run-", dir=scratch_parent) as temporary:
        env = dict(os.environ)
        env.update({"TEMP": temporary, "TMP": temporary, "TMPDIR": temporary,
                    "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8",
                    "SBX_REVIEW_M0_ROOT": str(source / "tools" / "m0")})
        if sys.platform == "linux":
            env["SBX_M0_INTEGRATION"] = "1"
        else:
            env.pop("SBX_M0_INTEGRATION", None)
        commands = [
            ("baseline-tests", [sys.executable, "-m", "unittest", "discover", "-s", "tools/m0/tests", "-v"], source),
            ("security-tests", [sys.executable, "-B", str(tests / "test_m0_review.py")], source),
            ("probe", [sys.executable, "-m", "sandbox_probe"], source / "tools" / "m0"),
        ]
        for label, command, cwd in commands:
            result = subprocess.run(command, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
                                    capture_output=True, timeout=60)
            stdout = result.stdout.decode("utf-8", errors="replace").replace("\r\n", "\n")
            stderr = result.stderr.decode("utf-8", errors="replace").replace("\r\n", "\n")
            # Keep evidence portable and remove local user/workspace paths.
            for original, replacement in ((str(tests), "<security-tests>"),
                                          (str(source), "<review-source>"),
                                          (str(output), "<evidence>")):
                stdout, stderr = stdout.replace(original, replacement), stderr.replace(original, replacement)
            (output / (label + ".stdout.txt")).write_bytes(stdout.encode("utf-8"))
            (output / (label + ".stderr.txt")).write_bytes(stderr.encode("utf-8"))
            entry = {"name": label, "exit_code": result.returncode}
            if label == "probe":
                report = json.loads(stdout)
                entry["observations"] = dict(Counter(item["status"] for item in report["observations"]))
                entry["production_ready"] = report["production_ready"]
            evidence["runs"].append(entry)
    evidence["temporary_fixture_removed"] = not Path(temporary).exists()
    (output / "summary.json").write_bytes((json.dumps(evidence, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    print(json.dumps(evidence, indent=2, sort_keys=True))
    # Probe exit 1/2 is meaningful research evidence, never rewritten as a pass.
    return 1 if any(run["exit_code"] for run in evidence["runs"] if run["name"] != "probe") else 0


if __name__ == "__main__":
    raise SystemExit(main())
