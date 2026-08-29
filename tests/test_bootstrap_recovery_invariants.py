from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def read_source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


class BootstrapRecoveryInvariantTests(unittest.TestCase):
    """Protect the bootstrap assumptions that failed during the first live AWS apply."""

    def test_api_gateway_logging_role_has_aws_required_service_policy(self):
        source = read_source("bootstrap/api_gateway_logging.tf")

        self.assertIn('Service = "apigateway.amazonaws.com"', source)
        self.assertIn(
            'AmazonAPIGatewayPushToCloudWatchLogs',
            source,
        )
        self.assertIn(
            'resource "aws_iam_role_policy_attachment" "api_gateway_cloudwatch_required"',
            source,
        )
        self.assertIn(
            "aws_iam_role_policy_attachment.api_gateway_cloudwatch_required",
            source,
        )

    def test_state_key_policy_allows_alias_creation_on_the_target_key(self):
        source = read_source("bootstrap/state.tf")

        self.assertIn('sid    = "DelegateExplicitStateKeyPermissionsToAccount"', source)
        self.assertIn('"kms:CreateAlias"', source)
        self.assertIn('"kms:PutKeyPolicy"', source)

    def test_deployment_state_delete_is_limited_to_lock_file(self):
        source = read_source("bootstrap/deployment_permissions.tf")

        self.assertIn('sid    = "ReadWriteOwnStateObject"', source)
        self.assertIn('sid    = "ManageOwnStateLock"', source)

        state_fragment = source.split(
            'sid    = "ReadWriteOwnStateObject"', 1
        )[1].split('sid    = "ManageOwnStateLock"', 1)[0]
        self.assertIn('"s3:GetObject"', state_fragment)
        self.assertIn('"s3:PutObject"', state_fragment)
        self.assertNotIn('"s3:DeleteObject"', state_fragment)
        self.assertNotIn('.tflock', state_fragment)

        lock_fragment = source.split(
            'sid    = "ManageOwnStateLock"', 1
        )[1].split('sid    = "UseStateEncryptionKey"', 1)[0]
        self.assertIn('"s3:GetObject"', lock_fragment)
        self.assertIn('"s3:PutObject"', lock_fragment)
        self.assertIn('"s3:DeleteObject"', lock_fragment)
        self.assertIn('.tflock', lock_fragment)

    def test_deployment_permissions_are_split_out_of_the_role_inline_quota(self):
        source = read_source("bootstrap/deployment_permissions.tf")

        self.assertNotIn('resource "aws_iam_role_policy" "deployment"', source)
        self.assertIn('resource "aws_iam_policy" "deployment"', source)
        self.assertIn(
            'resource "aws_iam_role_policy_attachment" "deployment"',
            source,
        )

        for policy_document in (
            "deployment_state_runtime",
            "deployment_application",
            "deployment_kms",
            "deployment_network",
            "deployment_observability",
        ):
            self.assertIn(
                f'data "aws_iam_policy_document" "{policy_document}"',
                source,
            )


if __name__ == "__main__":
    unittest.main()
