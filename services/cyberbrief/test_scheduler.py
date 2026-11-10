"""Tests for the CyberBrief schedule. Uses a fake clock, fake sender and a temp state file.
Run from the DevCore root:  python -m unittest services.cyberbrief.test_scheduler"""
import json
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from . import scheduler

TZ = ZoneInfo("Africa/Johannesburg")


def at(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=TZ)


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.patch = mock.patch.object(scheduler, "STATE_FILE", self.tmp / "schedule_state.json")
        self.patch.start()
        self.env = {"CYBERBRIEF_SCHEDULE": "on", "CYBERBRIEF_SEND_HOUR": "7", "CYBERBRIEF_WEEKLY_DAY": "0",
                    "CYBERBRIEF_TZ": "Africa/Johannesburg", "THREAT_FEED_REFRESH_HOURS": "6"}
        self.env_patch = mock.patch.object(scheduler, "_env", lambda k, d=None: self.env.get(k, d))
        self.env_patch.start()
        self.sent = []
        self.refreshes = 0
        self.digest = {"dispatched_at": "2026-11-10 05:00 UTC", "items": [{"story_id": "a"}]}

    def tearDown(self):
        self.patch.stop()
        self.env_patch.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def refresh(self, force=False):
        self.refreshes += 1
        return {"status": "refreshed"}

    def send(self, cadence):
        self.sent.append(cadence)
        return {"sent": 2, "message": "ok"}

    def tick(self, now):
        return scheduler.tick(now, refresh=self.refresh, send=self.send, manifest=lambda: self.digest)

    def baseline(self):
        """Simulate a scheduler that was first started on an earlier day."""
        scheduler.save_state({"initialized": True})

    def test_first_start_after_send_hour_waits_for_tomorrow(self):
        self.tick(at(2026, 11, 10, 21, 30))
        self.assertEqual(self.sent, [])
        self.digest = {"dispatched_at": "2026-11-11 05:00 UTC", "items": [{"story_id": "n"}]}
        self.tick(at(2026, 11, 11, 7, 0))
        self.assertEqual(self.sent, ["daily"])

    def test_nothing_before_send_hour(self):
        self.baseline()
        self.tick(at(2026, 11, 10, 6, 55))  # Tuesday
        self.assertEqual(self.sent, [])
        self.assertEqual(self.refreshes, 1)

    def test_daily_once_per_day(self):
        self.baseline()
        self.tick(at(2026, 11, 10, 7, 0))
        self.tick(at(2026, 11, 10, 7, 5))
        self.tick(at(2026, 11, 10, 18, 0))
        self.assertEqual(self.sent, ["daily"])

    def test_weekly_on_monday_monthly_on_first(self):
        self.baseline()
        self.tick(at(2026, 11, 9, 7, 0))   # Monday
        self.assertEqual(self.sent, ["daily", "weekly"])
        self.sent.clear()
        self.digest = {"dispatched_at": "2026-12-01 05:00 UTC", "items": [{"story_id": "b"}]}
        self.tick(at(2026, 12, 1, 9, 0))   # Tuesday the 1st
        self.assertEqual(self.sent, ["daily", "monthly"])

    def test_skip_when_no_new_stories(self):
        self.baseline()
        self.tick(at(2026, 11, 10, 7, 0))
        did = self.tick(at(2026, 11, 11, 7, 0))  # same digest next day
        self.assertEqual(self.sent, ["daily"])
        self.assertIn("daily", did["skipped"])
        self.digest = {"dispatched_at": "2026-11-12 05:00 UTC", "items": [{"story_id": "c"}]}
        self.tick(at(2026, 11, 12, 7, 0))
        self.assertEqual(self.sent, ["daily", "daily"])

    def test_late_start_same_day_still_sends_but_not_next_day_catchup(self):
        self.baseline()
        self.tick(at(2026, 11, 10, 15, 0))  # PC came on at 15:00
        self.assertEqual(self.sent, ["daily"])

    def test_pause_and_switch_off(self):
        self.baseline()
        scheduler.set_paused(True)
        self.tick(at(2026, 11, 10, 8, 0))
        self.assertEqual(self.sent, [])
        self.assertEqual(self.refreshes, 1)  # feed still refreshes while paused
        scheduler.set_paused(False)
        self.tick(at(2026, 11, 10, 8, 5))
        self.assertEqual(self.sent, ["daily"])
        self.env["CYBERBRIEF_SCHEDULE"] = "off"
        self.digest = {"dispatched_at": "new", "items": [{"story_id": "d"}]}
        self.tick(at(2026, 11, 11, 8, 0))
        self.assertEqual(self.sent, ["daily"])

    def test_empty_digest_not_sent(self):
        self.baseline()
        self.digest = {"dispatched_at": "x", "items": []}
        self.tick(at(2026, 11, 10, 7, 0))
        self.assertEqual(self.sent, [])

    def test_send_error_retries_next_pass(self):
        self.baseline()
        calls = []

        def flaky(cadence):
            calls.append(cadence)
            if len(calls) == 1:
                raise RuntimeError("smtp down")
            return {"sent": 2}
        scheduler.tick(at(2026, 11, 10, 7, 0), refresh=self.refresh, send=flaky, manifest=lambda: self.digest)
        scheduler.tick(at(2026, 11, 10, 7, 5), refresh=self.refresh, send=flaky, manifest=lambda: self.digest)
        scheduler.tick(at(2026, 11, 10, 7, 10), refresh=self.refresh, send=flaky, manifest=lambda: self.digest)
        self.assertEqual(calls, ["daily", "daily"])

    def test_refresh_interval(self):
        self.baseline()
        with mock.patch.object(scheduler.time, "time", return_value=1_000_000):
            self.tick(at(2026, 11, 10, 1, 0))
        with mock.patch.object(scheduler.time, "time", return_value=1_000_000 + 3600):
            self.tick(at(2026, 11, 10, 2, 0))
        with mock.patch.object(scheduler.time, "time", return_value=1_000_000 + 6 * 3600):
            self.tick(at(2026, 11, 10, 7, 0))
        self.assertEqual(self.refreshes, 2)


class QueueTests(unittest.TestCase):
    def test_applies_items_and_marks_done(self):
        items = [
            {"id": 1, "action": "subscribe", "payload": json.dumps({"email": "a@b.co", "topics": "zero_days,ransomware", "cadence": "weekly"})},
            {"id": 2, "action": "unsubscribe", "payload": json.dumps({"token": "tok", "purge": False})},
            {"id": 3, "action": "subscribe", "payload": json.dumps({"email": "bad"})},
            {"id": 4, "action": "subscribe", "payload": json.dumps({"email": "c@d.co"})},
        ]
        calls, done = [], []

        def api(method, path, body=None):
            if method == "GET":
                return {"items": items}
            done.extend(body["ids"])
            return {"success": True}

        def subscribe(**kw):
            if kw["email"] == "bad":
                raise ValueError("Enter a valid email address.")
            if kw["email"] == "c@d.co":
                raise RuntimeError("smtp down")
            calls.append(("sub", kw["email"], kw["topics"], kw["cadence"], kw["send_welcome"]))

        def unsubscribe(token, purge=False):
            calls.append(("unsub", token, purge))

        counts = scheduler.process_newsletter_queue(api=api, subscribe=subscribe, unsubscribe=unsubscribe)
        self.assertEqual(calls, [("sub", "a@b.co", ["zero_days", "ransomware"], "weekly", True), ("unsub", "tok", False)])
        self.assertEqual(sorted(done), [1, 2, 3])          # 4 failed on mail: retried next pass
        self.assertEqual(counts, {"subscribed": 1, "unsubscribed": 1, "invalid": 1})


if __name__ == "__main__":
    unittest.main()
