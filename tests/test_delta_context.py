import unittest
from ascp.delta_context import Checkpoint, DeltaContextManager, Message


def make_msgs(*contents: str) -> list[Message]:
    return [Message(role="user", content=c) for c in contents]


class TestCheckpoint(unittest.TestCase):
    def setUp(self):
        self.mgr = DeltaContextManager()

    def test_checkpoint_returns_sha256_id(self):
        msgs = make_msgs("hello")
        cp = self.mgr.checkpoint(msgs)
        self.assertIsInstance(cp, Checkpoint)
        self.assertTrue(cp.checkpoint_id.startswith("sha256:"))
        self.assertEqual(len(cp.checkpoint_id), len("sha256:") + 64)

    def test_checkpoint_idempotent_same_id(self):
        msgs = make_msgs("a", "b")
        cp1 = self.mgr.checkpoint(msgs)
        cp2 = self.mgr.checkpoint(msgs)
        self.assertEqual(cp1.checkpoint_id, cp2.checkpoint_id)

    def test_checkpoint_different_messages_different_id(self):
        cp1 = self.mgr.checkpoint(make_msgs("a"))
        cp2 = self.mgr.checkpoint(make_msgs("b"))
        self.assertNotEqual(cp1.checkpoint_id, cp2.checkpoint_id)

    def test_checkpoint_raises_on_empty(self):
        with self.assertRaises(ValueError):
            self.mgr.checkpoint([])


class TestDelta(unittest.TestCase):
    def setUp(self):
        self.mgr = DeltaContextManager()

    def test_delta_returns_new_messages(self):
        base = make_msgs("a", "b")
        cp = self.mgr.checkpoint(base)
        current = base + make_msgs("c", "d")
        result = self.mgr.delta(cp, current)
        self.assertEqual(result, make_msgs("c", "d"))

    def test_delta_empty_when_no_new_messages(self):
        base = make_msgs("a", "b")
        cp = self.mgr.checkpoint(base)
        result = self.mgr.delta(cp, base)
        self.assertEqual(result, [])

    def test_delta_raises_on_diverged_history(self):
        base = make_msgs("a", "b")
        cp = self.mgr.checkpoint(base)
        modified = [Message(role="user", content="CHANGED"), Message(role="user", content="b")] + make_msgs("c")
        with self.assertRaises(ValueError):
            self.mgr.delta(cp, modified)

    def test_delta_raises_when_current_shorter_than_checkpoint(self):
        base = make_msgs("a", "b", "c")
        cp = self.mgr.checkpoint(base)
        with self.assertRaises(ValueError):
            self.mgr.delta(cp, make_msgs("a"))


class TestReconstruct(unittest.TestCase):
    def setUp(self):
        self.mgr = DeltaContextManager()

    def test_reconstruct_returns_full_list(self):
        base = make_msgs("a", "b")
        cp = self.mgr.checkpoint(base)
        delta = make_msgs("c", "d")
        result = self.mgr.reconstruct(cp, delta)
        self.assertEqual(result, base + delta)

    def test_reconstruct_raises_on_duplicate(self):
        base = make_msgs("a", "b")
        cp = self.mgr.checkpoint(base)
        duplicate_delta = make_msgs("b", "c")
        with self.assertRaises(ValueError):
            self.mgr.reconstruct(cp, duplicate_delta)


class TestTokenSavings(unittest.TestCase):
    def setUp(self):
        self.mgr = DeltaContextManager()

    def test_token_savings_correct_counts_and_pct(self):
        base = make_msgs("a", "b", "c")
        cp = self.mgr.checkpoint(base)
        current = base + make_msgs("d")
        stats = self.mgr.token_savings(cp, current)
        self.assertEqual(stats["full_message_count"], 4)
        self.assertEqual(stats["delta_count"], 1)
        self.assertEqual(stats["saved_count"], 3)
        self.assertAlmostEqual(stats["saved_pct"], 75.0)

    def test_token_savings_zero_pct_no_savings(self):
        base = make_msgs("a")
        cp = self.mgr.checkpoint(base)
        stats = self.mgr.token_savings(cp, base)
        self.assertEqual(stats["full_message_count"], 1)
        self.assertEqual(stats["delta_count"], 0)
        self.assertEqual(stats["saved_count"], 1)
        self.assertAlmostEqual(stats["saved_pct"], 100.0)


if __name__ == "__main__":
    unittest.main()
