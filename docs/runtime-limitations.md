# Runtime limitations

The assets express a host configuration contract; they do not replace Codex runtime
enforcement. `doctor` is static evidence about package and installation shape. `verify`
is the opt-in disposable runtime smoke and must use the current host's actual tools,
schema, and retained app-server evidence where available. A successful CLI verification
can prove the exercised claims on that tested host; it does not prove that Desktop uses
the same configuration or runtime path.

Observed 2026-09-12: after additive installation, an already-open Desktop task's native
V2 tool returned `unknown agent_type 'omc_explorer'`. A fresh task or host reload may
discover newly installed definitions, but this observation does not establish that a
reload guarantees enforcement. Fresh CLI verification also does not prove behavior in
that already-open Desktop task.

The final native V2 run on macOS 26.6.2 arm64 with Codex 0.152.1 was `FAIL`. Its root
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
absence of observed child delegation does not prove hard prevention. There is no
read-only write-canary exception, and no supported hard read-only parent with a writable
child.

Production activation is gated on verified current-host evidence that the main model is
exactly `gpt-6-astra` or `gpt-5.6-sol`. Model self-claims, role text, and display names
are insufficient; the skill does not auto-switch or create an Orchestrator child. An
unsupported or unknown parent model is a production stop. A disposable diagnostic may
use an explicit `gpt-5.6-sol` parent smoke to measure routing, without authorizing
production activation.

V2 dispatch uses named `agent_type`, semantic `task_name`, and `fork_turns = "none"`.
V1 dispatch uses only fields accepted by the live schema, including `agent_type` and
`fork_context = false` where supported. The skill never invents V2 fields for V1. A
missing named role, wrong model or effort configuration, or unavailable or unverified
core permission separation is a production stop condition. There is no generic
model-only fallback.

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
