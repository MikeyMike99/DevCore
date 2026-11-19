"""Tests for core/lab_capacity.py: the memory-aware ceiling, per-learner limit, levels and warning messages."""
import base64
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from core import lab_capacity as cap  # noqa: E402


def token_for(learner: str) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"l": learner, "b": "lab", "e": 1}).encode()).decode().rstrip("=")
    return payload + "." + "a" * 64


class CapacityTests(unittest.TestCase):
    def setUp(self):
        cap._open.clear()
        cap._last_level = "ok"
        self._saved = (cap.MAX_TERMINALS, cap.PER_LEARNER, cap.RESERVE_MB, cap.PER_TERMINAL_MB)
        cap.MAX_TERMINALS, cap.PER_LEARNER, cap.RESERVE_MB, cap.PER_TERMINAL_MB = 10, 2, 1000, 50
        self._saved_host = (cap.host_free_mb, cap.HOST_RESERVE_MB)
        cap.host_free_mb = lambda: None                # never read the real Windows memory in tests
        cap.HOST_RESERVE_MB = 1000

    def tearDown(self):
        cap._open.clear()
        cap.MAX_TERMINALS, cap.PER_LEARNER, cap.RESERVE_MB, cap.PER_TERMINAL_MB = self._saved
        cap.host_free_mb, cap.HOST_RESERVE_MB = self._saved_host

    def test_windows_memory_can_be_the_tighter_limit(self):
        # WSL has plenty, but Windows has only 1250 MB free with 1000 reserved -> room for 5 more
        self.assertEqual(cap.effective_max(avail=64000, used=0, host=1250), 5)
        self.assertEqual(cap.snapshot(avail=64000, load=0.1, host=1250)["limit"], 5)

    def test_limit_grows_back_when_memory_is_freed(self):
        low = cap.effective_max(avail=1300, used=0)       # 6
        high = cap.effective_max(avail=1500, used=0)      # 10 (capped at the ceiling)
        self.assertLess(low, high)
        self.assertEqual(high, 10)

    def test_idle_limit_shrinks_as_we_fill_up(self):
        self.assertGreater(cap.idle_limit("ok"), cap.idle_limit("busy"))
        self.assertGreater(cap.idle_limit("busy"), cap.idle_limit("full"))
        self.assertGreaterEqual(cap.idle_limit("full"), 60)   # never a hair-trigger

    def fill(self, n):
        for i in range(n):
            cap._open[1000 + i] = f"learner-{i}"

    def test_plenty_of_memory_uses_hard_ceiling(self):
        self.assertEqual(cap.effective_max(avail=64000, used=0), 10)

    def test_low_memory_lowers_the_ceiling(self):
        # 1400 MB free, 1000 reserved, 50 MB each -> 8 more terminals on top of the 0 open
        self.assertEqual(cap.effective_max(avail=1400, used=0), 8)

    def test_below_reserve_means_nothing_new(self):
        self.assertEqual(cap.effective_max(avail=500, used=3), 0)

    def test_unreadable_memory_falls_back_to_ceiling(self):
        self.assertEqual(cap.effective_max(avail=None, used=4), 10)

    def test_levels(self):
        self.assertEqual(cap.snapshot(avail=64000, load=0.1)["level"], "ok")
        self.fill(7)                                              # 70% of 10
        s = cap.snapshot(avail=64000, load=0.1)
        self.assertEqual(s["level"], "busy")
        self.assertIn("slowly", s["message"])
        self.fill(10)
        s = cap.snapshot(avail=64000, load=0.1)
        self.assertEqual(s["level"], "full")
        self.assertIn("simulated terminal", s["message"])         # never a dead end: full means "use the simulation"

    def test_low_memory_alone_is_busy_then_full(self):
        self.assertEqual(cap.snapshot(avail=1400, load=0.1)["level"], "busy")   # under 1.5x reserve
        self.assertEqual(cap.snapshot(avail=900, load=0.1)["level"], "full")    # under reserve

    def test_high_load_is_busy(self):
        self.assertEqual(cap.snapshot(avail=64000, load=3.0)["level"], "busy")

    def test_ok_has_no_message(self):
        self.assertEqual(cap.snapshot(avail=64000, load=0.1)["message"], "")

    def test_per_learner_limit(self):
        t = token_for("alice")
        a, _ = cap.acquire(t)
        b, _ = cap.acquire(t)
        c, why = cap.acquire(t)
        self.assertTrue(a and b)
        self.assertIsNone(c)
        self.assertEqual(why, "per_learner")
        other, _ = cap.acquire(token_for("bob"))
        self.assertTrue(other)                                    # another learner is not affected

    def test_release_gives_the_place_back(self):
        t = token_for("alice")
        a, _ = cap.acquire(t)
        cap.acquire(t)
        cap.release(a)
        again, _ = cap.acquire(t)
        self.assertTrue(again)

    def test_full_refuses_new_terminals(self):
        self.fill(10)
        conn, why = cap.acquire(token_for("zed"))
        self.assertIsNone(conn)
        self.assertEqual(why, "full")

    def test_learner_of_handles_junk(self):
        self.assertEqual(cap.learner_of(token_for("alice")), "alice")
        self.assertTrue(cap.learner_of("not-a-token"))
        self.assertIsInstance(cap.learner_of(""), str)            # never raises (the proxy already rejects empty links)


if __name__ == "__main__":
    unittest.main()
