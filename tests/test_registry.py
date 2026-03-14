import time
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
        # After resurrection the entry should be resolvable
        result = registry.resolve(schema_id)
        self.assertEqual(result, BUNDLE_A)


if __name__ == "__main__":
    unittest.main()
