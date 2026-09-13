# Architecture

Oh-My-Codex is a thin, thread-scoped coordination contract over the host's native
Codex subagent surface. It has four custom child roles and one conceptual main-thread
role:

| Role | Model / effort | Writability | Purpose |
| --- | --- | --- | --- |
| Main-thread Orchestrator | User-selected Astra or Sol | No implementation (instruction enforced) | Interpret, graph, schedule, reconcile, verify, and answer |
| `omc_explorer` | Luna / medium | Desired read-only; host may ignore `sandbox_mode` | Repository evidence and navigation |
| `omc_librarian` | Luna / high | Desired read-only; host may ignore `sandbox_mode` | Primary external facts and versioned references |
| `omc_fixer` | Luna / high | Desired workspace-write; parent permissions authoritative | Bounded implementation packets |
| `omc_oracle` | Sol / high | Desired read-only; host may ignore `sandbox_mode` | Conditional independent high-level reasoning |

The main thread is not a custom child and is never switched to a role model. A child
role's model and effort are configuration intent; the host's parent permissions remain
authoritative. The role `sandbox_mode` values and `[agents] enabled = false` setting are
desired configuration: the current host may ignore either, so prompts also require that
specialists never subdelegate and runtime verification must inspect effective permissions.

The execution graph is deliberately small:

```text
request -> interpret and map ownership -> gather evidence
                                      -> dispatch independent bounded packets
                                      -> receive terminal results
                                      -> reconcile results with checkout
                                      -> verify -> final response
```

Each writer has an exclusive file scope. Independent lanes may run in parallel only when
their scopes do not overlap. A dependent operation waits behind a hard barrier until its
predecessor is terminal, received, and reconciled. Spawned, idle, acknowledged, or
partially observed work is not success. Contradictions produce a focused follow-up or a
blocker; they do not trigger an unbounded retry or a silent redesign.

Explorer, Librarian, and Oracle do not edit files. Fixer is the only implementation
writer and returns a structured receipt. Oracle is conditional rather than an automatic
review gate. There is no daemon, persistent task board, wake scheduler, or custom runtime
plumbing in this architecture.
