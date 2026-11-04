"""Capture fixed M0 commands; success means evidence saved, not sandbox approval.

Uses the selected Python interpreter and an unchanged source checkout. Does not
install dependencies, change host security, or execute user supplied workloads.
"""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time


BASELINE = "c19b23585d64d20869adb9654cfbc1f013584d40"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    scratch = output / "scratch"
    scratch.mkdir()
    env = os.environ.copy()
    env.update(TMP=str(scratch), TEMP=str(scratch), TMPDIR=str(scratch),
               PYTHONDONTWRITEBYTECODE="1")
    env.pop("SBX_M0_INTEGRATION", None)
    commands = []

    def run(label, command, cwd, overrides=None, timeout=90):
        started = datetime.now(timezone.utc).isoformat()
        before = time.monotonic()
        result = subprocess.run(command, cwd=str(cwd), env=dict(env, **(overrides or {})),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=timeout)
        (output / (label + ".stdout.txt")).write_bytes(result.stdout)
        (output / (label + ".stderr.txt")).write_bytes(result.stderr)
        entry = dict(label=label, argv=command, cwd=str(cwd), started_utc=started,
                     duration_seconds=round(time.monotonic() - before, 3),
                     exit_code=result.returncode, env_overrides=overrides or {})
        commands.append(entry)
        return result

    revision = run("revision", ["git", "rev-parse", "HEAD"], source)
    if revision.returncode or revision.stdout.decode().strip() != BASELINE:
        raise SystemExit("Source is not the requested baseline: " + BASELINE)
    clean = run("source-status-before", ["git", "status", "--porcelain"], source)
    if clean.returncode or clean.stdout.strip():
        raise SystemExit("Source checkout must be clean")
    if sys.platform == "linux":
        run("os-release", ["cat", "/etc/os-release"], source)
        run("identity", ["id"], source)
        if Path("/usr/bin/bwrap").is_file():
            run("bwrap-version", ["/usr/bin/bwrap", "--version"], source)
    suite = [sys.executable, "-m", "unittest", "discover", "-s", "tools/m0/tests", "-v"]
    run("unit-default", suite, source)
    if sys.platform == "linux":
        run("unit-integration", suite, source, {"SBX_M0_INTEGRATION": "1"})
    report_path = output / "probe.json"
    run("probe", [sys.executable, "-m", "sandbox_probe", "--output", str(report_path)],
        source / "tools/m0")
    run("source-status-after", ["git", "status", "--porcelain"], source)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    files = sorted((source / "tools/m0").rglob("*.py"))
    metadata = dict(
        baseline=BASELINE, captured_utc=datetime.now(timezone.utc).isoformat(),
        system=platform.system(), release=platform.release(), version=platform.version(),
        machine=platform.machine(), python=platform.python_version(), executable=sys.executable,
        wsl="microsoft" in (platform.release() + platform.version()).lower(),
        scoped_temp=str(scratch), source=str(source),
        observation_counts=dict(Counter(o["status"] for o in report["observations"])),
        production_ready=report["production_ready"],
        remaining_scratch_entries=[str(p.relative_to(scratch)) for p in scratch.rglob("*")],
        source_sha256={str(p.relative_to(source)).replace("\\", "/"):
                       hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        commands=commands)
    (output / "capture.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "commands": commands,
                      "observations": metadata["observation_counts"],
                      "remaining_scratch_entries": metadata["remaining_scratch_entries"]}, indent=2))


if __name__ == "__main__":
    main()
