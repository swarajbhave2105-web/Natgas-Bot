"""Model routing for the NATGAS analyst layer.

Llama can be supplied through an OpenAI-compatible endpoint such as OpenRouter
or a self-hosted Ollama endpoint. The application never hard-codes a provider
credential.
"""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class ModelRoute:
    provider: str
    model: str
    base_url: str | None = None


_active_route_override: str | None = None


def get_routes() -> dict[str, ModelRoute]:
    return {
        "omniroute": ModelRoute(
            provider=os.getenv("NATGAS_OMNIROUTE_PROVIDER", "omniroute"),
            model=os.getenv("NATGAS_OMNIROUTE_MODEL", os.getenv("OMNIROUTE_MODEL", "auto")),
            base_url=os.getenv(
                "NATGAS_OMNIROUTE_BASE_URL",
                os.getenv("OMNIROUTE_BASE_URL", "http://localhost:20128/v1"),
            ),
        ),
        "deep_reasoning": ModelRoute(
            provider=os.getenv("NATGAS_DEEP_PROVIDER", "openai"),
            model=os.getenv("NATGAS_DEEP_MODEL", "gpt-6-sol"),
            base_url=os.getenv("NATGAS_DEEP_BASE_URL"),
        ),
        "fast_reasoning": ModelRoute(
            provider=os.getenv("NATGAS_FAST_PROVIDER", "openai"),
            model=os.getenv("NATGAS_FAST_MODEL", "gpt-6-luna"),
            base_url=os.getenv("NATGAS_FAST_BASE_URL"),
        ),
        "llama": ModelRoute(
            provider=os.getenv("NATGAS_LLAMA_PROVIDER", "openrouter"),
            model=os.getenv("NATGAS_LLAMA_MODEL", "meta-llama/llama-4-maverick"),
            base_url=os.getenv("NATGAS_LLAMA_BASE_URL"),
        ),
    }


def get_active_route_name() -> str:
    if _active_route_override:
        return _active_route_override
    return os.getenv("NATGAS_ACTIVE_AI_ROUTE", "omniroute").strip().lower()


def set_active_route_name(name: str | None) -> None:
    global _active_route_override
    _active_route_override = name.strip().lower() if name else None


def get_active_route() -> ModelRoute:
    """Return the active model route. Defaults to OmniRoute."""
    routes = get_routes()
    name = get_active_route_name()
    return routes.get(name, routes["omniroute"])

