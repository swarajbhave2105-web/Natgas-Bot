"""Reference-market provider boundaries.

These inputs are used as explanatory drivers for MCX NATGAS rather than as
direct substitutes for the MCX contract price.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ReferenceSnapshot:
    henry_hub: float | None = None
    usdinr: float | None = None
    crude_oil: float | None = None


class ReferenceMarketProvider:
    async def latest(self) -> ReferenceSnapshot:
        raise NotImplementedError
