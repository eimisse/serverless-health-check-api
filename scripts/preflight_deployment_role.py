#!/usr/bin/env python3
"""Read-only AWS preflight for the OIDC deployment role before Terraform apply.

The preflight deliberately performs only AWS read operations. It validates the
provider refresh paths that previously failed only during a live apply, while
skipping resource-specific checks when a resource does not exist yet.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Any


MISSING_MARKERS = (
    "NoSuchEntity",
    "NotFoundException",
    "ResourceNotFoundException",
    "ResourceNotFound",
)


class PreflightError(RuntimeError):
    """Raised when a required read capability is unavailable or malformed."""


@dataclass
class AwsCli:
    region: str

    def json(
        self,
        service: str,
        operation: str,
        *args: str,
        allow_missing: bool = False,
    ) -> dict[str, Any] | None:
        command = [
            "aws",
            service,
            operation,
            *args,
            "--region",
            self.region,
            "--no-cli-pager",
            "--output",
            "json",
        ]
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if allow_missing and any(marker in stderr for marker in MISSING_MARKERS):
                return None
            short_error = stderr.splitlines()[-1] if stderr else "AWS CLI returned no error text"
            raise PreflightError(
                f"{service}:{operation} read capability failed: {short_error}"
            )

        try:
            return json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise PreflightError(
                f"{service}:{operation} returned invalid JSON"
            ) from exc


def _pass(label: str) -> None:
    print(f"PASS {label}")


def _skip(label: str) -> None:
    print(f"SKIP {label}: resource not present yet")


def _check_identity(aws: AwsCli, expected_account: str | None) -> None:
    identity = aws.json("sts", "get-caller-identity") or {}
    account = str(identity.get("Account", ""))
    if not account:
        raise PreflightError("sts:get-caller-identity returned no Account")
    if expected_account and account != expected_account:
        raise PreflightError("AWS account does not match the deployment role ARN")
    _pass("STS caller identity")


def _check_runtime_role(aws: AwsCli, environment: str) -> None:
    role_name = f"{environment}-health-check-function-role"
    role = aws.json("iam", "get-role", "--role-name", role_name, allow_missing=True)
    if role is None:
        _skip("IAM runtime role refresh")
        return
    aws.json("iam", "list-role-policies", "--role-name", role_name)
    aws.json("iam", "list-attached-role-policies", "--role-name", role_name)
    _pass("IAM runtime role refresh")


def _check_lambda(aws: AwsCli, environment: str) -> None:
    function_name = f"{environment}-health-check-function"
    config = aws.json(
        "lambda",
        "get-function-configuration",
        "--function-name",
        function_name,
        allow_missing=True,
    )
    if config is None:
        _skip("Lambda function refresh")
        _skip("Lambda published-version refresh")
        _skip("Lambda release-alias refresh")
        return

    _pass("Lambda function refresh")
    versions = aws.json(
        "lambda",
        "list-versions-by-function",
        "--function-name",
        function_name,
    ) or {}
    numeric_versions = sorted(
        (
            str(item.get("Version"))
            for item in versions.get("Versions", [])
            if str(item.get("Version", "")).isdigit()
        ),
        key=int,
    )
    if numeric_versions:
        aws.json(
            "lambda",
            "get-function-configuration",
            "--function-name",
            function_name,
            "--qualifier",
            numeric_versions[-1],
        )
        _pass(f"Lambda published-version refresh (:{numeric_versions[-1]})")
    else:
        _skip("Lambda published-version refresh")

    alias_name = f"{environment}-release"
    alias = aws.json(
        "lambda",
        "get-alias",
        "--function-name",
        function_name,
        "--name",
        alias_name,
        allow_missing=True,
    )
    if alias is None:
        _skip("Lambda release-alias refresh")
    else:
        _pass("Lambda release-alias refresh")


def _check_dynamodb(aws: AwsCli, environment: str) -> None:
    table_name = f"{environment}-requests-db"
    table = aws.json(
        "dynamodb", "describe-table", "--table-name", table_name, allow_missing=True
    )
    if table is None:
        _skip("DynamoDB table refresh")
        return
    table_arn = str((table.get("Table") or {}).get("TableArn", ""))
    aws.json("dynamodb", "describe-continuous-backups", "--table-name", table_name)
    aws.json("dynamodb", "describe-time-to-live", "--table-name", table_name)
    if table_arn:
        aws.json("dynamodb", "list-tags-of-resource", "--resource-arn", table_arn)
    _pass("DynamoDB table refresh")


def _check_kms(aws: AwsCli, environment: str) -> None:
    alias_name = f"alias/{environment}-requests-db-key"
    aliases = aws.json("kms", "list-aliases") or {}
    target = next(
        (item for item in aliases.get("Aliases", []) if item.get("AliasName") == alias_name),
        None,
    )
    if not target:
        _skip("KMS application key refresh")
        return
    key_id = str(target.get("TargetKeyId", ""))
    if not key_id:
        raise PreflightError(f"KMS alias {alias_name} has no TargetKeyId")
    aws.json("kms", "describe-key", "--key-id", key_id)
    aws.json("kms", "get-key-policy", "--key-id", key_id, "--policy-name", "default")
    aws.json("kms", "get-key-rotation-status", "--key-id", key_id)
    aws.json("kms", "list-resource-tags", "--key-id", key_id)
    _pass("KMS application key refresh")


def _check_api_gateway(aws: AwsCli, environment: str, region: str) -> None:
    api_name = f"{environment}-health-check-api"
    rest_apis = aws.json("apigateway", "get-rest-apis") or {}
    target = next(
        (item for item in rest_apis.get("items", []) if item.get("name") == api_name),
        None,
    )
    if target:
        api_id = str(target.get("id", ""))
        aws.json("apigateway", "get-rest-api", "--rest-api-id", api_id)
        aws.json("apigateway", "get-resources", "--rest-api-id", api_id)
        aws.json("apigateway", "get-deployments", "--rest-api-id", api_id)
        aws.json("apigateway", "get-stages", "--rest-api-id", api_id)
        aws.json(
            "apigateway",
            "get-tags",
            "--resource-arn",
            f"arn:aws:apigateway:{region}::/restapis/{api_id}",
        )
        _pass("API Gateway REST API refresh")
    else:
        _skip("API Gateway REST API refresh")

    api_key_name = f"{environment}-health-check-api-key"
    api_keys = aws.json(
        "apigateway",
        "get-api-keys",
        "--name-query",
        api_key_name,
        "--no-include-values",
    ) or {}
    for item in api_keys.get("items", []):
        if item.get("name") != api_key_name:
            continue
        key_id = str(item.get("id", ""))
        if key_id:
            aws.json("apigateway", "get-api-key", "--api-key", key_id)
            aws.json(
                "apigateway",
                "get-tags",
                "--resource-arn",
                f"arn:aws:apigateway:{region}::/apikeys/{key_id}",
            )
        break

    usage_plan_name = f"{environment}-health-check-usage-plan"
    usage_plans = aws.json("apigateway", "get-usage-plans") or {}
    for item in usage_plans.get("items", []):
        if item.get("name") != usage_plan_name:
            continue
        plan_id = str(item.get("id", ""))
        if plan_id:
            aws.json("apigateway", "get-usage-plan", "--usage-plan-id", plan_id)
            aws.json(
                "apigateway",
                "get-tags",
                "--resource-arn",
                f"arn:aws:apigateway:{region}::/usageplans/{plan_id}",
            )
        break
    _pass("API Gateway API-key, usage-plan and tag discovery")


def _check_observability(aws: AwsCli, environment: str) -> None:
    prefix = f"{environment}-health-check-"
    aws.json("logs", "describe-log-groups", "--log-group-name-prefix", prefix)
    alarm_names = (
        f"{environment}-health-check-function-errors",
        f"{environment}-health-check-function-throttles",
        f"{environment}-health-check-api-5xx",
        f"{environment}-health-check-api-latency",
    )
    aws.json("cloudwatch", "describe-alarms", "--alarm-names", *alarm_names)
    dashboard = aws.json(
        "cloudwatch",
        "get-dashboard",
        "--dashboard-name",
        f"{environment}-health-check-dashboard",
        allow_missing=True,
    )
    if dashboard is None:
        _skip("CloudWatch dashboard refresh")
    else:
        _pass("CloudWatch dashboard refresh")
    _pass("CloudWatch Logs and alarms discovery")


def _check_network(aws: AwsCli, environment: str) -> None:
    tag_filters = (
        "--filters",
        "Name=tag:Project,Values=serverless-health-check-api",
        f"Name=tag:Environment,Values={environment}",
    )
    aws.json("ec2", "describe-vpcs", *tag_filters)
    aws.json("ec2", "describe-subnets", *tag_filters)
    aws.json("ec2", "describe-route-tables", *tag_filters)
    aws.json("ec2", "describe-security-groups", *tag_filters)
    aws.json("ec2", "describe-vpc-endpoints", *tag_filters)
    aws.json("ec2", "describe-security-group-rules")
    _pass("EC2/VPC provider refresh discovery")


def run_preflight(
    environment: str,
    region: str,
    expected_account: str | None = None,
    *,
    aws: AwsCli | None = None,
) -> None:
    if environment not in {"staging", "prod"}:
        raise PreflightError("environment must be staging or prod")
    client = aws or AwsCli(region=region)

    _check_identity(client, expected_account)
    _check_runtime_role(client, environment)
    _check_lambda(client, environment)
    _check_dynamodb(client, environment)
    _check_kms(client, environment)
    _check_api_gateway(client, environment, region)
    _check_observability(client, environment)
    _check_network(client, environment)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", required=True, choices=("staging", "prod"))
    parser.add_argument("--region", required=True)
    parser.add_argument("--expected-account")
    args = parser.parse_args()

    try:
        run_preflight(args.environment, args.region, args.expected_account)
    except PreflightError as exc:
        print(f"Deployment-role live preflight FAILED: {exc}", file=sys.stderr)
        return 1

    print("Deployment-role live preflight passed: all available read paths succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
