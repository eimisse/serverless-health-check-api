"""Regression tests for verifier entrypoints executed exactly like GitHub Actions."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_RUNTIME_ENV = {
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
}


class VerifierCliEntrypointTests(unittest.TestCase):
    def run_without_runtime_environment(self, script: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        for name in REQUIRED_RUNTIME_ENV:
            env.pop(name, None)

        return subprocess.run(
            [sys.executable, script],
            cwd=ROOT,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def assert_imports_before_expected_config_failure(self, script: str) -> None:
        result = self.run_without_runtime_environment(script)
        combined = f"{result.stdout}\n{result.stderr}"

        self.assertEqual(1, result.returncode)
        self.assertIn("missing required environment variables", combined)
        self.assertNotIn("ModuleNotFoundError", combined)
        self.assertNotIn("ImportError", combined)

    def test_staging_release_verifier_runs_as_direct_script(self) -> None:
        self.assert_imports_before_expected_config_failure(
            "scripts/verify_staging_release.py"
        )

    def test_release_alias_verifier_runs_as_direct_script(self) -> None:
        self.assert_imports_before_expected_config_failure(
            "scripts/verify_release_alias.py"
        )


if __name__ == "__main__":
    unittest.main()
