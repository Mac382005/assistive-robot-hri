import tempfile
import unittest
from pathlib import Path

from database import RobotDatabase


class RobotDatabaseTests(unittest.TestCase):
    def test_save_and_read_trial(self):
        with tempfile.TemporaryDirectory() as directory:
            db = RobotDatabase(Path(directory) / "test.db")
            db.initialise()
            trial_id = db.save_trial(
                participant_id="P001",
                display_name="Test",
                reminder_type="medication",
                condition_name="HIGH",
                social_cue_count=5,
                cue_flags={"voice_reminder": True},
                started_at="2026-09-30T00:00:00+00:00",
                acknowledged_at="2026-09-30T00:00:03+00:00",
                response_time_ms=3000,
                action="acknowledged",
                source="manual",
            )
            self.assertEqual(trial_id, 1)
            rows = db.recent_trials()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["participant_id"], "P001")
            self.assertEqual(rows[0]["response_time_ms"], 3000)
            self.assertEqual(rows[0]["action"], "acknowledged")

    def test_schedule_crud(self):
        with tempfile.TemporaryDirectory() as directory:
            db = RobotDatabase(Path(directory) / "test.db")
            db.initialise()
            schedule_id = db.create_schedule(
                title="Morning water",
                reminder_type="hydration",
                time_of_day="10:30",
                days_of_week=[0, 1, 2, 3, 4],
                message="Have a glass of water.",
                condition_name="HIGH",
                enabled=True,
            )
            schedule = db.get_schedule(schedule_id)
            self.assertEqual(schedule["title"], "Morning water")
            self.assertEqual(schedule["days_of_week"], [0, 1, 2, 3, 4])
            self.assertTrue(schedule["enabled"])

            updated = db.update_schedule(
                schedule_id,
                title="Updated water",
                reminder_type="hydration",
                time_of_day="11:00",
                days_of_week=[0, 2, 4],
                message="Please drink some water.",
                condition_name="LOW",
                enabled=False,
            )
            self.assertTrue(updated)
            schedule = db.get_schedule(schedule_id)
            self.assertEqual(schedule["title"], "Updated water")
            self.assertEqual(schedule["time_of_day"], "11:00")
            self.assertFalse(schedule["enabled"])

            self.assertTrue(db.delete_schedule(schedule_id))
            self.assertIsNone(db.get_schedule(schedule_id))

    def test_profile_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            db = RobotDatabase(Path(directory) / "test.db")
            db.initialise()
            db.set_settings(
                {
                    "participant_id": "P009",
                    "display_name": "Mary",
                    "default_condition": "HIGH",
                }
            )
            settings = db.get_settings()
            self.assertEqual(settings["participant_id"], "P009")
            self.assertEqual(settings["display_name"], "Mary")


if __name__ == "__main__":
    unittest.main()
