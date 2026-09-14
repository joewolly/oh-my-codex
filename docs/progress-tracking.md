# Overall plan progress in Codex Desktop

Oh-My-Codex uses Codex's built-in `update_plan` surface as the canonical user-visible
progress monitor for non-trivial repository work when that tool is available.

The checklist represents the user's actual overall execution plan, not OMC's internal
specialist activity. The main-thread Orchestrator owns the checklist. Explorer, Librarian,
Fixer, and Oracle work rolls up beneath the currently active overall milestone and must not
create competing top-level plans.

A typical Desktop checklist should look like:

```text
✓ 1/7 - Audit the existing implementation
✓ 2/7 - Define the required architecture changes
→ 3/7 - Implement the new orchestration behavior
○ 4/7 - Add regression tests
○ 5/7 - Run the full validation suite
○ 6/7 - Perform independent review
○ 7/7 - Resolve findings and final verification
```

Exactly one milestone is `in_progress` while active work remains. The current milestone
must identify the major overall-plan step actually being executed. OMC updates that state
when work advances, when validation causes rework, when scope changes, or when a blocker
changes the remaining plan.

## Enable the Codex plan tool

Recent Codex builds may require the plan tool to be enabled explicitly. Add the following
to the effective Codex `config.toml`:

```toml
[tools.update_plan]
enabled = true
```

For the default installation this is normally `~/.codex/config.toml`. Fully quit and
relaunch Codex Desktop, then start a new thread so the tool inventory is refreshed.

Oh-My-Codex deliberately does not rewrite user-owned `config.toml` during installation.
If `update_plan` is unavailable, orchestration remains valid and the Orchestrator reports
the same `N/TOTAL` overall milestone in its normal parent-thread status updates instead of
creating a second persistent planning system.
