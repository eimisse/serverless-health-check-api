from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
NETWORK_SOURCE = ROOT / "terraform" / "modules" / "network" / "main.tf"


class NetworkRuleOwnershipTests(unittest.TestCase):
    """Lock the live staging fix for security-group egress ownership."""

    def test_lambda_security_group_does_not_manage_inline_rules(self) -> None:
        source = NETWORK_SOURCE.read_text(encoding="utf-8")
        security_group = source.split(
            'resource "aws_security_group" "lambda" {', maxsplit=1
        )[1].split(
            'resource "aws_vpc_security_group_egress_rule" "dynamodb_https" {',
            maxsplit=1,
        )[0]

        self.assertIsNone(re.search(r"(?m)^\s*(ingress|egress)\s*=", security_group))

    def test_dynamodb_egress_has_one_dedicated_rule(self) -> None:
        source = NETWORK_SOURCE.read_text(encoding="utf-8")
        self.assertEqual(
            1,
            source.count(
                'resource "aws_vpc_security_group_egress_rule" "dynamodb_https" {'
            ),
        )
        rule = source.split(
            'resource "aws_vpc_security_group_egress_rule" "dynamodb_https" {',
            maxsplit=1,
        )[1].split('resource "aws_vpc_endpoint" "dynamodb" {', maxsplit=1)[0]
        self.assertIn("prefix_list_id    = var.dynamodb_prefix_list_id", rule)
        self.assertIn("from_port         = 443", rule)
        self.assertIn("to_port           = 443", rule)
        self.assertIn('ip_protocol       = "tcp"', rule)


if __name__ == "__main__":
    unittest.main()
