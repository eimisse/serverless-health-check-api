from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def number_assignment(source: str, name: str) -> int:
    match = re.search(rf"^\s*{re.escape(name)}\s*=\s*(-?\d+)\s*$", source, re.MULTILINE)
    if not match:
        raise AssertionError(f"missing numeric assignment: {name}")
    return int(match.group(1))


class LiveAwsCompatibilityTests(unittest.TestCase):
    """Lock settings that were proven against the real staging AWS account."""

    def test_staging_uses_account_shared_lambda_concurrency(self) -> None:
        staging = read("terraform/environments/staging.tfvars")
        self.assertEqual(number_assignment(staging, "lambda_reserved_concurrency"), -1)
        self.assertEqual(number_assignment(staging, "stage_throttle_rate_limit"), 5)
        self.assertEqual(number_assignment(staging, "stage_throttle_burst_limit"), 10)
        self.assertEqual(number_assignment(staging, "usage_plan_rate_limit"), 2)
        self.assertEqual(number_assignment(staging, "usage_plan_burst_limit"), 4)

    def test_prod_keeps_explicit_reserved_concurrency(self) -> None:
        prod = read("terraform/environments/prod.tfvars")
        self.assertEqual(number_assignment(prod, "lambda_reserved_concurrency"), 10)

    def test_api_gateway_uses_live_supported_tls_policy(self) -> None:
        source = read("terraform/modules/api_gateway/main.tf")
        self.assertIn(
            'security_policy      = "SecurityPolicy_TLS13_1_2_2021_06"',
            source,
        )
        self.assertIn('endpoint_access_mode = "BASIC"', source)
        self.assertNotIn('security_policy      = "TLS_1_2"', source)


if __name__ == "__main__":
    unittest.main()
