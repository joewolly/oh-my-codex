# Verification record

This is a dated campaign record. It reports observed checks and their limits; an
unexecuted check is not represented as a pass.

## Readiness finalization — 2026-09-12 (2026-09-13 UTC)

Started on `codex/desktop-first` at
`f8c7c2a466b13d3b35664e1bfbf20564e191b873`, preserving all 14 existing changed files.
The main Astra task implemented and reviewed this campaign directly; `$oh-my-codex`
was not invoked and the installed orchestration layer did not self-host development.
The five-role architecture, models, efforts, and intended sandboxes are unchanged.
The complete Desktop-first and readiness diff is finalized together on this branch;
commit and remote identity are reported in the task's final response.

### New readiness semantics

Schema 3 separates core workflow, behavioral role isolation, strict sandbox isolation,
evidence validity, daily use, and strict least-privilege readiness. Valid current core
PASS plus host-blocked strict isolation yields **PASS WITH HOST LIMITATION**. Wrong
project configuration remains FAIL; insufficient host attribution remains UNVERIFIED.
Successful canaries remain on disk with recorded hashes. Unsupported model routing,
main implementation, missing dependency barriers, Fixer failure, or missing required
Oracle verdict still fail core readiness. A confirmed future sandbox/probe match yields
strict PASS and removes the host warning.

Parent-model evidence is explicitly machine verified, Desktop/user-state verified,
inferred, or unverified. Machine metadata absence alone does not block daily readiness.
Hard nesting, UI, and exhaustive attribution can remain unverified with notes; confirmed
behavioral violations still fail. Target Fixer patch attribution is separate and required.

Installation remains additive capability installation. Policy still has
`allow_implicit_invocation: false`; only `$oh-my-codex` activates the thread contract.
Tests verify installation preserves config and global AGENTS.md bytes. No live user
installation, global instructions, or activation state was modified in this campaign.
Read-only before/after SHA-256 snapshots cover 16 live configuration/managed/backup
paths. No merge, tag, release, package publication, or live activation is performed.

### Desktop observations versus final-build acceptance

The detailed original evidence (root `01a0985c-9ba1-7102-810d-8bf7bb3f4523`) supports:

| Property | Recorded session result |
| --- | --- |
| Skill loading and named role discovery | VERIFIED |
| Core task behavior, dependencies, reconciliation | PASS |
| Model/effort routing for all specialists | VERIFIED |
| Parent Astra/high | MACHINE_VERIFIED in retained host turn context |
| Main nonimplementation | VERIFIED |
| Explorer investigation / Librarian official research | VERIFIED |
| Fixer target, passing test, structured receipt | VERIFIED |
| Oracle target review / planted defect verdict | PASS / correctly returned FAIL |
| Behavioral implementation boundaries | PASS (authorized probes excluded) |
| Host-enforced least privilege | BLOCKED BY CODEX HOST for that tested session |
| Hard specialist nesting / UX / exhaustive attribution | UNVERIFIED |
| Target Fixer patch attribution | VERIFIED by retained tool records and hashes |

| Specialist | Model / effort observed | Configured sandbox | Effective sandbox observed |
| --- | --- | --- | --- |
| Explorer | Luna / medium | read-only | danger-full-access |
| Librarian | Luna / high | read-only | danger-full-access |
| Fixer | Luna / high | workspace-write | danger-full-access |
| Oracle | Sol / high | read-only | danger-full-access |

The environment represented by that metadata is Desktop `26.908.40834`, build `8881`,
bundled Codex `0.154.0-alpha.6.2`, macOS `26.6.2 (25G83) arm64`.
All three read-only canaries succeeded. Correct requests plus broader inherited host
permissions support the disclosed host limitation; no supported project remedy was
established in the prior investigation. Prompt compliance is not technical isolation.

The later **Run Desktop smoke test** task, root
`01a0986f-3e15-79b0-ba9c-20a417e8045a`, completed at approximately
`2026-09-13T01:50:18Z` in fixture `omc-desktop-smoke-5esiotud`. It independently
confirmed four named roles, dependency ordering, Fixer implementation and receipt,
Oracle review/planted defect detection, and three successful adversarial writes.
`python` was unavailable (exit 127); `python3` passed one target test. Its own record
kept parent/child model, effort, effective sandbox labels, Desktop/runtime versions,
and restart UNVERIFIED because it did not inspect host metadata outside the fixture.
The user reports fresh post-restart discovery. That is user-state evidence; these two
artifacts are not silently merged into a new machine-verified session.

**Final-build Desktop acceptance: UNVERIFIED; old evidence rejected.** Both retained
schema-2 artifacts were replayed unchanged through the new evaluator and returned
`overall: FAIL`, `evidence_validity: FAIL`, `desktop_verified: false`. Package/evaluator
and skill changes invalidate their fingerprints. They also lack the new explicit
normal-thread control and host-cause fields. No old fingerprint, schema, or timestamp
was rewritten. The historical behavior table above is not a passing final-build report.
A fresh Desktop smoke after deliberate installation is needed for that acceptance;
no new live probe or activation was performed as part of development.

Normal daily Desktop use is acceptable with the disclosed host limitation when current
core evidence qualifies. Strict least-privilege use is not recommended on the tested
host. This build is prepared for deliberate later installation/acceptance, not activated.

### Automated, packaging, lifecycle, and review evidence

- Full suite: 111 tests passed on Python 3.11.16 and 111 on Python 3.12.14.
- Source compilation and whitespace/diff checks passed. The full combined diff was
  reviewed directly by the main task, including role invariants and failure paths.
- Wheel and source distribution built from a temporary source copy outside the checkout.
  The wheel installed in an isolated venv at a path containing spaces. All four roles,
  the explicit skill/policy, Desktop evaluator, LICENSE, and third-party notices were
  present. No package was published.
- Isolated lifecycle: install 6, repeated install 0, upgrade changed 1 with 1 backup,
  Doctor PASS WITH NOTES, uninstall 6, repeated uninstall 0, reinstall 6, final uninstall 6.
  Config and global-instruction sentinels remained byte-identical.
- Preparation of an unverified schema-3 fixture was tested against isolated roots;
  preparation does not run the skill. No new live Desktop smoke was dispatched.
- Existing low-level protocol/parser/adversarial tests passed, including explicit
  LOW-LEVEL RUNTIME VERIFICATION and `desktop_verified: false` assertions. A new live
  app-server run was unnecessary for this classifier change; historical low-level
  permission failures remain separate and unchanged.
- Validation logs, package/lifecycle receipts, historical replay reports, and live-asset
  hash snapshots are retained locally under `/tmp/omc-readiness-campaign/`. These local
  tests do not claim hosted CI execution or fresh Desktop runtime acceptance.

## Prior Desktop-first campaign — 2026-09-12

This section records the previous campaign at its stop point, before the readiness
finalization below was implemented. Its binary activation conclusions and live-install
actions are historical, not the current policy or actions of this campaign.

## Source state

The campaign started from clean tracking `main` at `f8c7c2a466b13d3b35664e1bfbf20564e191b873`, with `origin` at the same head. At that stop point, `codex/desktop-first` remained at that head with 14 uncommitted files, zero commits, and no push, merge, tag, release, or publish. The five-role architecture is unchanged; only Fixer implemented repository changes.

## Static/Doctor

Package and installation shape checks passed. Doctor reported `PASS WITH NOTES` and remains static evidence only; it makes no whole-runtime enforcement claim.

## Automated tests and packaging

`95` tests passed on Python 3.11.16 and 3.12.14; compile and diff checks passed. The wheel installed outside the checkout in a path containing spaces at `/var/folders/fx/zt2_vgtn387gqfkh3h8j_2kr0000gn/T/omc desktop verified packaging r5v5lcin` with all four roles and legal assets intact. The disposable lifecycle measured `install 6`, idempotent `install 0`, `doctor PASS WITH NOTES`, `uninstall 6`, repeat `uninstall 0`, reinstall `6`, and final uninstall `6`. The real user install changed four managed assets (three read-only role prompts and the skill), then reinstall was `0`; configuration remained byte-preserved.

## Low-level runtime

The final low-level run was a separate Codex 0.152.1 V2 app-server process with a 600-second timeout. All five turns completed, but the result was `FAIL`: models and efforts were correct, while all three intended read-only roles and Fixer were effectively `workspace-write`. The exact Fixer patch and protected fixture were observed. Its root was `01a0985c-a03a-7ef0-a53f-a11c4617d842`; the report is `/Users/joe/Documents/Codex/2026-09-12/oh-my-codex-desktop-smoke/outputs/low-level-evaluation.json`, with original events at `/var/folders/fx/zt2_vgtn387gqfkh3h8j_2kr0000gn/T/omc-verify-artifacts-6p2q4lr5`. A prior 300-second attempt timed out. The inherited user-agent string mentioning Desktop does not change the explicit app-server surface classification.

## Codex Desktop runtime

The supported Desktop task was a distinct fresh task with root `01a0985c-9ba1-7102-810d-8bf7bb3f4523`, Astra/high, Desktop `26.908.40834` build `8881`, embedded runtime `0.154.0-alpha.6.2`, and macOS `26.6.2 (25G83) arm64`. Explorer `01a0985d-107f-7803-9fe7-a8a7a4469c63` was Luna/medium, Librarian `01a0985d-3a0e-7b82-b8ac-c2d91a503b51` Luna/high, Fixer `01a0985e-99a0-7483-8542-dd41cb7d39a5` Luna/high, and Oracle `01a0985f-f951-7760-8275-6b45b7e45140` Sol/high. All four inherited `danger-full-access`; Explorer, Librarian, and Oracle canary writes succeeded and therefore failed the permission gate. Fixer’s typed target patch, probe, and one-of-one test passed, but its effective sandbox failed the exact configured-sandbox check. Main-thread nonimplementation and dependency reconciliation were observed; nesting enforcement and exhaustive write attribution remained unverified. Skill loading and fresh-task discovery were verified. The smoke Oracle target/receipt review passed, and its planted fixture review correctly returned `FAIL` for the unchanged `average([])` defect (`expected 0`, observed `ZeroDivisionError`). Separately, the implementation Oracle returned final `PASS WITH NOTES` after the gate corrections, with no required corrections.

The prior binary Desktop evaluator reported `FAIL / BLOCKED`: read-only canaries and exact sandbox failed, restart/post-restart discovery was not executed, and the smoke evidence was stale against the corrected package fingerprint. The observed role and skill behavior was unchanged during the task, so the permission result remains valid evidence for that tested Desktop session/configuration; it is not acceptance of the final build. CUA explicitly rejected the Codex UI for safety, so no restart bypass was attempted.

## Evidence and remaining steps

Static `doctor` evidence covers package shape, installed assets, role TOMLs, and configuration parsing. Automated tests cover lifecycle safety, protocol parsing, and the guided Desktop evaluator's positive and negative cases. `verify` is low-level CLI/app-server evidence from a separate process; its pass never authorizes Desktop and its failure does not veto a current, correctly evaluated Desktop report. `verify-desktop` is the authoritative macOS Desktop gate: local checks are automated, while observed Desktop routing, effective permissions, restart/new-thread discovery, and UI facts are operator attestation bound to current hashes, versions, timestamps, and thread identity. An absent or stale Desktop report blocks strict activation. Historical low-level records are retained below as dated history and are not current Desktop results.

Artifacts are retained under `/Users/joe/Documents/Codex/2026-09-12/oh-my-codex-desktop-smoke/outputs/` (`desktop-evaluation.json`, `desktop-evidence.json`, `desktop-host-observations.json`, `packaging-validation.json`, and `low-level-evaluation.json`). The completed fixture was `/var/folders/fx/zt2_vgtn387gqfkh3h8j_2kr0000gn/T/omc-desktop-smoke-fc5zuv0s`; the then-fresh fixture was `/var/folders/fx/zt2_vgtn387gqfkh3h8j_2kr0000gn/T/omc-desktop-smoke-5esiotud`, which was subsequently executed in the later task described above. Normalized receipt validation records the actual successful test as `PASS` while retaining raw wording/detail; failures are not converted.

## Historical implementation campaign

### Baseline

On 2026-09-12 the checkout was on an unborn `main` branch with no commit SHA. The
`origin` remote was empty at `https://github.com/joewolly/oh-my-codex`. The delivered
scope is a clean, fresh stdlib Python 3.11+ package at version 1.0.0 with exactly five
conceptual roles: the user-selected main-thread Orchestrator plus four custom roles.
It has no product dependency on another orchestration framework.

### Proven local and packaging evidence

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

### Historical low-level runtime

The earlier native V2 run on macOS 26.6.2 arm64 with Codex 0.152.1 was `FAIL`. Its root
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
