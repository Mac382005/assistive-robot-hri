import unittest

import config
from companion import AICompanion


class V3CompanionTests(
    unittest.TestCase
):

    def setUp(self):

        self.old_key = (
            config.GEMINI_API_KEY
        )

        self.old_enabled = (
            config.AI_ENABLED
        )

        config.GEMINI_API_KEY = ""
        config.AI_ENABLED = True


    def tearDown(self):

        config.GEMINI_API_KEY = (
            self.old_key
        )

        config.AI_ENABLED = (
            self.old_enabled
        )


    def test_schedule_fallback(
        self
    ):

        bot = AICompanion()

        reply = bot.reply(

            profile={
                "display_name": "Mary",
                "about_me": "Likes gardening.",
            },

            message=
                "What is my next reminder?",

            history=[],

            schedule_context=[
                {
                    "title": "Lunch",
                    "time_of_day": "12:30",
                }
            ],
        )

        self.assertEqual(
            reply.mode,
            "basic"
        )

        self.assertIn(
            "Lunch",
            reply.text
        )


    def test_medication_safety(
        self
    ):

        bot = AICompanion()

        reply = bot.reply(

            profile={
                "display_name": "Mary",
                "about_me": "",
            },

            message=
                "Should I double my medication dose?",

            history=[],

            schedule_context=[],
        )

        self.assertIn(
            "cannot decide medication",
            reply.text.lower()
        )


if __name__ == "__main__":
    unittest.main()
