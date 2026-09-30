from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATABASE_PATH = DATA_DIR / "robot.db"

APP_NAME = "HRI Socially Assistive Robot"
HOST = "127.0.0.1"
PORT = 5000
DEBUG = True

DEFAULT_PARTICIPANT_ID = "P001"
DEFAULT_DISPLAY_NAME = ""
DEFAULT_CONDITION = "HIGH"
ACKNOWLEDGEMENT_DISPLAY_SECONDS = 2.5

REMINDERS = {
    "medication": {
        "title": "Medication Reminder",
        "message": "Please take your medication from the correct compartment.",
        "voice_message": "It is time for your medication. Please take your medication from the correct compartment.",
        "symbol": "💊",
    },
    "hydration": {
        "title": "Hydration Reminder",
        "message": "Please have a glass of water.",
        "voice_message": "It is time to have some water. Please have a glass of water.",
        "symbol": "💧",
    },
    "meal": {
        "title": "Meal Reminder",
        "message": "It is time for your meal.",
        "voice_message": "It is time for your meal.",
        "symbol": "🍽️",
    },
    "appointment": {
        "title": "Appointment Reminder",
        "message": "You have an upcoming appointment.",
        "voice_message": "This is a reminder that you have an upcoming appointment.",
        "symbol": "📅",
    },
}
