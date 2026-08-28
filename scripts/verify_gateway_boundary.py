#!/usr/bin/env python3
"""Prove API Gateway rejects invalid POST bodies before Lambda for any Content-Type."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import uuid

from verify_deployment import (
    Config,
    VerificationError,
    check,
    filter_lambda_logs,
    http_request,
)


def main() -> int:
    try:
        config = Config.from_environment()
        marker = f"content-type-bypass-{uuid.uuid4().hex}"
        started_ms = int((time.time() - 1) * 1000)
        body = json.dumps({"probe_marker": marker}, separators=(",", ":")).encode(
            "utf-8"
        )

        status, _, _ = http_request(
            config,
            method="POST",
            body=body,
            api_key=config.api_key,
            extra_headers={"Content-Type": "text/plain"},
        )
        check(
            status == 400,
            "API Gateway rejects an invalid POST even when Content-Type is text/plain",
        )

        # CloudWatch ingestion is eventually consistent. The normal deployment
        # verifier already proves that marker lookups can find real Lambda events.
        time.sleep(6)
        messages = filter_lambda_logs(config, marker, started_ms)
        check(
            not messages,
            "the content-type bypass probe never reaches Lambda",
        )
    except (VerificationError, ValueError, subprocess.TimeoutExpired, TimeoutError) as exc:
        print(f"API GATEWAY BOUNDARY VERIFICATION FAILED: {exc}", file=sys.stderr)
        return 1

    print("API GATEWAY BOUNDARY VERIFICATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
