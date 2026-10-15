"""EIA adapter boundary.

The implementation is intentionally isolated from the rest of the engine so
the data source can be changed without changing analyst logic.
"""

import httpx


class EIAProvider:
    BASE_URL = "https://api.eia.gov/v2"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def get(self, route: str, params: dict | None = None) -> dict:
        query = dict(params or {})
        query["api_key"] = self.api_key
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(f"{self.BASE_URL}/{route.lstrip('/')}", params=query)
            response.raise_for_status()
            return response.json()
