"""Lifecycle contracts for process scoped resources."""

from typing import Protocol

class AsyncCloseable(Protocol):
    "A process scoped resource that can be closed asynchronously."

    async def aclose(self) -> None: ...