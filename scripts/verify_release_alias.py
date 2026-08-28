#!/usr/bin/env python3
"""Verify that the environment release alias targets the intended immutable Lambda version."""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

if __package__:
    from .verify_deployment import Config, VerificationError, aws_json, check
else:
    from verify_deployment import Config, VerificationError, aws_json, check


def _source_arn(statement: dict[str, Any]) -> str | None:
    """Return the Lambda policy SourceArn from a narrow ArnLike/ArnEquals condition."""
    condition = statement.get("Condition")
    if not isinstance(condition, dict):
        return None
    for operator in ("ArnLike", "ArnEquals"):
        values = condition.get(operator)
        if not isinstance(values, dict):
            continue
        for key, value in values.items():
            if isinstance(key, str) and key.casefold() == "aws:sourcearn":
                return value if isinstance(value, str) else None
    return None


def verify_release_policy(config: Config, alias_name: str) -> None:
    """Prove the live alias policy exposes only the two intended API Gateway routes."""
    response = aws_json(
        config,
        "lambda",
        "get-policy",
        "--function-name",
        config.lambda_function_name,
        "--qualifier",
        alias_name,
    )
    policy_text = response.get("Policy")
    if not isinstance(policy_text, str):
        raise VerificationError("Lambda release alias policy is missing")
    try:
        policy = json.loads(policy_text)
    except json.JSONDecodeError as exc:
        raise VerificationError("Lambda release alias policy is not valid JSON") from exc

    statements = policy.get("Statement") if isinstance(policy, dict) else None
    check(
        isinstance(statements, list) and len(statements) == 2,
        "Lambda release alias has exactly two invoke-policy statements",
    )

    expected_suffixes = {
        f"/{config.environment}-health-check-stage/GET/health",
        f"/{config.environment}-health-check-stage/POST/health",
    }
    observed_suffixes: set[str] = set()

    for statement in statements:
        check(isinstance(statement, dict), "Lambda alias policy statements are JSON objects")
        check(statement.get("Effect") == "Allow", "Lambda alias invoke policy contains only Allow statements")
        check(
            statement.get("Action") == "lambda:InvokeFunction",
            "Lambda alias policy permits only lambda:InvokeFunction",
        )
        principal = statement.get("Principal")
        check(
            isinstance(principal, dict)
            and principal.get("Service") == "apigateway.amazonaws.com",
            "Lambda alias invoke policy trusts only API Gateway",
        )
        resource = statement.get("Resource")
        check(
            isinstance(resource, str) and resource.endswith(f":{alias_name}"),
            "Lambda invoke policy is attached to the environment release alias",
        )
        source_arn = _source_arn(statement)
        check(bool(source_arn), "Lambda alias invoke policy retains an exact API Gateway SourceArn")
        matching = {
            suffix for suffix in expected_suffixes if str(source_arn).endswith(suffix)
        }
        check(
            len(matching) == 1,
            "Lambda alias SourceArn targets only the exact stage, method and /health path",
        )
        observed_suffixes.update(matching)

    check(
        observed_suffixes == expected_suffixes,
        "Lambda release alias permits exactly GET and POST /health",
    )


def verify_release_alias(config: Config) -> str:
    """Return the live numeric version after proving the release alias contract."""
    alias_name = f"{config.environment}-release"
    alias = aws_json(
        config,
        "lambda",
        "get-alias",
        "--function-name",
        config.lambda_function_name,
        "--name",
        alias_name,
    )

    check(alias.get("Name") == alias_name, "Lambda release alias has the exact environment name")
    alias_arn = alias.get("AliasArn")
    check(
        isinstance(alias_arn, str)
        and alias_arn.endswith(
            f":function:{config.lambda_function_name}:{alias_name}"
        ),
        "Lambda release alias ARN is qualified by the environment alias",
    )

    function_version = alias.get("FunctionVersion")
    check(
        isinstance(function_version, str)
        and function_version.isdigit()
        and int(function_version) > 0,
        "Lambda release alias targets a published numeric version, not $LATEST",
    )

    qualified = aws_json(
        config,
        "lambda",
        "get-function-configuration",
        "--function-name",
        config.lambda_function_name,
        "--qualifier",
        alias_name,
    )
    check(
        qualified.get("Version") == function_version,
        "alias-qualified Lambda configuration resolves to the same published version",
    )

    environment = qualified.get("Environment")
    variables = environment.get("Variables") if isinstance(environment, dict) else None
    check(
        isinstance(variables, dict)
        and variables.get("APP_VERSION") == config.application_version,
        "release alias points to the Lambda version built from the deployed Git commit",
    )

    verify_release_policy(config, alias_name)
    return function_version


def main() -> int:
    try:
        config = Config.from_environment()
        version = verify_release_alias(config)
    except (VerificationError, ValueError, subprocess.TimeoutExpired, TimeoutError) as exc:
        print(f"RELEASE ALIAS VERIFICATION FAILED: {exc}", file=sys.stderr)
        return 1

    print(
        "RELEASE ALIAS VERIFICATION PASSED: "
        f"{config.environment}-release -> Lambda version {version}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
