import unittest

import config
from companion import AICompanion


class V3CompanionTests(unittest.TestCase):
    def test_basic_fallback_answers_schedule_question(self):
        original_key = config.OPENAI_API_KEY
        original_enabled = config.AI_ENABLED
        try:
            config.OPENAI_API_KEY = ""
            config.AI_ENABLED = True
            bot = AICompanion()
            reply = bot.reply(
                profile={"display_name": "Mary", "about_me": "Likes gardening."},
                message="What is my next reminder?",
                history=[],
                schedule_context=[{"title": "Lunch", "time_of_day": "12:30"}],
            )
            self.assertEqual(reply.mode, "basic")
            self.assertIn("Lunch", reply.text)
            self.assertIn("12:30", reply.text)
        finally:
            config.OPENAI_API_KEY = original_key
            config.AI_ENABLED = original_enabled

    def test_medication_fallback_does_not_change_dose(self):
        original_key = config.OPENAI_API_KEY
        try:
            config.OPENAI_API_KEY = ""
            bot = AICompanion()
            reply = bot.reply(
                profile={"display_name": "Mary", "about_me": ""},
                message="Should I double my medication dose?",
                history=[],
                schedule_context=[],
            )
            lowered = reply.text.lower()
            self.assertIn("cannot decide medication or dosage", lowered)
            self.assertIn("caregiver", lowered)
        finally:
            config.OPENAI_API_KEY = original_key


if __name__ == "__main__":
    unittest.main()
