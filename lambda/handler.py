"""AWS Lambda handler for the serverless health-check API."""

from __future__ import annotations

import base64
import binascii
import copy
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3

LOGGER = logging.getLogger()
LOGGER.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())

TABLE_NAME = os.getenv("TABLE_NAME", "")
REQUEST_TTL_DAYS = int(os.getenv("REQUEST_TTL_DAYS", "30"))
MAX_PAYLOAD_LENGTH = int(os.getenv("MAX_PAYLOAD_LENGTH", "4096"))
APP_VERSION = os.getenv("APP_VERSION", "unknown")

_HEALTH_PATH = "/health"
_SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "cookie",
        "proxy-authorization",
        "x-api-key",
    }
)
_SENSITIVE_QUERY_PARAMETERS = frozenset(
    {
        "access_token",
        "api-key",
        "api_key",
        "apikey",
        "authorization",
        "password",
        "secret",
        "token",
        "x-api-key",
    }
)

_table: Any | None = None


def _get_table() -> Any:
    """Create the DynamoDB table resource lazily and reuse it per execution environment."""
    global _table
    if _table is None:
        if not TABLE_NAME:
            raise RuntimeError("TABLE_NAME environment variable is required")
        _table = boto3.resource("dynamodb").Table(TABLE_NAME)
    return _table


def _redact_named_values(
    values: Any,
    sensitive_names: frozenset[str],
    *,
    multi_value: bool = False,
) -> Any:
    """Return a copied mapping with configured credential-bearing values removed."""
    if not isinstance(values, dict):
        return values

    redacted = copy.deepcopy(values)
    replacement: str | list[str] = ["[REDACTED]"] if multi_value else "[REDACTED]"
    for key in redacted:
        if isinstance(key, str) and key.casefold() in sensitive_names:
            redacted[key] = replacement
    return redacted


def _redact_headers(headers: Any, *, multi_value: bool = False) -> Any:
    """Return headers with known credential-bearing values removed."""
    return _redact_named_values(
        headers,
        _SENSITIVE_HEADERS,
        multi_value=multi_value,
    )


def _sanitize_event(event: dict[str, Any]) -> dict[str, Any]:
    """Copy an API Gateway event and redact credentials before logging it."""
    sanitized = copy.deepcopy(event)
    if "headers" in sanitized:
        sanitized["headers"] = _redact_headers(sanitized["headers"])
    if "multiValueHeaders" in sanitized:
        sanitized["multiValueHeaders"] = _redact_headers(
            sanitized["multiValueHeaders"], multi_value=True
        )
    if "queryStringParameters" in sanitized:
        sanitized["queryStringParameters"] = _redact_named_values(
            sanitized["queryStringParameters"],
            _SENSITIVE_QUERY_PARAMETERS,
        )
    if "multiValueQueryStringParameters" in sanitized:
        sanitized["multiValueQueryStringParameters"] = _redact_named_values(
            sanitized["multiValueQueryStringParameters"],
            _SENSITIVE_QUERY_PARAMETERS,
            multi_value=True,
        )

    # REST API Gateway can expose the plaintext usage-plan key through
    # requestContext.identity.apiKey in addition to the x-api-key header.
    # Redact that second representation before serializing the full event.
    request_context = sanitized.get("requestContext")
    if isinstance(request_context, dict):
        identity = request_context.get("identity")
        if isinstance(identity, dict) and "apiKey" in identity:
            identity["apiKey"] = "[REDACTED]"

    return sanitized


def _log(level: int, event_name: str, **fields: Any) -> None:
    """Write one machine-parseable JSON log record."""
    LOGGER.log(
        level,
        json.dumps(
            {"event": event_name, **fields},
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        ),
    )


def _response(
    status_code: int,
    body: dict[str, Any],
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    headers = {
        "Cache-Control": "no-store",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(body, separators=(",", ":")),
    }


def _decode_body(event: dict[str, Any]) -> Any:
    """Decode an API Gateway body and return its parsed JSON value."""
    raw_body = event.get("body")
    if raw_body is None:
        raise ValueError("Request body must be valid JSON.")

    if event.get("isBase64Encoded") is True:
        if not isinstance(raw_body, str):
            raise ValueError("Request body must be valid JSON.")
        try:
            raw_body = base64.b64decode(raw_body, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as exc:
            raise ValueError("Request body must be valid JSON.") from exc

    if isinstance(raw_body, dict):
        return raw_body

    try:
        return json.loads(raw_body)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Request body must be valid JSON.") from exc


def _validated_payload(event: dict[str, Any]) -> str:
    """Return a valid payload or raise a client-safe validation error."""
    body = _decode_body(event)
    if not isinstance(body, dict):
        raise ValueError("Request body must be a JSON object.")

    unexpected_fields = sorted(set(body) - {"payload"})
    if unexpected_fields:
        raise ValueError("Request body contains unsupported fields.")

    payload = body.get("payload")
    if not isinstance(payload, str) or not payload.strip():
        raise ValueError("Missing or invalid required field: payload.")
    if len(payload) > MAX_PAYLOAD_LENGTH:
        raise ValueError(
            f"Field payload must be at most {MAX_PAYLOAD_LENGTH} characters."
        )
    return payload


def _request_metadata(event: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    request_context = event.get("requestContext")
    if not isinstance(request_context, dict):
        request_context = {}
    identity = request_context.get("identity")
    if not isinstance(identity, dict):
        identity = {}
    return request_context, identity


def _http_method(event: dict[str, Any]) -> str:
    method = event.get("httpMethod", "POST")
    return method.upper() if isinstance(method, str) else "POST"


def _request_path(event: dict[str, Any]) -> str:
    path = event.get("path", _HEALTH_PATH)
    return path if isinstance(path, str) else ""


def _health_response() -> dict[str, Any]:
    return _response(
        200,
        {
            "status": "healthy",
            "message": "Service is available.",
            "version": APP_VERSION,
        },
    )


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Serve GET health checks or validate and persist POST requests."""
    _log(logging.INFO, "incoming_request", request=_sanitize_event(event))

    path = _request_path(event)
    if path != _HEALTH_PATH:
        _log(logging.WARNING, "request_rejected", reason="route_not_found", path=path)
        return _response(404, {"status": "error", "message": "Route not found."})

    method = _http_method(event)
    if method == "GET":
        _log(logging.INFO, "health_check_succeeded", application_version=APP_VERSION)
        return _health_response()

    if method != "POST":
        _log(logging.WARNING, "request_rejected", reason="method_not_allowed", method=method)
        return _response(
            405,
            {"status": "error", "message": "Method not allowed."},
            {"Allow": "GET, POST"},
        )

    try:
        payload = _validated_payload(event)
    except ValueError as exc:
        _log(logging.WARNING, "request_rejected", reason=str(exc))
        return _response(400, {"status": "error", "message": str(exc)})

    now = datetime.now(timezone.utc)
    request_context, identity = _request_metadata(event)
    request_id = str(uuid.uuid4())
    item = {
        "request_id": request_id,
        "timestamp": now.isoformat().replace("+00:00", "Z"),
        "expires_at": int((now + timedelta(days=REQUEST_TTL_DAYS)).timestamp()),
        "http_method": method,
        "path": path,
        "payload": payload,
        "source_ip": identity.get("sourceIp", "unknown"),
        "user_agent": identity.get("userAgent", "unknown"),
        "api_request_id": request_context.get("requestId", "unknown"),
        "application_version": APP_VERSION,
    }

    try:
        _get_table().put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(request_id)",
        )
    except Exception as exc:  # DynamoDB/configuration errors must never reach the client.
        _log(
            logging.ERROR,
            "request_persistence_failed",
            error_type=type(exc).__name__,
            request_id=request_id,
        )
        LOGGER.debug("DynamoDB failure details", exc_info=True)
        return _response(
            500,
            {"status": "error", "message": "Request could not be processed."},
        )

    _log(logging.INFO, "request_saved", request_id=request_id)
    return _response(
        200,
        {"status": "healthy", "message": "Request processed and saved."},
        {"X-Request-Id": request_id},
    )
