# Mandatory AI Agent Instructions — GEMINI.md

This file serves as the mandatory project-level instruction entry point for all AI agents and automated workflows operating in this repository.

The authoritative rules for this financial market analysis and trading platform are defined in the `.agents/rules/` directory:
- `.agents/rules/trading-platform.md` — Domain isolation (NIFTY vs. MCX NATGAS), conceptual architecture boundaries, and preservation of working functionality.
- `.agents/rules/live-market-data.md` — Strict live-data qualification, latency measurement across the complete pipeline, freshness/heartbeat tracking, and explicit fallback labeling.
- `.agents/rules/change-control.md` — Strict scope enforcement (e.g., NIFTY ONLY / NATGAS ONLY), pre-change impact analysis, and contract preservation.
- `.agents/rules/trading-safety.md` — Zero secret leakage, mandatory explicit user approval for live trade execution, numerical correctness, and testing before production.

All agents must strictly comply with the following 10 core principles:

## 1. BEFORE ANY TASK
Every AI agent must read all four rule files under `.agents/rules/` before inspecting, modifying, testing, reviewing, or deploying application code.

## 2. RULE PRIORITY
The four Trading Platform rules are mandatory project constraints. Agents must not override, ignore, weaken, or reinterpret them merely to complete a task faster.

## 3. SCOPE CONTROL
Respect explicit user scope boundaries at all times, including:
- `NIFTY ONLY`
- `NATGAS ONLY`
- `frontend only`
- `backend only`
- `data-feed only`

Do not modify unrelated systems or refactor out-of-scope code.

## 4. LIVE DATA
Never represent delayed, stale, simulated, cached, fallback, or public data as LIVE. Any non-live or fallback data must be clearly and explicitly labeled as such.

## 5. TRADING SAFETY
Never enable live order execution or modify live-trading safety controls without explicit, unambiguous user approval for that specific action. Separate analysis/signals from execution.

## 6. CHANGE CONTROL
Before making significant changes:
- Identify affected files
- Identify dependencies
- Identify shared components
- Evaluate and explain potential NIFTY / NATGAS cross-domain impact
- Implement strictly within the approved scope

## 7. VALIDATION
Material changes must be tested and verified against actual running services and tests before being considered complete.

## 8. SECRETS
Never expose API keys, tokens, credentials, or secrets in source code, logs, frontend code, commits, or model responses.

## 9. PRODUCTION
Do not deploy destructive or live-impacting changes without explicit approval, pre-deployment testing, and verified health checks.

## 10. UNCERTAINTY
If an agent cannot determine whether a change is safe or within scope, it must stop and report the uncertainty rather than inventing an assumption.
