"""One-run evidence collector; invokes only the project's fixed test commands."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

repo = Path(__file__).resolve().parents[2]
out = repo / 'docs/validation/runtime-evidence-2026-11-05'
out.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(repo / 'tools/security-tests'))
from bounded_process import run_bounded

def capture(label, python, source, args, expected, cwd=None):
    result = run_bounded([python] + args, cwd=cwd or source,
                         env=os.environ.copy(), timeout=60)
    for stream in ('stdout', 'stderr'):
        data = result.pop(stream).decode('utf-8', errors='replace').replace('\r\n', '\n')
        for path, name in ((str(source), '<source>'), (str(repo.parent), '<workspace>')):
            data = data.replace(path, name)
        (out / (label + '.' + stream + '.txt')).write_bytes(data.encode('utf-8'))
    result['command'] = ['python'] + args
    result['expected_exit_code'] = expected
    (out / (label + '.json')).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(label, result['exit_code'], result['cleanup'], flush=True)
    assert result['exit_code'] == expected, result
    assert result['cleanup']['complete'] and not result['timed_out'], result

baseline_sha = 'c19b23585d64d20869adb9654cfbc1f013584d40'
archive = subprocess.check_output(['git', 'archive', '--format=zip', baseline_sha, 'tools/m0'], cwd=repo)
with tempfile.TemporaryDirectory(prefix='runtime-baseline-', dir=str(repo.parent)) as name:
    baseline = Path(name)
    with zipfile.ZipFile(io.BytesIO(archive)) as files:
        files.extractall(baseline)
    capture('baseline-py38', sys.executable, baseline,
            ['-m', 'unittest', 'discover', '-s', 'tools/m0/tests', '-v'], 0)
    capture('baseline-probe-py38', sys.executable, baseline,
            ['-m', 'sandbox_probe'], 2, baseline / 'tools/m0')
    (baseline / 'tools/m0/tests/test_windows.py').write_bytes(
        (repo / 'tools/m0/tests/test_windows.py').read_bytes())
    capture('red-baseline-new-tests', sys.executable, baseline,
            ['-m', 'unittest', 'discover', '-s', 'tools/m0/tests', '-p', 'test_windows.py', '-v'], 1)

py312 = subprocess.check_output(['py', '-3.12', '-c', 'import sys;print(sys.executable)'], text=True).strip()
for label, python in (('py38', sys.executable), ('py312', py312)):
    capture('final-suite-' + label, python, repo,
            ['-m', 'unittest', 'discover', '-s', 'tools/m0/tests', '-v'], 0)
    capture('final-probe-' + label, python, repo,
            ['-m', 'sandbox_probe'], 2, repo / 'tools/m0')
capture('security-regression-py312', py312, repo,
        ['-m', 'unittest', 'discover', '-s', 'tools/security-tests', '-p', 'test_m0_review.py', '-v'], 0)
