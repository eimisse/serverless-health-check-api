"""Unit tests for the Lambda handler; no AWS credentials or network are used."""

from __future__ import annotations

import base64
import copy
import json
import logging
import pathlib
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

LAMBDA_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAMBDA_DIR))

import handler  # noqa: E402


class FakeTable:
    """Minimal DynamoDB table fake that records PutItem calls."""

    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.error = error

    @property
    def items(self) -> list[dict[str, object]]:
        return [call["Item"] for call in self.calls]  # type: ignore[misc]

    def put_item(self, **kwargs: object) -> dict[str, object]:
        if self.error is not None:
            raise self.error
        self.calls.append(kwargs)
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}


def make_event(body: object = '{"payload":"candidate-test"}') -> dict[str, object]:
    return {
        "resource": "/health",
        "path": "/health",
        "httpMethod": "POST",
        "headers": {"Content-Type": "application/json"},
        "multiValueHeaders": {},
        "body": body,
        "isBase64Encoded": False,
        "requestContext": {
            "requestId": "api-request-123",
            "identity": {
                "sourceIp": "203.0.113.10",
                "userAgent": "lambda-unit-test",
            },
        },
    }


def make_get_event() -> dict[str, object]:
    event = make_event(None)
    event["httpMethod"] = "GET"
    event["headers"] = {}
    return event


class FrozenDateTime(datetime):
    VALUE = datetime(2026, 8, 28, 7, 30, 0, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz: timezone | None = None) -> datetime:
        if tz is None:
            return cls.VALUE.replace(tzinfo=None)
        return cls.VALUE.astimezone(tz)


class HandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.table = FakeTable()
        handler._table = self.table

    def tearDown(self) -> None:
        handler._table = None

    def assert_bad_request(self, event: dict[str, object]) -> dict[str, object]:
        response = handler.lambda_handler(event, None)
        self.assertEqual(400, response["statusCode"])
        self.assertEqual([], self.table.calls)
        self.assertEqual("no-store", response["headers"]["Cache-Control"])
        return response

    def assert_header_is_redacted(
        self, header_name: str, header_value: str, *, multi_value: bool = False
    ) -> None:
        event = make_event()
        collection = "multiValueHeaders" if multi_value else "headers"
        event[collection][header_name] = [header_value] if multi_value else header_value
        original = copy.deepcopy(event)

        with self.assertLogs(handler.LOGGER, level=logging.INFO) as captured:
            response = handler.lambda_handler(event, None)

        self.assertEqual(200, response["statusCode"])
        combined_logs = "\n".join(captured.output)
        self.assertNotIn(header_value, combined_logs)
        self.assertIn("[REDACTED]", combined_logs)
        self.assertEqual(original, event, "logging must not mutate the input event")

    def assert_query_parameter_is_redacted(
        self, parameter_name: str, parameter_value: str, *, multi_value: bool = False
    ) -> None:
        event = make_event()
        collection = (
            "multiValueQueryStringParameters" if multi_value else "queryStringParameters"
        )
        event[collection] = {
            parameter_name: [parameter_value] if multi_value else parameter_value,
            "safe": ["visible"] if multi_value else "visible",
        }
        original = copy.deepcopy(event)

        with self.assertLogs(handler.LOGGER, level=logging.INFO) as captured:
            response = handler.lambda_handler(event, None)

        self.assertEqual(200, response["statusCode"])
        combined_logs = "\n".join(captured.output)
        self.assertNotIn(parameter_value, combined_logs)
        self.assertIn("visible", combined_logs)
        self.assertIn("[REDACTED]", combined_logs)
        self.assertEqual(original, event, "logging must not mutate the input event")

    def test_get_health_is_read_only_and_returns_version(self) -> None:
        with mock.patch.object(handler, "APP_VERSION", "commit-get-123"):
            response = handler.lambda_handler(make_get_event(), None)

        self.assertEqual(200, response["statusCode"])
        self.assertEqual(
            {
                "status": "healthy",
                "message": "Service is available.",
                "version": "commit-get-123",
            },
            json.loads(response["body"]),
        )
        self.assertEqual("application/json", response["headers"]["Content-Type"])
        self.assertEqual("no-store", response["headers"]["Cache-Control"])
        self.assertEqual([], self.table.calls)

    def test_get_health_does_not_require_a_body(self) -> None:
        event = make_get_event()
        event.pop("body", None)
        response = handler.lambda_handler(event, None)
        self.assertEqual(200, response["statusCode"])
        self.assertEqual([], self.table.calls)

    def test_wrong_route_returns_404_without_persistence(self) -> None:
        event = make_event()
        event["path"] = "/admin"
        event["resource"] = "/admin"

        response = handler.lambda_handler(event, None)

        self.assertEqual(404, response["statusCode"])
        self.assertEqual(
            {"status": "error", "message": "Route not found."},
            json.loads(response["body"]),
        )
        self.assertEqual([], self.table.calls)

    def test_non_string_route_is_rejected_without_persistence(self) -> None:
        event = make_event()
        event["path"] = 123

        response = handler.lambda_handler(event, None)

        self.assertEqual(404, response["statusCode"])
        self.assertEqual([], self.table.calls)

    def test_unsupported_method_returns_405_without_persistence(self) -> None:
        event = make_get_event()
        event["httpMethod"] = "DELETE"
        response = handler.lambda_handler(event, None)
        self.assertEqual(405, response["statusCode"])
        self.assertEqual("GET, POST", response["headers"]["Allow"])
        self.assertEqual([], self.table.calls)

    def test_valid_payload_is_saved_and_returns_exact_success(self) -> None:
        response = handler.lambda_handler(make_event(), None)

        self.assertEqual(200, response["statusCode"])
        self.assertEqual(
            '{"status":"healthy","message":"Request processed and saved."}',
            response["body"],
        )
        self.assertEqual("application/json", response["headers"]["Content-Type"])
        self.assertEqual("no-store", response["headers"]["Cache-Control"])
        self.assertEqual(1, len(self.table.items))
        self.assertEqual(
            self.table.items[0]["request_id"], response["headers"]["X-Request-Id"]
        )
        self.assertEqual("candidate-test", self.table.items[0]["payload"])
        self.assertEqual(
            "attribute_not_exists(request_id)",
            self.table.calls[0]["ConditionExpression"],
        )

    def test_valid_base64_json_is_accepted(self) -> None:
        event = make_event(
            base64.b64encode(b'{"payload":"base64-test"}').decode("ascii")
        )
        event["isBase64Encoded"] = True

        response = handler.lambda_handler(event, None)

        self.assertEqual(200, response["statusCode"])
        self.assertEqual("base64-test", self.table.items[0]["payload"])

    def test_missing_payload_is_rejected(self) -> None:
        response = self.assert_bad_request(make_event("{}"))
        self.assertIn("payload", json.loads(response["body"])["message"])

    def test_empty_payload_is_rejected(self) -> None:
        self.assert_bad_request(make_event('{"payload":""}'))

    def test_whitespace_payload_is_rejected(self) -> None:
        self.assert_bad_request(make_event('{"payload":"   "}'))

    def test_numeric_payload_is_rejected(self) -> None:
        self.assert_bad_request(make_event('{"payload":123}'))

    def test_malformed_json_is_rejected(self) -> None:
        response = self.assert_bad_request(make_event("not-json"))
        self.assertIn("valid JSON", json.loads(response["body"])["message"])

    def test_non_object_json_is_rejected(self) -> None:
        self.assert_bad_request(make_event('["payload", "test"]'))

    def test_invalid_base64_is_rejected(self) -> None:
        event = make_event("not+valid+base64===")
        event["isBase64Encoded"] = True
        self.assert_bad_request(event)

    def test_non_string_base64_body_is_rejected(self) -> None:
        event = make_event({"payload": "test"})
        event["isBase64Encoded"] = True
        self.assert_bad_request(event)

    def test_oversized_payload_is_rejected(self) -> None:
        body = json.dumps({"payload": "x" * (handler.MAX_PAYLOAD_LENGTH + 1)})
        self.assert_bad_request(make_event(body))

    def test_unexpected_fields_are_rejected(self) -> None:
        self.assert_bad_request(make_event('{"payload":"test","admin":true}'))

    def test_dynamodb_failure_returns_controlled_500(self) -> None:
        failure_text = "internal DynamoDB diagnostic must remain private"
        handler._table = FakeTable(error=RuntimeError(failure_text))

        response = handler.lambda_handler(make_event(), None)

        self.assertEqual(500, response["statusCode"])
        self.assertEqual(
            {"status": "error", "message": "Request could not be processed."},
            json.loads(response["body"]),
        )
        self.assertNotIn(failure_text, response["body"])

    def test_authorization_header_is_redacted_in_logs(self) -> None:
        self.assert_header_is_redacted("Authorization", "Bearer auth-value-123")

    def test_api_key_header_is_redacted_in_logs(self) -> None:
        self.assert_header_is_redacted("X-API-Key", "api-value-456")

    def test_cookie_header_is_redacted_in_logs(self) -> None:
        self.assert_header_is_redacted("Cookie", "session=cookie-value-789")

    def test_proxy_authorization_header_is_redacted_in_logs(self) -> None:
        self.assert_header_is_redacted(
            "pRoXy-AuThOrIzAtIoN", "Basic proxy-value-321", multi_value=True
        )

    def test_token_query_parameter_is_redacted_in_logs(self) -> None:
        self.assert_query_parameter_is_redacted("token", "query-token-must-not-leak")

    def test_api_key_multi_value_query_parameter_is_redacted_in_logs(self) -> None:
        self.assert_query_parameter_is_redacted(
            "API_KEY", "query-api-key-must-not-leak", multi_value=True
        )

    def test_request_context_api_key_is_redacted_in_logs(self) -> None:
        event = make_event()
        api_key = "context-api-key-must-not-leak"
        event["requestContext"]["identity"]["apiKey"] = api_key
        original = copy.deepcopy(event)

        with self.assertLogs(handler.LOGGER, level=logging.INFO) as captured:
            response = handler.lambda_handler(event, None)

        self.assertEqual(200, response["statusCode"])
        combined_logs = "\n".join(captured.output)
        self.assertNotIn(api_key, combined_logs)
        self.assertIn("[REDACTED]", combined_logs)
        self.assertEqual(original, event, "logging must not mutate the input event")

    def test_successful_requests_receive_distinct_uuids(self) -> None:
        handler.lambda_handler(make_event(), None)
        handler.lambda_handler(make_event(), None)

        first_id = self.table.items[0]["request_id"]
        second_id = self.table.items[1]["request_id"]
        self.assertNotEqual(first_id, second_id)
        self.assertEqual(36, len(first_id))
        self.assertEqual(36, len(second_id))

    def test_ttl_is_generated_from_configured_retention(self) -> None:
        with mock.patch.object(handler, "datetime", FrozenDateTime):
            handler.lambda_handler(make_event(), None)

        expected = int(
            (
                FrozenDateTime.VALUE
                + timedelta(days=handler.REQUEST_TTL_DAYS)
            ).timestamp()
        )
        self.assertEqual(expected, self.table.items[0]["expires_at"])

    def test_persisted_item_contains_required_non_secret_metadata(self) -> None:
        with mock.patch.object(handler, "APP_VERSION", "commit-abc123"):
            handler.lambda_handler(make_event('{"payload":"metadata-test"}'), None)

        item = self.table.items[0]
        self.assertEqual(
            {
                "api_request_id",
                "application_version",
                "expires_at",
                "http_method",
                "path",
                "payload",
                "request_id",
                "source_ip",
                "timestamp",
                "user_agent",
            },
            set(item),
        )
        self.assertEqual("api-request-123", item["api_request_id"])
        self.assertEqual("commit-abc123", item["application_version"])
        self.assertEqual("POST", item["http_method"])
        self.assertEqual("/health", item["path"])
        self.assertEqual("203.0.113.10", item["source_ip"])
        self.assertEqual("lambda-unit-test", item["user_agent"])
        self.assertNotIn("headers", item)


if __name__ == "__main__":
    unittest.main()
