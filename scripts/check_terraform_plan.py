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


def _known_or_unknown(change: dict[str, Any], attribute: str) -> bool:
    after = change.get("after") or {}
    after_unknown = change.get("after_unknown") or {}
    return bool(after.get(attribute)) or after_unknown.get(attribute) is True


def _positive_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _validate_request_schema(schema_text: Any, environment: str) -> list[str]:
    if not isinstance(schema_text, str):
        return ["API Gateway request model must contain a JSON Schema document"]

    try:
        schema = json.loads(schema_text)
    except json.JSONDecodeError:
        return ["API Gateway request model schema must be valid JSON"]

    if not isinstance(schema, dict):
        return ["API Gateway request model schema must be a JSON object"]

    errors: list[str] = []
    if schema.get("type") != "object":
        errors.append("API Gateway request model must validate a JSON object")
    if schema.get("additionalProperties") is not False:
        errors.append("API Gateway request model must reject additional properties")
    if schema.get("required") != ["payload"]:
        errors.append("API Gateway request model must require only payload")

    properties = schema.get("properties")
    payload = properties.get("payload") if isinstance(properties, dict) else None
    if not isinstance(payload, dict):
        errors.append("API Gateway request model must define the payload property")
        return errors

    if payload.get("type") != "string":
        errors.append("API Gateway payload must remain a string")
    if payload.get("minLength") != 1:
        errors.append("API Gateway payload must remain non-empty")
    if not _positive_number(payload.get("maxLength")):
        errors.append("API Gateway payload must retain a positive maximum length")
    if payload.get("pattern") != r".*\S.*":
        errors.append("API Gateway payload must retain the whitespace-only rejection pattern")

    expected_title = f"{environment}HealthCheckRequest"
    if schema.get("title") != expected_title:
        errors.append("API Gateway request schema title does not match the environment")

    return errors


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
        "module.lambda.aws_lambda_alias.release",
        "module.api_gateway.aws_api_gateway_rest_api.health",
        "module.api_gateway.aws_api_gateway_method.get",
        "module.api_gateway.aws_api_gateway_method.post",
        "module.api_gateway.aws_api_gateway_model.request",
        "module.api_gateway.aws_api_gateway_request_validator.body",
        "module.api_gateway.aws_api_gateway_integration.lambda_get",
        "module.api_gateway.aws_api_gateway_integration.lambda",
        "module.api_gateway.aws_api_gateway_method_settings.get",
        "module.api_gateway.aws_api_gateway_method_settings.post",
        "module.api_gateway.aws_api_gateway_api_key.health",
        "module.api_gateway.aws_api_gateway_usage_plan.health",
        "module.api_gateway.aws_api_gateway_usage_plan_key.health",
        "module.api_gateway.aws_lambda_permission.api_gateway_get",
        "module.api_gateway.aws_lambda_permission.api_gateway",
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
    table_pitr = _first_block(table_after, "point_in_time_recovery")
    table_ttl = _first_block(table_after, "ttl")

    if table_after.get("name") != f"{environment}-requests-db":
        errors.append("DynamoDB table name does not match the environment naming convention")
    if table_after.get("billing_mode") != "PAY_PER_REQUEST":
        errors.append("DynamoDB must retain PAY_PER_REQUEST billing mode")
    if table_after.get("hash_key") != "request_id":
        errors.append("DynamoDB partition key must remain request_id")

    attributes = table_after.get("attribute")
    has_request_id_string_key = isinstance(attributes, list) and any(
        isinstance(attribute, dict)
        and attribute.get("name") == "request_id"
        and attribute.get("type") == "S"
        for attribute in attributes
    )
    if not has_request_id_string_key:
        errors.append("DynamoDB request_id attribute must remain a string key")

    kms_reference_present = bool(table_sse.get("kms_key_arn")) or (
        table_sse_unknown.get("kms_key_arn") is True
    )
    if table_sse.get("enabled") is not True or not kms_reference_present:
        errors.append("DynamoDB must use enabled KMS server-side encryption")
    if table_pitr.get("enabled") is not True:
        errors.append("DynamoDB point-in-time recovery must remain enabled")
    if table_ttl.get("enabled") is not True or table_ttl.get("attribute_name") != "expires_at":
        errors.append("DynamoDB TTL must remain enabled on expires_at")
    if environment == "prod" and table_after.get("deletion_protection_enabled") is not True:
        errors.append("production DynamoDB deletion protection must remain enabled")

    kms_after = changes["module.kms.aws_kms_key.dynamodb"]["change"].get("after") or {}
    if kms_after.get("enable_key_rotation") is not True:
        errors.append("DynamoDB customer-managed KMS key rotation must remain enabled")

    lambda_change = changes["module.lambda.aws_lambda_function.health"]["change"]
    lambda_after = lambda_change.get("after") or {}
    expected_function_name = f"{environment}-health-check-function"
    expected_release_alias = f"{environment}-release"
    if lambda_after.get("function_name") != expected_function_name:
        errors.append("Lambda function name does not match the environment naming convention")
    concurrency = lambda_after.get("reserved_concurrent_executions")
    if concurrency != -1 and not _positive_number(concurrency):
        errors.append("Lambda reserved concurrency must be -1 (shared account pool) or a positive value")
    if not lambda_after.get("vpc_config"):
        errors.append(
            "Lambda must remain attached to the isolated VPC; reserved concurrency may be unreserved only behind the reviewed API throttling boundary"
        )
    if lambda_after.get("publish") is not True:
        errors.append("Lambda immutable version publishing must remain enabled")
    if not _known_or_unknown(lambda_change, "version"):
        errors.append("Lambda plan must expose a published version")

    alias_change = changes["module.lambda.aws_lambda_alias.release"]["change"]
    alias_after = alias_change.get("after") or {}
    if alias_after.get("name") != expected_release_alias:
        errors.append("Lambda release alias name does not match the environment")
    if alias_after.get("function_name") != expected_function_name:
        errors.append("Lambda release alias targets the wrong function")
    alias_version = alias_after.get("function_version")
    if alias_version == "$LATEST":
        errors.append("Lambda release alias must never target $LATEST")
    elif not alias_version and not _known_or_unknown(alias_change, "function_version"):
        errors.append("Lambda release alias must target a published immutable version")

    api_after = changes["module.api_gateway.aws_api_gateway_rest_api.health"]["change"].get("after") or {}
    if api_after.get("name") != f"{environment}-health-check-api":
        errors.append("API Gateway name does not match the environment naming convention")
    security_policy = api_after.get("security_policy")
    allowed_security_policies = {
        "TLS_1_2",
        "SecurityPolicy_TLS13_1_2_2021_06",
    }
    if security_policy not in allowed_security_policies:
        errors.append("API Gateway default endpoint must reject TLS 1.0")
    if isinstance(security_policy, str) and security_policy.startswith("SecurityPolicy_"):
        if api_after.get("endpoint_access_mode") not in {"BASIC", "STRICT"}:
            errors.append("API Gateway enhanced security policy requires an endpoint access mode")

    expected_model_name = f"{environment}HealthCheckRequest"
    model_after = changes["module.api_gateway.aws_api_gateway_model.request"]["change"].get("after") or {}
    if model_after.get("name") != expected_model_name:
        errors.append("API Gateway request model name does not match the environment")
    if model_after.get("content_type") != "application/json":
        errors.append("API Gateway request model must remain application/json")
    errors.extend(_validate_request_schema(model_after.get("schema"), environment))

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
        if default_model != expected_model_name or json_model != expected_model_name:
            errors.append(
                "POST /health must use the exact strict request model for $default and application/json"
            )

    request_validator_present = bool(post_after.get("request_validator_id")) or (
        post_after_unknown.get("request_validator_id") is True
    )
    if not request_validator_present:
        errors.append("POST /health must remain attached to the API Gateway request validator")

    validator_after = changes["module.api_gateway.aws_api_gateway_request_validator.body"]["change"].get("after") or {}
    if validator_after.get("validate_request_body") is not True:
        errors.append("API Gateway request-body validation must remain enabled")

    integration_expectations = {
        "lambda_get": "GET",
        "lambda": "POST",
    }
    for resource_name, method in integration_expectations.items():
        integration_change = changes[
            f"module.api_gateway.aws_api_gateway_integration.{resource_name}"
        ]["change"]
        integration_after = integration_change.get("after") or {}
        uri = integration_after.get("uri")
        if uri:
            expected_suffix = (
                f":function:{expected_function_name}:{expected_release_alias}/invocations"
            )
            if not isinstance(uri, str) or not uri.endswith(expected_suffix):
                errors.append(
                    f"{method} /health integration must invoke the immutable release alias"
                )
        elif not _known_or_unknown(integration_change, "uri"):
            errors.append(f"{method} /health integration must retain an alias-qualified URI")

    for method_name in ("get", "post"):
        settings_after = changes[
            f"module.api_gateway.aws_api_gateway_method_settings.{method_name}"
        ]["change"].get("after") or {}
        settings = _first_block(settings_after, "settings")
        if not _positive_number(settings.get("throttling_rate_limit")):
            errors.append(f"{method_name.upper()} /health must retain stage rate throttling")
        if not _positive_number(settings.get("throttling_burst_limit")):
            errors.append(f"{method_name.upper()} /health must retain stage burst throttling")
        if settings.get("metrics_enabled") is not True:
            errors.append(f"{method_name.upper()} /health must retain detailed API metrics")

    api_key_after = changes["module.api_gateway.aws_api_gateway_api_key.health"]["change"].get("after") or {}
    if api_key_after.get("name") != f"{environment}-health-check-api-key":
        errors.append("API Gateway API key name does not match the environment")
    if api_key_after.get("enabled") is not True:
        errors.append("API Gateway API key must remain enabled")

    usage_plan_after = changes["module.api_gateway.aws_api_gateway_usage_plan.health"]["change"].get("after") or {}
    throttle = _first_block(usage_plan_after, "throttle_settings")
    if not _positive_number(throttle.get("rate_limit")):
        errors.append("API Gateway usage plan must retain per-key rate throttling")
    if not _positive_number(throttle.get("burst_limit")):
        errors.append("API Gateway usage plan must retain per-key burst throttling")

    usage_plan_key_after = changes["module.api_gateway.aws_api_gateway_usage_plan_key.health"]["change"].get("after") or {}
    if usage_plan_key_after.get("key_type") != "API_KEY":
        errors.append("API Gateway usage plan must remain attached to an API key")

    permission_expectations = {
        "api_gateway_get": "GET",
        "api_gateway": "POST",
    }
    for resource_name, method in permission_expectations.items():
        permission_change = changes[
            f"module.api_gateway.aws_lambda_permission.{resource_name}"
        ]["change"]
        permission_after = permission_change.get("after") or {}
        if permission_after.get("action") != "lambda:InvokeFunction":
            errors.append(f"{method} /health permission must invoke only the Lambda function")
        if permission_after.get("principal") != "apigateway.amazonaws.com":
            errors.append(f"{method} /health Lambda permission must trust only API Gateway")
        if permission_after.get("function_name") != expected_function_name:
            errors.append(f"{method} /health Lambda permission targets the wrong function")
        if permission_after.get("qualifier") != expected_release_alias:
            errors.append(f"{method} /health Lambda permission must remain release-alias qualified")

        source_arn = permission_after.get("source_arn")
        if source_arn:
            expected_suffix = f"/{environment}-health-check-stage/{method}/health"
            if not isinstance(source_arn, str) or not source_arn.endswith(expected_suffix):
                errors.append(
                    f"{method} /health Lambda permission source ARN must target only the exact stage, method, and path"
                )
        elif not _known_or_unknown(permission_change, "source_arn"):
            errors.append(f"{method} /health Lambda permission must retain a scoped source ARN")

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
