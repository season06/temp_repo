from __future__ import annotations

import uuid
from typing import Any


class NullTracer:
    async def start_trace(self, name: str, metadata: dict[str, Any]) -> str:
        return uuid.uuid4().hex

    async def add_event(self, trace_id: str, name: str, metadata: dict[str, Any]) -> None:
        return None

    async def end_trace(
        self,
        trace_id: str,
        output: dict[str, Any],
        error: str | None = None,
    ) -> None:
        return None


class LangfuseSdkTracer:
    def __init__(self, sdk: Any) -> None:
        self.sdk = sdk

    async def start_trace(self, name: str, metadata: dict[str, Any]) -> str:
        trace_id = uuid.uuid4().hex
        await self.sdk.start_trace(trace_id=trace_id, name=name, metadata=metadata)
        return trace_id

    async def add_event(self, trace_id: str, name: str, metadata: dict[str, Any]) -> None:
        await self.sdk.add_event(trace_id=trace_id, name=name, metadata=metadata)

    async def end_trace(
        self,
        trace_id: str,
        output: dict[str, Any],
        error: str | None = None,
    ) -> None:
        await self.sdk.end_trace(trace_id=trace_id, output=output, error=error)

