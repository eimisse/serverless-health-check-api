"""Regression tests for API Gateway generated-resource tag guardrails."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "bootstrap" / "deployment_api_gateway_guardrails.tf"


class ApiGatewayTagGuardrailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.tag_section = cls.source.split(
            "# API Gateway authorizes inline create tags through PUT on /tags/<encoded ARN>.",
            maxsplit=1,
        )[1].split(
            'resource "aws_iam_role_policy" "deployment_api_gateway_guardrails"',
            maxsplit=1,
        )[0]

    def test_tag_pseudo_resource_uses_supported_condition_keys(self) -> None:
        for sid in (
            "DenyUnexpectedApiGatewayTagKeys",
            "DenyWrongEnvironmentBoundaryTag",
            "DenyWrongProjectBoundaryTag",
            "DenyWrongManagedByTag",
            "DenyWrongRepositoryTag",
            "DenyRemovingApiGatewayBoundaryTags",
        ):
            self.assertIn(sid, self.tag_section)

        self.assertIn('variable = "aws:RequestTag/Environment"', self.tag_section)
        self.assertIn('variable = "aws:RequestTag/Project"', self.tag_section)
        self.assertIn('variable = "aws:TagKeys"', self.tag_section)
        self.assertNotIn('variable = "aws:ResourceTag/', self.tag_section)

    def test_only_reviewed_application_tag_keys_can_be_mutated(self) -> None:
        statement = self.tag_section.split(
            'sid    = "DenyUnexpectedApiGatewayTagKeys"', maxsplit=1
        )[1].split("\n  statement {", maxsplit=1)[0]

        self.assertIn('test     = "ForAnyValue:StringNotEquals"', statement)
        for key in (
            "Environment",
            "ManagedBy",
            "Name",
            "Project",
            "Repository",
            "Workload",
        ):
            self.assertIn(f'"{key}"', statement)

    def test_security_boundary_tag_values_are_immutable(self) -> None:
        expected = {
            "DenyWrongEnvironmentBoundaryTag": "aws:RequestTag/Environment",
            "DenyWrongProjectBoundaryTag": "aws:RequestTag/Project",
            "DenyWrongManagedByTag": "aws:RequestTag/ManagedBy",
            "DenyWrongRepositoryTag": "aws:RequestTag/Repository",
        }
        for sid, condition_key in expected.items():
            with self.subTest(sid=sid):
                statement = self.tag_section.split(sid, maxsplit=1)[1].split(
                    "\n  statement {", maxsplit=1
                )[0]
                self.assertIn('actions   = ["apigateway:PUT"]', statement)
                self.assertIn('test     = "Null"', statement)
                self.assertIn('values   = ["false"]', statement)
                self.assertIn(f'variable = "{condition_key}"', statement)
                self.assertIn('test     = "StringNotEquals"', statement)

    def test_environment_and_project_tags_cannot_be_removed(self) -> None:
        statement = self.tag_section.split(
            'sid       = "DenyRemovingApiGatewayBoundaryTags"', maxsplit=1
        )[1].split("\n  statement {", maxsplit=1)[0]

        self.assertIn('actions   = ["apigateway:DELETE"]', statement)
        self.assertIn('test     = "ForAnyValue:StringEquals"', statement)
        self.assertIn('"Environment"', statement)
        self.assertIn('"Project"', statement)


if __name__ == "__main__":
    unittest.main()
