# decision-log

An append-only decision log for coding-agent sessions.

Coding agents make dozens of decisions per session — which library, which schema, which approach — and never write them down. The next session rediscovers all of it: same debates, same wrong turns, same "wait, why did we do it this way?"

Memory only holds what gets saved. If nobody saves the decision, it isn't there.

`dlog` is the 30-second habit that fixes this: `dlog add "chose X" -r "because Y"`. One line, appended to a JSONL file, searchable later and exportable to markdown for session handoffs.

v0.2 adds **two gates** around the log: `dlog verify` re-checks every entry's git anchor at read time (entries that fail verification are silently dropped), and `dlog gate --check <id>` / `dlog assert-logged` let your agent loop refuse to act on decisions that were never recorded.

## Install

Stdlib only, Python 3.9+. No dependencies, no network, no accounts.

```bash
pip install decision-log
# `dlog` is now on your PATH
```

Or the single-file way:

```bash
curl -O https://raw.githubusercontent.com/hahahahahahahahah6/decision-log/main/dlog.py
chmod +x dlog.py
# optionally: put dlog.py on your PATH as `dlog`
```

## Usage

```bash
$ dlog add "chose sqlite over postgres" -r "single-file, zero deps, enough for v1" -t db,infra
logged -> ./.dlog.jsonl (id 9f2ac41d7e03)

$ dlog add "dropped tailwind" -r "bundle size too big, hand-rolled css instead" -t css
logged -> ./.dlog.jsonl (id 51b8d0c94aa2)

$ dlog list
10-11 08:31  dropped tailwind [css]
10-11 08:30  chose sqlite over postgres [db, infra]

$ dlog list --tag db
10-11 08:30  chose sqlite over postgres [db, infra]

$ dlog search locking
10-11 08:30  chose sqlite over postgres [db, infra]
        single-file, zero deps, enough for v1

$ dlog export-md
# Decision Log

## chose sqlite over postgres

- **When:** 10-11 08:30 UTC
- **Tags:** db, infra
- **Git:** `a1b2c3d`

single-file, zero deps, enough for v1
```

Flags:

- `dlog add "title" -r "reason" [-t tag1,tag2]` — appends `{"id", "ts", "title", "reason", "tags", "cwd", "git"}` to `.dlog.jsonl` in the git repo root (or cwd outside a repo). `git` is the short commit sha, or `null` outside a repo. Prints the entry's `id`.
- `--global` on any command writes to `~/.dlog.jsonl` instead (a personal log across projects).
- `dlog list [--tag T] [--last N]` — newest-first table.
- `dlog search QUERY` — case-insensitive substring over title + reason + tags.
- `dlog export-md [--tag T]` — markdown with `##` entries, ready to paste into a handoff doc.
- `dlog verify [--tag T]` — read-time gate: re-checks every entry's git anchor and shows only entries that still verify. Fail-closed: an entry that fails verification is not shown at all (not flagged, not warned — it disappears). See "The two gates" below.
- `dlog gate --check <id>` — write-time gate: exits 0 and prints `gate: <id> is logged` if the decision id is recorded; exits 2 otherwise. Exact titles also match (for pre-0.2 entries, which have no id).
- `dlog assert-logged [id ...]` — bulk write-time gate: ids from args or stdin (one per line); exits 0 if all are recorded, exits 2 naming the missing ones.
- `dlog` with no args prints help. A missing log file prints "no decisions logged yet" and exits 0 — never a traceback.

## The two gates

### Gate 1 — read-time verify (enforced)

Every entry records the short commit sha it was written at — its *anchor*. `dlog verify` re-resolves each anchor against the current repo (`git cat-file -t <sha>` must be a commit). An entry whose anchor no longer resolves — tampered log line, rewritten history, force-pushed branch — is **silently dropped from output**. The summary goes to stderr so pipes still work:

```bash
$ dlog verify
10-11 08:30  chose sqlite over postgres [db, infra]
verify: 1 kept, 1 dropped (anchor commit not found)
```

This gate is enforced by the tool itself: `dlog` simply does not display what it cannot verify. `list`, `search`, and `export-md` stay fast and unverified on purpose — reach for `verify` when the record needs to be trustworthy.

### Gate 2 — write-time gate (a protocol, not physics)

A decision that never went through `dlog` never happened — but only if your loop actually checks. The write-time gate is a convention for agent loops:

```bash
# 1. Record the decision, capture its id
ID=$(dlog add "chose sqlite over postgres" -r "single-file, zero deps" | grep -oE '\(id [0-9a-f]{12}\)' | grep -oE '[0-9a-f]{12}')

# ... do the work ...

# 2. Before acting on the decision, refuse to proceed unless it was recorded
dlog gate --check "$ID" || exit 1

# Or bulk-check a whole plan at once:
printf '%s\n' "$ID1" "$ID2" "$ID3" | dlog assert-logged || exit 1
```

`dlog gate --check` exits 0 when the id is recorded and 2 when it isn't, so it composes with `&&`/`||`, `set -e`, pre-action hooks, and CI steps.

### Honest limitations

This is where most "agent memory" tools get vague, so let's be precise:

- **Read-time verify proves the anchor still exists, not that the text is unchanged.** The log is a plain JSONL file: someone with write access can rewrite an entry's text around a still-valid sha. `verify` catches anchor tampering (the cheap, common kind) — not text tampering. If that threat matters, commit the log file itself to git.
- **Entries recorded outside a git repo (`git: null`) have no anchor.** `verify` shows them as-is and says so in the summary. Verification needs a repo; without one there is nothing to check against.
- **The write-time gate is a protocol, not enforcement.** Nothing in `dlog` can force an agent to call `gate --check`. It binds cooperative agents that wire it into their loop; it cannot bind an agent that skips the call or fabricates the log. We ship the mechanism and the tests — we don't claim to solve agent compliance.
- **Why both?** A reader ran honesty experiments on frontier models: asked plainly, models said "I don't know" 0/8 times right; asked with leading questions, they confidently fabricated 8/8. The takeaway — *"empty, verified, wrong"* — is that read-time verification only protects what was written down. The real loss happens at write time, when the decision is never recorded at all. The read-time gate is the one we can enforce; the write-time gate is the one that matters. Hence two gates.

## Differentiation

This is **not a memory system**. Memory systems (vector stores, knowledge graphs, persistent agents) try to remember everything automatically and hope retrieval works. `dlog` is the opposite bet: a 10-second capture habit at the moment a decision is made. Explicit, tiny, and human-readable.

It pairs well with [session-handover](https://github.com/hahahahahahahahah6/session-handover): handover summarizes *what happened*; `dlog` records *why it was decided*. Paste `dlog export-md` into your handoff doc and the next session starts with the reasoning, not just the transcript.

What v0.2 adds over that bet: most capture tools verify nothing. `dlog` splits trust into the part a tool can enforce (read-time: don't show what you can't anchor) and the part only a loop can enforce (write-time: don't act on what you didn't record) — and documents which is which instead of pretending one mechanism covers both.

## License

MIT — see [LICENSE](LICENSE).
