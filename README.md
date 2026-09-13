# Oh-My-Codex

## What it does

Oh-My-Codex is a small Python 3.11+ package and skill for bounded, verification-first
Codex delegation, inspired by [oh-my-opencode-slim](https://github.com/alvinunreal/oh-my-opencode-slim).
It adds four named custom roles while keeping all interpretation,
dependency planning, scheduling, reconciliation, verification, and the final answer in
the user-selected main thread.

## The five-role matrix

| Role | Model | Effort | Writability | When invoked | Purpose |
| --- | --- | --- | --- | --- | --- |
| Main-thread Orchestrator | User-selected Astra or Sol | Host-selected | No implementation (instruction enforced) | Every request requiring interpretation or coordination | Owns the complete coordination contract |
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

Production activation also requires current-host evidence that the main model is exactly
`gpt-6-astra` or `gpt-5.6-sol`; the skill does not infer this from a model self-claim,
auto-switch, or Orchestrator child. An unsupported or unknown parent model stops
production activation. An explicit disposable diagnostic may use a Sol parent smoke to
measure routing, but its completion does not authorize production activation.

## Invocation and flows

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

Install from a checkout or with `pip install .`, then use `doctor` for static checks and
`verify` only for an explicit disposable runtime smoke.

## Install and use

From a checkout with Python 3.11 or newer, macOS and Linux:

```bash
python3 --version
python3 -m pip install .
python3 -m oh_my_codex install
python3 -m oh_my_codex doctor
python3 -m oh_my_codex verify --runtime v2 --timeout 300
```

Windows (PowerShell):

```powershell
py -3.11 --version
py -3.11 -m pip install .
py -3.11 -m oh_my_codex install
py -3.11 -m oh_my_codex doctor
py -3.11 -m oh_my_codex verify --runtime v2 --timeout 300
```

The console command is equivalent after installation:

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
backups automatically. To reinstall, run `install` again with the same roots after
reviewing the manifest and preserved files.

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
uninstall. Reinstall by running the install command again with the same roots.

## Doctor, verify, and limitations

`doctor` checks static package, asset, and installation shape. It does not prove provider
availability, native spawning, Desktop behavior, permissions, or model identity.

`verify` is an explicit disposable smoke. Its interface is `verify --runtime v1|v2`
with the default `v2`, `--timeout`, `--keep-artifacts`, and `--json`. It measures the
current host's actual schema and runtime evidence; a marker such as
`OMC_ROLE_FIXER_V1` is routing evidence, not self-reported proof. If named roles,
configured model/effort, or core permission separation are unavailable or unverified,
production dispatch stops. There is no generic model-only fallback. See
[`docs/runtime-limitations.md`](docs/runtime-limitations.md).

The final 2026-09-12 native V2 campaign run was `FAIL`: bound host execution metadata
and traces showed the expected models and efforts for all four named roles, but all were
effectively `workspace-write`, including the three desired read-only roles. Production
activation is therefore **NOT READY** on that host. Skill acceptance, the exact Fixer
patch, protected fixture, native web-source outcome, and Oracle's planted defect finding
were observed; opaque shell write attribution and hard nesting prevention remain
`UNVERIFIED`. See the [campaign verification record](docs/verification.md) for the
environment, lifecycle, packaging, and platform evidence.

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
