"""Tests for ascp.artifact_store — TDD, 14 cases."""

import hashlib
import time
import unittest

from ascp.artifact_store import ArtifactEntry, ArtifactStore


def _sha256_cid(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


class TestArtifactStoreStore(unittest.TestCase):
    def setUp(self):
        self.store = ArtifactStore()

    # 1. store(bytes) returns correct sha256: CID
    def test_store_bytes_returns_correct_cid(self):
        content = b"hello world"
        cid = self.store.store(content)
        self.assertEqual(cid, _sha256_cid(content))
        self.assertTrue(cid.startswith("sha256:"))
        self.assertEqual(len(cid), len("sha256:") + 64)

    # 2. store(str) encodes as UTF-8, returns correct CID
    def test_store_str_encodes_utf8(self):
        text = "héllo"
        cid = self.store.store(text)
        self.assertEqual(cid, _sha256_cid(text.encode("utf-8")))

    # 3. Idempotency: same content → same CID, no duplicate entry
    def test_store_idempotent(self):
        content = b"idempotent"
        cid1 = self.store.store(content)
        cid2 = self.store.store(content)
        self.assertEqual(cid1, cid2)
        self.assertEqual(self.store.count, 1)

    # 12. Empty content raises ValueError
    def test_store_empty_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.store.store(b"")
        with self.assertRaises(ValueError):
            self.store.store("")

    # 13. Content exceeding max_bytes raises ValueError
    def test_store_exceeds_max_bytes_raises_value_error(self):
        tiny_store = ArtifactStore(max_bytes=10)
        with self.assertRaises(ValueError):
            tiny_store.store(b"x" * 11)


class TestArtifactStoreRetrieve(unittest.TestCase):
    def setUp(self):
        self.store = ArtifactStore()

    # 4. retrieve() returns correct ArtifactEntry with all fields
    def test_retrieve_returns_correct_entry(self):
        content = b"retrieve me"
        before = time.time()
        cid = self.store.store(content, media_type="application/octet-stream")
        after = time.time()

        entry = self.store.retrieve(cid)
        self.assertIsInstance(entry, ArtifactEntry)
        self.assertEqual(entry.cid, cid)
        self.assertEqual(entry.content, content)
        self.assertEqual(entry.size, len(content))
        self.assertGreaterEqual(entry.stored_at, before)
        self.assertLessEqual(entry.stored_at, after)
        self.assertEqual(entry.media_type, "application/octet-stream")

    # 5. retrieve() raises KeyError for unknown CID
    def test_retrieve_unknown_cid_raises_key_error(self):
        with self.assertRaises(KeyError):
            self.store.retrieve("sha256:" + "a" * 64)

    # 14. retrieve() updates last-accessed time (affects LRU order)
    def test_retrieve_updates_access_time_affects_lru(self):
        small = ArtifactStore(max_bytes=30)
        # Store two entries of 10 bytes each (total 20)
        cid_a = small.store(b"0123456789", media_type="text/plain")  # 10 bytes
        cid_b = small.store(b"abcdefghij", media_type="text/plain")  # 10 bytes

        # Access A to make it more recently used than B
        small.retrieve(cid_a)

        # Adding 15 bytes pushes total to 35 > 30; LRU (B) should be evicted
        cid_c = small.store(b"ABCDEFGHIJK1234", media_type="text/plain")  # 15 bytes
        self.assertIn(cid_a, [small.retrieve(cid_a).cid])
        with self.assertRaises(KeyError):
            small.retrieve(cid_b)
        self.assertIn(cid_c, [small.retrieve(cid_c).cid])


class TestArtifactStoreDelete(unittest.TestCase):
    def setUp(self):
        self.store = ArtifactStore()

    # 6. delete() returns True when entry existed
    def test_delete_existing_returns_true(self):
        cid = self.store.store(b"delete me")
        result = self.store.delete(cid)
        self.assertTrue(result)
        self.assertEqual(self.store.count, 0)

    # 7. delete() returns False when entry not found
    def test_delete_nonexistent_returns_false(self):
        result = self.store.delete("sha256:" + "0" * 64)
        self.assertFalse(result)


class TestArtifactStoreMetrics(unittest.TestCase):
    def setUp(self):
        self.store = ArtifactStore()

    # 8. total_bytes sums correctly across multiple entries
    def test_total_bytes_sums_correctly(self):
        self.store.store(b"abc")    # 3
        self.store.store(b"defgh")  # 5
        self.assertEqual(self.store.total_bytes, 8)

    # 9. count reflects current number of entries
    def test_count_reflects_entries(self):
        self.assertEqual(self.store.count, 0)
        cid1 = self.store.store(b"one")
        self.assertEqual(self.store.count, 1)
        cid2 = self.store.store(b"two")
        self.assertEqual(self.store.count, 2)
        self.store.delete(cid1)
        self.assertEqual(self.store.count, 1)


class TestArtifactStoreLRU(unittest.TestCase):
    # 10. LRU eviction: storing past max_bytes evicts oldest-accessed entry
    def test_lru_eviction_on_store(self):
        small = ArtifactStore(max_bytes=20)
        cid_a = small.store(b"0123456789")  # 10 bytes — stored first (LRU)
        cid_b = small.store(b"abcdefghij")  # 10 bytes — total 20
        # Adding 5 more bytes pushes to 25 > 20 → evict A
        cid_c = small.store(b"12345")       # 5 bytes
        self.assertEqual(small.count, 2)
        with self.assertRaises(KeyError):
            small.retrieve(cid_a)
        small.retrieve(cid_b)  # should still exist
        small.retrieve(cid_c)  # should still exist

    # 11. evict_lru(target_bytes=0) evicts all entries
    def test_evict_lru_target_zero_clears_all(self):
        store = ArtifactStore()
        store.store(b"alpha")
        store.store(b"beta")
        store.store(b"gamma")
        evicted = store.evict_lru(target_bytes=0)
        self.assertEqual(evicted, 3)
        self.assertEqual(store.count, 0)
        self.assertEqual(store.total_bytes, 0)


if __name__ == "__main__":
    unittest.main()
