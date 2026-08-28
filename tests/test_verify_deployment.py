"""Unit tests for deployment-verification helpers; no AWS/network access is used."""

from __future__ import annotations

import json
import unittest
import urllib.error
from types import SimpleNamespace
from unittest import mock

from scripts import verify_deployment


def config() -> verify_deployment.Config:
    return verify_deployment.Config(
        environment="staging",
        region="eu-west-1",
        api_url="https://example.execute-api.eu-west-1.amazonaws.com/staging-health-check-stage",
        api_key="test-api-key",
        lambda_function_name="staging-health-check-function",
        dynamodb_table_name="staging-requests-db",
        dynamodb_table_arn="arn:aws:dynamodb:eu-west-1:123456789012:table/staging-requests-db",
        kms_key_arn="arn:aws:kms:eu-west-1:123456789012:key/example",
        vpc_id="vpc-example",
        private_subnet_ids=frozenset({"subnet-a", "subnet-b"}),
        dynamodb_vpc_endpoint_id="vpce-example",
        application_version="0123456789abcdef",
    )


class DeploymentVerificationHelperTests(unittest.TestCase):
    def test_cloudwatch_filter_pattern_quotes_hyphenated_marker(self) -> None:
        marker = "gateway-reject-0123456789abcdef"
        self.assertEqual(json.dumps(marker), verify_deployment.cloudwatch_exact_phrase(marker))

    def test_cloudwatch_filter_pattern_escapes_quotes_and_backslashes(self) -> None:
        marker = 'marker-with-"quote"-and-\\slash'
        pattern = verify_deployment.cloudwatch_exact_phrase(marker)
        self.assertEqual(marker, json.loads(pattern))
        self.assertTrue(pattern.startswith('"'))
        self.assertTrue(pattern.endswith('"'))

    def test_filter_lambda_logs_uses_exact_quoted_phrase(self) -> None:
        marker = "valid-0123456789abcdef"
        expected_pattern = json.dumps(marker)
        response = {
            "events": [
                {"message": f'{{"payload":"{marker}"}}'},
                {"message": "another matching event"},
            ]
        }

        with mock.patch.object(
            verify_deployment, "aws_json", return_value=response
        ) as aws_json:
            messages = verify_deployment.filter_lambda_logs(config(), marker, 123456)

        self.assertEqual(
            [f'{{"payload":"{marker}"}}', "another matching event"], messages
        )
        aws_json.assert_called_once_with(
            config(),
            "logs",
            "filter-log-events",
            "--log-group-name",
            "staging-health-check-function-logs",
            "--start-time",
            "123456",
            "--filter-pattern",
            expected_pattern,
        )

    def test_filter_lambda_logs_ignores_malformed_event_entries(self) -> None:
        response = {
            "events": [
                {"message": "expected"},
                {"message": 123},
                {"other": "missing-message"},
                "not-an-event-object",
            ]
        }
        with mock.patch.object(verify_deployment, "aws_json", return_value=response):
            messages = verify_deployment.filter_lambda_logs(config(), "marker", 1)
        self.assertEqual(["expected"], messages)

    def test_log_barrier_uses_read_only_get_before_proving_absence(self) -> None:
        cfg = config()
        rejected_marker = "gateway-reject-abc"
        barrier = "log-barrier-fixed"

        with (
            mock.patch.object(
                verify_deployment.uuid,
                "uuid4",
                return_value=SimpleNamespace(hex="fixed"),
            ),
            mock.patch.object(
                verify_deployment,
                "http_request",
                return_value=(200, {}, b"{}"),
            ) as http_request,
            mock.patch.object(
                verify_deployment,
                "wait_for_log_marker",
                return_value=["barrier-visible"],
            ) as wait_for_log_marker,
            mock.patch.object(
                verify_deployment,
                "filter_lambda_logs",
                return_value=[],
            ) as filter_lambda_logs,
        ):
            verify_deployment.prove_marker_absent_after_log_barrier(
                cfg, rejected_marker, 123456
            )

        http_request.assert_called_once_with(
            cfg,
            method="GET",
            api_key=cfg.api_key,
            extra_headers={"X-Verification-Barrier": barrier},
        )
        wait_for_log_marker.assert_called_once_with(cfg, barrier, 123456)
        filter_lambda_logs.assert_called_once_with(cfg, rejected_marker, 123456)

    def test_network_failure_is_reported_as_verification_error(self) -> None:
        with mock.patch.object(
            verify_deployment.urllib.request,
            "urlopen",
            side_effect=urllib.error.URLError("dns failure"),
        ):
            with self.assertRaisesRegex(
                verify_deployment.VerificationError,
                "API request failed before an HTTP response",
            ):
                verify_deployment.http_request(
                    config(), method="GET", api_key="test-api-key"
                )

    def test_throttling_probe_is_read_only_and_leaves_recovery_window(self) -> None:
        cfg = config()
        responses = [(200, {}, b"{}"), (429, {}, b"{}")] + [
            (429, {}, b"{}")
        ] * 10

        with (
            mock.patch.object(
                verify_deployment,
                "http_request",
                side_effect=responses,
            ) as http_request,
            mock.patch.object(verify_deployment.time, "sleep") as sleep,
        ):
            verify_deployment.verify_controlled_throttling(cfg)

        self.assertEqual(12, http_request.call_count)
        for call in http_request.call_args_list:
            self.assertEqual(
                mock.call(cfg, method="GET", api_key=cfg.api_key),
                call,
            )
        self.assertEqual(
            [
                mock.call(verify_deployment.THROTTLE_RECOVERY_SECONDS),
                mock.call(verify_deployment.THROTTLE_RECOVERY_SECONDS),
            ],
            sleep.call_args_list,
        )


if __name__ == "__main__":
    unittest.main()
