#!/usr/bin/env python3
"""Prove API Gateway rejects invalid POST bodies before Lambda."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import uuid

if __package__:
    from .verify_deployment import (
        FUNCTIONAL_REQUEST_INTERVAL_SECONDS,
        Config,
        VerificationError,
        check,
        http_request,
        prove_marker_absent_after_log_barrier,
    )
else:
    from verify_deployment import (
        FUNCTIONAL_REQUEST_INTERVAL_SECONDS,
        Config,
        VerificationError,
        check,
        http_request,
        prove_marker_absent_after_log_barrier,
    )


def prove_rejected_before_lambda(
    config: Config,
    *,
    body: bytes,
    marker: str,
    label: str,
    extra_headers: dict[str, str] | None = None,
) -> None:
    """Require HTTP 400 and prove a unique marker never reaches Lambda logs."""
    started_ms = int((time.time() - 1) * 1000)
    headers = {"X-Verification-Marker": marker}
    if extra_headers:
        headers.update(extra_headers)

    status, _, _ = http_request(
        config,
        method="POST",
        body=body,
        api_key=config.api_key,
        extra_headers=headers,
    )
    check(status == 400, f"API Gateway rejects {label} with HTTP 400")

    # A later read-only GET carries a unique log marker. Observing that marker
    # before asserting absence is stronger evidence than sleeping a fixed number
    # of seconds and assuming CloudWatch ingestion has completed.
    prove_marker_absent_after_log_barrier(config, marker, started_ms)
    time.sleep(FUNCTIONAL_REQUEST_INTERVAL_SECONDS)


def main() -> int:
    try:
        config = Config.from_environment()

        content_type_marker = f"content-type-bypass-{uuid.uuid4().hex}"
        prove_rejected_before_lambda(
            config,
            body=json.dumps(
                {"probe_marker": content_type_marker}, separators=(",", ":")
            ).encode("utf-8"),
            marker=content_type_marker,
            label="an invalid POST even when Content-Type is text/plain",
            extra_headers={"Content-Type": "text/plain"},
        )

        whitespace_marker = f"whitespace-payload-{uuid.uuid4().hex}"
        prove_rejected_before_lambda(
            config,
            body=b'{"payload":"   "}',
            marker=whitespace_marker,
            label="a whitespace-only payload",
        )
    except (VerificationError, ValueError, subprocess.TimeoutExpired, TimeoutError) as exc:
        print(f"API GATEWAY BOUNDARY VERIFICATION FAILED: {exc}", file=sys.stderr)
        return 1

    print("API GATEWAY BOUNDARY VERIFICATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
