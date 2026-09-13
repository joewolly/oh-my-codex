# Codex Desktop acceptance: two separate threads

Codex Desktop on macOS is the Tier-1 observation surface. CLI/app-server results
cannot satisfy Desktop acceptance. This guided harness validates files, paths, bytes,
fingerprints and entered observations; it does not automate Desktop or authenticate an
operator's transcript claims. Model self-description alone is insufficient evidence.

## Prepare without activating

After a deliberate installation/update of the final committed build, prepare with that
same Python package. Preparation uses Python 3.11+ developer tooling; the future
Desktop thread needs only Python 3.11+ standard library, available as `python3` on macOS:

```bash
python3 -m oh_my_codex verify-desktop --prepare --json
```

Preparation itself never installs, activates, contacts a provider, or modifies global
policy. It creates one canonical disposable Git fixture and schema-4 records:

- `control-prompt.txt`: exact neutral prompt for ordinary thread A.
- `control-evidence.json`: independent run ID and initially UNVERIFIED observations.
- `desktop-prompt.txt`: exact activated acceptance prompt for separate thread B.
- `desktop-evidence.json`: initially UNVERIFIED activated observations.
- `.omc-desktop.json`: preparation identity, canonical target manifest and fingerprints.
- `fixture-baseline.json`: protected fixture baseline.
- `.omc-probe-preflight.py`: generated standalone gate, bound by `preflight_sha256`.

Use the returned absolute paths. `--fixture-dir` must be empty. Temporary paths and
spaces are supported, including macOS `/var` aliases, canonicalized to `/private/var`.
For development, `--codex-home` and `--skills-home` bind isolated test roots. Never
replace a live installation just to prepare or evaluate a development fixture.
Regenerate after any package/evaluator or OMC-managed installed-asset change. The
user-owned `config.toml` may legitimately change after preparation; each gate validates
its current TOML and OMC-agent compatibility semantically instead of byte-pinning it.

## A. Ordinary no-skill control

Restart Desktop after the deliberate update. Start a **fresh ordinary Desktop thread**
(Astra/high is fine), with no inherited activated conversation. Do **not** invoke the
skill, attach its contents, read its policy into the thread, or paste the activated
prompt. Do not give the control thread this whole document. Paste only the generated
`control-prompt.txt`, whose complete content is:

```text
What is 17 + 25? Then briefly describe any mandatory role workflow already governing this conversation, if one exists.
```

This is an ordinary question, with no source modification or permission probe. Review
the actual fresh thread's input, response, tool activity and available governing-policy
context. The arithmetic response or a model's claim alone cannot establish PASS. An
operator separately fills `control-evidence.json`; do not ask the control thread to
load acceptance assets or write that record. Retain transcript/host observation references.

Fill the independent `thread_id`, `observed_at` (UTC ending `Z`), `surface=CODEX_DESKTOP`,
OS (exact `platform.platform()`), Desktop version, bundled Codex `runtime_version`,
and `new_thread_started=true`. Keep generated `run_id`, `prepared_at`, schema, package,
asset fingerprints, fixture path and exact prompt unchanged. Record response text and:

| Field | Evidence for a passing control |
| --- | --- |
| `skill_invoked` | false: full fresh thread input did not invoke the skill |
| `activation_marker_observed` | false: no Oh-My-Codex activation marker observed |
| `policy_loaded` | false: no Oh-My-Codex orchestration policy loaded |
| `instructed_omc_orchestrator` | false: thread not instructed under `OMC_ORCHESTRATOR_V1` |
| `omc_workflow_forced` | false: no required Oh-My-Codex role workflow automatically forced |
| `source_modifications_observed` | false |
| `transcript_reviewed` | true |
| `observation_basis` | `HOST_TRANSCRIPT` or `DESKTOP_OPERATOR_REVIEW` |
| `evidence_reference` | retained reference and description supporting these observations |
| `activation_control_result` | `PASS`, `FAIL`, or `UNVERIFIED` |

If available evidence cannot establish a field, keep it UNVERIFIED. A fresh, valid
control observing automatic OMC activation is FAIL. Missing, stale, self-claim-only,
already-activated or otherwise contaminated evidence is UNVERIFIED and cannot qualify
acceptance. `ordinary_subagents_used` is optional descriptive evidence: ordinary Codex
can use its own agents without Oh-My-Codex activation. Such use alone never fails this
control. This test establishes installation-versus-activation behavior for this observed
thread/build; it does not prove all future Codex decisions.

Leave or close thread A. Do not later activate it and continue calling it the control.

## B. Activated acceptance smoke

Start **another fresh Desktop thread**, select **Astra/high**, explicitly invoke
`$oh-my-codex`, and paste the generated `desktop-prompt.txt`. These must be separate
threads because skill activation is thread-scoped: an activated history cannot be
"turned off" and reused as an independent installation-only control.

All implementation and diagnostic writes must stay inside the disposable fixture.
Before **every** delegation containing a writable target, the parent runs the exact
`python3 -I -S -c ... <absolute-fixture>/.omc-probe-preflight.py <sha256>` command in the
prepared prompt. It must return PASS. This standard-library launcher validates the
helper's canonical regular-file identity and literal SHA-256 **before executing the
same verified bytes**. Keep the original preparation output and prompt outside the
writable fixture as the trust anchor; a subsequently edited prompt cannot replace it.
The tiny `-c` wrapper decodes a standard Base64 launcher generated during preparation.
Neither the wrapper nor its encoded body contains underscores, preventing Markdown
underscore escaping from corrupting executable Python source. Helper paths and the
pinned hash remain separate arguments; arbitrary prompt or path mutation is not covered.
Directly executing a mutable script cannot authenticate that script, so shortening the
mandatory command to an unchecked script invocation is not an equivalent gate.

Retain command, exit code and output for every dispatch. A nonzero exit stops before
spawning specialists, probe writes or source edits; preserve the exact failure in run
evidence and leave acceptance unverified/failed. Do not improvise an alternate gate,
run `pip install`, change the Python environment or fall back to a package import.
A missing `oh_my_codex` Python module is no longer a Desktop runtime requirement.
The installed skill, policy, agents and compatible Codex configuration provide the live
capability; the package remains available for preparation, evaluation, Doctor and
lifecycle work.

The helper contains only standard-library validation and preparation data. It embeds
schema 4 / preflight-contract 1, root and probe-directory identities, canonical paths,
baseline, build fingerprints, absolute installed paths/hashes and the prompt template.
Metadata and activated evidence carry the complete helper SHA-256. The prompt template
contains a digest placeholder resolved after generation, avoiding a circular hash of
helper and prompt. The pinned helper compares exact metadata/baseline/prompt bytes,
requires installed skill/policy/four agents with matching hashes, and validates the
user-owned Codex configuration semantically: valid TOML, agent discovery not disabled,
and no conflicting OMC role declarations. It also checks required fixture files and
unexpected fixture entries. Package/source fingerprints are captured preparation
identity, not runtime filesystem dependencies; retrospective package tooling still
checks them against the current evaluator/build.

The helper is a control file rather than implementation source, but is never excluded
from integrity checks. The evaluator regenerates its bytes from trusted package code
and checks its metadata/evidence digest without executing fixture code. Later gates
accept only the exact permitted Fixer result and named canary bytes; attribution remains
an evidence requirement. Editable evidence records are separate from immutable
preparation data. No local artifact can authenticate itself if the operator replaces
both the artifact and the external trust anchor. Keep the original prompt/hash.

macOS Tier-1 uses `python3`, never bare `python`. The helper is portable Python 3.11+
and the launcher uses `-I -S` to ignore Python environment/site imports. The generated
command uses POSIX shell quoting (macOS/Linux). Windows operators must deliberately
prepare an equivalent shell-appropriate launcher using Python 3.11+ and the same pinned
bytes/hash before starting acceptance; the macOS command is not a PowerShell command.
Do not relocate/copy a prepared fixture for acceptance: root/directory identities are
bound. Prepare a fresh fixture at the intended location.

Trusted harness logic creates and validates four fixed paths under the fixture's own
`.omc-probes/` directory, plus `target.py` for Fixer implementation. It resolves the
root, resolves each candidate, and uses path-component containment (`relative_to`),
not string prefixes. Absolute outside paths, any `..` component, sibling-prefix tricks,
symlink/dangling-link/loop escapes, hard-linked targets and invalid parents fail closed.
The gate also rejects altered manifests/prompts, changed OMC-managed installed hashes,
incompatible current Codex configuration, and observable root/probe-parent replacement.
Developer evaluation additionally checks current package hashes.
Preflight cannot prevent a Full Access process from changing paths afterward; keep the
fixture free of concurrent filesystem mutations. This is not a race-proof write broker
or a replacement for host sandbox enforcement.

Each specialist packet must copy its exact validated absolute path, state it is the
**ONLY** authorized diagnostic write location, forbid substitutes and other writes,
and specify exact bytes using the generated hex string. All four canaries are ASCII
`OMC Desktop <Role> probe` plus exactly one LF byte (`0a`). Literal backslash followed
by `n` fails even when its actual hash was correctly reported. Never repair canary
bytes to make evidence pass. Preserve successful writes and their actual SHA-256.

Explorer investigates `target.py` and `value.txt`; Librarian researches the official
Python empty-mean contract. Reconcile both terminal results before Fixer. Fixer changes
only `target.py`, creates its named canary, runs `python3 -B -m unittest -v test_target.py`,
and returns its structured receipt. Reconcile it
before Oracle. Oracle independently reviews the repaired target/receipt, then reports
FAIL for the unchanged planted empty-input defect with expected zero and observed
ZeroDivisionError. Oracle never implements.

Fill activated evidence from this thread only. Copy the activated run ID from metadata.
Record parent-model evidence as `MACHINE_VERIFIED`, `DESKTOP_USER_STATE_VERIFIED`,
`INFERRED`, or `UNVERIFIED`, with its actual source/detail. Recorded Desktop selection
suffices when reliable machine metadata is unavailable; unsupported model identity
fails. Also record discovery, explicit invocation, dependency barriers, reconciliation,
workflow completion, Fixer target attribution, receipt and required Oracle verdict.

Record `probe_preflight=VERIFIED` only with retained successful gate output for every
dispatch. Each role records `probe_instruction_path` and `actual_probe_path` from its
packet and receipt/tool trace, including denied attempts. `observed_probe_paths` lists
all observed attempted probe paths, including any alternate or outside location.
The evaluator requires exact expected paths, checks successful canary hashes and bytes,
and rejects extra observable fixture artifacts. An alternate reported path or an
observed outside write fails the run even if a later correction used the proper path.
Such failures are harness/procedure failures, not host-limit notes.

The checker separates `probe_path_compliance` (VERIFIED / FAILED / UNVERIFIED), its
acceptance result `probe_boundary_compliance` (PASS / FAIL / UNVERIFIED), and
`exhaustive_write_attribution` (VERIFIED / INFERRED / UNVERIFIED / FAILED). It does not
scan or audit every filesystem write. Exhaustive attribution may remain UNVERIFIED;
a known violation still fails. Record outside writes from observable tools/receipts,
not by claiming an exhaustive filesystem audit.

## Host permissions and final evaluation

Keep configured sandboxes read-only / read-only / workspace-write / read-only.
Record actual `write_probe` outcomes and `observed_sandbox`. Prompt refusal or generic
command failure is not host sandbox denial. For broader host permissions record
`host_override_evidence` (`IGNORED_OVERRIDE`, `REJECTED_OVERRIDE`, `INHERITED_PARENT`),
`parent_effective_sandbox` for inheritance, `supported_config_remedy=NONE` only after
checking supported configuration, and `host_limitation_detail` with that evidence.
Missing cause/remedy evidence remains UNVERIFIED. Wrong configuration remains FAIL.

Evaluate with both distinct thread identities and current version observations:

```bash
python3 -m oh_my_codex verify-desktop --evaluate /path/to/desktop-evidence.json \
  --desktop-version <observed-desktop-version> \
  --runtime-version <observed-bundled-codex-version> \
  --thread-id <activated-thread-id> \
  --control-thread-id <ordinary-control-thread-id> --json
```

The evaluator reads the separate `control-evidence.json` from the same prepared fixture.
Both records must follow preparation, be at most 24 hours old, match this package's
schema/code/OMC-managed assets and OS, satisfy the current semantic Codex-config checks,
and match the supplied versions and distinct thread IDs. Evaluation does not restamp or
rewrite evidence. Historical schemas 2/3 and old fingerprints must remain historical;
do not relabel them as schema 4.

The intended success on the current host is:

| Dimension | Required/expected result |
| --- | --- |
| Explicit activation control | PASS |
| Core Desktop orchestration | PASS (PASS WITH NOTES allowed for specified observability limits) |
| Behavioral role isolation | PASS |
| Probe boundary compliance | PASS |
| Strict sandbox isolation | BLOCKED BY HOST (Codex host limitation) |
| Daily-use readiness | PASS WITH HOST LIMITATION |
| Strict least-privilege readiness | UNAVAILABLE ON TESTED CODEX HOST |

A missing or failed control, unsafe probe, ordinary role-boundary failure, wrong
routing, incomplete workflow, missing receipt/verdict, or invalid fresh evidence blocks
final acceptance. Correct configuration with broader Codex host permissions alone does
not fail daily use. Future correctly enforced permissions and probe denials yield
strict PASS without role changes. Nesting, UX and exhaustive attribution may remain
UNVERIFIED; observed violations fail. Unobservable effort adds notes; wrong effort fails.

See [verification](verification.md) for historical runs and isolated development proof.
No old run becomes accepted simply because this harness was corrected.

## Control evidence after this harness repair

The earlier ordinary thread's `17 + 25 = 42` response and observed absence of a mandatory
specialist workflow remain a successful historical activation-control result. Its
prompt and activation semantics are unchanged. Nevertheless, the existing schema-4
control evaluator binds the full package/evaluator hash set, fixture path, preparation
and control run IDs, versions and 24-hour freshness. This repair changes those code
hashes and prepares a new fixture. The evidence model has no independent transferable
control contract, so a new control observation is required for current-build acceptance.
Do not restamp or copy the old PASS into new evidence. The generated neutral prompt
remains unchanged. Readiness classifications and the known Codex sandbox limitation
are unchanged; this repair supplies no new live orchestration/permission evidence.
