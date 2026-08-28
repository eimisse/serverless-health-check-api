"""Static CI/CD security invariants that run without GitHub or AWS access."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
SHA40_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
USES_RE = re.compile(r"^\s*uses:\s*([^\s#]+)", re.MULTILINE)


def read(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


class WorkflowSecurityTests(unittest.TestCase):
    def test_reusable_ci_has_no_aws_oidc_permission(self) -> None:
        ci = read("ci.yml")
        self.assertIn("workflow_call:", ci)
        self.assertNotIn("id-token: write", ci)
        self.assertNotIn("aws-actions/configure-aws-credentials", ci)
        self.assertIn("permissions:\n  contents: read", ci)

    def test_deployments_require_credential_free_quality_gate(self) -> None:
        for filename, environment in (
            ("deploy-staging.yml", "staging"),
            ("deploy-prod.yml", "prod"),
        ):
            with self.subTest(filename=filename):
                workflow = read(filename)
                self.assertIn("uses: ./.github/workflows/ci.yml", workflow)
                self.assertIn("needs: quality-gate", workflow)
                self.assertEqual(1, workflow.count("id-token: write"))
                self.assertIn(f"environment: {environment}", workflow)
                self.assertLess(
                    workflow.index("uses: ./.github/workflows/ci.yml"),
                    workflow.index("id-token: write"),
                )

    def test_live_read_preflight_runs_after_oidc_and_before_plan_or_apply(self) -> None:
        for filename, environment, plan_marker, apply_marker in (
            (
                "deploy-staging.yml",
                "staging",
                "Create saved staging plan",
                "Apply exact reviewed staging plan",
            ),
            (
                "deploy-prod.yml",
                "prod",
                "Create saved prod plan",
                "Apply exact approved prod plan",
            ),
        ):
            with self.subTest(filename=filename):
                workflow = read(filename)
                preflight = "Preflight live deployment-role read capabilities"
                self.assertEqual(1, workflow.count(preflight))
                self.assertEqual(1, workflow.count("scripts/preflight_deployment_role.py"))
                self.assertIn(f"--environment {environment}", workflow)
                self.assertIn('--expected-account "${expected_account}"', workflow)
                self.assertLess(
                    workflow.index("aws-actions/configure-aws-credentials"),
                    workflow.index(preflight),
                )
                self.assertLess(workflow.index(preflight), workflow.index(plan_marker))
                self.assertLess(workflow.index(preflight), workflow.index(apply_marker))

    def test_production_remains_manual_only(self) -> None:
        workflow = read("deploy-prod.yml")
        on_block = workflow.split("permissions:", 1)[0]
        self.assertIn("workflow_dispatch:", on_block)
        self.assertNotIn("push:", on_block)
        self.assertNotIn("pull_request:", on_block)

    def test_workflows_do_not_enable_static_aws_credentials(self) -> None:
        forbidden = (
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
        )
        for path in sorted(WORKFLOWS.glob("*.yml")):
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                with self.subTest(path=path.name, token=token):
                    self.assertNotIn(token, text)

    def test_external_actions_are_pinned_to_full_commit_sha(self) -> None:
        for path in sorted(WORKFLOWS.glob("*.yml")):
            text = path.read_text(encoding="utf-8")
            for reference in USES_RE.findall(text):
                if reference.startswith("./"):
                    continue
                with self.subTest(path=path.name, reference=reference):
                    self.assertIn("@", reference)
                    _, ref = reference.rsplit("@", 1)
                    self.assertRegex(ref, SHA40_RE)

    def test_checkout_credentials_are_never_persisted(self) -> None:
        for path in sorted(WORKFLOWS.glob("*.yml")):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertNotIn("persist-credentials: true", text)

    def test_pull_request_target_is_not_used(self) -> None:
        for path in sorted(WORKFLOWS.glob("*.yml")):
            with self.subTest(path=path.name):
                self.assertNotIn(
                    "pull_request_target:", path.read_text(encoding="utf-8")
                )


if __name__ == "__main__":
    unittest.main()
