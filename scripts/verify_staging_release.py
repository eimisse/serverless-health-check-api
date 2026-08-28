#!/usr/bin/env python3
"""Deterministic staging release gate over the user path and AWS control plane."""

from __future__ import annotations

import os
import subprocess

from scripts import verify_deployment as base


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"missing required environment variable: {name}")
    return value


def _expected_float(name: str) -> float:
    try:
        return float(_required(name))
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
    base.check(stage.get("stageName") == stage_name, "live API Gateway stage name matches Terraform")

    method_settings = stage.get("methodSettings", {})
    if not isinstance(method_settings, dict):
        raise base.VerificationError("API Gateway stage returned invalid method settings")

    for method_key in ("~1health/GET", "~1health/POST"):
        settings = method_settings.get(method_key)
        if not isinstance(settings, dict):
            raise base.VerificationError(
                f"live API Gateway stage is missing method settings for {method_key}"
            )
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
        raise base.VerificationError("API Gateway usage plan returned invalid throttle settings")
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
    base.check(associated, "usage plan remains associated with the exact deployed API stage")

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
    base.check(attached_key, "generated API key remains attached to the deployed usage plan")


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
        verify_live_throttling_configuration(config)
    except (
        base.VerificationError,
        ValueError,
        subprocess.TimeoutExpired,
        TimeoutError,
    ) as exc:
        print(f"DEPLOYMENT VERIFICATION FAILED: {exc}", file=__import__("sys").stderr)
        return 1

    print(
        "DEPLOYMENT VERIFICATION PASSED: staging functionality, persistence, security, "
        "and live throttling controls are healthy."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
