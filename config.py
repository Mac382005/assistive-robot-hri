from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATABASE_PATH = DATA_DIR / "robot.db"

APP_NAME = "HRI Socially Assistive Robot"
APP_VERSION = "2.0"
HOST = "127.0.0.1"
PORT = 5000
DEBUG = True

DEFAULT_PARTICIPANT_ID = "P001"
DEFAULT_DISPLAY_NAME = ""
DEFAULT_CONDITION = "HIGH"
ACKNOWLEDGEMENT_DISPLAY_SECONDS = 3.0
DEFAULT_SNOOZE_MINUTES = 10
STATE_POLL_SECONDS = 1.0

REMINDERS = {
    "medication": {
        "title": "Medication Reminder",
        "message": "Please take your medication from the correct compartment.",
        "voice_message": "It is time for your medication. Please take your medication from the correct compartment.",
        "symbol": "💊",
        "expression": "caring",
    },
    "hydration": {
        "title": "Hydration Reminder",
        "message": "Please have a glass of water.",
        "voice_message": "It is time to have some water. Please have a glass of water.",
        "symbol": "💧",
        "expression": "happy",
    },
    "meal": {
        "title": "Meal Reminder",
        "message": "It is time for your meal.",
        "voice_message": "It is time for your meal. I hope you enjoy it.",
        "symbol": "🍽️",
        "expression": "excited",
    },
    "appointment": {
        "title": "Appointment Reminder",
        "message": "You have an upcoming appointment.",
        "voice_message": "Just a reminder that you have an upcoming appointment.",
        "symbol": "📅",
        "expression": "attentive",
    },
    "activity": {
        "title": "Activity Reminder",
        "message": "It is a good time for some light movement or a short walk.",
        "voice_message": "How about some light movement or a short walk? Take it at your own pace.",
        "symbol": "🚶",
        "expression": "encouraging",
    },
    "bedtime": {
        "title": "Evening Routine",
        "message": "It is time to begin your evening routine and get ready to rest.",
        "voice_message": "It is getting late. This is a gentle reminder to begin your evening routine and get ready to rest.",
        "symbol": "🌙",
        "expression": "sleepy",
    },
}

# Demonstration schedule only. It is synthetic and is not medical advice.
# 0 = Monday ... 6 = Sunday.
SYNTHETIC_SCHEDULE = [
    {
        "title": "Morning medication",
        "reminder_type": "medication",
        "time_of_day": "08:00",
        "days_of_week": [0, 1, 2, 3, 4, 5, 6],
        "message": "Please take your morning medication from the Morning compartment.",
        "condition_name": "HIGH",
        "enabled": True,
    },
    {
        "title": "Breakfast",
        "reminder_type": "meal",
        "time_of_day": "08:30",
        "days_of_week": [0, 1, 2, 3, 4, 5, 6],
        "message": "Breakfast time. Please have your morning meal.",
        "condition_name": "HIGH",
        "enabled": True,
    },
    {
        "title": "Morning water",
        "reminder_type": "hydration",
        "time_of_day": "10:30",
        "days_of_week": [0, 1, 2, 3, 4, 5, 6],
        "message": "Please have a glass of water.",
        "condition_name": "HIGH",
        "enabled": True,
    },
    {
        "title": "Lunch",
        "reminder_type": "meal",
        "time_of_day": "12:30",
        "days_of_week": [0, 1, 2, 3, 4, 5, 6],
        "message": "It is time for lunch.",
        "condition_name": "HIGH",
        "enabled": True,
    },
    {
        "title": "Afternoon activity",
        "reminder_type": "activity",
        "time_of_day": "15:00",
        "days_of_week": [0, 1, 2, 3, 4],
        "message": "It is a good time for some light movement or a short walk.",
        "condition_name": "HIGH",
        "enabled": True,
    },
    {
        "title": "Evening medication",
        "reminder_type": "medication",
        "time_of_day": "18:00",
        "days_of_week": [0, 1, 2, 3, 4, 5, 6],
        "message": "Please take your evening medication from the Evening compartment.",
        "condition_name": "HIGH",
        "enabled": True,
    },
    {
        "title": "Dinner",
        "reminder_type": "meal",
        "time_of_day": "18:30",
        "days_of_week": [0, 1, 2, 3, 4, 5, 6],
        "message": "It is time for dinner.",
        "condition_name": "HIGH",
        "enabled": True,
    },
    {
        "title": "Evening hydration",
        "reminder_type": "hydration",
        "time_of_day": "20:30",
        "days_of_week": [0, 1, 2, 3, 4, 5, 6],
        "message": "Please have some water before your evening routine.",
        "condition_name": "HIGH",
        "enabled": True,
    },
    {
        "title": "Wind-down routine",
        "reminder_type": "bedtime",
        "time_of_day": "21:30",
        "days_of_week": [0, 1, 2, 3, 4, 5, 6],
        "message": "It is time to begin your evening routine and get ready to rest.",
        "condition_name": "HIGH",
        "enabled": True,
    },
]

COMPANION_RESPONSES = {
    "how_are_you": [
        ("happy", "😊", "I am doing well, thank you. I am here and ready to help with your day."),
        ("excited", "✨", "I am feeling bright and ready to help. It is nice to spend some time with you."),
        ("caring", "💛", "I am doing well. Most importantly, I am here if you need a reminder or a little company."),
    ],
    "encourage": [
        ("encouraging", "🌟", "You are doing well. One small task at a time is enough."),
        ("happy", "💪", "You have got this. We can take the day one step at a time."),
        ("excited", "🌈", "A little progress still counts. I will keep you company along the way."),
    ],
}
