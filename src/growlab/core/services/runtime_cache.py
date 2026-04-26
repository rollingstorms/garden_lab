from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from time import monotonic
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    value: T
    expires_at: float


class TTLCache:
    def __init__(self) -> None:
        self._lock = RLock()
        self._entries: dict[tuple[object, ...], CacheEntry[object]] = {}

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def invalidate_prefix(self, prefix: tuple[object, ...]) -> None:
        with self._lock:
            for key in list(self._entries.keys()):
                if key[: len(prefix)] == prefix:
                    del self._entries[key]

    def get_or_set(self, key: tuple[object, ...], *, ttl_seconds: float, builder: Callable[[], T]) -> T:
        now = monotonic()
        with self._lock:
            cached = self._entries.get(key)
            if cached is not None and cached.expires_at > now:
                return cached.value  # type: ignore[return-value]
            if cached is not None:
                del self._entries[key]

        value = builder()
        expires_at = monotonic() + ttl_seconds
        with self._lock:
            self._entries[key] = CacheEntry(value=value, expires_at=expires_at)
        return value
