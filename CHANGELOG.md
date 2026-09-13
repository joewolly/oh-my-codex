# Changelog

## 1.0.0 — 2026-09-13

Initial stable release of Oh-My-Codex.

Highlights:

- Explicit, thread-scoped Oh-My-Codex activation.
- Main-thread Orchestrator with Explorer, Librarian, Fixer, and Oracle specialists.
- Bounded Fixer implementation ownership and independent Oracle review.
- One-command macOS/Linux and Windows bootstrap installers.
- Additive lifecycle management with Doctor, uninstall, backups, and idempotent reinstall support.
- Tier-1 macOS Codex Desktop acceptance harness with independent control and activated threads.
- Cross-platform GitHub Actions coverage on Ubuntu, macOS, and Windows with Python 3.11 and 3.12.

Final macOS Desktop acceptance returned **PASS WITH HOST LIMITATION** with zero failed evaluator checks. Daily orchestration, explicit activation control, behavioral role isolation, and probe-boundary compliance passed. Hard least-privilege sandbox isolation remains unavailable on the tested Codex Desktop host.

See `docs/release-notes.md` and `docs/verification.md` for release and historical verification context.
