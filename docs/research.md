# Research record

This record captures the local source inspection that shaped the bounded contracts. It
is evidence for design boundaries, not a claim that Oh-My-Codex embeds or depends on the
source projects.

## Local inspiration snapshot

The supplied `/tmp/oh-my-opencode-slim.7qna8z` checkout was inspected at commit
`14623890db4a535fa4d4e1a0a149bbcc27385a34`, dated 2026-09-12, package version 2.2.19.
The checkout's describe output was `1462389`; package 2.2.19 != beta tag. Relevant files
were:

- [`src/agents/*.ts`](https://github.com/alvinunreal/oh-my-opencode-slim/tree/14623890db4a535fa4d4e1a0a149bbcc27385a34/src/agents)
  and the agent permission helpers: role descriptions separate
  read-only advisory lanes from the write-capable Fixer and discourage default review.
- [`src/utils/background-job-board.ts`](https://github.com/alvinunreal/oh-my-opencode-slim/blob/14623890db4a535fa4d4e1a0a149bbcc27385a34/src/utils/background-job-board.ts)
  and [`src/utils/background-job-coordinator.ts`](https://github.com/alvinunreal/oh-my-opencode-slim/blob/14623890db4a535fa4d4e1a0a149bbcc27385a34/src/utils/background-job-coordinator.ts):
  terminal state, reconciliation, retry boundaries, and explicit ownership are more
  reliable than assuming an idle or spawned task succeeded.
- [`src/tools/task-result.ts`](https://github.com/alvinunreal/oh-my-opencode-slim/blob/14623890db4a535fa4d4e1a0a149bbcc27385a34/src/tools/task-result.ts)
  and [`src/utils/task.ts`](https://github.com/alvinunreal/oh-my-opencode-slim/blob/14623890db4a535fa4d4e1a0a149bbcc27385a34/src/utils/task.ts): task results preserve running,
  retry, error, cancellation, and terminal ambiguity for the coordinator to reconcile.
- [`docs/background-orchestration.md`](https://github.com/alvinunreal/oh-my-opencode-slim/blob/14623890db4a535fa4d4e1a0a149bbcc27385a34/docs/background-orchestration.md): the useful sequence is understand, graph, dispatch,
  monitor, reconcile, and verify; its OpenCode-specific task plumbing, wake scheduler,
  and board are intentionally excluded here.
- [`src/skills/verification-planning/SKILL.md`](https://github.com/alvinunreal/oh-my-opencode-slim/blob/14623890db4a535fa4d4e1a0a149bbcc27385a34/src/skills/verification-planning/SKILL.md),
  [`src/skills/deepwork/SKILL.md`](https://github.com/alvinunreal/oh-my-opencode-slim/blob/14623890db4a535fa4d4e1a0a149bbcc27385a34/src/skills/deepwork/SKILL.md),
  and [`src/skills/loop-engineering/SKILL.md`](https://github.com/alvinunreal/oh-my-opencode-slim/blob/14623890db4a535fa4d4e1a0a149bbcc27385a34/src/skills/loop-engineering/SKILL.md): bounded verification, independent maker/checker reasoning, ownership isolation, durable evidence, and bounded retries informed the contract language.

## Codex host snapshot

The supplied `/tmp/codex-upstream.SbJ09S` checkout was inspected at main commit
`b979d4f1f04538ba5a5fcc434d499c007bfe1b8c` and local tag commit
`3c6cfbab81e44218c729dc8c6b304cb760d1b8a1` (installed version 0.152.1). The role source
[`codex-rs/core/src/agent/role.rs`](https://github.com/openai/codex/blob/b979d4f1f04538ba5a5fcc434d499c007bfe1b8c/codex-rs/core/src/agent/role.rs) applies named role overrides to a parent-derived
configuration. The inspected implementation projects model, effort, and developer
instructions, while the effective parent configuration remains the authority.

The inspected [`multi_agents.rs`](https://github.com/openai/codex/blob/b979d4f1f04538ba5a5fcc434d499c007bfe1b8c/codex-rs/core/src/session/multi_agents.rs)
protocol accepts V2 `agent_type`, `task_name`, and `fork_turns`; `fork_turns = "none"`
avoids copying parent context. V2 ignores the legacy `max_depth` setting, while the V1
surface uses `agent_type` and `fork_context` and defaults to a maximum depth of one where
that schema supports it. Schema support must be checked on the current host; fields are
not invented across versions.

The current role source projects selected model/effort/instructions but does not establish
`sandbox_mode` or `[agents]` overrides as effective child permission enforcement, even
though broader settings may appear in host documentation. Permission separation remains
a runtime verification requirement. The installed 0.152.1 Thread metadata observed in
this source does not expose model or effort, and the inspected exec request JSON drops
those fields; UI/thread metadata is therefore not execution telemetry.

## Authoritative references

- [Codex subagents](https://developers.openai.com/codex/subagents) redirects to the
  current [subagent configuration documentation](https://learn.chatgpt.com/docs/agent-configuration/subagents).
- [Codex skills](https://learn.chatgpt.com/docs/build-skills) documents skill discovery
  and explicit invocation conventions.

No external research, provider assumption, or runtime claim is substituted for evidence
from the current host's schema and retained traces.
