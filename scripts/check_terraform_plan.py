#!/usr/bin/env python3
"""Reject destructive Terraform plans and verify critical security invariants."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ALLOWED_REPLACEMENTS = {
    "module.api_gateway.aws_api_gateway_deployment.health",
}


def _resource_changes(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for change in plan.get("resource_changes", []):
        address = change.get("address")
        if isinstance(address, str):
            result[address] = change
    return result


def _first_block(after: dict[str, Any], name: str) -> dict[str, Any]:
    value = after.get(name)
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    return {}


def audit(plan: dict[str, Any], environment: str) -> list[str]:
    if environment not in {"staging", "prod"}:
        return [f"unsupported environment: {environment}"]

    errors: list[str] = []
    changes = _resource_changes(plan)

    for address, resource in sorted(changes.items()):
        actions = resource.get("change", {}).get("actions", [])
        if not isinstance(actions, list):
            errors.append(f"{address}: invalid change action structure")
            continue
        if "delete" not in actions:
            continue
        if set(actions) == {"create", "delete"} and address in ALLOWED_REPLACEMENTS:
            continue
        errors.append(f"{address}: destructive action is not approved: {actions}")

    required = {
        "module.dynamodb.aws_dynamodb_table.requests",
        "module.kms.aws_kms_key.dynamodb",
        "module.lambda.aws_lambda_function.health",
        "module.api_gateway.aws_api_gateway_method.get",
        "module.api_gateway.aws_api_gateway_method.post",
        "module.api_gateway.aws_api_gateway_request_validator.body",
    }
    missing = sorted(required - changes.keys())
    if missing:
        errors.append("critical resources missing from plan: " + ", ".join(missing))
        return errors

    table_change = changes["module.dynamodb.aws_dynamodb_table.requests"]["change"]
    table_after = table_change.get("after") or {}
    table_after_unknown = table_change.get("after_unknown") or {}
    table_sse = _first_block(table_after, "server_side_encryption")
    table_sse_unknown = _first_block(table_after_unknown, "server_side_encryption")
    if table_after.get("name") != f"{environment}-requests-db":
        errors.append("DynamoDB table name does not match the environment naming convention")
    kms_reference_present = bool(table_sse.get("kms_key_arn")) or (
        table_sse_unknown.get("kms_key_arn") is True
    )
    if table_sse.get("enabled") is not True or not kms_reference_present:
        errors.append("DynamoDB must use enabled KMS server-side encryption")

    kms_after = changes["module.kms.aws_kms_key.dynamodb"]["change"].get("after") or {}
    if kms_after.get("enable_key_rotation") is not True:
        errors.append("DynamoDB customer-managed KMS key rotation must remain enabled")

    lambda_after = changes["module.lambda.aws_lambda_function.health"]["change"].get("after") or {}
    if lambda_after.get("function_name") != f"{environment}-health-check-function":
        errors.append("Lambda function name does not match the environment naming convention")
    concurrency = lambda_after.get("reserved_concurrent_executions")
    if not isinstance(concurrency, (int, float)) or concurrency < 1:
        errors.append("Lambda reserved concurrency must remain enabled")
    if not lambda_after.get("vpc_config"):
        errors.append("Lambda must remain attached to the isolated VPC")

    get_after = changes["module.api_gateway.aws_api_gateway_method.get"]["change"].get("after") or {}
    if get_after.get("http_method") != "GET":
        errors.append("health endpoint must expose GET")
    if get_after.get("api_key_required") is not True:
        errors.append("GET /health must continue requiring an API key")

    post_change = changes["module.api_gateway.aws_api_gateway_method.post"]["change"]
    post_after = post_change.get("after") or {}
    post_after_unknown = post_change.get("after_unknown") or {}
    if post_after.get("http_method") != "POST":
        errors.append("health endpoint must expose POST")
    if post_after.get("api_key_required") is not True:
        errors.append("POST /health must continue requiring an API key")

    request_models = post_after.get("request_models")
    if not isinstance(request_models, dict):
        errors.append("POST /health must retain API Gateway request models")
    else:
        default_model = request_models.get("$default")
        json_model = request_models.get("application/json")
        if not default_model or not json_model or default_model != json_model:
            errors.append(
                "POST /health must use the same strict request model for $default and application/json"
            )

    request_validator_present = bool(post_after.get("request_validator_id")) or (
        post_after_unknown.get("request_validator_id") is True
    )
    if not request_validator_present:
        errors.append("POST /health must remain attached to the API Gateway request validator")

    validator_after = changes["module.api_gateway.aws_api_gateway_request_validator.body"]["change"].get("after") or {}
    if validator_after.get("validate_request_body") is not True:
        errors.append("API Gateway request-body validation must remain enabled")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan_json", type=Path)
    parser.add_argument("--environment", required=True, choices=["staging", "prod"])
    args = parser.parse_args()

    try:
        plan = json.loads(args.plan_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Terraform plan guard configuration error: {exc}", file=sys.stderr)
        return 2

    errors = audit(plan, args.environment)
    if errors:
        print("Terraform plan guard FAILED:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(
        "Terraform plan guard passed: no unapproved destructive actions and "
        "critical security controls remain enabled."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
