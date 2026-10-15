"""Upstox broker integration for the NATGAS engine.

Account connectivity and order submission are deliberately separated.
Live order placement remains disabled unless UPSTOX_LIVE_ORDER_ENABLED=true.
"""

from __future__ import annotations

import os
from typing import Any

import httpx


class UpstoxBroker:
    def __init__(self) -> None:
        self.access_token = os.getenv("UPSTOX_ACCESS_TOKEN", "")
        self.live_order_enabled = (
            os.getenv("UPSTOX_LIVE_ORDER_ENABLED", "false").lower() == "true"
        )
        self.base_url = "https://api.upstox.com"

    @property
    def configured(self) -> bool:
        return bool(self.access_token)

    def _headers(self) -> dict[str, str]:
        if not self.configured:
            raise RuntimeError("UPSTOX_ACCESS_TOKEN is not configured.")
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
        }

    def status(self) -> dict[str, Any]:
        if not self.configured:
            return {
                "broker": "upstox",
                "configured": False,
                "live_order_enabled": self.live_order_enabled,
            }

        response = httpx.get(
            f"{self.base_url}/v3/user/get-funds-and-margin",
            headers=self._headers(),
            timeout=15,
        )
        response.raise_for_status()
        return {
            "broker": "upstox",
            "configured": True,
            "live_order_enabled": self.live_order_enabled,
            "funds": response.json(),
        }

    def positions(self) -> dict[str, Any]:
        if not self.configured:
            raise RuntimeError("UPSTOX_ACCESS_TOKEN is not configured.")

        response = httpx.get(
            f"{self.base_url}/v2/portfolio/short-term-positions",
            headers=self._headers(),
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def place_order(
        self,
        *,
        instrument_token: str,
        quantity: int,
        transaction_type: str,
        order_type: str = "MARKET",
        price: float = 0,
        trigger_price: float = 0,
        product: str = "I",
        validity: str = "DAY",
        tag: str = "natgas-ai",
        slice_order: bool = False,
    ) -> dict[str, Any]:
        if not self.live_order_enabled:
            raise RuntimeError(
                "LIVE_ORDER_DISABLED: set UPSTOX_LIVE_ORDER_ENABLED=true "
                "on the server only after deliberate activation."
            )

        if not self.configured:
            raise RuntimeError("UPSTOX_ACCESS_TOKEN is not configured.")

        payload = {
            "quantity": quantity,
            "product": product,
            "validity": validity,
            "price": price,
            "tag": tag,
            "instrument_token": instrument_token,
            "order_type": order_type,
            "transaction_type": transaction_type,
            "disclosed_quantity": 0,
            "trigger_price": trigger_price,
            "is_amo": False,
            "slice": slice_order,
            "market_protection": -1,
        }

        response = httpx.post(
            "https://api-hft.upstox.com/v3/order/place",
            headers={
                **self._headers(),
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15,
        )
        response.raise_for_status()
        return response.json()
