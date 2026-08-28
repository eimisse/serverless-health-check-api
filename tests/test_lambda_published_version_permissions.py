from pathlib import Path
import unittest

from scripts.check_iam_wildcards import audit


ROOT = Path(__file__).resolve().parents[1]


def read_source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


class LambdaPublishedVersionPermissionTests(unittest.TestCase):
    """Regression coverage for Terraform polling newly published Lambda versions."""

    def test_published_version_permission_is_read_only_and_function_scoped(self):
        source = read_source(
            "bootstrap/deployment_lambda_published_version_read_permissions.tf"
        )

        self.assertIn('sid     = "ReadPublishedLambdaVersionConfiguration"', source)
        self.assertIn('actions = ["lambda:GetFunctionConfiguration"]', source)
        self.assertIn('"${local.resource_arns[each.key].function}:*"', source)
        self.assertIn(
            'role   = aws_iam_role.deployment[each.key].name',
            source,
        )

        for forbidden_action in (
            "lambda:AddPermission",
            "lambda:DeleteFunction",
            "lambda:InvokeFunction",
            "lambda:PublishVersion",
            "lambda:RemovePermission",
            "lambda:UpdateFunctionCode",
            "lambda:UpdateFunctionConfiguration",
        ):
            self.assertNotIn(forbidden_action, source)

    def test_mutating_lambda_permissions_remain_on_unqualified_function_only(self):
        source = read_source("bootstrap/deployment_permissions.tf")
        start = source.index('sid    = "ManageExactLambda"')
        end = source.index('sid    = "ManageExactDynamoDBTable"', start)
        statement = source[start:end]

        self.assertIn(
            'resources = [local.resource_arns[each.key].function]',
            statement,
        )
        self.assertNotIn('function}:*', statement)
        self.assertNotIn('function_alias', statement)

    def test_repository_wildcard_catalog_accepts_the_version_family(self):
        errors = audit(ROOT, ROOT / "security/iam-wildcard-exceptions.json")
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
