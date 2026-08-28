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

_SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "cookie",
        "proxy-authorization",
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


def _redact_headers(headers: Any, *, multi_value: bool = False) -> Any:
    """Return headers with known credential-bearing values removed."""
    if not isinstance(headers, dict):
        return headers

    redacted = copy.deepcopy(headers)
    replacement: str | list[str] = ["[REDACTED]"] if multi_value else "[REDACTED]"
    for key in redacted:
        if isinstance(key, str) and key.casefold() in _SENSITIVE_HEADERS:
            redacted[key] = replacement
    return redacted


def _sanitize_event(event: dict[str, Any]) -> dict[str, Any]:
    """Copy an API Gateway event and redact authentication headers for logging."""
    sanitized = copy.deepcopy(event)
    if "headers" in sanitized:
        sanitized["headers"] = _redact_headers(sanitized["headers"])
    if "multiValueHeaders" in sanitized:
        sanitized["multiValueHeaders"] = _redact_headers(
            sanitized["multiValueHeaders"], multi_value=True
        )
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


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "Cache-Control": "no-store",
            "Content-Type": "application/json",
        },
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


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Validate, log, and persist one health-check request."""
    _log(logging.INFO, "incoming_request", request=_sanitize_event(event))

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
        "http_method": event.get("httpMethod", "POST"),
        "path": event.get("path", "/health"),
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
    )
