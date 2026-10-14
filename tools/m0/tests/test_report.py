import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


M0_ROOT = Path(__file__).resolve().parents[1]
if str(M0_ROOT) not in sys.path:
    sys.path.insert(0, str(M0_ROOT))

from sandbox_probe.report import (  # noqa: E402
    Observation,
    build_report,
    collect_observations,
    exit_code,
    main,
)


class ObservationTests(unittest.TestCase):
    def test_rejects_unknown_status(self):
        with self.assertRaises(ValueError):
            Observation("example", "maybe", "not a defined status")

    def test_none_details_become_an_independent_empty_mapping(self):
        first = Observation("first", "pass", "ok")
        second = Observation("second", "pass", "ok")

        first.details["changed"] = True

        self.assertEqual(second.details, {})

    def test_to_dict_round_trips_through_json(self):
        observation = Observation(
            "filesystem.scope", "unverified", "Needs a native run", {"attempts": 0}
        )

        encoded = json.dumps(observation.to_dict())

        self.assertEqual(json.loads(encoded), observation.to_dict())


class ReportTests(unittest.TestCase):
    def test_all_pass_report_is_never_production_ready(self):
        report = build_report([Observation("job.lifecycle", "pass", "Observed")])

        self.assertFalse(report["production_ready"])
        self.assertEqual(report["observations"][0]["status"], "pass")
        self.assertIn("release", report["platform"])
        self.assertIn("python_version", report)
        self.assertIn("wsl", report["platform"])

    def test_exit_code_prioritizes_failures(self):
        observations = [
            Observation("missing", "unavailable", "Missing dependency"),
            Observation("failed", "fail", "Probe failed"),
        ]

        self.assertEqual(exit_code(observations), 1)

    def test_exit_code_is_two_for_incomplete_evidence(self):
        self.assertEqual(exit_code([]), 2)
        self.assertEqual(exit_code([Observation("x", "unavailable", "Missing")]), 2)
        self.assertEqual(exit_code([Observation("x", "unverified", "Not run")]), 2)
        self.assertEqual(exit_code([Observation("x", "pass", "Observed")]), 0)

    def test_unsupported_platform_is_explicitly_unverified(self):
        observations = collect_observations("darwin")

        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].status, "unverified")
        self.assertIn("darwin", observations[0].summary.lower())

    def test_missing_platform_module_is_unavailable(self):
        with mock.patch(
            "sandbox_probe.report.importlib.import_module",
            side_effect=ModuleNotFoundError(
                "No module named 'sandbox_probe.linux'", name="sandbox_probe.linux"
            ),
        ):
            observations = collect_observations("linux")

        self.assertEqual(observations[0].status, "unavailable")

    def test_inner_import_error_is_a_controlled_failure(self):
        with mock.patch(
            "sandbox_probe.report.importlib.import_module",
            side_effect=ModuleNotFoundError("secret=/private/value", name="dependency"),
        ):
            observations = collect_observations("linux")

        self.assertEqual(observations[0].status, "fail")
        self.assertEqual(observations[0].details, {"error_type": "ModuleNotFoundError"})
        self.assertNotIn("private", observations[0].summary)

    def test_probe_exception_does_not_expose_exception_message(self):
        platform_module = mock.Mock()
        platform_module.probe.side_effect = RuntimeError("TOKEN=should-not-leak")
        with mock.patch(
            "sandbox_probe.report.importlib.import_module", return_value=platform_module
        ):
            observations = collect_observations("win32")

        serialized = json.dumps(observations[0].to_dict())
        self.assertEqual(observations[0].status, "fail")
        self.assertNotIn("should-not-leak", serialized)

    def test_empty_probe_result_cannot_produce_success(self):
        platform_module = mock.Mock()
        platform_module.probe.return_value = []
        with mock.patch(
            "sandbox_probe.report.importlib.import_module", return_value=platform_module
        ):
            observations = collect_observations("linux")

        self.assertEqual(observations[0].status, "unverified")
        self.assertEqual(exit_code(observations), 2)

    def test_invalid_probe_result_becomes_a_controlled_failure(self):
        platform_module = mock.Mock()
        platform_module.probe.return_value = ["TOKEN=should-not-leak"]
        with mock.patch(
            "sandbox_probe.report.importlib.import_module", return_value=platform_module
        ):
            observations = collect_observations("linux")

        self.assertEqual(observations[0].status, "fail")
        self.assertNotIn("should-not-leak", json.dumps(observations[0].to_dict()))

    def test_cli_prints_json_and_writes_utf8_output(self):
        stdout = io.StringIO()
        observations = [Observation("only", "pass", "Observed")]
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "evidence.json"
            with mock.patch(
                "sandbox_probe.report.collect_observations", return_value=observations
            ):
                result = main(["--output", str(output)], stdout=stdout)

            printed = json.loads(stdout.getvalue())
            written = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(result, 0)
        self.assertEqual(printed, written)
        self.assertFalse(written["production_ready"])

    def test_cli_uses_json_newlines_independent_of_host(self):
        stdout = io.StringIO()
        with mock.patch(
            "sandbox_probe.report.collect_observations",
            return_value=[Observation("only", "pass", "Observed")],
        ):
            result = main([], stdout=stdout)

        self.assertEqual(result, 0)
        self.assertTrue(stdout.getvalue().endswith("\n"))
        self.assertNotIn("\r\n", stdout.getvalue())

    def test_output_failure_emits_one_sanitized_failure_report(self):
        stdout = io.StringIO()
        with mock.patch(
            "sandbox_probe.report.collect_observations",
            return_value=[Observation("only", "pass", "Observed")],
        ), mock.patch(
            "builtins.open",
            side_effect=PermissionError("/private/path TOKEN=should-not-leak"),
        ):
            result = main(["--output", "secret-path.json"], stdout=stdout)

        report = json.loads(stdout.getvalue())
        output_observations = [
            item for item in report["observations"] if item["id"] == "report.output"
        ]
        self.assertEqual(result, 1)
        self.assertEqual(len(output_observations), 1)
        self.assertEqual(output_observations[0]["status"], "fail")
        self.assertEqual(output_observations[0]["details"], {"error_type": "PermissionError"})
        self.assertNotIn("private", stdout.getvalue())
        self.assertNotIn("secret-path", stdout.getvalue())
        self.assertNotIn("should-not-leak", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
