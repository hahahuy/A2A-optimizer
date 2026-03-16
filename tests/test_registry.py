import time
import threading
import unittest
from unittest.mock import patch

from ascp.registry import SchemaRegistry


BUNDLE_A = [
    {"name": "get_weather", "parameters": {"location": {"type": "string"}}},
]

BUNDLE_B = [
    {"name": "send_email", "parameters": {"to": {"type": "string"}, "body": {"type": "string"}}},
]


class TestSchemaRegistryRegistration(unittest.TestCase):
    def setUp(self):
        self.reg = SchemaRegistry()

    def test_register_returns_sha256_prefixed_id(self):
        schema_id, ttl = self.reg.register(BUNDLE_A)
        self.assertTrue(schema_id.startswith("sha256:"), schema_id)
        self.assertEqual(len(schema_id), len("sha256:") + 64)

    def test_register_returns_ttl(self):
        _, ttl = self.reg.register(BUNDLE_A, ttl=1800)
        self.assertEqual(ttl, 1800)

    def test_idempotent_same_id(self):
        id1, _ = self.reg.register(BUNDLE_A)
        id2, _ = self.reg.register(BUNDLE_A)
        self.assertEqual(id1, id2)

    def test_idempotent_ttl_extended(self):
        self.reg.register(BUNDLE_A, ttl=60)
        _, ttl2 = self.reg.register(BUNDLE_A, ttl=3600)
        self.assertEqual(ttl2, 3600)

    def test_different_bundles_different_ids(self):
        id_a, _ = self.reg.register(BUNDLE_A)
        id_b, _ = self.reg.register(BUNDLE_B)
        self.assertNotEqual(id_a, id_b)

    def test_empty_bundle_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.reg.register([])

    def test_register_ttl_zero_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.reg.register(BUNDLE_A, ttl=0)

    def test_register_ttl_negative_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.reg.register(BUNDLE_A, ttl=-1)


class TestSchemaRegistryResolve(unittest.TestCase):
    def setUp(self):
        self.reg = SchemaRegistry()

    def test_resolve_returns_original_bundle(self):
        schema_id, _ = self.reg.register(BUNDLE_A)
        result = self.reg.resolve(schema_id)
        self.assertEqual(result, BUNDLE_A)

    def test_resolve_unknown_id_raises_key_error(self):
        with self.assertRaises(KeyError):
            self.reg.resolve("sha256:" + "a" * 64)

    def test_resolve_expired_raises_key_error(self):
        registry = SchemaRegistry()
        schema_id, _ = registry.register([{"name": "t", "inputSchema": {}}], ttl=60)
        with patch("ascp.registry.time") as mock_time:
            mock_time.time.return_value = time.time() + 3600
            with self.assertRaises(KeyError):
                registry.resolve(schema_id)


class TestSchemaRegistryRefresh(unittest.TestCase):
    def setUp(self):
        self.reg = SchemaRegistry()

    def test_refresh_extends_ttl(self):
        schema_id, _ = self.reg.register(BUNDLE_A, ttl=60)
        new_ttl = self.reg.refresh(schema_id, ttl=7200)
        self.assertEqual(new_ttl, 7200)

    def test_refresh_unknown_raises_key_error(self):
        with self.assertRaises(KeyError):
            self.reg.refresh("sha256:" + "b" * 64)

    def test_refresh_expired_raises_key_error(self):
        registry = SchemaRegistry()
        schema_id, _ = registry.register([{"name": "t", "inputSchema": {}}], ttl=60)
        with patch("ascp.registry.time") as mock_time:
            mock_time.time.return_value = time.time() + 3600
            with self.assertRaises(KeyError):
                registry.refresh(schema_id)

    def test_refresh_ttl_zero_raises_value_error(self):
        registry = SchemaRegistry()
        schema_id, _ = registry.register([{"name": "t", "inputSchema": {}}])
        with self.assertRaises(ValueError):
            registry.refresh(schema_id, ttl=0)

    def test_refresh_ttl_negative_raises_value_error(self):
        registry = SchemaRegistry()
        schema_id, _ = registry.register([{"name": "t", "inputSchema": {}}])
        with self.assertRaises(ValueError):
            registry.refresh(schema_id, ttl=-1)


class TestSchemaRegistryEviction(unittest.TestCase):
    def setUp(self):
        self.reg = SchemaRegistry()

    def test_evict_expired_removes_entries(self):
        registry = SchemaRegistry()
        now = time.time()
        with patch("ascp.registry.time") as mock_time:
            mock_time.time.return_value = now
            registry.register(BUNDLE_A, ttl=60)
            registry.register(BUNDLE_B, ttl=3600)
            mock_time.time.return_value = now + 61
            removed = registry.evict_expired()
        self.assertEqual(removed, 1)

    def test_evict_expired_returns_zero_when_none_expired(self):
        self.reg.register(BUNDLE_A, ttl=3600)
        removed = self.reg.evict_expired()
        self.assertEqual(removed, 0)


class TestCanonicalJson(unittest.TestCase):
    def test_canonical_json_sorts_nested_keys(self):
        """Schema ID must be identical regardless of key order in nested objects."""
        registry = SchemaRegistry()
        bundle_ordered = [{"name": "t", "inputSchema": {"properties": {"a": {"type": "string"}, "z": {"type": "integer"}}}}]
        bundle_reversed = [{"name": "t", "inputSchema": {"properties": {"z": {"type": "integer"}, "a": {"type": "string"}}}}]
        id1, _ = registry.register(bundle_ordered)
        id2, _ = registry.register(bundle_reversed)
        self.assertEqual(id1, id2, "Same schema content with different key order must produce same ID")


class TestSchemaRegistryLen(unittest.TestCase):
    def setUp(self):
        self.reg = SchemaRegistry()

    def test_len_counts_active_entries(self):
        self.assertEqual(len(self.reg), 0)
        self.reg.register(BUNDLE_A)
        self.reg.register(BUNDLE_B)
        self.assertEqual(len(self.reg), 2)

    def test_len_excludes_expired(self):
        registry = SchemaRegistry()
        now = time.time()
        with patch("ascp.registry.time") as mock_time:
            mock_time.time.return_value = now
            registry.register(BUNDLE_A, ttl=60)
            registry.register(BUNDLE_B, ttl=3600)
            mock_time.time.return_value = now + 61
            self.assertEqual(len(registry), 1)


class TestSchemaRegistryEdgeCases(unittest.TestCase):
    def test_reregister_expired_bundle_resurrects_entry(self):
        registry = SchemaRegistry()
        schema_id, _ = registry.register(BUNDLE_A, ttl=60)
        with patch("ascp.registry.time") as mock_time:
            future = time.time() + 3600
            mock_time.time.return_value = future
            # Entry is expired; re-registering should resurrect it
            new_id, _ = registry.register(BUNDLE_A, ttl=60)
            self.assertEqual(schema_id, new_id)
            # Resolve while mock time is before the new entry expires
            mock_time.time.return_value = future + 30
            result = registry.resolve(schema_id)
        self.assertEqual(result, BUNDLE_A)


class TestSchemaRegistryMaxEntries(unittest.TestCase):
    def test_max_entries_constructor_param(self):
        registry = SchemaRegistry(max_entries=5)
        self.assertEqual(registry._max_entries, 5)

    def test_max_entries_zero_raises_value_error(self):
        with self.assertRaises(ValueError):
            SchemaRegistry(max_entries=0)

    def test_max_entries_negative_raises_value_error(self):
        with self.assertRaises(ValueError):
            SchemaRegistry(max_entries=-1)

    def test_evict_expired_cleans_up_at_capacity(self):
        registry = SchemaRegistry(max_entries=3)
        now = time.time()
        with patch("ascp.registry.time") as mock_time:
            mock_time.time.return_value = now
            registry.register([{"name": "t1"}], ttl=60)
            registry.register([{"name": "t2"}], ttl=60)
            registry.register([{"name": "t3"}], ttl=60)
            # Advance time so those 3 are expired
            mock_time.time.return_value = now + 120
            # Registering a 4th triggers auto-eviction; expired entries removed first
            registry.register([{"name": "t4"}], ttl=60)
        self.assertEqual(len(registry._store), 1)

    def test_store_does_not_grow_past_max_entries(self):
        registry = SchemaRegistry(max_entries=3)
        ids = []
        for i in range(5):
            sid, _ = registry.register([{"name": f"t{i}"}])
            ids.append(sid)
        # Store must be capped at 3
        self.assertEqual(len(registry._store), 3)
        # The 3 most recently registered entries (t2, t3, t4) should be present
        self.assertIn(ids[2], registry._store)
        self.assertIn(ids[3], registry._store)
        self.assertIn(ids[4], registry._store)
        # The 2 oldest (t0, t1) should be evicted
        self.assertNotIn(ids[0], registry._store)
        self.assertNotIn(ids[1], registry._store)

    def test_auto_eviction_not_triggered_when_under_max(self):
        registry = SchemaRegistry(max_entries=100)
        registry.register([{"name": "t1"}])
        registry.register([{"name": "t2"}])
        registry.register([{"name": "t3"}])
        registry.register([{"name": "t4"}])
        registry.register([{"name": "t5"}])
        self.assertEqual(len(registry._store), 5)

    def test_concurrent_register_safe_with_max_entries(self):
        registry = SchemaRegistry(max_entries=50)
        errors = []

        def register_batch(thread_id: int) -> None:
            try:
                for i in range(10):
                    registry.register([{"name": f"tool_t{thread_id}_{i}"}], ttl=3600)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=register_batch, args=(t,)) for t in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Concurrent registration raised errors: {errors}")
        # Hard cap must be respected — store must not exceed max_entries
        self.assertLessEqual(len(registry._store), 50)


if __name__ == "__main__":
    unittest.main()
