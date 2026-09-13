# Oh-My-Codex

## What it does

Oh-My-Codex is a small Python 3.11+ package and skill for bounded, verification-first
Codex delegation, inspired by [oh-my-opencode-slim](https://github.com/alvinunreal/oh-my-opencode-slim).
It adds four named custom roles while keeping all interpretation,
dependency planning, scheduling, reconciliation, verification, and the final answer in
the user-selected main thread.

## Normal Desktop use

1. Install Oh-My-Codex using the commands below.
2. Restart Codex Desktop after installation or update.
3. Start a new Desktop thread.
4. Select Astra or Sol as the main model.
5. Explicitly invoke `$oh-my-codex`.
6. Give it the task.

**Installation installs capability. `$oh-my-codex` activates orchestration in that
thread.** Installing agents does not globally activate this skill. Without invocation,
Astra/Sol behave as ordinary Codex, including ordinary implementation work.

**Tested host limitation:** Desktop `26.908.40834` build `8881` / bundled Codex
`0.154.0-alpha.6.2` on macOS `26.6.2 arm64` gave all four specialists
`danger-full-access`, despite their configured role sandboxes. Normal orchestration
worked in the recorded session; hard least-privilege isolation did not. Behavioral
instructions do not technically prevent writes. See the [evidence record](docs/verification.md)
for historical observations versus final-build acceptance.

## The five-role matrix

| Role | Model | Effort | Writability | When invoked | Purpose |
| --- | --- | --- | --- | --- | --- |
| Main-thread Orchestrator | User-selected Astra or Sol | Host-selected | No implementation (instruction enforced) | While the skill is explicitly active | Owns the complete coordination contract |
| `omc_explorer` | `gpt-5.6-luna` | medium | Desired read-only; current host may ignore role `sandbox_mode` | Repository evidence is needed before a packet | Repository evidence |
| `omc_librarian` | `gpt-5.6-luna` | high | Desired read-only; current host may ignore role `sandbox_mode` | Version-sensitive or external primary facts are needed | Primary external facts |
| `omc_fixer` | `gpt-5.6-luna` | high | Desired workspace-write; parent permissions remain authoritative | An explicit implementation packet is reconciled and ready | Bounded implementation |
| `omc_oracle` | `gpt-5.6-sol` | high | Desired read-only; current host may ignore role `sandbox_mode` | Independent high-level risk review is material | Conditional independent reasoning |

The main thread is not a custom child and is never switched. Explorer is not the default
reviewer; Oracle is used only when independent high-level reasoning materially reduces
risk. Specialists never subdelegate. The requested `[agents] enabled = false` nested
prevention may be ignored by the current host, so the role instructions also prohibit
nested delegation. The read-only and writable entries are desired role settings, not
proof of effective runtime permissions.

The user selects Astra or Sol. Parent-model evidence may be machine verified,
Desktop/user-state verified, inferred, or unverified. Recorded Desktop selection is
sufficient when machine-readable metadata is unavailable; observability alone is not
a daily-use blocker. A known unsupported model remains a core failure.

## Supported runtime tiers

Codex Desktop on macOS is Tier 1 and is the authoritative daily-use and release
acceptance target. Windows Codex Desktop is Tier 2: implementation and path tests are
portable, but live Windows Desktop behavior remains runtime-unverified until observed.
Standalone Codex CLI/app-server is a secondary surface for installation, doctor,
automated tests, and low-level troubleshooting. Its result is never equivalent to
Desktop verification.

## Invocation and flows

### Desktop daily flow (Tier 1)

Install the package and role assets, quit and restart Codex Desktop, then start a NEW
thread. Select Astra (`gpt-6-astra`) or Sol (`gpt-5.6-sol`) as the main-thread model and
invoke `$oh-my-codex`. The main thread is the Orchestrator; it dispatches Explorer and
Librarian, reconciles their receipts, sends the bounded packet to Fixer, and requests
Oracle review when the risk warrants it. Use the guided Desktop smoke when fresh build acceptance is required.

Activate the skill explicitly in a thread with `$oh-my-codex`. It is not implicitly
invoked. For a simple non-repository answer, use no delegation. For repository work, the
Orchestrator maps dependencies and exclusive file scopes, gathers needed evidence,
dispatches independent packets, waits for terminal results, reconciles each receipt with
the checkout, and verifies before answering.

Normal work uses Explorer for local evidence, Librarian for primary external facts when
needed, Fixer for implementation, and optional Oracle analysis. A downstream packet waits
until its prerequisite result is terminal, received, and reconciled. Spawned, idle,
acknowledged, or partially observed work is not success. Parallel writer lanes require
non-overlapping exclusive scopes. External or risky post-implementation actions retain
their own authorization gate and are verified separately.

For a simple answer that needs no repository edits, the main thread answers directly with
no delegation. For a tiny repository change, Explorer gathers evidence when needed, then
Fixer applies the bounded packet and the Orchestrator verifies it. A normal feature uses
the same sequence with explicit ownership and dependencies. An external dependency
question goes to Librarian for dated primary sources and implications. A risky
architecture decision uses Oracle for an independent `PASS`, `PASS WITH NOTES`, or `FAIL`
review before Fixer is dispatched. After implementation, Oracle can provide a separate
conditional review for a risky change after the Fixer receipt is reconciled; Oracle never
writes. Examples:

```text
$oh-my-codex implement the bounded parser fix in src/parser.py
$oh-my-codex ask Oracle to review this risky architecture before Fixer implements it
```

## Usage

The recommended installer is now repository-owned and one-command from a checkout. It
creates a private per-user Python tooling environment, installs the exact checkout into
that environment, runs the managed-asset installer, and runs `doctor`. The tooling venv
is only for installation/diagnostics; normal Codex Desktop orchestration still uses the
installed skill and custom-agent assets and does not require the Python package to be
importable inside a coding thread.

## Install and use

### One-command bootstrap (recommended)

Clone the repository, then run the platform bootstrap from the repository root.

macOS and Linux:

```bash
bash install.sh
```

Windows PowerShell:

```powershell
.\install.ps1
```

The bootstrap finds Python 3.11+, creates or reuses a private tooling venv, installs the
current checkout into it, runs `oh_my_codex install`, then runs `doctor`. It preserves
unrelated Codex configuration and **does not globally activate Oh-My-Codex**. After it
finishes, fully quit/relaunch Codex Desktop, start a NEW thread, select Astra or Sol, and
explicitly invoke `$oh-my-codex`.

For Windows Desktop build verification, the normal operator flow is:

1. Open PowerShell in the checkout and run `.\install.ps1`.
2. Fully quit and relaunch Codex Desktop.
3. Run `.\verify-desktop.ps1` and follow its short two-thread instructions.
4. Rerun `.\verify-desktop.ps1` when instructed after each thread. The wrapper copies
   the correct prompt, retains the pending run identity, and invokes final evaluation.

No venv path, pip cache setting, Base64 gate, fixture/evidence path, shell quoting, or
evaluator command needs to be assembled manually. `-Reset` safely archives only wrapper
state and preserves the prepared forensic fixture.

Optional bootstrap overrides are available for isolated/test installations:

```bash
bash install.sh --venv-dir /custom/tooling --codex-home /custom/.codex --skills-home /custom/skills
```

```powershell
.\install.ps1 -VenvDir C:\Tools\omc -CodexHome C:\Temp\.codex -SkillsHome C:\Temp\skills
```

This also gives Codex itself a simple install procedure: clone
`https://github.com/joewolly/oh-my-codex`, then run the platform bootstrap script and
restart Codex Desktop.

### Advanced/manual installation and troubleshooting

From a checkout with Python 3.11 or newer, macOS and Linux:

```bash
python3 --version
python3 -m pip install .
python3 -m oh_my_codex install
# Quit/restart Codex Desktop, start a NEW thread, select Astra or Sol, then invoke:
# $oh-my-codex
```

CLI diagnostics are secondary:

```bash
python3 -m oh_my_codex doctor
python3 -m oh_my_codex verify --runtime v2 --timeout 300
python3 -m oh_my_codex verify-desktop --prepare
```

Windows (PowerShell):

```powershell
py -3.11 --version
py -3.11 -m pip install .
py -3.11 -m oh_my_codex install
# Quit/restart Codex Desktop, start a NEW thread, select Astra or Sol, then invoke:
# $oh-my-codex
```

CLI diagnostics are secondary:

```powershell
py -3.11 -m oh_my_codex doctor
py -3.11 -m oh_my_codex verify --runtime v2 --timeout 300
py -3.11 -m oh_my_codex verify-desktop --prepare
```

These lower-level commands remain available for development and CI; they are not the
recommended Windows operator workflow. If Windows marks a downloaded script as blocked,
unblock only that checkout's scripts (for example,
`Get-Item .\install.ps1, .\verify-desktop.ps1 | Unblock-File`) or use a process-scoped
policy for the current PowerShell session.
Do not make an execution-policy bypass a permanent machine-wide setting.

The console command is equivalent after a manual package installation:

```bash
oh-my-codex doctor
oh-my-codex verify --runtime v2 --timeout 300
```

The package also supports `python -m oh_my_codex` from the checkout. By default, role
files install to `${CODEX_HOME:-~/.codex}/agents/omc_*.toml`, the skill installs to
`~/.agents/skills/oh-my-codex/`, and the ownership manifest is
`${CODEX_HOME:-~/.codex}/oh-my-codex/manifest.json`. Use `--codex-home` and
`--skills-home` to select other roots.

The additive installer preserves the main configuration, uses a manifest and backups,
and accepts `--codex-home` and `--skills-home` overrides. It does not rewrite unrelated
configuration. Uninstall removes only unchanged files recorded as Oh-My-Codex managed;
modified files are preserved and their backups remain available. It does not restore
backups automatically. To reinstall, run the bootstrap or `install` again with the same
roots after reviewing the manifest and preserved files. After install or reinstall, quit
and restart Codex Desktop, then start a NEW thread; custom-agent discovery has no
supported hot reload guarantee. Select Astra or Sol in that thread and invoke
`$oh-my-codex`.

## Uninstall

After reviewing the manifest and preserved files, remove managed assets first. macOS and
Linux:

```bash
python3 -m oh_my_codex uninstall
python3 -m pip uninstall oh-my-codex
```

Windows (PowerShell):

```powershell
py -3.11 -m oh_my_codex uninstall
py -3.11 -m pip uninstall oh-my-codex
```

The pip uninstall is optional package removal; it does not replace the managed-asset
uninstall. Reinstall by running the bootstrap or install command again with the same
roots.

## Doctor, verify, and Desktop smoke

`doctor` is static evidence only. It checks package, asset, and installation shape and
explicitly reports Desktop behavior as unverified. It does not prove provider
availability, native spawning, Desktop behavior, permissions, or model identity.

`verify` is **LOW-LEVEL RUNTIME VERIFICATION** in a separate CLI/app-server process.
It measures routing, fixture execution, and permissions for that process; it cannot
establish or override Desktop readiness. No generic model-only role fallback is used.

`verify-desktop --prepare` (or the recommended Windows `verify-desktop.ps1` wrapper)
creates a disposable fixture and two unverified
evidence forms for separate ordinary-control and activated threads (schema 4), plus
`.omc-probe-preflight.py`, a self-contained standard-library gate. The activated prompt
runs a platform-native command (`python3` through a POSIX shell, or
`& '...python.exe' ...` through PowerShell) with a hash-pinned launcher that checks the helper before execution;
no package import, checkout working directory, or `PYTHONPATH` is required. Retain the
preparation-time prompt/hash outside the mutable fixture. Gate failure stops delegation;
never install packages or substitute a different gate inside the smoke thread. See the
[Desktop procedure](docs/desktop-smoke.md) for trust bindings and platform details.
`verify-desktop --evaluate <path>` checks current evidence against source,
installed assets/configuration, OS, versions, timestamps, and task identity. It reports:

| Dimension | Results |
| --- | --- |
| Explicit activation control | PASS / FAIL / UNVERIFIED |
| Probe boundary compliance | PASS / FAIL / UNVERIFIED |
| Core Desktop orchestration | PASS / PASS WITH NOTES / FAIL |
| Strict sandbox isolation | PASS / BLOCKED BY HOST / FAIL / UNVERIFIED |
| Daily-use readiness | PASS / PASS WITH NOTES / PASS WITH HOST LIMITATION / FAIL |
| Strict least-privilege readiness | READY / UNAVAILABLE ON TESTED CODEX HOST / BLOCKED / UNVERIFIED |

Core PASS, independent no-skill control PASS, and probe boundary PASS plus confirmed
host-blocked isolation produce **PASS WITH HOST LIMITATION**.
Incorrect project configuration remains FAIL. Missing host attribution remains
UNVERIFIED. Future correct enforcement produces isolation PASS and removes the host
warning automatically. Stale evidence cannot qualify current-build acceptance.

The checker validates skill discovery and explicit activation, a normal thread without
the skill, named model/effort routing, Orchestrator nonimplementation, dependency
barriers, reconciliation, role work, Fixer receipt, Oracle verdict, target attribution,
and the completed workflow. Nesting enforcement, UI details, exhaustive attribution,
and unobservable effort retain their actual evidence classifications.

Keep the hostile probes: read-only writes should be denied, and the bounded Fixer write
should succeed. Successful exact fixture canaries can establish a host limitation, not secure
isolation. Outside-fixture or substitute probe paths fail acceptance. The harness owns
all targets and requires a successful `--check-probes` preflight before delegation. See [Desktop smoke](docs/desktop-smoke.md) and
[runtime limitations](docs/runtime-limitations.md).

The existing Desktop observations support operational orchestration with the disclosed
host limitation. They do **not** accept this revised build: the old fingerprints and
schema are stale. This development campaign does not install or activate the build in
live user configuration. The [verification record](docs/verification.md) separates
those facts from automated and isolated lifecycle validation.

## Development

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

The repository's configured CI checks are configuration evidence until they are actually
run. Local test results, static doctor output, runtime verify evidence, hosted review,
and any published release are separate claims.

## Principles

- Explicit `$oh-my-codex` activation is thread-scoped.
- The Orchestrator coordinates and verifies; Fixer alone writes implementation changes.
- Every writer has exclusive ownership; independent lanes may run in parallel only when
  scopes do not overlap.
- Hard barriers require terminal results to be received and reconciled before downstream
  work.
- Contradictions become focused follow-ups or blockers, with bounded retries and visible
  evidence.
- Read-only roles remain read-only, and runtime limitations are reported plainly.

See [`docs/architecture.md`](docs/architecture.md), [`docs/research.md`](docs/research.md),
and [`docs/verification.md`](docs/verification.md) for the contract, research, and
campaign evidence.
