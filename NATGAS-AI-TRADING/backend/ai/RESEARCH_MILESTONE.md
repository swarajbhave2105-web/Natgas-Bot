# Research milestone — Exa + Llama

- Exa search has been exercised against current NATGAS market research and returned source records suitable for the desk.
- backend/ai/exa_research.py normalizes those records into ResearchSource.
- backend/ai/runtime_research.py assembles the source-grounded ResearchContext.
- backend/ai/agent_prompts.py supplies separate Bull and Bear instructions with a strict no-invention rule.
- backend/ai/model_router.py keeps Llama available through OpenRouter or Ollama.
- The deterministic NATGAS decision gate remains downstream of all research.
- No broker, order-placement, or autonomous execution API is connected.

The upstream TradingAgents project is currently v0.5.1 and is used here as an orchestration reference rather than as a source of NATGAS market facts.
