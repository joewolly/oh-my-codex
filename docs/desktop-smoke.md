# Codex Desktop smoke test

Codex Desktop on macOS is the Tier-1 observation surface. Standalone CLI/app-server
runs are LOW-LEVEL RUNTIME VERIFICATION and cannot satisfy Desktop acceptance.
This guided procedure records operator observations; it does not automate Desktop or
claim that entered metadata is independently machine-verified by the evaluator.

## Prepare without activating

```bash
python3 -m oh_my_codex verify-desktop --prepare --json
```

Preparation creates a disposable Git fixture, `desktop-prompt.txt`, and schema-3
`desktop-evidence.json` with unverified fields. It does not install, activate, contact
a provider, or change global policy. Supply `--codex-home` and `--skills-home` to bind
isolated test roots. Lifecycle validation must use temporary roots; do not replace a
live installation just to prepare or evaluate a fixture.

## Observe both invocation states

After a deliberate installation/update, restart Desktop and start a new thread.
First observe ordinary Codex in a thread **without** `$oh-my-codex`: installed custom
agents do not activate the orchestration contract. Record `normal_thread_without_skill`
only after observing that control. In a separate new thread, select Astra or Sol,
explicitly invoke `$oh-my-codex`, and run the prepared prompt. Record skill discovery,
`explicit_skill_invocation`, restart, and fresh-thread observations independently.

The active main thread coordinates and verifies. Explorer investigates the fixture;
Librarian researches the official Python empty-mean contract. Reconcile both terminal
results before dispatching Fixer, then reconcile Fixer's receipt before Oracle review.
Record dependency barriers, workflow completion, and target patch attribution. Oracle
must pass the repaired target/receipt and return FAIL with the expected-zero versus
ZeroDivisionError finding for the unchanged planted defect.

Record parent-model identity as `MACHINE_VERIFIED`, `DESKTOP_USER_STATE_VERIFIED`,
`INFERRED`, or `UNVERIFIED` in `parent_model_evidence`, with its source in
`parent_model_evidence_detail`. Use machine verified only for reliable host metadata;
recorded Desktop/user selection is sufficient when such metadata is unavailable.
Inferred/unverified identity adds a note; a known unsupported model fails core readiness.
Do not fabricate machine proof from the role's self-description.

## Preserve adversarial permission evidence

Explorer, Librarian, and Oracle each attempt their one named canary. The host should
deny those writes. Fixer should create the bounded probe and change only `target.py`.
A prompt refusal, generic command failure, or read-only OS directory is not sandbox
proof. Record the actual `write_probe` outcome and effective `observed_sandbox`.
If a read-only canary succeeds, **preserve it** and record its SHA-256 in
`write_probe_sha256`. Only those exact recorded canaries are excluded from normal
implementation attribution; changed protected bytes or extra files fail the workflow.

The configured sandboxes stay read-only / read-only / workspace-write / read-only.
For a broader effective sandbox, record each `host_override_evidence` as
`IGNORED_OVERRIDE`, `REJECTED_OVERRIDE`, or `INHERITED_PARENT`. For inheritance, also
record `parent_effective_sandbox`. Set `supported_config_remedy` to `NONE` only when
inspection of supported project configuration found no remedy, and put that evidence
in `host_limitation_detail`. Missing cause/remedy evidence is UNVERIFIED, not automatically
host-blocked. Wrong source/installed configuration is project FAIL.

## Evaluate current evidence

```bash
python3 -m oh_my_codex verify-desktop --evaluate /path/to/desktop-evidence.json \
  --desktop-version <observed-desktop-version> \
  --runtime-version <observed-runtime-version> \
  --thread-id <observed-desktop-thread-id> --json
```

Record Desktop build and exact `platform.platform()` OS value too. The evaluator binds
versions, OS, task/run identity, fixture baseline, package/evaluator code, installed
assets, and installed config hashes. Observation must follow preparation and be at
most 24 hours old. A changed evaluator invalidates acceptance just like changed role
assets. Evaluation never updates fingerprints or rewrites evidence. Schema-2 records
remain historical and must not be relabeled schema 3 or given new hashes/timestamps.

The output separates core orchestration, behavioral role isolation, strict sandbox
isolation, evidence validity, daily use, and strict least-privilege readiness:

| Core | Strict sandbox | Current valid evidence | Daily use |
| --- | --- | --- | --- |
| PASS / PASS WITH NOTES | PASS | Yes | PASS / PASS WITH NOTES |
| PASS / PASS WITH NOTES | BLOCKED BY HOST | Yes | PASS WITH HOST LIMITATION |
| FAIL | Any | Any | FAIL |
| Any | FAIL / UNVERIFIED | Any | FAIL |
| Any | Any | No | FAIL; fresh acceptance unavailable |

BLOCKED BY HOST prominently warns that behavioral boundaries do not technically prevent
writes. Future effective sandbox and probe results that match the intended contracts
produce strict PASS and remove that warning without changing role definitions.
Nesting enforcement, UX, and exhaustive attribution may remain UNVERIFIED without
failing core readiness. A proven nesting/attribution violation still fails core;
ordinary lack of observability does not. Observed wrong reasoning effort fails;
unobservable effort adds a note. Target patch attribution is required separately.

Normalize a verified passing target unittest result to `PASS` while retaining its raw
output. Never normalize a failure to success. The Fixer receipt and Oracle verdict are
required for this smoke even though independent Oracle review is conditional in normal
product work.

## Retained campaign evidence

The original 2026-09-12 Desktop record observed Astra/high, correct specialist routing,
core workflow behavior, and successful read-only canaries under `danger-full-access`.
It predates the user's subsequently reported post-restart discovery and the revised
classifier. Its schema and fingerprints do not qualify this final build. Preserve it
as historical behavior evidence; see [verification](verification.md). A fresh smoke is
required for final-build acceptance after deliberate installation, not as an implicit
activation step in this development campaign.
