"""Tests for the deterministic Lambda packager."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts import package_lambda


class PackageLambdaTests(unittest.TestCase):
    def test_package_is_minimal_and_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "lambda.zip"

            first_digest = package_lambda.build(output)
            first_bytes = output.read_bytes()
            second_digest = package_lambda.build(output)

            self.assertEqual(first_bytes, output.read_bytes())
            self.assertEqual(first_digest, second_digest)
            self.assertEqual(hashlib.sha256(first_bytes).hexdigest(), first_digest)

            with zipfile.ZipFile(output) as archive:
                self.assertEqual(["handler.py"], archive.namelist())
                member = archive.getinfo("handler.py")
                self.assertEqual(package_lambda.FIXED_ZIP_TIME, member.date_time)
                self.assertEqual(3, member.create_system)
                self.assertEqual(0o644, (member.external_attr >> 16) & 0o777)
                self.assertEqual(zipfile.ZIP_STORED, member.compress_type)
                self.assertEqual(
                    (package_lambda.LAMBDA_DIR / "handler.py").read_bytes(),
                    archive.read("handler.py"),
                )


if __name__ == "__main__":
    unittest.main()
