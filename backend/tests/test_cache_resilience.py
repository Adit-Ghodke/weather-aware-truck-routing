"""
Unit tests for SafeHaul ResilientCache wrapper (Phase 5).

Specifications from BUILD_PLAN.md §A18, §DR-06, §10, and §12.
Verifies that when primary Redis cache fails or times out, all operations
transparently fall back to LocMemCache without throwing exceptions.
"""

from unittest.mock import MagicMock, patch

from safehaul.adapters.cache import ResilientCache


class TestResilientCacheNormalOperations:
    """Verify standard cache operations on ResilientCache."""

    def test_get_and_set(self):
        cache = ResilientCache()
        cache.set("test_key", "test_value", timeout=60)
        assert cache.get("test_key") == "test_value"

    def test_get_default_when_missing(self):
        cache = ResilientCache()
        assert cache.get("nonexistent_key_123", default="fallback") == "fallback"

    def test_delete(self):
        cache = ResilientCache()
        cache.set("delete_me", 42)
        assert cache.get("delete_me") == 42
        cache.delete("delete_me")
        assert cache.get("delete_me") is None

    def test_get_many_and_set_many(self):
        cache = ResilientCache()
        data = {"multi_1": "a", "multi_2": "b"}
        cache.set_many(data, timeout=60)
        res = cache.get_many(["multi_1", "multi_2", "multi_missing"])
        assert res.get("multi_1") == "a"
        assert res.get("multi_2") == "b"
        assert "multi_missing" not in res

    def test_has_key(self):
        cache = ResilientCache()
        cache.set("present_key", True)
        assert cache.has_key("present_key") is True
        assert cache.has_key("absent_key") is False


class TestResilientCacheFallbackUnderRedisOutage:
    """Simulate Redis outages (ConnectionError, TimeoutError, etc.)

    and assert seamless fallback to LocMemCache.
    """

    def test_redis_connection_error_on_set_falls_back(self):
        cache = ResilientCache(fallback_cache_name="locmem")
        mock_primary = MagicMock()
        mock_primary.set.side_effect = ConnectionError("Connection refused by Redis")

        with patch.object(cache, "primary_cache", mock_primary):
            # Must NOT raise exception!
            cache.set("resilient_key", "survived_redis_outage", timeout=60)
            assert cache.is_fallback_active is True

            # Value should be preserved in fallback cache
            val = cache.fallback_cache.get("resilient_key")
            assert val == "survived_redis_outage"

    def test_redis_connection_error_on_get_falls_back(self):
        cache = ResilientCache(fallback_cache_name="locmem")
        # Pre-seed fallback cache
        cache.fallback_cache.set("preseeded_key", "recovered_value", timeout=60)

        mock_primary = MagicMock()
        mock_primary.get.side_effect = TimeoutError("Redis socket read timeout")

        with patch.object(cache, "primary_cache", mock_primary):
            val = cache.get("preseeded_key")
            assert val == "recovered_value"
            assert cache.is_fallback_active is True

    def test_redis_error_on_get_many_falls_back(self):
        cache = ResilientCache(fallback_cache_name="locmem")
        cache.fallback_cache.set_many({"k1": 10, "k2": 20})

        mock_primary = MagicMock()
        mock_primary.get_many.side_effect = ConnectionError("Redis crashed")

        with patch.object(cache, "primary_cache", mock_primary):
            res = cache.get_many(["k1", "k2"])
            assert res == {"k1": 10, "k2": 20}

    def test_redis_error_on_delete_falls_back(self):
        cache = ResilientCache(fallback_cache_name="locmem")
        cache.fallback_cache.set("k_del", "val")

        mock_primary = MagicMock()
        mock_primary.delete.side_effect = ConnectionError("Redis down")

        with patch.object(cache, "primary_cache", mock_primary):
            deleted = cache.delete("k_del")
            assert deleted is True
            assert cache.fallback_cache.get("k_del") is None

    def test_redis_error_on_clear_falls_back(self):
        cache = ResilientCache(fallback_cache_name="locmem")
        cache.fallback_cache.set("k_clear", "val")

        mock_primary = MagicMock()
        mock_primary.clear.side_effect = ConnectionError("Redis unavailable")

        with patch.object(cache, "primary_cache", mock_primary):
            cache.clear()  # Must not crash
            assert cache.fallback_cache.get("k_clear") is None

    def test_redis_error_on_add_falls_back(self):
        cache = ResilientCache(fallback_cache_name="locmem")
        mock_primary = MagicMock()
        mock_primary.add.side_effect = ConnectionError("Redis down")

        with patch.object(cache, "primary_cache", mock_primary):
            ok = cache.add("k_add", "val_add")
            assert ok is True
            assert cache.fallback_cache.get("k_add") == "val_add"

    def test_redis_error_on_set_many_falls_back(self):
        cache = ResilientCache(fallback_cache_name="locmem")
        mock_primary = MagicMock()
        mock_primary.set_many.side_effect = ConnectionError("Redis down")

        with patch.object(cache, "primary_cache", mock_primary):
            cache.set_many({"sm1": 1, "sm2": 2})
            assert cache.fallback_cache.get("sm1") == 1
            assert cache.fallback_cache.get("sm2") == 2

    def test_redis_error_on_delete_many_falls_back(self):
        cache = ResilientCache(fallback_cache_name="locmem")
        cache.fallback_cache.set("dm1", "a")
        mock_primary = MagicMock()
        mock_primary.delete_many.side_effect = ConnectionError("Redis down")

        with patch.object(cache, "primary_cache", mock_primary):
            cache.delete_many(["dm1"])
            assert cache.fallback_cache.get("dm1") is None

    def test_redis_error_on_has_key_falls_back(self):
        cache = ResilientCache(fallback_cache_name="locmem")
        cache.fallback_cache.set("hk1", "exists")
        mock_primary = MagicMock()
        mock_primary.has_key.side_effect = ConnectionError("Redis down")

        with patch.object(cache, "primary_cache", mock_primary):
            assert cache.has_key("hk1") is True
            assert cache.has_key("hk_absent") is False

    def test_add_normal_operation(self):
        cache = ResilientCache()
        assert cache.add("add_key", 100) is True
        assert cache.add("add_key", 200) is False  # already exists

    def test_delete_many_normal_operation(self):
        cache = ResilientCache()
        cache.set("dm_a", 1)
        cache.set("dm_b", 2)
        cache.delete_many(["dm_a", "dm_b"])
        assert cache.get("dm_a") is None
        assert cache.get("dm_b") is None

    def test_clear_normal_operation(self):
        cache = ResilientCache()
        cache.set("cl_a", 1)
        cache.clear()
        assert cache.get("cl_a") is None

    def test_get_resilient_cache_helper(self):
        from safehaul.adapters.cache import get_resilient_cache
        c = get_resilient_cache()
        assert isinstance(c, ResilientCache)

    def test_cache_deleters(self):
        cache = ResilientCache()
        cache.primary_cache = MagicMock()
        assert cache._primary_cache_override is not None
        del cache.primary_cache
        assert cache._primary_cache_override is None

        cache.fallback_cache = MagicMock()
        assert cache._fallback_cache_override is not None
        del cache.fallback_cache
        assert cache._fallback_cache_override is None

