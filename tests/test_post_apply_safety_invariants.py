"""Regression tests for post-apply deployment safety invariants."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def read_source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


class PostApplySafetyInvariantTests(unittest.TestCase):
    def test_filter_log_events_uses_exact_log_group_resource(self) -> None:
        source = read_source("bootstrap/deployment_verification.tf")
        statement = source.split(
            'sid       = "VerifyLambdaApplicationLogs"', maxsplit=1
        )[1].split("\n  statement {", maxsplit=1)[0]

        self.assertIn('actions   = ["logs:FilterLogEvents"]', statement)
        self.assertIn(
            'resources = [local.resource_arns[each.key].lambda_log_group]',
            statement,
        )
        self.assertNotIn('lambda_log_group}:*', statement)


if __name__ == "__main__":
    unittest.main()
