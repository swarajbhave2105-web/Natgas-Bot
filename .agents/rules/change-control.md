# Change Control Rules

Scope boundaries are strict.

If the user says:
"NIFTY ONLY"
then NATGAS code, calculations, feeds, APIs, UI and configuration must not be modified unless explicitly required by a shared dependency and clearly reported.

If the user says:
"NATGAS ONLY"
then NIFTY must remain untouched under the same principle.

Before making a significant change:
1. Identify affected files.
2. Identify dependencies.
3. Identify shared components.
4. Explain potential cross-domain impact.
5. Implement only the requested scope.

Never modify unrelated files for cleanup.

Never rewrite working systems merely because another implementation is preferred.

Preserve existing APIs/contracts unless the requested change requires a breaking change.

Before completion, verify that unrelated domains remain unchanged.
