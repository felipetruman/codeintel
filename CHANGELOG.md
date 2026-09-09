# Changelog

## [0.6.0] — 2026-09-09

### Added

- Agent Benchmark v1 with deterministic rg and CodeIntel runners, synthetic
  corpora, paired repetitions, retrieval and graph scoring, and JSON/CSV reports.
- Opt-in Claude and Codex baseline/CodeIntel runners with strict structured
  output parsing, nullable telemetry, bounded process output, process-group
  cleanup, and Linux Bubblewrap containment.
- Repository snapshot isolation with symlink validation and mutation detection.
- GitHub verification for Rust formatting, tests, Clippy, release builds,
  offline benchmark tests, and the deterministic matrix.
- README setup guidance, Shields.io badges, architecture and benefits, and a
  reproducible functional proof for retrieval, impact, and incremental reuse.

- A 17-test release-binary integration suite covering all 10 CLI commands and
  all 4 MCP tools, included in CI.

### Compatibility and evidence

The Rust retrieval runtime and dependency versions are unchanged from v0.5.0.
The benchmark is separate Python tooling; real-agent execution is optional and
requires explicit opt-in. No real-agent token savings or speedup is claimed.

The benchmark integration was verified with 59 Rust tests and 116 Python tests
passing, 2 real-agent tests skipped, and 16 successful deterministic matrix
results. See [the integration CI run](https://github.com/felipetruman/codeintel/actions/runs/34413646396)
and the [benchmark guide](benchmarks/agent/README.md) for scope and reproduction.

[0.6.0]: https://github.com/felipetruman/codeintel/compare/v0.5.0...b49c901926ac32089698a48dfe27adf10f42aa80
