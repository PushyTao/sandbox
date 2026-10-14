"""Fixed, synthetic bubblewrap experiments. This is NOT a sandbox backend.

The deliberately incomplete mount plan exposes counterexamples that must block
production use. It never accepts a user command, config, or workspace to run.
"""

import json
import os
from pathlib import Path
import selectors
import socket
import stat
import subprocess
import sys
import tempfile
import time
import uuid

from .report import Observation


def _trusted_bwrap():
    """Do not execute a workspace-controlled PATH candidate."""
    candidate = Path("/usr/bin/bwrap")
    try:
        resolved = candidate.resolve(strict=True)
        for path in (resolved,) + tuple(resolved.parents):
            metadata = path.stat()
            if metadata.st_uid != 0 or metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                return None
        if not resolved.is_file() or not os.access(str(resolved), os.X_OK):
            return None
    except OSError:
        return None
    return str(resolved)


def _plan(bwrap, workspace):
    # /usr is intentionally broad for this disposable experiment. It is NOT
    # the design's reviewed host-toolchain-v1 runtime profile.
    args = [bwrap, "--unshare-user", "--unshare-pid", "--unshare-net",
            "--unshare-ipc", "--unshare-uts", "--new-session", "--die-with-parent",
            "--cap-drop", "ALL", "--clearenv", "--ro-bind", "/usr", "/usr"]
    for entry in ("/bin", "/sbin", "/lib", "/lib64"):
        if os.path.islink(entry):
            args += ["--symlink", os.readlink(entry), entry]
        elif os.path.isdir(entry):
            args += ["--ro-bind", entry, entry]
    args += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
             "--tmpfs", "/home", "--dir", "/home/probe",
             "--setenv", "HOME", "/home/probe", "--setenv", "PATH", "/usr/bin:/bin",
             "--setenv", "LANG", "C.UTF-8", "--bind", str(workspace), "/workspace",
             "--chdir", "/workspace"]
    return args


def _run(plan, script, data=None):
    # Only constant, local probe scripts reach this function. No shell and no
    # inherited stdin/FDs; these scripts emit at most a small JSON dictionary.
    command = plan + ["--", "/usr/bin/python3", "-I", "-c", script]
    if data is not None:
        command.append(json.dumps(data))
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               close_fds=True, env={"PATH": "/usr/bin:/bin",
                               "SBX_M0_SYNTHETIC_SECRET": "synthetic-only"})
    output = bytearray()
    total_bytes = 0
    deadline = time.monotonic() + 8
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, "stdout")
            selector.register(process.stderr, selectors.EVENT_READ, "stderr")
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, 8)
                for key, _ in selector.select(min(remaining, .1)):
                    chunk = os.read(key.fd, 4096)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    total_bytes += len(chunk)
                    if total_bytes > 16384:
                        raise RuntimeError("fixed probe produced oversized output")
                    if key.data == "stdout":
                        output.extend(chunk)
        returncode = process.wait(timeout=max(.01, deadline - time.monotonic()))
        if returncode != 0:
            # Do not serialize arbitrary stderr or host paths in the evidence.
            raise RuntimeError("probe process exited with code {}".format(returncode))
        return json.loads(output.decode("utf-8"))
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        process.stdout.close()
        process.stderr.close()


def _check(identifier, summary, fn):
    try:
        passed, details = fn()
        return Observation(identifier, "pass" if passed else "fail", summary, details)
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        return Observation(identifier, "fail", summary,
                           {"error_type": type(error).__name__})


def _counterexample(identifier, summary, reproduced):
    return Observation(identifier, "fail" if reproduced else "unverified", summary,
                       {"bypass_reproduced": reproduced,
                        "candidate_usable_in_production": False})


_FS_SCRIPT = r'''
import json, os, pathlib
def denied(action):
    try:
        action()
        return False
    except OSError:
        return True
work = pathlib.Path('/workspace')
(work / 'ordinary').write_text('allowed')
result = {'workspace': (work / 'ordinary').read_text() == 'allowed'}
result['symlink_read_denied'] = denied(lambda: (work / 'escape').read_text())
result['symlink_write_denied'] = denied(lambda: (work / 'escape').write_text('changed'))
target = work / 'protected' / 'control'
result['protected_read'] = target.read_text() == 'synthetic control'
result['protected_write_denied'] = denied(lambda: target.write_text('changed'))
result['protected_unlink_denied'] = denied(lambda: target.unlink())
result['protected_rename_denied'] = denied(lambda: target.rename(work / 'moved'))
result['protected_parent_rename_denied'] = denied(lambda: target.parent.rename(work / 'moved-parent'))
result['private_home'] = os.environ['HOME'] == '/home/probe'
result['environment_scrubbed'] = 'SBX_M0_SYNTHETIC_SECRET' not in os.environ
pathlib.Path('/home/probe/cache').write_text('private')
pathlib.Path('/tmp/scratch').write_text('private')
print(json.dumps(result))
'''


def _filesystem(plan, workspace, synthetic_secret):
    protected = workspace / "protected"
    protected.mkdir()
    control = protected / "control"
    control.write_text("synthetic control", encoding="utf-8")
    (workspace / "escape").symlink_to(synthetic_secret)
    protected_plan = plan + ["--ro-bind", str(protected), "/workspace/protected"]
    data = _run(protected_plan, _FS_SCRIPT)
    data["synthetic_secret_unchanged"] = synthetic_secret.read_text() == "synthetic secret"
    results = [
        Observation("FS-1.workspace", "pass" if data["workspace"] else "fail",
                    "Synthetic workspace read/write", {"read_write_succeeded": data["workspace"]}),
        Observation("FS-2.symlink", "pass" if all(data[key] for key in
                    ("symlink_read_denied", "symlink_write_denied", "synthetic_secret_unchanged")) else "fail",
                    "Symlink to a synthetic file outside the mount view",
                    {key: data[key] for key in ("symlink_read_denied", "symlink_write_denied", "synthetic_secret_unchanged")}),
        Observation("FS-3.existing", "pass" if all(data[key] for key in
                    ("protected_read", "protected_write_denied", "protected_unlink_denied",
                     "protected_rename_denied", "protected_parent_rename_denied")) else "fail",
                    "Existing protected mount: read allowed, tested mutations blocked",
                    {key: value for key, value in data.items() if key.startswith("protected_")}),
        Observation("ENV.private", "pass" if data["private_home"] and data["environment_scrubbed"] else "fail",
                    "Private scratch and cleared environment (single synthetic variable)",
                    {"private_home": data["private_home"], "environment_scrubbed": data["environment_scrubbed"]}),
    ]
    os.link(str(control), str(workspace / "alias"))
    bypass = _run(protected_plan, "from pathlib import Path; import json; "
                  "Path('/workspace/alias').write_text('alias bypass'); "
                  "print(json.dumps({'changed': Path('/workspace/protected/control').read_text() == 'alias bypass'}))")
    results.append(_counterexample("FS-4.hardlink", "Read-only subtree mount does not protect a writable hardlink alias",
                                   bypass["changed"] and control.read_text() == "alias bypass"))
    future = _run(protected_plan, "from pathlib import Path; import json; "
                  "Path('/workspace/.agents').mkdir(); "
                  "Path('/workspace/.agents/config').write_text('future bypass'); "
                  "print(json.dumps({'created': Path('/workspace/.agents/config').is_file()}))")
    results.append(_counterexample("FS-4.future-name", "Mounting existing protected entries does not reserve absent names", future["created"]))
    return results


_NETWORK_SCRIPT = r'''
import json, os, socket, sys
data = json.loads(sys.argv[1])
family = getattr(socket, data['family'])
kind = getattr(socket, data['kind'])
endpoint = data['endpoint']
if family != socket.AF_UNIX:
    endpoint = tuple(endpoint)
result = {'net_namespace': os.readlink('/proc/self/ns/net')}
with socket.socket(family, kind) as client:
    client.settimeout(0.4)
    try:
        if kind == socket.SOCK_DGRAM:
            client.sendto(b'm0-packet', endpoint)
        else:
            client.connect(endpoint)
        result['operation_succeeded'] = True
    except OSError as error:
        result['operation_succeeded'] = False
        result['errno'] = error.errno
print(json.dumps(result))
'''


def _network_case(plan, family, kind, abstract=False):
    with socket.socket(family, kind) as listener:
        listener.settimeout(0.4)
        if abstract:
            address = "\0sbx-m0-" + uuid.uuid4().hex
        else:
            address = ("::1" if family == socket.AF_INET6 else "127.0.0.1", 0)
        listener.bind(address)
        # Linux getsockname() returns bytes for abstract AF_UNIX addresses;
        # keep our generated ASCII string so JSON can carry the leading NUL.
        endpoint = address if abstract else listener.getsockname()
        if kind == socket.SOCK_STREAM:
            listener.listen(2)
        with socket.socket(family, kind) as host_client:
            host_client.settimeout(0.4)
            if kind == socket.SOCK_STREAM:
                host_client.connect(endpoint)
                accepted, _ = listener.accept()
                accepted.close()
            else:
                host_client.sendto(b"positive-control", endpoint)
                if listener.recv(64) != b"positive-control":
                    raise RuntimeError("positive UDP control failed")
        data = _run(plan, _NETWORK_SCRIPT, {"family": family.name, "kind": kind.name,
                                           "endpoint": endpoint})
        data["different_net_namespace"] = data.pop("net_namespace") != os.readlink("/proc/self/ns/net")
        data["host_positive_control"] = True
        if kind == socket.SOCK_DGRAM:
            try:
                listener.recv(64)
                data["host_received_probe_packet"] = True
            except socket.timeout:
                data["host_received_probe_packet"] = False
            denied = not data["host_received_probe_packet"]
        else:
            denied = not data["operation_succeeded"]
        return denied and data["different_net_namespace"], data


def _children(pid):
    try:
        value = Path("/proc/{0}/task/{0}/children".format(pid)).read_text()
        direct = [int(item) for item in value.split()]
    except (FileNotFoundError, ProcessLookupError):
        return []
    return direct + [descendant for child in direct for descendant in _children(child)]


def _process_start(pid):
    try:
        # Split after comm's last ')' so spaces in names do not shift fields.
        return Path("/proc/{}/stat".format(pid)).read_text().rsplit(")", 1)[1].split()[19]
    except (FileNotFoundError, ProcessLookupError):
        return None


_LIFECYCLE_SCRIPT = r'''
import os, pathlib, time
work = pathlib.Path('/workspace')
child = os.fork()
if child == 0:
    os.setsid()
    (work / 'child-ready').write_text(str(os.getpid()))
    # Self-expiry bounds this synthetic process even if cleanup is broken.
    time.sleep(6)
    os._exit(0)
deadline = time.monotonic() + 5
while not (work / 'release-root').exists() and time.monotonic() < deadline:
    time.sleep(.01)
'''


def _lifecycle(plan, workspace):
    process = subprocess.Popen(plan + ["--", "/usr/bin/python3", "-I", "-c", _LIFECYCLE_SCRIPT],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, close_fds=True,
                               env={"PATH": "/usr/bin:/bin"})
    try:
        deadline = time.monotonic() + 3
        marker = workspace / "child-ready"
        while not marker.exists() and time.monotonic() < deadline and process.poll() is None:
            time.sleep(.01)
        if not marker.exists():
            raise RuntimeError("detached child did not reach ready state")
        inner_pid = int(marker.read_text())
        candidates = []
        for pid in _children(process.pid):
            try:
                status = Path("/proc/{}/status".format(pid)).read_text()
            except (FileNotFoundError, ProcessLookupError):
                continue
            ns_pids = [line.split()[1:] for line in status.splitlines() if line.startswith("NSpid:")]
            if ns_pids and int(ns_pids[0][-1]) == inner_pid:
                candidates.append(pid)
        if len(candidates) != 1:
            raise RuntimeError("cannot identify the synthetic detached child")
        child_pid = candidates[0]
        identity = _process_start(child_pid)
        if identity is None:
            raise RuntimeError("child exited before cleanup test")
        (workspace / "release-root").touch()
        returncode = process.wait(timeout=3)
        deadline = time.monotonic() + 1
        while _process_start(child_pid) == identity and time.monotonic() < deadline:
            time.sleep(.01)
        reaped = _process_start(child_pid) != identity
        return returncode == 0 and reaped, {"root_exit_code": returncode,
                "detached_child_observed_alive": True, "detached_child_reaped": reaped,
                "supervisor_crash_tested": False}
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        # The synthetic descendant self-expires at six seconds even if the
        # experimental namespace cleanup fails; no arbitrary process is killed.


def probe():
    if sys.platform != "linux":
        return [Observation("LINUX.platform", "unverified", "Requires a real Linux kernel")]
    bwrap = _trusted_bwrap()
    if bwrap is None:
        return [Observation("LINUX.setup", "unavailable", "Trusted /usr/bin/bwrap is missing or unsafe")]
    with tempfile.TemporaryDirectory(prefix="sbx-m0-") as temp:
        root = Path(temp)
        workspace = root / "workspace"
        workspace.mkdir()
        synthetic_secret = root / "synthetic-secret"
        synthetic_secret.write_text("synthetic secret", encoding="utf-8")
        plan = _plan(bwrap, workspace)
        try:
            version = subprocess.run([bwrap, "--version"], capture_output=True, timeout=3,
                                     check=True, env={"PATH": "/usr/bin:/bin"}).stdout.decode().strip()
            setup = _run(plan, "import json, os; print(json.dumps({'pid': os.getpid(), 'uid': os.getuid()}))")
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            return [Observation("LINUX.setup", "unavailable", "Namespace setup failed; no candidate workload executed",
                                {"error_type": type(error).__name__})]
        results = [Observation("LINUX.setup", "pass", "Fixed Python probe started in new namespaces",
                               {"bubblewrap": version, "probe": setup, "runtime_profile": "broad-/usr-PoC-only"})]
        try:
            results.extend(_filesystem(plan, workspace, synthetic_secret))
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            results.append(Observation("FS.probe", "fail", "Filesystem experiment failed",
                                       {"error_type": type(error).__name__}))
        for label, family in (("ipv4", socket.AF_INET), ("ipv6", socket.AF_INET6)):
            for transport, kind in (("tcp", socket.SOCK_STREAM), ("udp", socket.SOCK_DGRAM)):
                results.append(_check("NET-1.{}-{}".format(label, transport),
                                      "Isolated namespace cannot reach a verified host loopback endpoint",
                                      lambda family=family, kind=kind: _network_case(plan, family, kind)))
        results.append(_check("NET-1.abstract-unix", "Abstract Unix host socket is outside the namespace",
                              lambda: _network_case(plan, socket.AF_UNIX, socket.SOCK_STREAM, True)))
        results.append(_check("PR-1.root-exit", "Detached synthetic child is reaped after root exit",
                              lambda: _lifecycle(plan, workspace)))
        results.extend([
            Observation("LINUX.production", "unverified", "Not a production backend: no policy compiler, seccomp, audited runtime profile or resource limits"),
            Observation("FS-4.nested-userns", "unverified", "Nested user/mount namespace remount attacks are not tested or prevented by this PoC"),
            Observation("NET-1.full", "unverified", "External routes, DNS, pathname IPC, WSL interop and all socket families are not fully tested"),
            Observation("PR-2.handles", "unverified", "Inherited FD and control-channel attack matrix is not implemented"),
            Observation("LIFE-1.full", "unverified", "Supervisor crash, timeout, cancellation and disconnect matrix remains incomplete"),
        ])
        return results
