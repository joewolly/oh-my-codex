# Runtime limitations

The assets express a host configuration contract; they do not replace Codex runtime
enforcement. `doctor` is static evidence about package and installation shape. `verify`
is the opt-in disposable runtime smoke and must use the current host's actual tools,
schema, and retained app-server evidence where available. A successful CLI verification
can prove the exercised claims on that tested host; it does not prove that Desktop uses
the same configuration or runtime path.

Codex Desktop on macOS is Tier 1 and is the authoritative daily-use gate. Windows
Desktop is Tier 2 and remains runtime-unverified until a Windows Desktop smoke is
observed. Standalone CLI/app-server is secondary diagnostic evidence. After install or
reinstall, restart Codex Desktop and start a NEW thread; no hot reload of custom agents
is promised. Use `verify-desktop --prepare` and the guided procedure in
[`desktop-smoke.md`](desktop-smoke.md) for the Desktop gate.

## Current tested Codex host limitation

Desktop `26.908.40834` build `8881`, bundled Codex `0.154.0-alpha.6.2`, macOS
`26.6.2 (25G83) arm64` applied `danger-full-access` to every specialist. Explorer,
Librarian, and Oracle adversarial writes succeeded; Fixer's bounded write succeeded.
The role requests remain read-only / read-only / workspace-write / read-only.
The recorded workflow demonstrated model/effort routing, repository investigation,
external research, dependency ordering, reconciliation, main nonimplementation,
Fixer implementation/receipt, and Oracle independent review/verdict.

This is **behavioral role isolation**, not technical sandbox isolation. The tested
host retained broader write capability than Oh-My-Codex requested. Core orchestration
can PASS while strict isolation is BLOCKED BY HOST and daily readiness is
PASS WITH HOST LIMITATION. Users requiring hard least-privilege separation should not
use this tested host for that requirement.

Keep strong role instructions, exclusive Fixer implementation ownership, source sandbox
requests, and adversarial probes. These mitigations do not replace host enforcement.
No parent-read-only/child-escalation tricks, OS wrappers, or unsupported runtime
modifications are introduced. Future versions must be retested; the evaluator compares
configured and observed permissions without hardcoding a version-dependent result.

BLOCKED BY HOST requires valid source and installed configuration, broader observed
permissions, recorded ignored/rejected override or parent inheritance, and evidence
that no supported project configuration remedy exists. Wrong project settings are FAIL;
missing or contradictory runtime/cause evidence is UNVERIFIED.

The old smoke fingerprint is stale for this build. Its observations remain historical
session evidence, not fresh final acceptance. The user reports subsequent post-restart
role discovery; the retained original artifact predates that observation and says
restart was not completed. These records are not silently combined or re-stamped.
See [verification](verification.md) for provenance and acceptance limits.

## Historical low-level record

The earlier native V2 run on macOS 26.6.2 arm64 with Codex 0.152.1 was `FAIL`. Its root
was `01a0982b-8114-7401-a595-dc81af445193`; the retained report is
`/var/folders/fx/zt2_vgtn387gqfkh3h8j_2kr0000gn/T/omc-verify-artifacts-3oyft6rs/report.json`
with `events.jsonl` alongside it. All five turns completed, and bound host execution
metadata and traces showed the expected models and efforts. Explorer, Librarian, and
Fixer used Luna at medium, high, and high; Oracle used Sol at high. Every role was effectively
`workspace-write`, including the three desired read-only roles, so runtime read-only
checks and capability D were `FAILED`.

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

The current lifecycle protects writes with immediate target identity, hash, and type
checks, plus deterministic locks covering both the Codex and skills roots. The
`.oh-my-codex.lock` file in the shared skills root is intentionally retained. A narrow
race with a non-cooperating process or filesystem cannot be eliminated; recheck the
manifest and resulting files when that boundary matters.

The host can ignore role `sandbox_mode` and `[agents] enabled = false`, so the read-only
and writable labels are desired configuration. A prompt cannot enforce read-only
behavior; the parent session's effective permissions are authoritative. Non-recursion is
defended by both the configuration request and every specialist's instruction, but the
absence of observed child delegation does not prove hard prevention. Normal production
work has no write-canary exception; the guided Desktop smoke permits one explicitly
authorized probe per role inside its disposable fixture. A denied prompt or generic
command error is not a permission observation, and there is no supported hard
read-only parent with a writable child until Desktop evidence proves it.

The user explicitly selects Astra or Sol and invokes `$oh-my-codex` to activate
orchestration. Installation does not inject global policy. Record parent-model evidence
as machine verified, Desktop/user-state verified, inferred, or unverified. Missing
machine telemetry alone is a note; a known unsupported model is a core failure.

V2 dispatch uses named `agent_type`, semantic `task_name`, and `fork_turns = "none"`.
V1 uses only the fields accepted by the actual host schema. Missing named roles or
wrong model/effort routing remain core failures. Unobservable effort adds a note.
Confirmed host sandbox override blocks strict isolation, independently of core
orchestration. Standalone CLI/app-server verification stays secondary.

Diagnostic mode can run a disposable fixture smoke to measure broken routing even when
the production gate would halt. Markers such as `OMC_ROLE_FIXER_V1` and
`OMC_ORCHESTRATOR_V1` are routing observations only. They are not self-reported proof of
identity, permissions, or safe production dispatch. Diagnostic completion cannot authorize
production work.

Native Linux and Windows were unavailable for native validation. Docker daemon
unavailability prevented only the optional Linux container check. Path and Windows lock
behavior have simulated coverage, while the CI matrix remains unexecuted. The latest
retained runtime artifact is
`/var/folders/fx/zt2_vgtn387gqfkh3h8j_2kr0000gn/T/omc-verify-artifacts-3oyft6rs/`.

The package has no provider daemon, wake scheduler, copied framework, or custom task
plumbing. Availability, approvals, sandbox behavior, and execution telemetry belong to
the installed Codex host and must be verified there.
