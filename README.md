# decision-log

An append-only decision log for coding-agent sessions.

Coding agents make dozens of decisions per session — which library, which schema, which approach — and never write them down. The next session rediscovers all of it: same debates, same wrong turns, same "wait, why did we do it this way?"

Memory only holds what gets saved. If nobody saves the decision, it isn't there.

`dlog` is the 30-second habit that fixes this: `dlog add "chose X" -r "because Y"`. One line, appended to a JSONL file, searchable later and exportable to markdown for session handoffs.

## Install

Stdlib only, Python 3.9+. No dependencies, no network, no accounts.

```bash
curl -O https://raw.githubusercontent.com/hahahahahahahahah6/decision-log/main/dlog.py
chmod +x dlog.py
# optionally: put dlog.py on your PATH as `dlog`
```

## Usage

```bash
$ dlog add "chose sqlite over postgres" -r "single-file, zero deps, enough for v1" -t db,infra
logged -> ./.dlog.jsonl

$ dlog add "dropped tailwind" -r "bundle size too big, hand-rolled css instead" -t css
logged -> ./.dlog.jsonl

$ dlog list
10-01 00:31  dropped tailwind [css]
10-01 00:30  chose sqlite over postgres [db, infra]

$ dlog list --tag db
10-01 00:30  chose sqlite over postgres [db, infra]

$ dlog search locking
10-01 00:30  chose sqlite over postgres [db, infra]
        single-file, zero deps, enough for v1

$ dlog export-md
# Decision Log

## chose sqlite over postgres

- **When:** 10-01 00:30
- **Tags:** db, infra

single-file, zero deps, enough for v1

## dropped tailwind

- **When:** 10-01 00:31
- **Tags:** css

bundle size too big, hand-rolled css instead
```

Flags:

- `dlog add "title" -r "reason" [-t tag1,tag2]` — appends `{"ts", "title", "reason", "tags", "cwd", "git"}` to `.dlog.jsonl` in the current directory. `git` is the short commit sha, or `null` outside a repo.
- `--global` on any command writes to `~/.dlog.jsonl` instead (a personal log across projects).
- `dlog list [--tag T] [--last N]` — newest-first table.
- `dlog search QUERY` — case-insensitive substring over title + reason + tags.
- `dlog export-md [--tag T]` — markdown with `##` entries, ready to paste into a handoff doc.
- `dlog` with no args prints help. A missing log file prints "no decisions logged yet" and exits 0 — never a traceback.

## Differentiation

This is **not a memory system**. Memory systems (vector stores, knowledge graphs, persistent agents) try to remember everything automatically and hope retrieval works. `dlog` is the opposite bet: a 10-second capture habit at the moment a decision is made. Explicit, tiny, and human-readable.

It pairs well with [session-handover](https://github.com/hahahahahahahahah6/session-handover): handover summarizes *what happened*; `dlog` records *why it was decided*. Paste `dlog export-md` into your handoff doc and the next session starts with the reasoning, not just the transcript.

## License

MIT — see [LICENSE](LICENSE).
