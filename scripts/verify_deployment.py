#!/usr/bin/env python3
"""Verify a deployed health-check stack from the user path through AWS state."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Config:
    environment: str
    region: str
    api_url: str
    api_key: str
    lambda_function_name: str
    dynamodb_table_name: str
    dynamodb_table_arn: str
    kms_key_arn: str
    vpc_id: str
    private_subnet_ids: frozenset[str]
    dynamodb_vpc_endpoint_id: str
    application_version: str

    @classmethod
    def from_environment(cls) -> "Config":
        required = [
            "ENVIRONMENT",
            "AWS_REGION",
            "API_URL",
            "API_KEY",
            "LAMBDA_FUNCTION_NAME",
            "DYNAMODB_TABLE_NAME",
            "DYNAMODB_TABLE_ARN",
            "KMS_KEY_ARN",
            "VPC_ID",
            "PRIVATE_SUBNET_IDS",
            "DYNAMODB_VPC_ENDPOINT_ID",
            "APPLICATION_VERSION",
        ]
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise ValueError("missing required environment variables: " + ", ".join(missing))

        environment = os.environ["ENVIRONMENT"]
        if environment not in {"staging", "prod"}:
            raise ValueError("ENVIRONMENT must be staging or prod")

        return cls(
            environment=environment,
            region=os.environ["AWS_REGION"],
            api_url=os.environ["API_URL"].rstrip("/"),
            api_key=os.environ["API_KEY"],
            lambda_function_name=os.environ["LAMBDA_FUNCTION_NAME"],
            dynamodb_table_name=os.environ["DYNAMODB_TABLE_NAME"],
            dynamodb_table_arn=os.environ["DYNAMODB_TABLE_ARN"],
            kms_key_arn=os.environ["KMS_KEY_ARN"],
            vpc_id=os.environ["VPC_ID"],
            private_subnet_ids=frozenset(
                item for item in os.environ["PRIVATE_SUBNET_IDS"].split(",") if item
            ),
            dynamodb_vpc_endpoint_id=os.environ["DYNAMODB_VPC_ENDPOINT_ID"],
            application_version=os.environ["APPLICATION_VERSION"],
        )


class VerificationError(RuntimeError):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)
    print(f"PASS: {message}")


def aws_json(config: Config, *arguments: str) -> dict[str, Any]:
    command = ["aws", *arguments, "--region", config.region, "--output", "json"]
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or "AWS CLI command failed"
        raise VerificationError(f"AWS verification command failed: {stderr}")
    try:
        value = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise VerificationError("AWS CLI returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise VerificationError("AWS CLI returned an unexpected JSON type")
    return value


def http_request(
    config: Config,
    *,
    body: bytes,
    api_key: str | None,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "candidate-homework-integration-test/1.0",
    }
    if api_key is not None:
        headers["x-api-key"] = api_key
    if extra_headers:
        headers.update(extra_headers)

    request = urllib.request.Request(
        f"{config.api_url}/health",
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # nosec B310 - URL is the Terraform output under test.
            return response.status, dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read()


def json_request(
    config: Config,
    payload: Any,
    *,
    api_key: str | None,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    return http_request(
        config,
        body=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        api_key=api_key,
        extra_headers=extra_headers,
    )


def parsed_body(body: bytes) -> dict[str, Any]:
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError("API response body is not valid JSON") from exc
    if not isinstance(value, dict):
        raise VerificationError("API response body must be a JSON object")
    return value


def wait_for_dynamodb_item(
    config: Config, request_id: str, *, timeout_seconds: float = 15.0
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    key = json.dumps({"request_id": {"S": request_id}}, separators=(",", ":"))
    while time.monotonic() < deadline:
        response = aws_json(
            config,
            "dynamodb",
            "get-item",
            "--table-name",
            config.dynamodb_table_name,
            "--key",
            key,
            "--consistent-read",
        )
        item = response.get("Item")
        if isinstance(item, dict) and item:
            return item
        time.sleep(1)
    raise VerificationError("valid API request was not persisted to DynamoDB")


def filter_lambda_logs(
    config: Config, marker: str, start_time_ms: int
) -> list[str]:
    response = aws_json(
        config,
        "logs",
        "filter-log-events",
        "--log-group-name",
        f"/aws/lambda/{config.lambda_function_name}",
        "--start-time",
        str(start_time_ms),
        "--filter-pattern",
        marker,
    )
    events = response.get("events", [])
    if not isinstance(events, list):
        return []
    return [
        event.get("message", "")
        for event in events
        if isinstance(event, dict) and isinstance(event.get("message"), str)
    ]


def wait_for_log_marker(
    config: Config,
    marker: str,
    start_time_ms: int,
    *,
    timeout_seconds: float = 20.0,
) -> list[str]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        messages = filter_lambda_logs(config, marker, start_time_ms)
        if messages:
            return messages
        time.sleep(2)
    raise VerificationError(f"Lambda log marker did not appear: {marker}")


def verify_user_path(config: Config) -> tuple[str, int]:
    marker = f"valid-{uuid.uuid4().hex}"
    authorization_probe = f"Bearer probe-{uuid.uuid4().hex}"
    cookie_probe = f"probe_cookie={uuid.uuid4().hex}"
    started_ms = int((time.time() - 2) * 1000)

    status, headers, body = json_request(
        config,
        {"payload": marker},
        api_key=config.api_key,
        extra_headers={
            "Authorization": authorization_probe,
            "Cookie": cookie_probe,
        },
    )
    check(status == 200, "valid POST /health returns HTTP 200")
    response_body = parsed_body(body)
    check(
        response_body
        == {"status": "healthy", "message": "Request processed and saved."},
        "valid request returns the exact homework success body",
    )

    request_id = next(
        (value for key, value in headers.items() if key.casefold() == "x-request-id"),
        None,
    )
    check(bool(request_id), "successful response exposes the generated request ID")

    item = wait_for_dynamodb_item(config, str(request_id))
    check(item.get("payload", {}).get("S") == marker, "DynamoDB stores the submitted payload")
    check(
        item.get("application_version", {}).get("S") == config.application_version,
        "DynamoDB records the immutable application commit version",
    )
    check(bool(item.get("expires_at", {}).get("N")), "DynamoDB record contains TTL metadata")

    messages = wait_for_log_marker(config, marker, started_ms)
    combined = "\n".join(messages)
    check(config.api_key not in combined, "CloudWatch logs never contain the plaintext API key")
    check(authorization_probe not in combined, "CloudWatch logs redact Authorization credentials")
    check(cookie_probe not in combined, "CloudWatch logs redact Cookie credentials")
    check("[REDACTED]" in combined, "CloudWatch contains explicit credential redaction evidence")

    return marker, started_ms


def verify_negative_requests(config: Config) -> None:
    cases = [
        (b"{}", 400, "missing payload"),
        (b'{"payload":123}', 400, "wrong payload type"),
        (b'{"payload":', 400, "malformed JSON"),
        (
            json.dumps({"payload": "x" * 4097}, separators=(",", ":")).encode(),
            400,
            "oversized payload",
        ),
        (b'{"payload":"ok","unexpected":true}', 400, "unexpected property"),
    ]
    for body, expected, label in cases:
        status, _, _ = http_request(config, body=body, api_key=config.api_key)
        check(status == expected, f"API Gateway rejects {label} with HTTP {expected}")

    status, _, _ = json_request(config, {"payload": "no-key"}, api_key=None)
    check(status == 403, "request without API key is rejected with HTTP 403")

    status, _, _ = json_request(config, {"payload": "wrong-key"}, api_key="not-a-valid-key")
    check(status == 403, "request with wrong API key is rejected with HTTP 403")


def verify_gateway_rejects_before_lambda(config: Config) -> None:
    marker = f"gateway-reject-{uuid.uuid4().hex}"
    started_ms = int((time.time() - 1) * 1000)
    status, _, _ = json_request(
        config,
        {"probe_marker": marker},
        api_key=config.api_key,
    )
    check(status == 400, "strict request model rejects the early-rejection probe")

    # CloudWatch ingestion is eventually consistent. A short delay makes the absence
    # check meaningful; a separate valid marker test has already proven log lookup works.
    time.sleep(6)
    messages = filter_lambda_logs(config, marker, started_ms)
    check(
        not messages,
        "invalid request is rejected by API Gateway before Lambda execution",
    )


def verify_encryption(config: Config) -> None:
    table = aws_json(
        config,
        "dynamodb",
        "describe-table",
        "--table-name",
        config.dynamodb_table_name,
    ).get("Table", {})
    sse = table.get("SSEDescription", {}) if isinstance(table, dict) else {}
    check(sse.get("Status") == "ENABLED", "live DynamoDB server-side encryption is enabled")
    check(
        sse.get("KMSMasterKeyArn") == config.kms_key_arn,
        "live DynamoDB table uses the expected customer-managed KMS key",
    )

    rotation = aws_json(
        config,
        "kms",
        "get-key-rotation-status",
        "--key-id",
        config.kms_key_arn,
    )
    check(rotation.get("KeyRotationEnabled") is True, "live KMS automatic key rotation is enabled")


def verify_network(config: Config) -> None:
    lambda_config = aws_json(
        config,
        "lambda",
        "get-function-configuration",
        "--function-name",
        config.lambda_function_name,
    )
    vpc_config = lambda_config.get("VpcConfig", {})
    check(vpc_config.get("VpcId") == config.vpc_id, "Lambda is attached to the expected isolated VPC")
    check(
        frozenset(vpc_config.get("SubnetIds", [])) == config.private_subnet_ids,
        "Lambda uses exactly the two expected private subnets",
    )

    subnet_response = aws_json(
        config,
        "ec2",
        "describe-subnets",
        "--subnet-ids",
        *sorted(config.private_subnet_ids),
    )
    subnets = subnet_response.get("Subnets", [])
    check(
        len(subnets) == 2 and all(subnet.get("MapPublicIpOnLaunch") is False for subnet in subnets),
        "both Lambda subnets disable public IP assignment",
    )

    igws = aws_json(
        config,
        "ec2",
        "describe-internet-gateways",
        "--filters",
        f"Name=attachment.vpc-id,Values={config.vpc_id}",
    ).get("InternetGateways", [])
    check(not igws, "isolated Lambda VPC has no Internet Gateway")

    nat_gateways = aws_json(
        config,
        "ec2",
        "describe-nat-gateways",
        "--filter",
        f"Name=vpc-id,Values={config.vpc_id}",
    ).get("NatGateways", [])
    active_nat = [
        gateway
        for gateway in nat_gateways
        if isinstance(gateway, dict) and gateway.get("State") not in {"deleted", "failed"}
    ]
    check(not active_nat, "isolated Lambda VPC has no active NAT Gateway")

    route_tables = aws_json(
        config,
        "ec2",
        "describe-route-tables",
        "--filters",
        f"Name=vpc-id,Values={config.vpc_id}",
    ).get("RouteTables", [])
    public_routes = []
    for route_table in route_tables:
        for route in route_table.get("Routes", []):
            if route.get("GatewayId", "").startswith("igw-") or route.get("NatGatewayId"):
                public_routes.append(route)
    check(not public_routes, "VPC route tables contain no Internet or NAT gateway route")

    endpoint_response = aws_json(
        config,
        "ec2",
        "describe-vpc-endpoints",
        "--vpc-endpoint-ids",
        config.dynamodb_vpc_endpoint_id,
    )
    endpoints = endpoint_response.get("VpcEndpoints", [])
    check(len(endpoints) == 1, "expected DynamoDB VPC endpoint exists")
    endpoint = endpoints[0]
    check(endpoint.get("VpcId") == config.vpc_id, "DynamoDB endpoint belongs to the Lambda VPC")
    check(endpoint.get("VpcEndpointType") == "Gateway", "DynamoDB endpoint is a Gateway endpoint")

    try:
        policy = json.loads(endpoint.get("PolicyDocument") or "{}")
    except json.JSONDecodeError as exc:
        raise VerificationError("DynamoDB VPC endpoint policy is not valid JSON") from exc
    statements = policy.get("Statement", []) if isinstance(policy, dict) else []
    check(len(statements) == 1, "DynamoDB endpoint policy contains one narrow allow statement")
    statement = statements[0]
    check(statement.get("Action") == "dynamodb:PutItem", "endpoint policy permits only DynamoDB PutItem")
    check(statement.get("Resource") == config.dynamodb_table_arn, "endpoint policy targets only the application table")


def verify_controlled_throttling(config: Config) -> None:
    statuses: list[int] = []
    burst_id = uuid.uuid4().hex
    for attempt in range(2):
        for index in range(12):
            status, _, _ = json_request(
                config,
                {"payload": f"throttle-{burst_id}-{attempt}-{index}"},
                api_key=config.api_key,
            )
            statuses.append(status)
        if 429 in statuses:
            break
    check(200 in statuses, "controlled throttling probe still permits valid requests")
    check(429 in statuses, "controlled request burst produces API Gateway HTTP 429 throttling")
    unexpected = sorted({status for status in statuses if status not in {200, 429}})
    check(not unexpected, f"controlled throttling probe has no unexpected HTTP status: {unexpected}")


def main() -> int:
    try:
        config = Config.from_environment()
        check(config.environment == "staging", "runtime verification is intentionally limited to staging")
        check(len(config.private_subnet_ids) == 2, "verification received exactly two private subnet IDs")
        verify_user_path(config)
        verify_negative_requests(config)
        verify_gateway_rejects_before_lambda(config)
        verify_encryption(config)
        verify_network(config)
        verify_controlled_throttling(config)
    except (VerificationError, ValueError, subprocess.TimeoutExpired, TimeoutError) as exc:
        print(f"DEPLOYMENT VERIFICATION FAILED: {exc}", file=sys.stderr)
        return 1

    print("DEPLOYMENT VERIFICATION PASSED: staging functionality and security controls are live.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
