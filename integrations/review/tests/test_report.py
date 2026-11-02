from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from integrations.review.report import ReviewError, build_review_report


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


class ReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "test@example.com")
        git(self.repo, "config", "user.name", "Test")
        (self.repo / "service.py").write_text("def original():\n    return 1\n")
        (self.repo / "related.py").write_text("def dependent():\n    return 1\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "baseline")
        self.base = git(self.repo, "rev-parse", "HEAD")
        self.fake = self.root / "fake-codeintel.py"
        self.fake.write_text("""import json
import sys
if sys.argv[1] != 'context':
    sys.exit(3)
print(json.dumps({'task': sys.argv[2], 'files': [
    {'path': 'service.py', 'score': 0.6},
    {'path': 'related.py', 'score': 0.2}
]}))
""")
        self.cmd = [sys.executable, str(self.fake)]

    def commit(self, filename: str = "service.py", content: str = "def updated():\n    return 2\n") -> str:
        (self.repo / filename).write_text(content)
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "change")
        return git(self.repo, "rev-parse", "HEAD")

    def report(self, head: str, **kwargs):
        return build_review_report(self.repo, self.base, head, codeintel_command=self.cmd, **kwargs)

    def test_changed_file_and_adjacent_context_are_evidence_not_findings(self):
        head = self.commit()
        result = self.report(head)
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["status"], "context_ready")
        self.assertEqual(result["base_sha"], self.base)
        self.assertEqual(result["head_sha"], head)
        self.assertEqual(result["changed_files"], ["service.py"])
        self.assertEqual([x["path"] for x in result["context_files"]], ["service.py", "related.py"])
        self.assertEqual(result["findings"], [])
        self.assertFalse(result["validated"])

    def test_no_diff_skips_codeintel(self):
        self.fake.unlink()
        result = self.report(self.base)
        self.assertEqual(result["status"], "no_changes")
        self.assertEqual(result["context_files"], [])

    def test_deleted_files_are_not_considered_editable(self):
        (self.repo / "service.py").unlink()
        head = self.commit("another.py", "ok\n")
        self.assertEqual(self.report(head)["changed_files"], ["another.py"])

    def test_filename_with_spaces_is_handled_without_shell_expansion(self):
        head = self.commit("two words.py", "value = 3\n")
        self.assertIn("two words.py", self.report(head)["changed_files"])

    def test_invalid_revision_fails_closed(self):
        with self.assertRaises(ReviewError):
            self.report("--output=/tmp/unsafe")

    def test_bad_json_fails_closed(self):
        self.fake.write_text("print('not-json')\n")
        with self.assertRaises(ReviewError):
            self.report(self.commit())

    def test_failed_codeintel_fails_closed(self):
        self.fake.write_text("raise SystemExit(9)\n")
        with self.assertRaises(ReviewError):
            self.report(self.commit())

    def test_codeintel_context_paths_outside_repository_are_discarded(self):
        self.fake.write_text("""import json
print(json.dumps({'files': [
 {'path':'../../secrets.txt', 'score':4},
 {'path':'/etc/passwd', 'score':3},
 {'path':'service.py', 'score': 1},
 {'path':'service.py', 'score': 0.5}
]}))
""")
        result = self.report(self.commit())
        self.assertEqual([x["path"] for x in result["context_files"]], ["service.py"])

    def test_head_must_match_checked_out_commit(self):
        self.commit()
        with self.assertRaises(ReviewError):
            self.report(self.base)

    def test_dirty_checkout_is_rejected(self):
        head = self.commit()
        (self.repo / "service.py").write_text("uncommitted edit\n")
        with self.assertRaises(ReviewError):
            self.report(head)

    def test_nonfinite_context_score_is_not_emitted(self):
        self.fake.write_text("print('{\"files\":[{\"path\":\"service.py\",\"score\":NaN}]}')\n")
        head = self.commit()
        self.assertIsNone(self.report(head)["context_files"][0]["score"])

    def test_too_many_changed_files_is_rejected(self):
        self.commit("one.py")
        with self.assertRaises(ReviewError):
            self.report(git(self.repo, "rev-parse", "HEAD"), max_files=0)


if __name__ == "__main__":
    unittest.main()
