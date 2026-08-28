#!/usr/bin/env python3
"""Run non-load post-deployment verification for the manually approved prod stack."""

from __future__ import annotations

import subprocess
import sys

from verify_deployment import (
    Config,
    VerificationError,
    check,
    verify_encryption,
    verify_gateway_rejects_before_lambda,
    verify_get_health,
    verify_negative_requests,
    verify_network,
    verify_user_path,
)


def main() -> int:
    try:
        config = Config.from_environment()
        check(config.environment == "prod", "production verifier is restricted to prod")
        check(len(config.private_subnet_ids) == 2, "verification received exactly two private subnet IDs")
        verify_get_health(config)
        verify_user_path(config)
        verify_negative_requests(config)
        verify_gateway_rejects_before_lambda(config)
        verify_encryption(config)
        verify_network(config)
    except (VerificationError, ValueError, subprocess.TimeoutExpired, TimeoutError) as exc:
        print(f"PRODUCTION VERIFICATION FAILED: {exc}", file=sys.stderr)
        return 1

    print(
        "PRODUCTION VERIFICATION PASSED: core functionality and security controls "
        "are live; no throttling load probe was executed in prod."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
