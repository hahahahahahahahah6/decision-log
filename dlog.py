#!/usr/bin/env python3
"""decision-log: an append-only decision log for coding-agent sessions.

Usage:
    dlog add "chose X" -r "because Y" [-t tag1,tag2] [--global]
    dlog list [--tag T] [--last N]
    dlog search QUERY
    dlog export-md [--tag T]
    dlog verify [--tag T] [--global]      # read-time gate: only entries whose
                                         # anchor commit still resolves are shown
    dlog gate --check <id>               # write-time gate: exit 0 iff the
                                         # decision id is recorded
    dlog assert-logged [id ...]          # bulk write-time gate (ids from args
                                         # or stdin); exit 2 on any missing
    dlog            # prints help

Two gates, two different jobs:
  * read-time (verify): enforced by the tool itself. An entry whose anchor
    commit no longer resolves in this repo is silently dropped from output.
  * write-time (gate/assert-logged): a protocol for your agent loop. Nothing
    can force an agent to call it; it binds cooperative loops, not
    adversarial ones. See README "The two gates" for the honest limits.

Stdlib only, Python 3.9+.
"""

import argparse
import datetime
import json
import os
import subprocess
import sys
import uuid

__version__ = "0.2.0"

LOCAL_NAME = ".dlog.jsonl"
GLOBAL_NAME = ".dlog.jsonl"
NO_LOG_MSG = "no decisions logged yet — use `dlog add \"title\" -r \"reason\"` to record one"


def _git_root() -> "str | None":
    """Repo top-level dir, or None when not inside a git repo. Never raises."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _log_path(global_scope: bool) -> str:
    if global_scope:
        return os.path.join(os.path.expanduser("~"), GLOBAL_NAME)
    # One log per repo: running from a subdirectory must not split the log.
    return os.path.join(_git_root() or os.getcwd(), LOCAL_NAME)


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


def _anchor_resolves(sha: str, repo: "str | None") -> bool:
    """True iff `sha` still resolves to a commit in this repo. Never raises.

    This is the read-time gate: the entry claims "recorded at commit <sha>".
    If the repo no longer contains that commit (rewritten history, tampered
    log line, or no repo here at all), the claim fails and the entry is
    dropped from output.
    """
    if not sha or not repo:
        return False
    try:
        out = subprocess.run(
            ["git", "cat-file", "-t", sha],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=repo,
        )
        return out.returncode == 0 and out.stdout.strip() == "commit"
    except (OSError, subprocess.SubprocessError):
        return False


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


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


def _find_entry(entries: list, key: str):
    """Match a decision by id first, then by exact title (v0.1 compat)."""
    for e in entries:
        if e.get("id") == key:
            return e
    for e in entries:
        if e.get("title") == key:
            return e
    return None


def cmd_add(args) -> int:
    tags = []
    if args.tags:
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    entry = {
        "id": _new_id(),
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
    print(f"logged -> {path} (id {entry['id']})")
    return 0


def _fmt_time(ts: str) -> str:
    try:
        dt = datetime.datetime.fromisoformat(ts)
        out = dt.strftime("%m-%d %H:%M")
        # Entries are stored in UTC; label them so readers don't assume local.
        return out + " UTC" if dt.tzinfo is not None else out
    except (ValueError, TypeError):
        return str(ts)


def _print_entries(entries: list) -> None:
    for e in entries:
        tags = " [" + ", ".join(e.get("tags", [])) + "]" if e.get("tags") else ""
        print(f"{_fmt_time(e.get('ts', ''))}  {e.get('title', '')}{tags}")


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
    _print_entries(entries)
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


def cmd_verify(args) -> int:
    """Read-time gate: show only entries whose anchor commit still resolves.

    Fail-closed: an entry whose sha cannot be confirmed (tampered line,
    rewritten history, or no repo available here) is not shown at all —
    a failed check makes the record disappear, not a red warning.
    Entries recorded outside a git repo (git: null) have no anchor to
    check and are shown as-is.
    """
    path = _log_path(args.global_)
    if not os.path.exists(path):
        print(NO_LOG_MSG)
        return 0
    repo = _git_root()
    entries = _read_log(path)
    if args.tag:
        entries = [e for e in entries if args.tag in e.get("tags", [])]
    kept, dropped = [], 0
    for e in entries:
        sha = e.get("git")
        if not sha:
            kept.append(e)  # no anchor to verify against; show as-is
        elif _anchor_resolves(sha, repo):
            kept.append(e)
        else:
            dropped += 1
    entries_out = list(reversed(kept))  # newest first
    if entries_out:
        _print_entries(entries_out)
    else:
        print(NO_LOG_MSG)
    reason = "anchor commit not found" if repo else "no git repo here to check anchors against"
    print(f"verify: {len(kept)} kept, {dropped} dropped ({reason})", file=sys.stderr)
    return 0


def cmd_gate(args) -> int:
    """Write-time gate: exit 0 iff the decision id was recorded.

    Meant for agent loops: `dlog gate --check <id> || exit 1` refuses to
    act on a decision that never went through the log.
    """
    path = _log_path(args.global_)
    entries = _read_log(path) if os.path.exists(path) else []
    key = args.check
    if _find_entry(entries, key) is not None:
        print(f"gate: {key} is logged")
        return 0
    print(
        f"gate: {key} is NOT logged — the decision was never recorded",
        file=sys.stderr,
    )
    return 2


def cmd_assert_logged(args) -> int:
    """Bulk write-time gate: every id (args or stdin, one per line) must be
    recorded, else exit 2 naming the missing ones."""
    path = _log_path(args.global_)
    entries = _read_log(path) if os.path.exists(path) else []
    ids = list(args.ids)
    if not ids and not sys.stdin.isatty():
        ids = [ln.strip() for ln in sys.stdin if ln.strip()]
    missing = [i for i in ids if _find_entry(entries, i) is None]
    if not missing:
        print(f"assert-logged: all {len(ids)} decision(s) recorded")
        return 0
    print(
        f"assert-logged FAILED: {len(missing)}/{len(ids)} not recorded: "
        + ", ".join(missing),
        file=sys.stderr,
    )
    return 2


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
            help=f"use ~/{GLOBAL_NAME} instead of ./{LOCAL_NAME} in the git repo root",
        )

    a = sub.add_parser("add", help="record a decision (prints its id)")
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

    v = sub.add_parser(
        "verify",
        help="read-time gate: show only entries whose git anchor still resolves",
    )
    v.add_argument("--tag")
    add_common(v)

    g = sub.add_parser(
        "gate",
        help="write-time gate: exit 0 iff a decision id was recorded",
    )
    g.add_argument("--check", required=True, metavar="ID",
                   help="decision id (or exact title for pre-0.2 entries)")
    add_common(g)

    al = sub.add_parser(
        "assert-logged",
        help="bulk write-time gate: all ids (args or stdin) must be recorded",
    )
    al.add_argument("ids", nargs="*", metavar="ID")
    add_common(al)

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
    if args.cmd == "verify":
        return cmd_verify(args)
    if args.cmd == "gate":
        return cmd_gate(args)
    if args.cmd == "assert-logged":
        return cmd_assert_logged(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
