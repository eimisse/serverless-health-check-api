import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_iam_wildcards import audit


class IamWildcardAuditTests(unittest.TestCase):
    def _write_catalog(self, root: Path, exceptions):
        security = root / "security"
        security.mkdir(parents=True, exist_ok=True)
        path = security / "iam-wildcard-exceptions.json"
        path.write_text(json.dumps({"exceptions": exceptions}), encoding="utf-8")
        return path

    def test_rejects_uncatalogued_resource_wildcard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bootstrap = root / "bootstrap"
            bootstrap.mkdir()
            (bootstrap / "policy.tf").write_text(
                'statement {\n  sid = "Bad"\n  resources = ["*"]\n}\n',
                encoding="utf-8",
            )
            catalog = self._write_catalog(root, [])
            errors = audit(root, catalog)
            self.assertTrue(any("unreviewed wildcard" in error for error in errors))

    def test_rejects_wildcard_action_even_if_catalogued(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            terraform = root / "terraform"
            terraform.mkdir()
            (terraform / "policy.tf").write_text(
                'statement {\n  sid = "BadAction"\n  actions = ["kms:*"]\n}\n',
                encoding="utf-8",
            )
            catalog = self._write_catalog(root, [])
            errors = audit(root, catalog)
            self.assertTrue(any("wildcard IAM action" in error for error in errors))

    def test_accepts_exact_catalogued_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bootstrap = root / "bootstrap"
            bootstrap.mkdir()
            (bootstrap / "policy.tf").write_text(
                'statement {\n  sid = "DescribeOnly"\n  resources = ["*"]\n}\n',
                encoding="utf-8",
            )
            catalog = self._write_catalog(
                root,
                [
                    {
                        "id": "TEST-DESCRIBE",
                        "path": "bootstrap/policy.tf",
                        "sid": "DescribeOnly",
                        "literal": "*",
                        "expected_count": 1,
                        "reason": "The synthetic test models an AWS list operation without resource-level authorization.",
                    }
                ],
            )
            self.assertEqual(audit(root, catalog), [])

    def test_fails_if_catalog_entry_becomes_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bootstrap = root / "bootstrap"
            bootstrap.mkdir()
            (bootstrap / "policy.tf").write_text(
                'statement {\n  sid = "DescribeOnly"\n  resources = ["arn:aws:logs:eu-west-1:123456789012:log-group:exact"]\n}\n',
                encoding="utf-8",
            )
            catalog = self._write_catalog(
                root,
                [
                    {
                        "id": "TEST-STALE",
                        "path": "bootstrap/policy.tf",
                        "sid": "DescribeOnly",
                        "literal": "*",
                        "expected_count": 1,
                        "reason": "This intentionally stale exception must be detected and removed by the audit.",
                    }
                ],
            )
            errors = audit(root, catalog)
            self.assertTrue(any("catalog mismatch" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
