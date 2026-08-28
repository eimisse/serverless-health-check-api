"""Unit tests for API Gateway boundary verification helpers."""

from __future__ import annotations

import unittest
from unittest import mock

from scripts import verify_deployment, verify_gateway_boundary


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


class GatewayBoundaryVerificationTests(unittest.TestCase):
    def test_rejected_probe_uses_marker_header_and_log_barrier(self) -> None:
        cfg = config()
        marker = "whitespace-payload-marker"
        body = b'{"payload":"   "}'

        with (
            mock.patch.object(
                verify_gateway_boundary.time,
                "time",
                return_value=1000.0,
            ),
            mock.patch.object(
                verify_gateway_boundary,
                "http_request",
                return_value=(400, {}, b"{}"),
            ) as http_request,
            mock.patch.object(
                verify_gateway_boundary,
                "prove_marker_absent_after_log_barrier",
            ) as prove_absent,
            mock.patch.object(verify_gateway_boundary.time, "sleep") as sleep,
        ):
            verify_gateway_boundary.prove_rejected_before_lambda(
                cfg,
                body=body,
                marker=marker,
                label="a whitespace-only payload",
            )

        http_request.assert_called_once_with(
            cfg,
            method="POST",
            body=body,
            api_key=cfg.api_key,
            extra_headers={"X-Verification-Marker": marker},
        )
        prove_absent.assert_called_once_with(cfg, marker, 999000)
        sleep.assert_called_once_with(
            verify_gateway_boundary.FUNCTIONAL_REQUEST_INTERVAL_SECONDS
        )

    def test_content_type_override_keeps_unique_marker_header(self) -> None:
        cfg = config()
        marker = "content-type-marker"

        with (
            mock.patch.object(
                verify_gateway_boundary,
                "http_request",
                return_value=(400, {}, b"{}"),
            ) as http_request,
            mock.patch.object(
                verify_gateway_boundary,
                "prove_marker_absent_after_log_barrier",
            ),
            mock.patch.object(verify_gateway_boundary.time, "sleep"),
        ):
            verify_gateway_boundary.prove_rejected_before_lambda(
                cfg,
                body=b"{}",
                marker=marker,
                label="invalid text/plain body",
                extra_headers={"Content-Type": "text/plain"},
            )

        self.assertEqual(
            {
                "X-Verification-Marker": marker,
                "Content-Type": "text/plain",
            },
            http_request.call_args.kwargs["extra_headers"],
        )

    def test_non_400_response_fails_before_absence_is_claimed(self) -> None:
        cfg = config()
        with (
            mock.patch.object(
                verify_gateway_boundary,
                "http_request",
                return_value=(429, {}, b"{}"),
            ),
            mock.patch.object(
                verify_gateway_boundary,
                "prove_marker_absent_after_log_barrier",
            ) as prove_absent,
        ):
            with self.assertRaisesRegex(
                verify_deployment.VerificationError,
                "HTTP 400",
            ):
                verify_gateway_boundary.prove_rejected_before_lambda(
                    cfg,
                    body=b"{}",
                    marker="marker",
                    label="invalid body",
                )

        prove_absent.assert_not_called()


if __name__ == "__main__":
    unittest.main()
