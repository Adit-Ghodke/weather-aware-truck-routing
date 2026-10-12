"""
SafeHaul ResilientCache wrapper — automatic fallback from Redis to LocMemCache.

Requirements (§A18, §10, §12):
  • Django does NOT automatically fall back to LocMemCache when Redis fails.
  • Intercepts connection, timeout, and operational errors from primary cache (Redis).
  • Transparently delegates to in-memory LocMemCache fallback without crashing caller.
  • Provides full cache API (get, set, add, delete, get_many, set_many, delete_many, has_key, clear).
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.cache import caches
from django.core.cache.backends.base import DEFAULT_TIMEOUT, BaseCache

logger = logging.getLogger(__name__)

# Errors that trigger immediate fallback to in-memory cache
REDIS_FALLBACK_EXCEPTIONS: tuple[type[Exception], ...] = (
    ConnectionError,
    ConnectionRefusedError,
    TimeoutError,
    OSError,
)

try:
    import redis.exceptions
    REDIS_FALLBACK_EXCEPTIONS += (
        redis.exceptions.ConnectionError,
        redis.exceptions.TimeoutError,
        redis.exceptions.RedisError,
    )
except ImportError:
    pass


class ResilientCache(BaseCache):
    """Resilient cache wrapper that tries a primary cache (Redis) and falls back

    to a secondary in-memory cache (LocMemCache) on any network or connection failure.
    """

    def __init__(
        self,
        primary_cache_name: str = "default",
        fallback_cache_name: str = "locmem",
        params: dict | None = None,
    ):
        super().__init__(params or {})
        self.primary_cache_name = primary_cache_name
        self.fallback_cache_name = fallback_cache_name
        self._fallback_active = False
        self._primary_cache_override: BaseCache | None = None
        self._fallback_cache_override: BaseCache | None = None

    @property
    def primary_cache(self) -> BaseCache:
        if self._primary_cache_override is not None:
            return self._primary_cache_override
        return caches[self.primary_cache_name]

    @primary_cache.setter
    def primary_cache(self, value: BaseCache | None) -> None:
        self._primary_cache_override = value

    @primary_cache.deleter
    def primary_cache(self) -> None:
        self._primary_cache_override = None

    @property
    def fallback_cache(self) -> BaseCache:
        if self._fallback_cache_override is not None:
            return self._fallback_cache_override
        return caches[self.fallback_cache_name]

    @fallback_cache.setter
    def fallback_cache(self, value: BaseCache | None) -> None:
        self._fallback_cache_override = value

    @fallback_cache.deleter
    def fallback_cache(self) -> None:
        self._fallback_cache_override = None

    @property
    def is_fallback_active(self) -> bool:
        """Returns True if the cache has encountered errors and is using fallback."""
        return self._fallback_active

    def _handle_failure(self, operation: str, error: Exception) -> None:
        """Log warning and activate fallback state."""
        self._fallback_active = True
        logger.warning(
            f"ResilientCache: Primary cache '{self.primary_cache_name}' failed during {operation}: "
            f"{error}. Falling back to '{self.fallback_cache_name}'."
        )

    def get(self, key: str, default: Any = None, version: Any = None) -> Any:
        try:
            val = self.primary_cache.get(key, default=None, version=version)
            if val is not None:
                return val
        except REDIS_FALLBACK_EXCEPTIONS as err:
            self._handle_failure("get", err)

        # Fallback cache lookup
        return self.fallback_cache.get(key, default=default, version=version)

    def set(
        self,
        key: str,
        value: Any,
        timeout: Any = DEFAULT_TIMEOUT,
        version: Any = None,
    ) -> None:
        primary_ok = False
        try:
            self.primary_cache.set(key, value, timeout=timeout, version=version)
            primary_ok = True
        except REDIS_FALLBACK_EXCEPTIONS as err:
            self._handle_failure("set", err)

        # Always write to fallback cache if primary failed or fallback is active
        if not primary_ok or self._fallback_active:
            self.fallback_cache.set(key, value, timeout=timeout, version=version)

    def add(
        self,
        key: str,
        value: Any,
        timeout: Any = DEFAULT_TIMEOUT,
        version: Any = None,
    ) -> bool:
        try:
            return self.primary_cache.add(key, value, timeout=timeout, version=version)
        except REDIS_FALLBACK_EXCEPTIONS as err:
            self._handle_failure("add", err)
            return self.fallback_cache.add(key, value, timeout=timeout, version=version)

    def delete(self, key: str, version: Any = None) -> bool:
        deleted = False
        try:
            deleted = self.primary_cache.delete(key, version=version)
        except REDIS_FALLBACK_EXCEPTIONS as err:
            self._handle_failure("delete", err)

        fallback_deleted = self.fallback_cache.delete(key, version=version)
        return deleted or fallback_deleted

    def get_many(self, keys: list[str], version: Any = None) -> dict[str, Any]:
        results: dict[str, Any] = {}
        missing_keys = set(keys)

        try:
            primary_res = self.primary_cache.get_many(keys, version=version)
            if primary_res:
                results.update(primary_res)
                missing_keys -= set(primary_res.keys())
        except REDIS_FALLBACK_EXCEPTIONS as err:
            self._handle_failure("get_many", err)

        if missing_keys:
            fallback_res = self.fallback_cache.get_many(list(missing_keys), version=version)
            if fallback_res:
                results.update(fallback_res)

        return results

    def set_many(
        self,
        data: dict[str, Any],
        timeout: Any = DEFAULT_TIMEOUT,
        version: Any = None,
    ) -> list[Any]:
        failed_keys: list[Any] = []
        try:
            failed_keys = self.primary_cache.set_many(data, timeout=timeout, version=version) or []
        except REDIS_FALLBACK_EXCEPTIONS as err:
            self._handle_failure("set_many", err)

        if failed_keys or self._fallback_active:
            self.fallback_cache.set_many(data, timeout=timeout, version=version)

        return failed_keys

    def delete_many(self, keys: list[str], version: Any = None) -> None:
        try:
            self.primary_cache.delete_many(keys, version=version)
        except REDIS_FALLBACK_EXCEPTIONS as err:
            self._handle_failure("delete_many", err)

        self.fallback_cache.delete_many(keys, version=version)

    def has_key(self, key: str, version: Any = None) -> bool:
        try:
            if self.primary_cache.has_key(key, version=version):
                return True
        except REDIS_FALLBACK_EXCEPTIONS as err:
            self._handle_failure("has_key", err)

        return self.fallback_cache.has_key(key, version=version)

    def clear(self) -> None:
        try:
            self.primary_cache.clear()
        except REDIS_FALLBACK_EXCEPTIONS as err:
            self._handle_failure("clear", err)

        self.fallback_cache.clear()


# Default singleton instance
resilient_cache = ResilientCache()


def get_resilient_cache() -> ResilientCache:
    """Convenience getter for the global resilient cache instance."""
    return resilient_cache
