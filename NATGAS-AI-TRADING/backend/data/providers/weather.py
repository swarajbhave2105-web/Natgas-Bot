"""Weather provider boundary for U.S. natural-gas demand signals."""

import httpx


class NWSProvider:
    BASE_URL = "https://api.weather.gov"

    async def get(self, path: str) -> dict:
        headers = {"User-Agent": "NATGAS-AI-TRADING/0.1"}
        async with httpx.AsyncClient(timeout=20, headers=headers) as client:
            response = await client.get(f"{self.BASE_URL}/{path.lstrip('/')}")
            response.raise_for_status()
            return response.json()
