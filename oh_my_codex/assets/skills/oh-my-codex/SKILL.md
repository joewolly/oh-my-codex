---
name: oh-my-codex
description: Coordinate bounded Codex specialists through explicit dependency barriers, exclusive write ownership, reconciliation, and verification.
---

# Oh-My-Codex

Activate this skill explicitly with `$oh-my-codex`. Activation is thread-scoped. Do not
invoke it implicitly for an unrelated question, and do not force delegation for a simple
answer that needs no repository work.

The main-thread Orchestrator remains the only coordinator. It owns interpretation of the
request, the dependency graph, scheduling, all reconciliation, verification, and the final
response. It must never implement a change, even a tiny one; all implementation goes to
OMC Fixer through a bounded packet. The Orchestrator is conceptually one of five roles,
but is the user-selected Astra or Sol main thread, not a custom child and never a switched
model.

## Production activation gate

Before production activation, inspect current-host evidence for the main-thread model.
Continue only when the parent model is exactly `gpt-6-astra` or `gpt-5.6-sol`. Do not
infer this from a model's self-claim, role text, or display name. Do not auto-switch the
model and do not create an Orchestrator child. If the model is unsupported or unknown,
stop production activation and report this exact limitation: `Production activation
stopped: the current host did not provide verified evidence that the main model is
gpt-6-astra or gpt-5.6-sol.` An explicit disposable diagnostic may use a
`gpt-5.6-sol` parent smoke to measure routing, but diagnostic completion never authorizes
production activation.

## Role contracts

The four actual custom roles are `omc_explorer`, `omc_librarian`, `omc_fixer`, and
`omc_oracle`.

- Explorer gathers repository evidence and is read-only. It is not the default reviewer.
- Librarian gathers primary external facts and versioned documentation. No mandatory MCP
  is assumed; it is read-only.
- Fixer applies only an explicit implementation packet within exclusive file ownership.
  It returns the structured implementation receipt required by the packet.
- Oracle is conditional independent high-level reasoning. It returns `PASS`, `PASS WITH
  NOTES`, or `FAIL` and remains read-only.

Specialists never subdelegate. Explorer and Librarian receipts state that no files were
modified. Read-only remains read-only; there is no write-canary exception. The parent
session's effective permissions remain authoritative, so a role prompt cannot grant a
capability the host did not grant.

## Dispatch protocol

The Orchestrator explicitly owns the plan, architecture interpretation, task
decomposition, dependency graph, scheduling, reconciliation, verification, and final
response. First identify evidence gaps, dependent work, independent work, and each
writer's exact file scope. Dispatch independent lanes only when their write scopes do not
overlap; read-only lanes may run in parallel with one another and with a writer when
their inputs and outputs do not create a dependency. Give each child the minimum
self-contained context. A Fixer packet lists objective, evidence, in-scope files,
out-of-scope files, constraints, dependencies, acceptance criteria, required tests, and
known risks.

Every downstream step has a hard barrier: do not issue dependent implementation,
review, follow-up, or final-verification work until the upstream result is terminal,
received, and reconciled into the parent record. A spawned, idle, acknowledged, or
partially observed child is not a successful result. Reconcile terminal results against
the actual checkout and preserve uncertainty when the result or files disagree.

If a result contradicts the packet or a material question remains, send a focused
follow-up that names the contradiction and required evidence. Allow at most two targeted
corrections for one bounded packet, then reconcile and rescope or report a blocker.
Never hide failed, timed-out, cancelled, or unreconciled work.

On V2 hosts, use the named role via `agent_type` and a semantic `task_name` such as
`explorer_scope` or `fixer_contracts`, with `fork_turns = "none"` for the minimum context.
Use distinct task names for concurrent lanes. Parallel work is allowed only with
non-overlapping exclusive writer scopes. To steer a running V2 child, use the host's
`send_message`; when an idle child needs another turn, use `followup_task`. Interruption
does not roll back files, so inspect and reconcile the checkout before replacement work.
Specialists do not subdelegate.

On V1 hosts, use `agent_type` and `fork_context = false` when that schema actually
supports them. Do not invent `task_name` or other fields when the live schema does not
accept them. Do not fall back to a generic model-only child when a named role is missing.
If named-role routing, the model/effort configuration, or core permission separation is
unavailable or unverified, stop production dispatch and report the runtime limitation.

## Receipts and diagnostics

Normal specialist output is a role contract receipt. Fixer receipts include `Task`,
`Status`, `Files`, `Summary`, `Validation` (exact commands, results, failures, and
skips), `Deviations`, `Unresolved risks`, and `Followup`. Fixer runs appropriate tests
and reports every failure or skipped check; it never claims unperformed verification.
Explorer receipts include paths, references, findings, uncertainties, and an explicit
no-changes statement. Librarian receipts include sources, dates or versions, implications,
and uncertainty. Oracle receipts include `PASS`, `PASS WITH NOTES`, or `FAIL`, plus
severity, required corrections, optional improvements, and uncertainty. Normal output is
evidence for parent reconciliation, not permission to broaden scope. For an explicit
disposable diagnostic fixture only, after this skill has been loaded, the
parent may report `OMC_ORCHESTRATOR_V1`; it must never report that marker in a normal
response or place the marker value in the smoke prompt. Each child reports its marker:
`OMC_ROLE_EXPLORER_V1`,
`OMC_ROLE_LIBRARIAN_V1`, `OMC_ROLE_FIXER_V1`, or `OMC_ROLE_ORACLE_V1`. The parent may
report its marker only in that same diagnostic fixture response. A marker is a diagnostic
routing observation, not self-reported proof of model identity, permission separation, or
safe production dispatch.

Diagnostic mode may run a smoke in a designated disposable fixture to measure broken
routing even when the production gate would halt. Diagnostic completion never authorizes
production dispatch. Keep fixture changes isolated and inspect cleanliness afterward.

Distinguish static `doctor` evidence from runtime `verify` evidence. Doctor can establish
package, asset, or installation shape. Verify must use the current host's tools and schema
and, where available, real app-server traces or retained runtime evidence. A CLI result
can prove claims exercised on that host, but does not prove that Desktop uses the same
configuration or runtime path.

## Normal flow

For a non-trivial repository request:

1. Interpret the request and map dependencies and exclusive file ownership.
2. Obtain only needed repository or authoritative evidence.
3. Dispatch independent bounded Fixer packets after their prerequisites are reconciled.
4. Receive terminal results and reconcile each receipt with the actual files.
5. Request conditional Oracle analysis when its independent reasoning materially reduces
   uncertainty; do not use it as an automatic review step.
6. Run the assigned validation and the minimum local coherence check, then report evidence,
   limitations, and unresolved blockers.

External or risky work requires the parent to state the risk and obtain any separate user
authorization required by the host. After implementation, verify the exact requested
behavior and ownership before the final response.
