"""Thin adapter around TauricResearch/TradingAgents.

The upstream project is used as the orchestration engine. NATGAS-specific
data collection and decision validation remain in this repository so we can
keep the instrument scope narrow and auditable.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TradingAgentsConfig:
    upstream_version: str = "0.5.1"
    ticker: str = "MCX_NATGAS"
    research_depth: int = 2
    debug: bool = False


class TradingAgentsAdapter:
    """Integration seam for the upstream LangGraph TradingAgents engine."""

    def __init__(self, config: TradingAgentsConfig | None = None):
        self.config = config or TradingAgentsConfig()

    def validate_scope(self, ticker: str) -> None:
        if ticker != self.config.ticker:
            raise ValueError(
                f"NATGAS-only engine: expected {self.config.ticker}, got {ticker}"
            )

    def build_context(self, evidence: dict) -> dict:
        """Convert normalized NATGAS evidence into an agent-ready context."""
        return {
            "instrument": self.config.ticker,
            "upstream_version": self.config.upstream_version,
            "evidence": evidence,
            "constraints": {
                "no_invented_data": True,
                "no_forced_trade": True,
                "allow_no_trade": True,
            },
        }
