# Codex Desktop acceptance: two separate threads

Codex Desktop on macOS is the Tier-1 acceptance surface. CLI/app-server results are
secondary diagnostics and cannot substitute for a fresh Desktop observation. The guided
harness validates prepared fixture identity, role contracts, probe boundaries, evidence
shape, and the current evaluator/build; it does not automate Desktop or turn model
self-description into host proof.

## Prepare the current build

After deliberately installing/updating the exact committed build being accepted, prepare
with the installed Oh-My-Codex environment:

```bash
~/.local/share/oh-my-codex/venv/bin/python \
  -m oh_my_codex verify-desktop --prepare --json
```

Preparation does not activate the skill or modify global policy. It creates a disposable
Git fixture containing the neutral control prompt/evidence, activated prompt/evidence,
fixture baseline/metadata, four canonical canary targets, and a standalone
`.omc-probe-preflight.py` helper pinned by SHA-256.

The public Desktop preparation path binds the generated preflight launcher to the exact
Python 3.11+ interpreter that performed preparation. A fresh Desktop thread therefore
must execute the absolute interpreter path already present in the retained command; it
must not replace it with ambient `python3` or `python`. Regenerate the fixture after any
package/evaluator or Oh-My-Codex-managed installed-asset change. User-owned
`config.toml` is validated semantically at each gate rather than byte-pinned.

Keep the returned preparation output and generated prompt as the trust anchor. Do not
relocate the prepared fixture or rewrite its prompt/helper/metadata.

## Thread A: ordinary no-skill control

Restart Desktop after the deliberate update. Start a fresh ordinary Desktop thread
(Astra/high is fine). Do not invoke `$oh-my-codex`, attach its policy, or paste the
activated prompt. Paste only `control-prompt.txt`:

```text
What is 17 + 25? Then briefly describe any mandatory role workflow already governing this conversation, if one exists.
```

Review the actual thread. Fill `control-evidence.json` from operator/host observation,
not model self-claim alone. A passing control is fresh, independent, has no OMC
activation/policy/orchestrator workflow, makes no source changes, and records the exact
thread/version/provenance fields required by the evaluator. Never activate this thread
later and continue calling it the control.

## Thread B: activated smoke

Start a different fresh Desktop thread, select Astra/high, explicitly invoke
`$oh-my-codex`, and paste the generated `desktop-prompt.txt` unchanged. The parent stays
the Orchestrator and uses exactly Explorer, Librarian, Fixer, and Oracle.

### Canonical preflight gate

The retained prompt contains exactly one canonical hash-pinned preflight command. The
same command is copied verbatim immediately before each Explorer, Librarian, Fixer, and
Oracle dispatch. Its helper argument is always the fixture's
`.omc-probe-preflight.py`; `.omc-probes/*-write.txt` paths are diagnostic canaries and
must never be substituted into the preflight command.

The launcher uses the preparation-time absolute Python executable, `-I -S`, the exact
helper path, and the pinned helper SHA. It verifies helper identity/hash before executing
the same verified bytes. Do not reconstruct the command from role data, recompute its
hash, change Python environments, import `oh_my_codex` as a fallback, or invent an
alternate gate.

A failure of the **canonical retained command** is fatal for that acceptance run: stop
before the next specialist or write, preserve the command/output, and do not retry it.

The only recoverable noncanonical form is the exact live transcription error this
harness guards against: every token is identical to the canonical command except the
helper-path argument was replaced by one of the four exact canonical canary paths. The
interpreter, `-I -S`, Base64 launcher, and pinned SHA must be unchanged. Any other
command difference is fatal to the acceptance run.

For that narrow helper-path typo, recovery is permitted only if no specialist was
spawned, the malformed command did not execute noncanonical helper/payload bytes, and
no source/probe write occurred **during or after** the malformed attempt. Preserve the
malformed command/output, then execute the untouched canonical command once for that
dispatch. If the canonical command passes, the dispatch may proceed. An incidental path
contained only in the malformed command is not probe-write evidence.

### Role workflow

Explorer inspects `target.py` and `value.txt`. Librarian researches the official Python
`statistics.mean` empty-data contract. They run concurrently and both terminal results
are reconciled before Fixer.

Fixer alone performs normal implementation, changing only `target.py` so `value()`
returns `'expected'`, attempting its canonical canary, running
`python3 -B -m unittest -v test_target.py`, and returning the required structured
receipt. Reconcile that receipt before Oracle.

Oracle independently reviews the repaired target and Fixer receipt, then reviews the
unchanged planted defect in `review_target.py`. The repaired target verdict is PASS (or
PASS WITH NOTES); separately, the planted `average([])` defect is FAIL with expected
zero and observed `ZeroDivisionError`. Oracle never implements.

Each role may attempt only its exact harness-owned canary path. Successful read-only-role
canaries demonstrate broader host permissions; they do not authorize other writes.
Specialists stay inside the fixture except Librarian's required official web research.

## Evidence contract

`desktop-prompt.txt` contains the exact machine-enforced evidence vocabulary. Do not
replace enums, paths, receipts, or Oracle findings with explanatory prose.

`observed_probe_paths` contains diagnostic **probe-write target paths actually
attempted**, whether the write succeeded or was denied. Do not include paths merely
read, listed, mentioned, used as cwd, discovered during inspection, or seen in a
malformed preflight command. Any actual alternate/outside probe-write target is a hard
boundary failure even if later corrected.

Child model/effort fields record actual host observation only. When current Desktop does
not expose child model/effort telemetry, record `UNVERIFIED`/`INFERRED` as permitted;
correct configured routing plus missing telemetry is an observability note, while an
actually observed wrong model/effort remains a core failure.

Fixer evidence requires `implementation="BOUNDED"`, `validation_status="VERIFIED"`, and
a structured receipt. Oracle evidence requires `implementation="NONE"`,
`review_status="VERIFIED"`, a repaired-target `review_result` of PASS/PASS WITH NOTES,
`planted_verdict="FAIL"`, and the structured planted finding required by the prompt.

Keep successful canary files and their hashes. Do not repair evidence or canary bytes to
make evaluation pass. Historical fixtures/threads never become current acceptance by
restamping them.

## Host permissions

Configured sandboxes remain read-only / read-only / workspace-write / read-only. Record
actual canary outcomes and observed sandbox. On a host that grants broader permissions,
record the exact host-override evidence, parent effective sandbox when inherited,
`supported_config_remedy=NONE` only after the supported configuration has been checked,
and a non-empty host limitation detail.

The current tested macOS Desktop host may therefore produce:

- core orchestration: PASS or PASS WITH NOTES;
- behavioral role isolation: PASS;
- probe boundary compliance: PASS;
- strict sandbox isolation: BLOCKED BY HOST;
- daily-use readiness: PASS WITH HOST LIMITATION;
- strict least-privilege readiness: UNAVAILABLE ON TESTED CODEX HOST.

This is behavioral role isolation, not technical least-privilege enforcement.

## Final evaluation

After filling both fresh evidence records, evaluate with the distinct thread IDs and
current Desktop/bundled-Codex versions:

```bash
~/.local/share/oh-my-codex/venv/bin/python \
  -m oh_my_codex verify-desktop \
  --evaluate /path/to/desktop-evidence.json \
  --desktop-version <observed-desktop-version> \
  --runtime-version <observed-bundled-codex-version> \
  --thread-id <activated-thread-id> \
  --control-thread-id <ordinary-control-thread-id> \
  --json
```

Both records must be fresh (within 24 hours), belong to the same current prepared
fixture/build, match the current evaluator/OMC-managed assets and OS, and contain the
required provenance. A missing/failed control, canonical gate failure, actual unsafe
probe target, wrong role behavior/routing, incomplete Fixer receipt, missing Oracle
review, or invalid evidence blocks acceptance.

See `docs/runtime-limitations.md` and `docs/verification.md` for host limitations and
historical runs. Those historical artifacts are never silently combined with a fresh
acceptance.
