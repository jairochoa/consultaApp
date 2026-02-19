from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class EventBus:
    _subs: dict[str, list[Callable[[], None]]] = field(default_factory=dict)

    def subscribe(self, topic: str, fn: Callable[[], None]) -> None:
        self._subs.setdefault(topic, []).append(fn)

    def publish(self, topic: str) -> None:
        for fn in self._subs.get(topic, []):
            fn()
