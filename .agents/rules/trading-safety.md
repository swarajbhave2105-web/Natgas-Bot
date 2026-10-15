# Trading Safety Rules

This is a financial/trading application.

Never expose API keys, access tokens, secrets or credentials in source code, logs, commits or frontend code.

Never remove a safety check merely to improve performance.

Never enable live trade execution, order placement, cancellation or modification without explicit user approval for that specific action.

Separate analysis/signals from execution.

Treat production credentials and live execution as high-risk operations.

For trading calculations:
* preserve numerical correctness
* test important edge cases
* avoid silent changes to formulas
* verify timeframe assumptions
* verify instrument/contract assumptions
* verify units and price scales

For production changes:
* build/test first
* verify deployment
* verify live health
* verify affected market-data paths
* confirm no unrelated domain was altered

When uncertain, stop and report the uncertainty rather than inventing an assumption.
