"""Public requirements-lock audit checks with synthetic, non-secret inputs."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from scripts.check_public_tree import inspect_file, main


class PublicTreeTests(unittest.TestCase):
    def test_lock_content_is_scanned_including_comments(self):
        # Construct fake paths/IPs so the test source itself stays publishable.
        fixtures = (
            ("# build: " + "C:/" + "Users/" + "example-user/pkg", "user-home-path"),
            ("# mirror: https://" + "192.168." + "1.2/simple", "private-ip"),
        )
        for text, rule in fixtures:
            for name in ("example.lock", "example.LOCK"):
                with self.subTest(name=name, rule=rule):
                    self.assertIn((rule, 1), list(inspect_file(name, text.encode())))

    def test_lock_rejects_embedded_sources_and_local_dependencies(self):
        cases = (
            ("--index-url https://packages.example.invalid/simple", "lock-source-option"),
            ("--extra-index-url=https://packages.example.invalid/simple", "lock-source-option"),
            ("-ihttps://packages.example.invalid/simple", "lock-source-option"),
            ("--find-links ../wheels", "lock-source-option"),
            ("-f ../wheels", "lock-source-option"),
            ("-r ../requirements.txt", "lock-source-option"),
            ("--constraint=../constraints.txt", "lock-source-option"),
            ("-e ../example", "lock-editable"),
            ("-e../example", "lock-editable"),
            ("--editable=../example", "lock-editable"),
            ("example @ https://packages.example.invalid/example.whl", "lock-source-url"),
            ("example @ file:///D:/build/example.whl", "lock-local-path"),
            ("example @ ../example.whl", "lock-local-path"),
            ("D:\\build\\example.whl", "lock-local-path"),
            ("/srv/build/example.whl", "lock-local-path"),
            ("vendor/example.whl", "lock-local-path"),
            ("example-1.0-py3-none-any.whl", "lock-local-archive"),
            ("example @ example-1.0.tar.gz", "lock-local-archive"),
        )
        for text, rule in cases:
            with self.subTest(text=text):
                self.assertIn((rule, 1), list(inspect_file("example.lock", text.encode())))

    def test_lock_accepts_pins_hashes_markers_and_public_comments(self):
        text = (
            "# Source policy: https://pypi.org/simple\n"
            "example-package[extra]==1.2.3 ; python_version >= '3.10' \\\n"
            "    --hash=sha256:" + "a" * 64 + " \\\n"
            "    --hash=sha256:" + "b" * 64 + "\n"
            "    # via example-parent\n"
        )
        self.assertEqual(list(inspect_file("example.lock", text.encode())), [])

    def test_staged_audit_fails_without_printing_matched_values(self):
        value = "--index-url https://packages.example.invalid/simple"
        output = io.StringIO()
        with patch("sys.argv", ["check_public_tree.py", "--staged"]), patch(
            "scripts.check_public_tree.git",
            side_effect=[b"example.lock\0", value.encode()],
        ), redirect_stdout(output), self.assertRaises(SystemExit) as result:
            main()
        self.assertEqual(result.exception.code, 1)
        self.assertIn("example.lock:1: lock-source-option", output.getvalue())
        self.assertNotIn("packages.example.invalid", output.getvalue())


if __name__ == "__main__":
    unittest.main()
