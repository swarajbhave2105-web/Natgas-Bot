# LLM research runner

The NATGAS desk now has an executable model layer:

Exa ResearchProvider
-> ResearchContext
-> Bull prompt + Bear prompt
-> OpenAI-compatible LLM runner
-> Llama route
-> BullBearResearch result

The runner is deliberately separated from the deterministic decision service.
Model output is research evidence only and cannot place orders.

Required runtime configuration:
- OPENROUTER_API_KEY when using the default Llama route.
- NATGAS_LLAMA_MODEL to select the model.
- NATGAS_LLAMA_BASE_URL when using a custom OpenAI-compatible endpoint.

The upstream TradingAgents framework supports multiple LLM providers and uses
LangGraph for orchestration; this repository keeps its NATGAS data and risk
boundaries independent of provider-specific model logic.
