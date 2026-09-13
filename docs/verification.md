# Verification record

This is a dated campaign record. It reports observed checks and their limits; an
unexecuted check is not represented as a pass.

## Baseline

On 2026-09-12 the checkout was on an unborn `main` branch with no commit SHA. The
`origin` remote was empty at `https://github.com/joewolly/oh-my-codex`. The delivered
scope is a clean, fresh stdlib Python 3.11+ package at version 1.0.0 with exactly five
conceptual roles: the user-selected main-thread Orchestrator plus four custom roles.
It has no product dependency on another orchestration framework.

## Proven local and packaging evidence

The parent built a wheel from the checkout and installed it with `pip --target` into a
temporary path containing spaces outside the checkout. The package assets and legal
notices were present in that install. The disposable lifecycle sequence
`install -> install -> doctor -> uninstall -> uninstall -> install -> uninstall`
completed successfully; `doctor` reported notes where expected.

The measured user-home cycle was:

```text
uninstall: 6 removed
uninstall: 0 removed
install: 6 installed
install: 0 installed
doctor: PASS WITH NOTES
```

During that cycle, `config.toml` and three unrelated Luna agent files were byte
preserved. The backing application may independently change configuration, so this is
not a whole-campaign immutable hash claim. Modified managed files remain preserved and
their backups remain available; uninstall does not restore backups automatically.

The lifecycle uses two project-managed locks, both intentionally retained as metadata:
`$CODEX_HOME/oh-my-codex/.lock` and `$SKILLS_HOME/.oh-my-codex.lock`. Earlier
campaign-created empty locks were removed before the final cycle; recognizable metadata
was then created by the lifecycle. A narrow race with a non-cooperating process or
filesystem remains outside the guarantees of these checks.

Python 3.11.16 and 3.12.14 each passed 84 tests in the final automated runs.

## Runtime evidence and limits

The final native V2 run on macOS 26.6.2 arm64 with Codex 0.152.1 was `FAIL`. Its root
was `01a0982b-8114-7401-a595-dc81af445193`; the retained report is
`/var/folders/fx/zt2_vgtn387gqfkh3h8j_2kr0000gn/T/omc-verify-artifacts-3oyft6rs/report.json`
with `events.jsonl` alongside it. All five turns completed, and bound host execution
metadata and traces showed the expected models and efforts: Explorer, Librarian, and
Fixer used Luna at medium, high, and high; Oracle used Sol at high. Every role was effectively
`workspace-write`, including the three roles configured as desired read-only, so runtime
read-only checks and capability D were `FAILED`.

Skill acceptance was `VERIFIED`, as were exact Fixer patch attribution and an unchanged
protected fixture (`changed=false`, `target_corrected=true`). Librarian's official
Python statistics source was `VERIFIED`. Fixer receipt evidence was `INFERRED`; Oracle's
known-bug `FAIL` verdict was `INFERRED`, with the actual numeric-zero/
`ZeroDivisionError` finding. Opaque shell commands cannot prove exhaustive write
attribution and remain `UNVERIFIED`; no observed child delegation does not prove hard
nesting prevention. One incorrect native agent argument appeared in host stderr but was
recovered; it did not leave a transport failure or incomplete turn.

A V1 attempt correctly **FAILED** the requested-versus-observed version check: current
metadata advertises V2 for Sol and V1 for Luna, while disabling the V2 feature does not
force V1. No supported explicit V1 selector exists for the conforming Sol parent, and
changing the parent to Luna would violate the product parent contract. The stricter
Oracle parser replay accepted the actual native finding, and the late parser negative
case guard was verified by tests and that replay.

Strict production use is **NOT READY** on this host. The gate remains
fail-closed: there is no generic wrong-model fallback, and no supported hard read-only
parent with a writable child. Upstream role sandbox enforcement plus fresh discovery and
reverification are required before the desired role permissions can be accepted.

An already-open Desktop task previously returned `unknown agent_type 'omc_explorer'`;
fresh task discovery is a separate concern, and fresh CLI verification does not prove
that task's behavior. Native Linux and Windows were unavailable for native validation.
Docker daemon unavailability prevented only the optional Linux container check. Path and
Windows lock behavior have simulated coverage, while the CI matrix remains unexecuted.
The latest retained runtime artifact is
`/var/folders/fx/zt2_vgtn387gqfkh3h8j_2kr0000gn/T/omc-verify-artifacts-3oyft6rs/`.

No release, push, merge, tag, or publish occurred.
