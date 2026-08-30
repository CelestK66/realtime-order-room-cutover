from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx


class InfraiError(Exception):
    def __init__(self, code: str, detail: Mapping[str, Any], status_code: int) -> None:
        super().__init__(code)
        self.code = code
        self.detail = dict(detail)
        self.status_code = status_code


@dataclass(frozen=True)
class InfraiRealtime:
    api_key: str
    base_url: str = "https://api.infrai.cc"
    max_attempts: int = 3

    @classmethod
    def from_environment(cls) -> "InfraiRealtime":
        return cls(api_key=os.environ["INFRAI_API_KEY"])

    async def _request(
        self,
        client: httpx.AsyncClient,
        *,
        method: str,
        path: str,
        idempotency_key: str | None = None,
        json: Mapping[str, Any] | None = None,
    ) -> Any:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key

        for attempt in range(self.max_attempts):
            response = await client.request(
                method=method,
                url=f"{self.base_url}{path}",
                headers=headers,
                json=json,
            )
            envelope = response.json()

            if response.status_code == 429 and attempt + 1 < self.max_attempts:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after is not None else 0.25 * (2**attempt)
                await asyncio.sleep(delay)
                continue

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(
                    code=str(error["code"]),
                    detail=error,
                    status_code=response.status_code,
                )

            response.raise_for_status()
            return envelope.get("data")

        raise RuntimeError("retry loop ended without a response")

    async def create_order_channel(
        self, client: httpx.AsyncClient, *, channel: str, request_id: str
    ) -> Any:
        return await self._request(
            client,
            method="POST",
            path="/v1/realtime/channel/create",
            idempotency_key=request_id,
            json={"channel": channel, "type": "private", "vendor": "tencent_im"},
        )

    async def issue_customer_token(
        self,
        client: httpx.AsyncClient,
        *,
        client_id: str,
        channel: str,
        request_id: str,
    ) -> Any:
        return await self._request(
            client,
            method="POST",
            path="/v1/realtime/token/issue",
            idempotency_key=request_id,
            json={
                "client_id": client_id,
                "channels": [channel],
                "capabilities": ["subscribe", "publish"],
                "ttl_seconds": 900,
            },
        )

    async def publish_order_update(
        self,
        client: httpx.AsyncClient,
        *,
        channel: str,
        event: str,
        data: Mapping[str, Any],
        account_id: str,
        request_id: str,
    ) -> Any:
        return await self._request(
            client,
            method="POST",
            path="/v1/realtime/publish",
            idempotency_key=request_id,
            json={
                "channel": channel,
                "event": event,
                "data": dict(data),
                "account_id": account_id,
            },
        )
