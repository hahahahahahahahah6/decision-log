"""Smoke tests for dlog (decision-log). stdlib only; all tests use tmp dirs."""
import io
import json
import os
import sys
import unittest
from contextlib import contextmanager, redirect_stdout
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dlog


@contextmanager
def tmp_cwd(tmpdir):
    """Run inside a fresh tmp dir as cwd."""
    with __import__("tempfile").TemporaryDirectory() as d:
        prev = os.getcwd()
        os.chdir(d)
        try:
            yield d
        finally:
            os.chdir(prev)


@contextmanager
def tmp_home():
    """Run with HOME pointed at a tmp dir."""
    with __import__("tempfile").TemporaryDirectory() as d:
        with patch.dict(os.environ, {"HOME": d}):
            # expanduser caches HOME? no, it reads env each call. OK.
            yield d


def run(args):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = dlog.main(args)
    return rc, buf.getvalue()


class TestSmoke(unittest.TestCase):
    def test_add_list_roundtrip(self):
        with tmp_cwd(None):
            rc, _ = run(["add", "chose sqlite", "-r", "zero deps"])
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(".dlog.jsonl"))
            with open(".dlog.jsonl", encoding="utf-8") as f:
                entry = json.loads(f.readline())
            self.assertEqual(entry["title"], "chose sqlite")
            self.assertEqual(entry["reason"], "zero deps")
            self.assertIn("ts", entry)
            self.assertIn("cwd", entry)
            rc, out = run(["list"])
            self.assertEqual(rc, 0)
            self.assertIn("chose sqlite", out)

    def test_add_tags_and_filter(self):
        with tmp_cwd(None):
            run(["add", "used redis", "-r", "cache", "-t", "infra,db"])
            run(["add", "chose blue theme", "-r", "looks nice", "-t", "ui"])
            rc, out = run(["list", "--tag", "infra"])
            self.assertEqual(rc, 0)
            self.assertIn("used redis", out)
            self.assertNotIn("chose blue theme", out)

    def test_list_last_n(self):
        with tmp_cwd(None):
            for i in range(3):
                run(["add", f"decision {i}", "-r", "x"])
            rc, out = run(["list", "--last", "2"])
            self.assertEqual(rc, 0)
            self.assertIn("decision 2", out)
            self.assertIn("decision 1", out)
            self.assertNotIn("decision 0", out)

    def test_search_finds_and_misses(self):
        with tmp_cwd(None):
            run(["add", "migrate to postgres", "-r", "sqlite hit locking issues", "-t", "db"])
            rc, out = run(["search", "postgres"])
            self.assertEqual(rc, 0)
            self.assertIn("migrate to postgres", out)
            rc, out = run(["search", "locking"])
            self.assertIn("migrate to postgres", out)
            rc, out = run(["search", "kubernetes"])
            self.assertEqual(rc, 0)
            self.assertIn("no matches", out)

    def test_export_md_contains_entries(self):
        with tmp_cwd(None):
            run(["add", "dropped tailwind", "-r", "bundle size too big", "-t", "css"])
            rc, out = run(["export-md"])
            self.assertEqual(rc, 0)
            self.assertIn("## dropped tailwind", out)
            self.assertIn("bundle size too big", out)

    def test_missing_file_friendly(self):
        with tmp_cwd(None):
            for cmd in (["list"], ["search", "foo"], ["export-md"]):
                rc, out = run(cmd)
                self.assertEqual(rc, 0)
                self.assertNotIn("Traceback", out)
            rc, out = run(["list"])
            self.assertIn("no decisions logged yet", out)

    def test_global_writes_to_home(self):
        with tmp_cwd(None):
            with tmp_home() as home:
                rc, _ = run(["add", "global call", "-r", "y", "--global"])
                self.assertEqual(rc, 0)
                gpath = os.path.join(home, ".dlog.jsonl")
                self.assertTrue(os.path.exists(gpath))
                self.assertFalse(os.path.exists(".dlog.jsonl"))
                rc, out = run(["list", "--global"])
                self.assertEqual(rc, 0)
                self.assertIn("global call", out)

    def test_no_args_prints_help(self):
        rc, out = run([])
        self.assertEqual(rc, 0)
        self.assertIn("usage", out.lower())


if __name__ == "__main__":
    unittest.main()
