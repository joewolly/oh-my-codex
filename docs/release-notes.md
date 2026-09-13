# Oh-My-Codex v1.0.0

Final macOS Codex Desktop acceptance completed on 2026-09-13.

## Acceptance

| Dimension | Result |
| --- | --- |
| Overall | **PASS WITH HOST LIMITATION** |
| Desktop verified | **true** |
| Evidence validity | **PASS** |
| Explicit activation control | **PASS** |
| Core orchestration | **PASS WITH NOTES** |
| Behavioral role isolation | **PASS** |
| Probe boundary compliance | **PASS** |
| Strict sandbox isolation | **BLOCKED BY HOST** |
| Daily-use readiness | **PASS WITH HOST LIMITATION** |
| Strict least-privilege readiness | **UNAVAILABLE ON TESTED CODEX HOST** |
| Failed evaluator checks | **0** |

Tested host:

- Codex Desktop `26.908.40834`
- Desktop build `8881`
- bundled Codex `0.154.0-alpha.6.2`
- bundle identifier `com.openai.codex`

The final fresh acceptance established that ordinary Desktop threads do not implicitly activate Oh-My-Codex, while explicit activation completes the intended Explorer/Librarian, Fixer, and Oracle dependency workflow with bounded Fixer implementation and independent Oracle review.

## Known host limitation

The tested Codex Desktop host grants broader permissions than the configured specialist sandboxes request. Daily orchestration, explicit activation control, behavioral role isolation, and probe-boundary compliance passed, but technical least-privilege enforcement is unavailable on this tested host.

This is a host-enforcement limitation rather than an Oh-My-Codex orchestration failure. The release does not claim hard read-only enforcement for specialists when the host does not provide it.

## Release scope

The package already declares version `1.0.0` in both package metadata and `oh_my_codex.__version__`. Release-finalization changes are documentation-only, so they do not alter the package/evaluator/managed-asset fingerprint used by the successful Desktop acceptance.

See `CHANGELOG.md` for the stable-release highlights and `docs/verification.md` for the dated historical verification campaigns.
