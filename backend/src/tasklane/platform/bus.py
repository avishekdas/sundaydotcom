"""Event bus port (ADR-004) with an in-process implementation for local dev and tests.

``InProcessBus()`` is deterministic (sync mode). ``InProcessBus(chaos_seed=n)`` reproduces what
EventBridge + SQS can do in production — reordering, duplicate delivery — while keeping FIFO order within
a message group, exactly like SQS FIFO (DX-8). Consumers must be idempotent and order-tolerant.
"""

from __future__ import annotations

import fnmatch
import random
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

Handler = Callable[["Event"], None]


@dataclass(frozen=True, slots=True)
class Event:
    type: str
    event_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    group: str | None = None  # FIFO message group (e.g. "auto:{automation}:{item}")
    schema_version: int = 1


class Bus(Protocol):
    def publish(self, event: Event) -> None: ...


class InProcessBus:
    DUPLICATE_RATE = 0.1

    def __init__(self, chaos_seed: int | None = None) -> None:
        self._subs: list[tuple[str, Handler]] = []
        self._rng = random.Random(chaos_seed) if chaos_seed is not None else None  # noqa: S311 (test chaos, not crypto)
        self._ungrouped: deque[Event] = deque()
        self._groups: dict[str, deque[Event]] = {}

    def subscribe(self, pattern: str, handler: Handler) -> None:
        self._subs.append((pattern, handler))

    def publish(self, event: Event) -> None:
        self._enqueue(event)
        if self._rng is not None and self._rng.random() < self.DUPLICATE_RATE:
            self._enqueue(event)  # at-least-once delivery

    def _enqueue(self, event: Event) -> None:
        if event.group is None:
            self._ungrouped.append(event)
        else:
            self._groups.setdefault(event.group, deque()).append(event)

    def _next(self) -> Event | None:
        sources: list[deque[Event]] = [q for q in self._groups.values() if q]
        if self._ungrouped:
            sources.append(self._ungrouped)
        if not sources:
            return None
        if self._rng is None:
            # deterministic: ungrouped FIFO first, then groups in creation order
            return (self._ungrouped or next(q for q in self._groups.values() if q)).popleft()
        q = self._rng.choice(sources)
        if q is self._ungrouped:
            i = self._rng.randrange(len(q))  # reorder freely
            q.rotate(-i)
            e = q.popleft()
            q.rotate(i)
            return e
        return q.popleft()  # FIFO within a group

    def drain(self, max_deliveries: int = 100_000) -> int:
        delivered = 0
        while (event := self._next()) is not None:
            for pattern, handler in self._subs:
                if fnmatch.fnmatchcase(event.type, pattern):
                    handler(event)
            delivered += 1
            if delivered >= max_deliveries:
                raise RuntimeError("bus did not quiesce (possible event loop)")
        return delivered
