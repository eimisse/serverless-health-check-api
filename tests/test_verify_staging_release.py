"""Regression tests for deterministic staging release verification."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from scripts import verify_deployment
from scripts import verify_staging_release


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "deploy-staging.yml"


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


ENV = {
    "API_ID": "api123",
    "API_STAGE_NAME": "staging-health-check-stage",
    "API_USAGE_PLAN_ID": "plan123",
    "API_KEY_ID": "key123",
    "STAGE_THROTTLE_RATE_LIMIT": "5",
    "STAGE_THROTTLE_BURST_LIMIT": "10",
    "USAGE_PLAN_RATE_LIMIT": "2",
    "USAGE_PLAN_BURST_LIMIT": "4",
}


def stage(method_key_prefix: str = "health") -> dict[str, object]:
    return {
        "stageName": "staging-health-check-stage",
        "methodSettings": {
            f"{method_key_prefix}/GET": {
                "throttlingRateLimit": 5.0,
                "throttlingBurstLimit": 10,
                "metricsEnabled": True,
            },
            f"{method_key_prefix}/POST": {
                "throttlingRateLimit": 5.0,
                "throttlingBurstLimit": 10,
                "metricsEnabled": True,
            },
        },
    }


def usage_plan() -> dict[str, object]:
    return {
        "throttle": {"rateLimit": 2.0, "burstLimit": 4},
        "apiStages": [
            {"apiId": "api123", "stage": "staging-health-check-stage"}
        ],
    }


def usage_plan_keys() -> dict[str, object]:
    return {"items": [{"id": "key123", "type": "API_KEY"}]}


class LiveNetworkEgressTests(unittest.TestCase):
    @staticmethod
    def _endpoint() -> dict[str, object]:
        # Real DescribeVpcEndpoints shape does not include PrefixListId.
        return {
            "VpcEndpoints": [
                {"ServiceName": "com.amazonaws.eu-west-1.dynamodb"}
            ]
        }

    @staticmethod
    def _prefix_lists() -> dict[str, object]:
        return {
            "PrefixLists": [
                {
                    "PrefixListId": "pl-dynamodb",
                    "PrefixListName": "com.amazonaws.eu-west-1.dynamodb",
                }
            ]
        }

    def test_lambda_egress_is_exactly_dynamodb_https(self) -> None:
        lambda_config = {"VpcConfig": {"SecurityGroupIds": ["sg-runtime"]}}
        security_group = {
            "SecurityGroups": [
                {
                    "IpPermissionsEgress": [
                        {
                            "IpProtocol": "tcp",
                            "FromPort": 443,
                            "ToPort": 443,
                            "PrefixListIds": [{"PrefixListId": "pl-dynamodb"}],
                            "IpRanges": [],
                            "Ipv6Ranges": [],
                            "UserIdGroupPairs": [],
                        }
                    ]
                }
            ]
        }

        with mock.patch.object(
            verify_deployment,
            "aws_json",
            side_effect=[
                lambda_config,
                self._endpoint(),
                self._prefix_lists(),
                security_group,
            ],
        ) as aws_json:
            verify_staging_release.verify_live_dynamodb_egress(config())

        self.assertEqual(4, aws_json.call_count)
        self.assertEqual(
            mock.call(
                config(),
                "ec2",
                "describe-prefix-lists",
                "--filters",
                "Name=prefix-list-name,Values=com.amazonaws.eu-west-1.dynamodb",
            ),
            aws_json.call_args_list[2],
        )

    def test_missing_lambda_egress_fails_release_gate(self) -> None:
        lambda_config = {"VpcConfig": {"SecurityGroupIds": ["sg-runtime"]}}
        security_group = {"SecurityGroups": [{"IpPermissionsEgress": []}]}

        with mock.patch.object(
            verify_deployment,
            "aws_json",
            side_effect=[
                lambda_config,
                self._endpoint(),
                self._prefix_lists(),
                security_group,
            ],
        ):
            with self.assertRaisesRegex(
                verify_deployment.VerificationError,
                "exactly one outbound rule",
            ):
                verify_staging_release.verify_live_dynamodb_egress(config())

    def test_public_cidr_egress_fails_release_gate(self) -> None:
        lambda_config = {"VpcConfig": {"SecurityGroupIds": ["sg-runtime"]}}
        security_group = {
            "SecurityGroups": [
                {
                    "IpPermissionsEgress": [
                        {
                            "IpProtocol": "tcp",
                            "FromPort": 443,
                            "ToPort": 443,
                            "PrefixListIds": [{"PrefixListId": "pl-dynamodb"}],
                            "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                            "Ipv6Ranges": [],
                            "UserIdGroupPairs": [],
                        }
                    ]
                }
            ]
        }

        with mock.patch.object(
            verify_deployment,
            "aws_json",
            side_effect=[
                lambda_config,
                self._endpoint(),
                self._prefix_lists(),
                security_group,
            ],
        ):
            with self.assertRaisesRegex(
                verify_deployment.VerificationError,
                "no CIDR, IPv6, or security-group destination",
            ):
                verify_staging_release.verify_live_dynamodb_egress(config())

    def test_endpoint_without_prefix_list_id_uses_regional_prefix_list_api(self) -> None:
        lambda_config = {"VpcConfig": {"SecurityGroupIds": ["sg-runtime"]}}
        security_group = {
            "SecurityGroups": [
                {
                    "IpPermissionsEgress": [
                        {
                            "IpProtocol": "tcp",
                            "FromPort": 443,
                            "ToPort": 443,
                            "PrefixListIds": [{"PrefixListId": "pl-dynamodb"}],
                            "IpRanges": [],
                            "Ipv6Ranges": [],
                            "UserIdGroupPairs": [],
                        }
                    ]
                }
            ]
        }

        endpoint = self._endpoint()
        self.assertNotIn("PrefixListId", endpoint["VpcEndpoints"][0])

        with mock.patch.object(
            verify_deployment,
            "aws_json",
            side_effect=[lambda_config, endpoint, self._prefix_lists(), security_group],
        ):
            verify_staging_release.verify_live_dynamodb_egress(config())


class LiveThrottleConfigurationTests(unittest.TestCase):
    def _verify(self, live_stage: dict[str, object]) -> mock.Mock:
        with (
            mock.patch.dict(os.environ, ENV, clear=False),
            mock.patch.object(
                verify_deployment,
                "aws_json",
                side_effect=[live_stage, usage_plan(), usage_plan_keys()],
            ) as aws_json,
        ):
            verify_staging_release.verify_live_throttling_configuration(config())
        return aws_json

    def test_live_throttle_control_plane_matches_terraform_outputs(self) -> None:
        aws_json = self._verify(stage())

        self.assertEqual(3, aws_json.call_count)
        self.assertEqual(
            mock.call(
                config(),
                "apigateway",
                "get-stage",
                "--rest-api-id",
                "api123",
                "--stage-name",
                "staging-health-check-stage",
            ),
            aws_json.call_args_list[0],
        )
        self.assertEqual(
            mock.call(
                config(),
                "apigateway",
                "get-usage-plan",
                "--usage-plan-id",
                "plan123",
            ),
            aws_json.call_args_list[1],
        )
        self.assertEqual(
            mock.call(
                config(),
                "apigateway",
                "get-usage-plan-keys",
                "--usage-plan-id",
                "plan123",
            ),
            aws_json.call_args_list[2],
        )

    def test_aws_json_pointer_method_keys_are_normalized(self) -> None:
        self._verify(stage("~1health"))

    def test_slash_prefixed_method_keys_are_normalized(self) -> None:
        self._verify(stage("/health"))

    def test_duplicate_semantic_method_key_fails_release_gate(self) -> None:
        live_stage = stage()
        method_settings = live_stage["methodSettings"]
        self.assertIsInstance(method_settings, dict)
        method_settings["~1health/GET"] = dict(method_settings["health/GET"])

        with (
            mock.patch.dict(os.environ, ENV, clear=False),
            mock.patch.object(verify_deployment, "aws_json", return_value=live_stage),
        ):
            with self.assertRaisesRegex(
                verify_deployment.VerificationError,
                "exactly one method setting for health/GET",
            ):
                verify_staging_release.verify_live_throttling_configuration(config())

    def test_live_stage_rate_mismatch_fails_release_gate(self) -> None:
        live_stage = stage()
        method_settings = live_stage["methodSettings"]
        self.assertIsInstance(method_settings, dict)
        method_settings["health/GET"]["throttlingRateLimit"] = 99.0

        with (
            mock.patch.dict(os.environ, ENV, clear=False),
            mock.patch.object(verify_deployment, "aws_json", return_value=live_stage),
        ):
            with self.assertRaisesRegex(
                verify_deployment.VerificationError,
                "live stage rate limit matches Terraform",
            ):
                verify_staging_release.verify_live_throttling_configuration(config())

    def test_workflow_uses_deterministic_release_gate_and_exports_control_ids(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("python scripts/verify_staging_release.py", source)
        self.assertNotIn("run: python scripts/verify_deployment.py", source)
        for variable in (
            "API_ID",
            "API_KEY_ID",
            "API_STAGE_NAME",
            "API_USAGE_PLAN_ID",
            "STAGE_THROTTLE_RATE_LIMIT",
            "STAGE_THROTTLE_BURST_LIMIT",
            "USAGE_PLAN_RATE_LIMIT",
            "USAGE_PLAN_BURST_LIMIT",
        ):
            self.assertIn(f'echo "{variable}=', source)

    def test_post_apply_diagnostics_continue_after_functional_gate_failure(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")
        condition = (
            "if: ${{ always() && steps.apply.outcome == 'success' && "
            "steps.export_runtime.outcome == 'success' }}"
        )
        self.assertGreaterEqual(source.count(condition), 2)
        self.assertIn(
            "if: ${{ always() && steps.apply.outcome == 'success' }}",
            source,
        )


if __name__ == "__main__":
    unittest.main()
