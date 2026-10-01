#!/usr/bin/env python3
"""decision-log: an append-only decision log for coding-agent sessions.

Usage:
    dlog add "chose X" -r "because Y" [-t tag1,tag2] [--global]
    dlog list [--tag T] [--last N]
    dlog search QUERY
    dlog export-md [--tag T]
    dlog            # prints help

Stdlib only, Python 3.9+.
"""

import argparse
import datetime
import json
import os
import subprocess
import sys

LOCAL_NAME = ".dlog.jsonl"
GLOBAL_NAME = ".dlog.jsonl"
NO_LOG_MSG = "no decisions logged yet — use `dlog add \"title\" -r \"reason\"` to record one"


def _log_path(global_scope: bool) -> str:
    if global_scope:
        return os.path.join(os.path.expanduser("~"), GLOBAL_NAME)
    return os.path.join(os.getcwd(), LOCAL_NAME)


def _git_sha() -> "str | None":
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _read_log(path: str) -> list:
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def cmd_add(args) -> int:
    tags = []
    if args.tags:
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    entry = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "title": args.title,
        "reason": args.reason or "",
        "tags": tags,
        "cwd": os.getcwd(),
        "git": _git_sha(),
    }
    path = _log_path(args.global_)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"logged -> {path}")
    return 0


def _fmt_time(ts: str) -> str:
    try:
        dt = datetime.datetime.fromisoformat(ts)
        return dt.strftime("%m-%d %H:%M")
    except (ValueError, TypeError):
        return str(ts)


def cmd_list(args) -> int:
    path = _log_path(args.global_)
    if not os.path.exists(path):
        print(NO_LOG_MSG)
        return 0
    entries = _read_log(path)
    if args.tag:
        entries = [e for e in entries if args.tag in e.get("tags", [])]
    entries.reverse()  # newest first
    if args.last is not None:
        entries = entries[: args.last]
    if not entries:
        print(NO_LOG_MSG)
        return 0
    for e in entries:
        tags = " [" + ", ".join(e.get("tags", [])) + "]" if e.get("tags") else ""
        print(f"{_fmt_time(e.get('ts', ''))}  {e.get('title', '')}{tags}")
    return 0


def cmd_search(args) -> int:
    path = _log_path(args.global_)
    if not os.path.exists(path):
        print(NO_LOG_MSG)
        return 0
    q = args.query.lower()
    hits = [
        e
        for e in _read_log(path)
        if q in str(e.get("title", "")).lower()
        or q in str(e.get("reason", "")).lower()
        or any(q in str(t).lower() for t in e.get("tags", []))
    ]
    if not hits:
        print(f"no matches for {args.query!r}")
        return 0
    for e in reversed(hits):
        tags = " [" + ", ".join(e.get("tags", [])) + "]" if e.get("tags") else ""
        print(f"{_fmt_time(e.get('ts', ''))}  {e.get('title', '')}{tags}")
        if e.get("reason"):
            print(f"        {e['reason']}")
    return 0


def cmd_export_md(args) -> int:
    path = _log_path(args.global_)
    if not os.path.exists(path):
        print("<!-- no decisions logged yet -->")
        return 0
    entries = _read_log(path)
    if args.tag:
        entries = [e for e in entries if args.tag in e.get("tags", [])]
    if not entries:
        print("<!-- no decisions logged yet -->")
        return 0
    lines = ["# Decision Log", ""]
    for e in entries:
        lines.append(f"## {e.get('title', '')}")
        lines.append("")
        lines.append(f"- **When:** {_fmt_time(e.get('ts', ''))}")
        if e.get("tags"):
            lines.append(f"- **Tags:** {', '.join(e['tags'])}")
        if e.get("git"):
            lines.append(f"- **Git:** `{e['git']}`")
        if e.get("reason"):
            lines.append("")
            lines.append(str(e["reason"]))
        lines.append("")
    print("\n".join(lines).rstrip() + "\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dlog",
        description="Append-only decision log for coding-agent sessions.",
    )
    sub = p.add_subparsers(dest="cmd")

    def add_common(sp):
        sp.add_argument(
            "--global",
            dest="global_",
            action="store_true",
            help=f"use ~/{GLOBAL_NAME} instead of ./{LOCAL_NAME} in cwd",
        )

    a = sub.add_parser("add", help="record a decision")
    a.add_argument("title")
    a.add_argument("-r", "--reason", default="")
    a.add_argument("-t", "--tags", default="")
    add_common(a)

    l = sub.add_parser("list", help="list decisions, newest first")
    l.add_argument("--tag")
    l.add_argument("--last", type=int)
    add_common(l)

    s = sub.add_parser("search", help="case-insensitive substring search")
    s.add_argument("query")
    add_common(s)

    x = sub.add_parser("export-md", help="export as markdown for handoff docs")
    x.add_argument("--tag")
    add_common(x)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd is None:
        parser.print_help()
        return 0
    if args.cmd == "add":
        return cmd_add(args)
    if args.cmd == "list":
        return cmd_list(args)
    if args.cmd == "search":
        return cmd_search(args)
    if args.cmd == "export-md":
        return cmd_export_md(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
