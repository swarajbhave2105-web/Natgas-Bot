"""EIA weekly natural-gas storage adapter."""

import httpx


class EIAStorageProvider:
    """Fetch the configured EIA weekly storage dataset.

    The route is deliberately configurable so the application does not bake
    an unverified dataset path into trading logic.
    """

    BASE_URL = "https://api.eia.gov/v2"

    def __init__(self, api_key: str, route: str):
        if not api_key:
            raise ValueError("EIA API key is required")
        if not route:
            raise ValueError("EIA route is required")
        self.api_key = api_key
        self.route = route

    async def latest(self, limit: int = 5) -> dict:
        if limit < 1:
            raise ValueError("limit must be positive")

        params = {
            "api_key": self.api_key,
            "frequency": "weekly",
            "data[0]": "value",
            "sort[0][column]": "period",
            "sort[0][direction]": "desc",
            "offset": 0,
            "length": limit,
        }

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"{self.BASE_URL}/{self.route.lstrip('/')}",
                params=params,
            )
            response.raise_for_status()
            return response.json()
