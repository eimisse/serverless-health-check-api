"""Unit tests for the live Lambda release-alias verifier."""

from __future__ import annotations

import json
import unittest
from unittest import mock

from scripts import verify_deployment, verify_release_alias


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


def alias_policy(*, extra_statement: dict[str, object] | None = None) -> dict[str, str]:
    alias_arn = "arn:aws:lambda:eu-west-1:123456789012:function:staging-health-check-function:staging-release"
    statements: list[dict[str, object]] = []
    for method in ("GET", "POST"):
        statements.append(
            {
                "Sid": f"Allow{method}",
                "Effect": "Allow",
                "Principal": {"Service": "apigateway.amazonaws.com"},
                "Action": "lambda:InvokeFunction",
                "Resource": alias_arn,
                "Condition": {
                    "ArnLike": {
                        "AWS:SourceArn": (
                            "arn:aws:execute-api:eu-west-1:123456789012:api123/"
                            f"staging-health-check-stage/{method}/health"
                        )
                    }
                },
            }
        )
    if extra_statement is not None:
        statements.append(extra_statement)
    return {"Policy": json.dumps({"Version": "2012-10-17", "Statement": statements})}


class ReleaseAliasVerificationTests(unittest.TestCase):
    def test_accepts_alias_bound_to_expected_published_commit(self) -> None:
        cfg = config()
        responses = [
            {
                "Name": "staging-release",
                "AliasArn": "arn:aws:lambda:eu-west-1:123456789012:function:staging-health-check-function:staging-release",
                "FunctionVersion": "42",
            },
            {
                "Version": "42",
                "Environment": {
                    "Variables": {"APP_VERSION": cfg.application_version}
                },
            },
            alias_policy(),
        ]

        with mock.patch.object(
            verify_release_alias, "aws_json", side_effect=responses
        ) as aws_json:
            version = verify_release_alias.verify_release_alias(cfg)

        self.assertEqual("42", version)
        self.assertEqual(3, aws_json.call_count)
        self.assertEqual(
            mock.call(
                cfg,
                "lambda",
                "get-alias",
                "--function-name",
                cfg.lambda_function_name,
                "--name",
                "staging-release",
            ),
            aws_json.call_args_list[0],
        )
        self.assertEqual(
            mock.call(
                cfg,
                "lambda",
                "get-function-configuration",
                "--function-name",
                cfg.lambda_function_name,
                "--qualifier",
                "staging-release",
            ),
            aws_json.call_args_list[1],
        )
        self.assertEqual(
            mock.call(
                cfg,
                "lambda",
                "get-policy",
                "--function-name",
                cfg.lambda_function_name,
                "--qualifier",
                "staging-release",
            ),
            aws_json.call_args_list[2],
        )

    def test_rejects_missing_alias_arn_even_if_function_arn_is_present(self) -> None:
        cfg = config()
        with mock.patch.object(
            verify_release_alias,
            "aws_json",
            return_value={
                "Name": "staging-release",
                "FunctionArn": "arn:aws:lambda:eu-west-1:123456789012:function:staging-health-check-function:staging-release",
                "FunctionVersion": "42",
            },
        ):
            with self.assertRaisesRegex(
                verify_deployment.VerificationError,
                "release alias ARN is qualified",
            ):
                verify_release_alias.verify_release_alias(cfg)

    def test_rejects_latest_instead_of_published_version(self) -> None:
        cfg = config()
        with mock.patch.object(
            verify_release_alias,
            "aws_json",
            return_value={
                "Name": "staging-release",
                "AliasArn": "arn:aws:lambda:eu-west-1:123456789012:function:staging-health-check-function:staging-release",
                "FunctionVersion": "$LATEST",
            },
        ):
            with self.assertRaisesRegex(
                verify_deployment.VerificationError,
                "published numeric version",
            ):
                verify_release_alias.verify_release_alias(cfg)

    def test_rejects_alias_version_configuration_mismatch(self) -> None:
        cfg = config()
        with mock.patch.object(
            verify_release_alias,
            "aws_json",
            side_effect=[
                {
                    "Name": "staging-release",
                    "AliasArn": "arn:aws:lambda:eu-west-1:123456789012:function:staging-health-check-function:staging-release",
                    "FunctionVersion": "42",
                },
                {
                    "Version": "41",
                    "Environment": {
                        "Variables": {"APP_VERSION": cfg.application_version}
                    },
                },
            ],
        ):
            with self.assertRaisesRegex(
                verify_deployment.VerificationError,
                "same published version",
            ):
                verify_release_alias.verify_release_alias(cfg)

    def test_rejects_alias_pointing_to_wrong_git_commit(self) -> None:
        cfg = config()
        with mock.patch.object(
            verify_release_alias,
            "aws_json",
            side_effect=[
                {
                    "Name": "staging-release",
                    "AliasArn": "arn:aws:lambda:eu-west-1:123456789012:function:staging-health-check-function:staging-release",
                    "FunctionVersion": "42",
                },
                {
                    "Version": "42",
                    "Environment": {"Variables": {"APP_VERSION": "different-sha"}},
                },
            ],
        ):
            with self.assertRaisesRegex(
                verify_deployment.VerificationError,
                "deployed Git commit",
            ):
                verify_release_alias.verify_release_alias(cfg)

    def test_rejects_extra_live_alias_permission(self) -> None:
        cfg = config()
        broad_statement = {
            "Sid": "ManualBroadPermission",
            "Effect": "Allow",
            "Principal": {"Service": "apigateway.amazonaws.com"},
            "Action": "lambda:InvokeFunction",
            "Resource": "arn:aws:lambda:eu-west-1:123456789012:function:staging-health-check-function:staging-release",
            "Condition": {
                "ArnLike": {"AWS:SourceArn": "arn:aws:execute-api:eu-west-1:123456789012:*/*/*/*"}
            },
        }
        with mock.patch.object(
            verify_release_alias,
            "aws_json",
            side_effect=[
                {
                    "Name": "staging-release",
                    "AliasArn": "arn:aws:lambda:eu-west-1:123456789012:function:staging-health-check-function:staging-release",
                    "FunctionVersion": "42",
                },
                {
                    "Version": "42",
                    "Environment": {
                        "Variables": {"APP_VERSION": cfg.application_version}
                    },
                },
                alias_policy(extra_statement=broad_statement),
            ],
        ):
            with self.assertRaisesRegex(
                verify_deployment.VerificationError,
                "exactly two invoke-policy statements",
            ):
                verify_release_alias.verify_release_alias(cfg)

    def test_rejects_wrong_source_path_in_live_alias_policy(self) -> None:
        cfg = config()
        policy = json.loads(alias_policy()["Policy"])
        policy["Statement"][1]["Condition"]["ArnLike"]["AWS:SourceArn"] = (
            "arn:aws:execute-api:eu-west-1:123456789012:api123/"
            "staging-health-check-stage/POST/*"
        )
        with mock.patch.object(
            verify_release_alias,
            "aws_json",
            side_effect=[
                {
                    "Name": "staging-release",
                    "AliasArn": "arn:aws:lambda:eu-west-1:123456789012:function:staging-health-check-function:staging-release",
                    "FunctionVersion": "42",
                },
                {
                    "Version": "42",
                    "Environment": {
                        "Variables": {"APP_VERSION": cfg.application_version}
                    },
                },
                {"Policy": json.dumps(policy)},
            ],
        ):
            with self.assertRaisesRegex(
                verify_deployment.VerificationError,
                "exact stage, method and /health path",
            ):
                verify_release_alias.verify_release_alias(cfg)


if __name__ == "__main__":
    unittest.main()
