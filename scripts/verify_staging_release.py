#!/usr/bin/env python3
"""Deterministic staging release gate over the user path and AWS control plane."""

from __future__ import annotations

import os
import subprocess
import sys

if __package__:
    from . import verify_deployment as base
else:
    import verify_deployment as base


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"missing required environment variable: {name}")
    return value


def _expected_float(name: str) -> float:
    raw = _required(name)
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc


def _expected_int(name: str) -> int:
    raw = _required(name)
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


def _canonical_method_setting_key(key: str) -> str:
    """Normalize API Gateway/Terraform method-setting path encodings."""

    return key.replace("~1", "/").lstrip("/")


def _method_setting(method_settings: dict[str, object], expected_key: str) -> dict[str, object]:
    matches = [
        value
        for key, value in method_settings.items()
        if isinstance(key, str)
        and _canonical_method_setting_key(key) == expected_key
        and isinstance(value, dict)
    ]
    if len(matches) != 1:
        raise base.VerificationError(
            f"live API Gateway stage must expose exactly one method setting for {expected_key}"
        )
    return matches[0]


def verify_live_dynamodb_egress(config: base.Config) -> None:
    """Prove the Lambda SG has exactly one egress path: DynamoDB HTTPS."""

    lambda_config = base.aws_json(
        config,
        "lambda",
        "get-function-configuration",
        "--function-name",
        config.lambda_function_name,
    )
    vpc_config = lambda_config.get("VpcConfig", {})
    security_group_ids = vpc_config.get("SecurityGroupIds", [])
    base.check(
        isinstance(security_group_ids, list) and len(security_group_ids) == 1,
        "Lambda uses exactly one runtime security group",
    )
    security_group_id = security_group_ids[0]

    service_name = f"com.amazonaws.{config.region}.dynamodb"
    endpoint_response = base.aws_json(
        config,
        "ec2",
        "describe-vpc-endpoints",
        "--vpc-endpoint-ids",
        config.dynamodb_vpc_endpoint_id,
    )
    endpoints = endpoint_response.get("VpcEndpoints", [])
    base.check(
        isinstance(endpoints, list) and len(endpoints) == 1,
        "DynamoDB endpoint is available for egress verification",
    )
    base.check(
        endpoints[0].get("ServiceName") == service_name,
        "egress verification uses the regional DynamoDB endpoint",
    )

    # DescribeVpcEndpoints does not expose the AWS-managed prefix-list ID for a
    # Gateway endpoint. Discover the regional service prefix list explicitly;
    # this is the same EC2 read path Terraform uses for data.aws_prefix_list.
    prefix_list_response = base.aws_json(
        config,
        "ec2",
        "describe-prefix-lists",
        "--filters",
        f"Name=prefix-list-name,Values={service_name}",
    )
    prefix_lists = prefix_list_response.get("PrefixLists", [])
    base.check(
        isinstance(prefix_lists, list) and len(prefix_lists) == 1,
        "AWS exposes exactly one regional DynamoDB managed prefix list",
    )
    prefix_list_id = prefix_lists[0].get("PrefixListId")
    base.check(
        isinstance(prefix_list_id, str) and prefix_list_id.startswith("pl-"),
        "regional DynamoDB managed prefix list has a valid ID",
    )
    base.check(
        prefix_lists[0].get("PrefixListName") == service_name,
        "regional DynamoDB managed prefix list has the expected service name",
    )

    security_groups = base.aws_json(
        config,
        "ec2",
        "describe-security-groups",
        "--group-ids",
        security_group_id,
    ).get("SecurityGroups", [])
    base.check(
        isinstance(security_groups, list) and len(security_groups) == 1,
        "Lambda runtime security group is readable",
    )

    egress = security_groups[0].get("IpPermissionsEgress", [])
    base.check(
        isinstance(egress, list) and len(egress) == 1,
        "Lambda security group has exactly one outbound rule",
    )
    rule = egress[0]
    prefix_lists = rule.get("PrefixListIds", [])
    actual_prefixes = {
        item.get("PrefixListId")
        for item in prefix_lists
        if isinstance(item, dict) and item.get("PrefixListId")
    }
    base.check(
        rule.get("IpProtocol") == "tcp"
        and rule.get("FromPort") == 443
        and rule.get("ToPort") == 443,
        "Lambda outbound rule permits only TCP/443",
    )
    base.check(
        actual_prefixes == {prefix_list_id},
        "Lambda outbound rule targets only the DynamoDB managed prefix list",
    )
    base.check(
        not rule.get("IpRanges")
        and not rule.get("Ipv6Ranges")
        and not rule.get("UserIdGroupPairs"),
        "Lambda outbound rule exposes no CIDR, IPv6, or security-group destination",
    )


def verify_live_throttling_configuration(config: base.Config) -> None:
    """Verify effective API Gateway throttle configuration without a flaky 429 gate.

    API Gateway documents throttling and usage-plan limits as best-effort targets,
    not hard request ceilings. A release gate therefore verifies the live control
    plane values and associations rather than requiring one synthetic burst to
    observe a 429 response at a particular instant.
    """

    api_id = _required("API_ID")
    stage_name = _required("API_STAGE_NAME")
    usage_plan_id = _required("API_USAGE_PLAN_ID")
    api_key_id = _required("API_KEY_ID")

    expected_stage_rate = _expected_float("STAGE_THROTTLE_RATE_LIMIT")
    expected_stage_burst = _expected_int("STAGE_THROTTLE_BURST_LIMIT")
    expected_usage_rate = _expected_float("USAGE_PLAN_RATE_LIMIT")
    expected_usage_burst = _expected_int("USAGE_PLAN_BURST_LIMIT")

    stage = base.aws_json(
        config,
        "apigateway",
        "get-stage",
        "--rest-api-id",
        api_id,
        "--stage-name",
        stage_name,
    )
    base.check(
        stage.get("stageName") == stage_name,
        "live API Gateway stage name matches Terraform",
    )

    method_settings = stage.get("methodSettings", {})
    if not isinstance(method_settings, dict):
        raise base.VerificationError("API Gateway stage returned invalid method settings")

    for method_key in ("health/GET", "health/POST"):
        settings = _method_setting(method_settings, method_key)
        base.check(
            float(settings.get("throttlingRateLimit", -1)) == expected_stage_rate,
            f"{method_key} live stage rate limit matches Terraform",
        )
        base.check(
            int(settings.get("throttlingBurstLimit", -1)) == expected_stage_burst,
            f"{method_key} live stage burst limit matches Terraform",
        )
        base.check(
            settings.get("metricsEnabled") is True,
            f"{method_key} detailed API Gateway metrics remain enabled",
        )

    usage_plan = base.aws_json(
        config,
        "apigateway",
        "get-usage-plan",
        "--usage-plan-id",
        usage_plan_id,
    )
    throttle = usage_plan.get("throttle", {})
    if not isinstance(throttle, dict):
        raise base.VerificationError(
            "API Gateway usage plan returned invalid throttle settings"
        )
    base.check(
        float(throttle.get("rateLimit", -1)) == expected_usage_rate,
        "live usage-plan rate limit matches Terraform",
    )
    base.check(
        int(throttle.get("burstLimit", -1)) == expected_usage_burst,
        "live usage-plan burst limit matches Terraform",
    )

    api_stages = usage_plan.get("apiStages", [])
    associated = any(
        isinstance(item, dict)
        and item.get("apiId") == api_id
        and item.get("stage") == stage_name
        for item in api_stages
    )
    base.check(
        associated,
        "usage plan remains associated with the exact deployed API stage",
    )

    usage_plan_keys = base.aws_json(
        config,
        "apigateway",
        "get-usage-plan-keys",
        "--usage-plan-id",
        usage_plan_id,
    )
    items = usage_plan_keys.get("items", [])
    attached_key = any(
        isinstance(item, dict)
        and item.get("id") == api_key_id
        and item.get("type") == "API_KEY"
        for item in items
    )
    base.check(
        attached_key,
        "generated API key remains attached to the deployed usage plan",
    )


def main() -> int:
    try:
        config = base.Config.from_environment()
        base.check(
            config.environment == "staging",
            "runtime verification is intentionally limited to staging",
        )
        base.check(
            len(config.private_subnet_ids) == 2,
            "verification received exactly two private subnet IDs",
        )
        base.verify_get_health(config)
        base.verify_user_path(config)
        base.verify_negative_requests(config)
        base.verify_gateway_rejects_before_lambda(config)
        base.verify_encryption(config)
        base.verify_network(config)
        verify_live_dynamodb_egress(config)
        verify_live_throttling_configuration(config)
    except (
        base.VerificationError,
        ValueError,
        subprocess.TimeoutExpired,
        TimeoutError,
    ) as exc:
        print(f"DEPLOYMENT VERIFICATION FAILED: {exc}", file=sys.stderr)
        return 1

    print(
        "DEPLOYMENT VERIFICATION PASSED: staging functionality, persistence, security, "
        "network egress, and live throttling controls are healthy."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
