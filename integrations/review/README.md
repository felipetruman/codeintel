# CodeIntel Review: evidence collector (experimental)

This is an **optional, read-only** preparatory step for future AI code reviews. It is **not** a code reviewer, validator, approver or PR publisher. No models are called.

Run from CodeIntel repository checkout after installing its CLI:

```bash
cargo install --path . --locked
python3 -m integrations.review --repo /path/to/checkout --base BASE_COMMIT --head HEAD_COMMIT
```

Both commits must exist in that checkout. The checkout must be clean and its HEAD must equal the requested head commit. The JSON report includes `base_sha`, `head_sha`, `changed_files`, ranked `context_files`, and `findings: []`, `validated: false`.

Run offline unit tests:

```bash
python3 -m unittest discover -s integrations/review/tests -v
```

**Security:** `codeintel context` reads repository files and creates/refreshes the `.codeintel/` index. For untrusted PRs, the entire collector and checkout must run **inside a disposable E2B sandbox**; the collector is not an OS security boundary. The E2B/GitHub/Claude/Codex adapters are future tasks and **are not wired in this PR**.

See design and implementation plan under `docs/superpowers/`.
