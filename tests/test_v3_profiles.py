import tempfile
import unittest
from pathlib import Path

from database import RobotDatabase


class V3ProfileTests(unittest.TestCase):
    def test_profiles_have_isolated_schedules_and_chat(self):
        with tempfile.TemporaryDirectory() as directory:
            db = RobotDatabase(Path(directory) / "test.db")
            db.initialise()

            first = db.get_active_profile()
            first_id = int(first["id"])
            second_id = db.create_profile(
                participant_id="P002",
                display_name="Second User",
                default_condition="HIGH",
                about_me="Likes music.",
            )

            db.create_schedule(
                profile_id=first_id,
                title="First schedule",
                reminder_type="hydration",
                time_of_day="10:00",
                days_of_week=[0, 1, 2, 3, 4, 5, 6],
                message="First",
                condition_name="HIGH",
                enabled=True,
            )
            db.create_schedule(
                profile_id=second_id,
                title="Second schedule",
                reminder_type="meal",
                time_of_day="12:00",
                days_of_week=[0, 1, 2, 3, 4, 5, 6],
                message="Second",
                condition_name="HIGH",
                enabled=True,
            )

            self.assertEqual(db.list_schedules(profile_id=first_id)[0]["title"], "First schedule")
            self.assertEqual(db.list_schedules(profile_id=second_id)[0]["title"], "Second schedule")

            db.add_chat_message(first_id, "user", "Hello first")
            db.add_chat_message(second_id, "user", "Hello second")
            self.assertEqual(db.chat_history(first_id)[0]["content"], "Hello first")
            self.assertEqual(db.chat_history(second_id)[0]["content"], "Hello second")

            db.set_active_profile(second_id)
            self.assertEqual(db.get_active_profile_id(), second_id)
            self.assertEqual(db.get_active_profile()["participant_id"], "P002")

    def test_cannot_delete_last_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            db = RobotDatabase(Path(directory) / "test.db")
            db.initialise()
            only_id = db.get_active_profile_id()
            with self.assertRaises(ValueError):
                db.delete_profile(only_id)


if __name__ == "__main__":
    unittest.main()
