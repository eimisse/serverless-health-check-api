from __future__ import annotations

import unittest
from pathlib import Path

from scripts.preflight_deployment_role import PreflightError, run_preflight


ROOT = Path(__file__).resolve().parents[1]


class FakeAws:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def json(self, service, operation, *args, allow_missing=False):
        self.calls.append((service, operation, args, allow_missing))
        response = self.responses.get((service, operation))
        if isinstance(response, Exception):
            raise response
        if callable(response):
            return response(args, allow_missing)
        if response is None and allow_missing:
            return None
        return response if response is not None else {}


class DeploymentRolePreflightTests(unittest.TestCase):
    def _existing_stack(self):
        return {
            ("sts", "get-caller-identity"): {"Account": "705029438597"},
            ("iam", "get-role"): {"Role": {"RoleName": "staging-health-check-function-role"}},
            ("lambda", "get-function-configuration"): {"State": "Active"},
            ("lambda", "list-versions-by-function"): {
                "Versions": [{"Version": "$LATEST"}, {"Version": "2"}, {"Version": "7"}]
            },
            ("lambda", "get-alias"): {"Name": "staging-release", "FunctionVersion": "7"},
            ("dynamodb", "describe-table"): {
                "Table": {
                    "TableName": "staging-requests-db",
                    "TableArn": "arn:aws:dynamodb:eu-west-1:705029438597:table/staging-requests-db",
                }
            },
            ("kms", "list-aliases"): {
                "Aliases": [
                    {
                        "AliasName": "alias/staging-requests-db-key",
                        "TargetKeyId": "example-key-id",
                    }
                ]
            },
            ("apigateway", "get-rest-apis"): {
                "items": [{"id": "abc123", "name": "staging-health-check-api"}]
            },
            ("apigateway", "get-api-keys"): {
                "items": [{"id": "key123", "name": "staging-health-check-api-key"}]
            },
            ("apigateway", "get-usage-plans"): {
                "items": [{"id": "plan123", "name": "staging-health-check-usage-plan"}]
            },
            ("cloudwatch", "get-dashboard"): {"DashboardName": "staging-health-check-dashboard"},
        }

    def test_existing_stack_checks_provider_refresh_paths_that_failed_live(self):
        aws = FakeAws(self._existing_stack())
        run_preflight(
            "staging",
            "eu-west-1",
            "705029438597",
            aws=aws,
        )

        calls = {(service, operation, args) for service, operation, args, _ in aws.calls}
        self.assertIn(
            ("iam", "list-attached-role-policies", ("--role-name", "staging-health-check-function-role")),
            calls,
        )
        self.assertIn(
            (
                "lambda",
                "get-function-configuration",
                (
                    "--function-name",
                    "staging-health-check-function",
                    "--qualifier",
                    "7",
                ),
            ),
            calls,
        )
        self.assertIn(
            (
                "lambda",
                "get-alias",
                (
                    "--function-name",
                    "staging-health-check-function",
                    "--name",
                    "staging-release",
                ),
            ),
            calls,
        )
        self.assertIn(
            (
                "apigateway",
                "get-api-keys",
                (
                    "--name-query",
                    "staging-health-check-api-key",
                    "--no-include-values",
                ),
            ),
            calls,
        )
        self.assertIn(
            (
                "apigateway",
                "get-tags",
                (
                    "--resource-arn",
                    "arn:aws:apigateway:eu-west-1::/restapis/abc123",
                ),
            ),
            calls,
        )
        self.assertIn(
            (
                "apigateway",
                "get-tags",
                (
                    "--resource-arn",
                    "arn:aws:apigateway:eu-west-1::/apikeys/key123",
                ),
            ),
            calls,
        )
        self.assertIn(
            (
                "apigateway",
                "get-tags",
                (
                    "--resource-arn",
                    "arn:aws:apigateway:eu-west-1::/usageplans/plan123",
                ),
            ),
            calls,
        )
        self.assertIn(
            (
                "cloudwatch",
                "describe-alarms",
                (
                    "--alarm-names",
                    "staging-health-check-function-errors",
                    "staging-health-check-function-throttles",
                    "staging-health-check-api-5xx",
                    "staging-health-check-api-latency",
                ),
            ),
            calls,
        )

    def test_first_deployment_skips_missing_resources_but_keeps_discovery_checks(self):
        responses = {
            ("sts", "get-caller-identity"): {"Account": "705029438597"},
            ("iam", "get-role"): None,
            ("lambda", "get-function-configuration"): None,
            ("dynamodb", "describe-table"): None,
            ("kms", "list-aliases"): {"Aliases": []},
            ("apigateway", "get-rest-apis"): {"items": []},
            ("cloudwatch", "get-dashboard"): None,
        }
        aws = FakeAws(responses)

        run_preflight(
            "staging",
            "eu-west-1",
            "705029438597",
            aws=aws,
        )

        operations = {(service, operation) for service, operation, _, _ in aws.calls}
        self.assertIn(("apigateway", "get-usage-plans"), operations)
        self.assertIn(("logs", "describe-log-groups"), operations)
        self.assertIn(("cloudwatch", "describe-alarms"), operations)
        self.assertIn(("ec2", "describe-vpc-endpoints"), operations)
        self.assertIn(("ec2", "describe-security-group-rules"), operations)
        self.assertNotIn(("lambda", "list-versions-by-function"), operations)

    def test_account_mismatch_fails_before_resource_checks(self):
        aws = FakeAws({("sts", "get-caller-identity"): {"Account": "111111111111"}})
        with self.assertRaisesRegex(PreflightError, "does not match"):
            run_preflight(
                "staging",
                "eu-west-1",
                "705029438597",
                aws=aws,
            )
        self.assertEqual(aws.calls[0][0:2], ("sts", "get-caller-identity"))
        self.assertEqual(len(aws.calls), 1)

    def test_missing_required_read_permission_is_a_hard_failure(self):
        responses = self._existing_stack()
        responses[("iam", "list-attached-role-policies")] = PreflightError(
            "iam:list-attached-role-policies read capability failed: AccessDenied"
        )
        aws = FakeAws(responses)
        with self.assertRaisesRegex(PreflightError, "AccessDenied"):
            run_preflight(
                "staging",
                "eu-west-1",
                "705029438597",
                aws=aws,
            )

    def test_preflight_script_contains_no_mutating_aws_operations(self):
        source = (ROOT / "scripts" / "preflight_deployment_role.py").read_text(
            encoding="utf-8"
        )
        forbidden_operations = (
            '"create-function"',
            '"update-function-code"',
            '"update-function-configuration"',
            '"publish-version"',
            '"put-role-policy"',
            '"attach-role-policy"',
            '"create-table"',
            '"update-table"',
            '"create-rest-api"',
            '"put-rest-api"',
            '"create-key"',
            '"put-key-policy"',
            '"authorize-security-group-egress"',
        )
        for operation in forbidden_operations:
            with self.subTest(operation=operation):
                self.assertNotIn(operation, source)


if __name__ == "__main__":
    unittest.main()
