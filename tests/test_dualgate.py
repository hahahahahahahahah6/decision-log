"""Tests for the v0.2 dual gates: read-time verify + write-time gate."""
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dlog


@contextmanager
def tmp_cwd():
    with tempfile.TemporaryDirectory() as d:
        prev = os.getcwd()
        os.chdir(d)
        try:
            yield d
        finally:
            os.chdir(prev)


def git_repo():
    """A tmp git repo with one real commit; yields (dir, short-sha)."""
    d = tempfile.TemporaryDirectory()
    subprocess.run(["git", "init", "-q", d.name], check=True, timeout=15)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=d.name,
                   check=True, timeout=15)
    subprocess.run(["git", "config", "user.name", "t"], cwd=d.name,
                   check=True, timeout=15)
    with open(os.path.join(d.name, "f.txt"), "w") as f:
        f.write("x")
    subprocess.run(["git", "add", "."], cwd=d.name, check=True, timeout=15)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=d.name,
                   check=True, timeout=15)
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True, cwd=d.name,
                         check=True, timeout=15).stdout.strip()
    return d, sha


def run(args, stdin_data=None):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        if stdin_data is not None:
            with patch.object(sys, "stdin", io.StringIO(stdin_data)):
                rc = dlog.main(args)
        else:
            rc = dlog.main(args)
    return rc, out.getvalue(), err.getvalue()


def last_id(out):
    m = re.search(r"\(id ([0-9a-f]{12})\)", out)
    assert m, f"no id in add output: {out!r}"
    return m.group(1)


class TestReadTimeVerify(unittest.TestCase):
    def test_verify_keeps_valid_anchor(self):
        repo, sha = git_repo()
        prev = os.getcwd()
        os.chdir(repo.name)
        try:
            run(["add", "anchored decision", "-r", "at commit"])
            rc, out, err = run(["verify"])
            self.assertEqual(rc, 0)
            self.assertIn("anchored decision", out)
            self.assertIn("1 kept, 0 dropped", err)
        finally:
            os.chdir(prev)
            repo.cleanup()

    def test_verify_drops_tampered_sha(self):
        """Tampering the sha makes the entry disappear, not get flagged."""
        repo, sha = git_repo()
        prev = os.getcwd()
        os.chdir(repo.name)
        try:
            run(["add", "real one", "-r", "x"])
            run(["add", "tampered one", "-r", "x"])
            # rewrite the second entry's sha to a bogus value
            path = os.path.join(repo.name, ".dlog.jsonl")
            lines = open(path, encoding="utf-8").read().splitlines()
            e = json.loads(lines[1])
            e["git"] = "deadbee"
            lines[1] = json.dumps(e)
            open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")

            rc, out, err = run(["verify"])
            self.assertEqual(rc, 0)
            self.assertIn("real one", out)
            self.assertNotIn("tampered one", out)  # disappeared, not flagged
            self.assertIn("1 kept, 1 dropped", err)
        finally:
            os.chdir(prev)
            repo.cleanup()

    def test_verify_keeps_entries_without_anchor(self):
        """Entries recorded outside a repo (git: null) have nothing to
        check against; verify shows them as-is."""
        with tmp_cwd():
            run(["add", "no-repo decision", "-r", "x"])
            rc, out, err = run(["verify"])
            self.assertEqual(rc, 0)
            self.assertIn("no-repo decision", out)
            self.assertIn("1 kept, 0 dropped", err)

    def test_verify_respects_tag_filter(self):
        repo, _ = git_repo()
        prev = os.getcwd()
        os.chdir(repo.name)
        try:
            run(["add", "db choice", "-r", "x", "-t", "db"])
            run(["add", "ui choice", "-r", "x", "-t", "ui"])
            rc, out, _ = run(["verify", "--tag", "db"])
            self.assertEqual(rc, 0)
            self.assertIn("db choice", out)
            self.assertNotIn("ui choice", out)
        finally:
            os.chdir(prev)
            repo.cleanup()

    def test_verify_missing_file_friendly(self):
        with tmp_cwd():
            rc, out, err = run(["verify"])
            self.assertEqual(rc, 0)
            self.assertIn("no decisions logged yet", out)
            self.assertNotIn("Traceback", err)


class TestWriteTimeGate(unittest.TestCase):
    def test_add_prints_id_and_entry_has_id(self):
        with tmp_cwd():
            rc, out, _ = run(["add", "id check", "-r", "x"])
            self.assertEqual(rc, 0)
            entry_id = last_id(out)
            entries = dlog._read_log(".dlog.jsonl")
            self.assertEqual(entries[0]["id"], entry_id)

    def test_gate_check_logged_id_passes(self):
        with tmp_cwd():
            _, out, _ = run(["add", "gated decision", "-r", "x"])
            entry_id = last_id(out)
            rc, out2, _ = run(["gate", "--check", entry_id])
            self.assertEqual(rc, 0)
            self.assertIn("is logged", out2)

    def test_gate_check_unknown_id_fails(self):
        with tmp_cwd():
            run(["add", "something", "-r", "x"])
            rc, out, err = run(["gate", "--check", "000000000000"])
            self.assertEqual(rc, 2)
            self.assertIn("NOT logged", err)
            self.assertEqual(out.strip(), "")

    def test_gate_matches_pre02_entry_by_exact_title(self):
        """v0.1 entries have no id; exact title still gates."""
        with tmp_cwd():
            path = ".dlog.jsonl"
            old = {"ts": "2026-10-01T00:00:00+00:00", "title": "legacy pick",
                   "reason": "old", "tags": [], "cwd": "/tmp", "git": None}
            with open(path, "w", encoding="utf-8") as f:
                f.write(json.dumps(old) + "\n")
            rc, out, _ = run(["gate", "--check", "legacy pick"])
            self.assertEqual(rc, 0)
            self.assertIn("is logged", out)

    def test_assert_logged_all_recorded(self):
        with tmp_cwd():
            _, o1, _ = run(["add", "one", "-r", "x"])
            _, o2, _ = run(["add", "two", "-r", "x"])
            rc, out, _ = run(["assert-logged", last_id(o1), last_id(o2)])
            self.assertEqual(rc, 0)
            self.assertIn("all 2 decision(s) recorded", out)

    def test_assert_logged_names_missing(self):
        with tmp_cwd():
            _, o1, _ = run(["add", "one", "-r", "x"])
            rc, out, err = run(["assert-logged", last_id(o1), "ffffffffff00"])
            self.assertEqual(rc, 2)
            self.assertIn("ffffffffff00", err)
            self.assertIn("FAILED", err)
            self.assertEqual(out.strip(), "")

    def test_assert_logged_reads_ids_from_stdin(self):
        with tmp_cwd():
            _, o1, _ = run(["add", "one", "-r", "x"])
            rc, out, _ = run(["assert-logged"], stdin_data=last_id(o1) + "\n")
            self.assertEqual(rc, 0)
            self.assertIn("recorded", out)


if __name__ == "__main__":
    unittest.main()
