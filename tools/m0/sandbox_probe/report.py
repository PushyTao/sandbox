"""Evidence model and bounded platform-probe dispatcher."""

import argparse
import importlib
import json
import platform
import sys
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, TextIO


ALLOWED_STATUSES = frozenset(("pass", "fail", "unavailable", "unverified"))
SCHEMA_VERSION = "1.0"


class Observation:
    """One bounded piece of feasibility evidence."""

    def __init__(
        self,
        id: str,
        status: str,
        summary: str,
        details: Optional[Mapping[str, Any]] = None,
    ) -> None:
        if status not in ALLOWED_STATUSES:
            raise ValueError("unknown observation status: {!r}".format(status))
        self.id = id
        self.status = status
        self.summary = summary
        self.details = dict(details) if details is not None else {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "summary": self.summary,
            "details": dict(self.details),
        }


def _wsl_metadata() -> Dict[str, Any]:
    release = platform.release().lower()
    version = platform.version().lower()
    detected = "microsoft" in release or "microsoft" in version
    return {"detected": detected}


def platform_metadata() -> Dict[str, Any]:
    return {
        "sys_platform": sys.platform,
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "wsl": _wsl_metadata(),
    }


def build_report(observations: Iterable[Observation]) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "platform": platform_metadata(),
        "python_version": platform.python_version(),
        "observations": [observation.to_dict() for observation in observations],
        "production_ready": False,
    }


def _diagnostic(status: str, summary: str, error: BaseException) -> Observation:
    # Exception messages can contain paths, environment values, or secrets.
    return Observation(
        "probe.dispatch",
        status,
        summary,
        {"error_type": type(error).__name__},
    )


def collect_observations(platform_name: Optional[str] = None) -> List[Observation]:
    """Run the fixed probe selected from the real platform family.

    ``platform_name`` exists for deterministic unit testing. The command-line
    interface never exposes a platform override and always uses ``sys.platform``.
    """
    selected = sys.platform if platform_name is None else platform_name
    if selected.startswith("linux"):
        module_name = "sandbox_probe.linux"
    elif selected == "win32":
        module_name = "sandbox_probe.windows"
    else:
        return [
            Observation(
                "platform.support",
                "unverified",
                "Platform {!r} has no M0 probe implementation".format(selected),
                {"platform": selected},
            )
        ]

    try:
        probe_module = importlib.import_module(module_name)
    except ModuleNotFoundError as error:
        if error.name == module_name:
            return [
                Observation(
                    "probe.dispatch",
                    "unavailable",
                    "The selected platform probe module is not available",
                    {"module": module_name},
                )
            ]
        return [_diagnostic("fail", "The platform probe could not be loaded", error)]
    except Exception as error:
        return [_diagnostic("fail", "The platform probe could not be loaded", error)]

    try:
        observations = list(probe_module.probe())
    except Exception as error:
        return [_diagnostic("fail", "The platform probe raised an exception", error)]
    if not observations:
        return [
            Observation(
                "probe.dispatch",
                "unverified",
                "The platform probe returned no observations",
            )
        ]
    if not all(isinstance(item, Observation) for item in observations):
        return [
            Observation(
                "probe.dispatch",
                "fail",
                "The platform probe returned an invalid observation",
            )
        ]
    return observations


def exit_code(observations: Iterable[Observation]) -> int:
    statuses = {observation.status for observation in observations}
    if not statuses:
        return 2
    if "fail" in statuses:
        return 1
    if "unavailable" in statuses or "unverified" in statuses:
        return 2
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run fixed, non-destructive M0 sandbox feasibility probes."
    )
    parser.add_argument(
        "--output", metavar="FILE", help="also write the JSON report to FILE as UTF-8"
    )
    return parser


def main(
    argv: Optional[Sequence[str]] = None, stdout: Optional[TextIO] = None
) -> int:
    args = _parser().parse_args(argv)
    stream = sys.stdout if stdout is None else stdout
    observations = collect_observations()
    report = build_report(observations)
    serialized = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8", newline="") as output_file:
                output_file.write(serialized)
        except OSError as error:
            observations.append(
                Observation(
                    "report.output",
                    "fail",
                    "The JSON report output file could not be written",
                    {"error_type": type(error).__name__},
                )
            )
            report = build_report(observations)
            serialized = (
                json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
            )
    stream.write(serialized)
    return exit_code(observations)


__all__ = [
    "ALLOWED_STATUSES",
    "Observation",
    "build_report",
    "collect_observations",
    "exit_code",
    "main",
    "platform_metadata",
]
