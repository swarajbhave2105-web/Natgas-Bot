# Trading Platform Rules

This repository contains a production-oriented financial market analysis and trading platform.

The system has two explicitly separated domains:
1. NIFTY
2. MCX NATGAS

Maintain strict domain isolation.

The platform should conceptually separate:
MARKET DATA
→ DATA INGESTION
→ NORMALIZATION
→ TIMEFRAME/INDICATOR ENGINE
→ STRATEGY/ANALYSIS
→ POSITION/P&L
→ API/STREAM
→ FRONTEND/DASHBOARD

Do not mix market-data responsibilities with UI logic.

Do not duplicate trading calculations between backend and frontend unless explicitly required.

Preserve existing working functionality unless the requested change explicitly requires modification.

Prefer small, testable, reversible changes.

Never perform unrelated refactoring during a scoped task.
