# M0 feasibility implementation plan

> **For agentic workers:** Use subagent-driven-development for independent probes and a separate security review. Steps below are tracked independently; M0 probes do not freeze a production API.

**Goal:** Establish a reproducible, non-destructive feasibility harness and record the evidence needed to proceed with the sandbox design.

**Architecture:** Python standard-library probes run fixed synthetic programs in disposable directories. Platform-specific modules report observations; an aggregation layer keeps availability, successful individual probes, and production support separate. No module accepts arbitrary user commands or promises a security boundary.

**Tech stack:** Python 3.8+ for disposable M0 probes; Rust remains the recommended production language pending D3 confirmation. Linux bubblewrap and Windows Job APIs are tested only when available. No persistent host security configuration is modified.

**Spec:** `docs/design/2026-09-30-agent-sandbox-design.md`, especially sections 5, 9, 10, 12 and 14.

## Global constraints

- D1–D7 remain pending; the source explicitly permits M0 before those decisions.
- Never label an unexecuted target-platform test as passed or a single passing primitive as production support.
- Use only synthetic files and fixed probe programs, never real secrets or repository Git metadata as canaries.
- Do not change ACLs, users, firewall rules, kernel settings, or machine-wide environment.
- Missing dependencies and permissions produce explicit unavailable/unverified evidence.
- Keep raw subprocess output bounded and do not expose secrets through reports.
- `production_ready` remains false until all required design gates have been implemented and verified.

## Task 1: Evidence model and report command

Files: `tools/m0/sandbox_probe/{__init__,__main__,report}.py`, `tools/m0/tests/test_report.py`.

Interface: `Observation(id, status, summary, details={}).to_dict()`; statuses are `pass`, `fail`, `unavailable`, `unverified`. Platform modules expose `probe() -> list[Observation]`. The report command emits schema version, platform, Python version, observations, and `production_ready: false`; unsupported hosts produce unverified results.

- [x] Write tests rejecting unknown statuses, round-tripping JSON, and proving even all-pass observations never mark production ready.
- [x] Run `python -m unittest discover -s tools/m0/tests -v` and confirm the missing behavior.
- [x] Implement the report model and module dispatcher. A failing observation yields exit 1; unavailable/unverified results yield exit 2; otherwise exit 0. Exit 0 means only the selected probes passed.
- [x] Run the same tests and a report smoke test.
- [x] Commit as `feat(m0): add structured feasibility reports`.

## Task 2: Windows Job feasibility

Files: `tools/m0/sandbox_probe/windows.py`, `tools/m0/tests/test_windows.py`.

Consumes the observation interface. Produces native evidence for creating a kill-on-close Job, starting a fixed child suspended, assigning it before resume, and observing termination on Job close. All handles must be closed on every failure path. Record ACL/token/network/IPC enforcement as unverified, regardless of Job success.

- [x] Add tests for unsupported platforms and explicit non-support claims.
- [x] Observe test failure, then implement the smallest ctypes wrapper and fixed child probe.
- [x] Run native Windows tests; record actual process termination evidence.
- [x] Review the handle lifecycle and initialization-before-resume ordering.
- [x] Commit as `feat(m0): probe Windows Job lifecycle without host changes`.

## Task 3: Linux isolation feasibility

Files: `tools/m0/sandbox_probe/linux.py`, `tools/m0/tests/test_linux.py`.

Consumes the observation interface. Produces real bwrap evidence using fixed commands for filesystem scope, existing protection, network namespaces and descendant lifecycle. Record the known hardlink/protected-name limitations as blockers, not passing guarantees. WSL evidence must be labeled WSL and must not count as native Windows support.

- [x] Add tests for unavailable dependencies, bounded invocation, and report classification.
- [x] Observe failure; implement fixed bwrap plans with separate setup versus behavior evidence and synthetic canaries.
- [x] Execute in the available Linux environment and retain the versioned JSON report.
- [x] Review that broad runtime read mounts are explicitly PoC-only and that no arbitrary workload interface exists.
- [x] Commit as `feat(m0): exercise Linux filesystem and namespace primitives`.

## Task 4: Decisions, reproducibility and review

Files: `README.md`, `CONTRIBUTING.md`, `docs/decisions/0001-m0-scope.md`, `docs/validation/*`.

- [x] Record D1–D7 as pending, Git grant precedence and trusted approval transport gaps, and a platform evidence matrix.
- [x] Compare fixed upstream references and explain why mechanism reuse does not imply policy equivalence.
- [x] Document exact run commands, prerequisites, report exit codes and remaining M0/M1 gates.
- [x] Run all unit tests on Windows and Linux; run the real platform probes; inspect every failure/unverified item.
- [x] Obtain independent spec/security review and fix material findings.
- [ ] Preserve meaningful commits. If GitHub credentials permit, create a PR targeting main and merge with a merge commit; otherwise deliver a Git bundle and report the authentication blocker without claiming merge success.

## Pre-flight interface review

| Tasks | Shared contract | Finding |
|---|---|---|
| 1 / 2 | Observation and probe() | Windows uses the same four statuses; no production claims. |
| 1 / 3 | Observation and probe() | Linux distinguishes missing setup from failed isolation checks. |
| 2 / 3 | No shared files | Platform implementations can proceed independently. |
| 1–3 / 4 | Serialized reports | Documentation must distinguish passed primitives from unverified complete backends. |

Ruling: implement only the explicitly authorized M0 feasibility work while D1–D7 confirmation is pending. This does not satisfy M1 or the overall issue; no safe production runtime will be inferred from a passing PoC.

## Delivery checkpoint

The bounded probe tasks and independent review are complete. The overall sandbox project and full M0 are NOT complete. GitHub rejected the initial push with invalid credentials; no PR or merge exists. A Git bundle and source archive are delivered on PUSH-1. D1–D7 remain pending. The remote-integration checkbox stays open until authenticated push, PR and merge are actually completed.
