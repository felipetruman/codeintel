from __future__ import annotations

import io
import json
from unittest import TestCase
from unittest.mock import patch

from integrations.review.cli import main
from integrations.review.report import ReviewError


class CliTests(TestCase):
    def test_json_report_on_stdout(self):
        expected = {"status": "no_changes", "validated": False}
        with patch("integrations.review.cli.build_review_report", return_value=expected) as build:
            with patch("sys.stdout", new_callable=io.StringIO) as stdout:
                code = main(["--repo", ".", "--base", "main", "--head", "HEAD"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue()), expected)
        self.assertEqual(build.call_args.args[1:], ("main", "HEAD"))

    def test_failure_does_not_publish_json_as_success(self):
        with patch("integrations.review.cli.build_review_report", side_effect=ReviewError("failure")):
            with patch("sys.stdout", new_callable=io.StringIO) as stdout:
                with patch("sys.stderr", new_callable=io.StringIO) as stderr:
                    code = main(["--base", "unknown", "--head", "HEAD"])
        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("failure", stderr.getvalue())
