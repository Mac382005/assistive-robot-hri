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
            )
            self.assertEqual(trial_id, 1)
            rows = db.recent_trials()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["participant_id"], "P001")
            self.assertEqual(rows[0]["response_time_ms"], 3000)


if __name__ == "__main__":
    unittest.main()
