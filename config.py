from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # V3 installer adds python-dotenv
    def load_dotenv(*args, **kwargs):
        return False

# === V4.5 cloud/runtime configuration ===
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


IS_RAILWAY = any(
    os.getenv(name)
    for name in (
        "RAILWAY_SERVICE_NAME",
        "RAILWAY_DEPLOYMENT_ID",
        "RAILWAY_ENVIRONMENT_NAME",
    )
)
CLOUD_MODE = _env_flag("CLOUD_MODE", default=IS_RAILWAY)

# Railway exposes the attached volume path automatically. Locally, continue to
# use the project's existing data/ directory unless explicitly overridden.
_data_dir_value = (
    os.getenv("DATA_DIR", "").strip()
    or os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "").strip()
)
DATA_DIR = Path(_data_dir_value).expanduser() if _data_dir_value else BASE_DIR / "data"

_database_path_value = os.getenv("DATABASE_PATH", "").strip()
DATABASE_PATH = (
    Path(_database_path_value).expanduser()
    if _database_path_value
    else DATA_DIR / "robot.db"
)

APP_NAME = "HRI Socially Assistive Robot"
APP_VERSION = "4.5"
_default_host = "0.0.0.0" if CLOUD_MODE else "127.0.0.1"
HOST = os.getenv("HOST", _default_host).strip() or _default_host
try:
    PORT = max(1, min(int(os.getenv("PORT", "5000")), 65535))
except ValueError:
    PORT = 5000
DEBUG = _env_flag("DEBUG", default=not CLOUD_MODE)

# Cloud containers often run in UTC. Force the research robot's local civil
# time unless the deployer deliberately chooses another IANA timezone.
APP_TIMEZONE = os.getenv(
    "APP_TIMEZONE",
    "Australia/Sydney" if CLOUD_MODE else "",
).strip()

# Public deployments should not expose caregiver controls and participant data
# to anyone who discovers the URL. Local development remains unlocked.
CLOUD_AUTH_REQUIRED = _env_flag("CLOUD_AUTH_REQUIRED", default=CLOUD_MODE)
CLOUD_ACCESS_CODE = os.getenv("CLOUD_ACCESS_CODE", "").strip()
APP_SECRET_KEY = os.getenv("APP_SECRET_KEY", "").strip()
try:
    CLOUD_SESSION_DAYS = max(1, min(int(os.getenv("CLOUD_SESSION_DAYS", "30")), 365))
except ValueError:
    CLOUD_SESSION_DAYS = 30
# === V4.5 cloud/runtime configuration end ===

# V4.3 tablet/base networking. The normal desktop default remains localhost.
SSL_CERT_PATH = os.getenv("SSL_CERT_PATH", "").strip()
SSL_KEY_PATH = os.getenv("SSL_KEY_PATH", "").strip()
TABLET_AUDIO_MAX_BYTES = max(
    1_000_000,
    min(int(os.getenv("TABLET_AUDIO_MAX_BYTES", str(8 * 1024 * 1024))), 20_000_000),
)

DEFAULT_PARTICIPANT_ID = "P001"
DEFAULT_DISPLAY_NAME = ""
DEFAULT_CONDITION = "HIGH"
ACKNOWLEDGEMENT_DISPLAY_SECONDS = 3.0
DEFAULT_SNOOZE_MINUTES = 10
STATE_POLL_SECONDS = 1.0

# V4.2 adaptive reminder follow-up.
# Defaults are deliberately short enough for a prototype/demo while still
# giving the participant time to respond to the first reminder.
REMINDER_FOLLOWUP_SECONDS = max(
    8.0,
    min(float(os.getenv("REMINDER_FOLLOWUP_SECONDS", "20")), 300.0),
)
REMINDER_MAX_FOLLOWUPS = max(
    0,
    min(int(os.getenv("REMINDER_MAX_FOLLOWUPS", "3")), 8),
)

# ---------------------------------------------------------------------------
# Optional cloud companion AI
# ---------------------------------------------------------------------------

AI_ENABLED = (
    os.getenv("AI_ENABLED", "true")
    .strip()
    .lower()
    not in {"0", "false", "no", "off"}
)

AI_PROVIDER = (
    os.getenv("AI_PROVIDER", "gemini")
    .strip()
    .lower()
    or "gemini"
)

GEMINI_API_KEY = (
    os.getenv("GEMINI_API_KEY", "")
    .strip()
)

GEMINI_MODEL = (
    os.getenv(
        "GEMINI_MODEL",
        "gemini-3.5-flash-lite"
    ).strip()
    or "gemini-3.5-flash-lite"
)

GEMINI_TRANSCRIBE_MODEL = (
    os.getenv(
        "GEMINI_TRANSCRIBE_MODEL",
        "gemini-3.5-transcribe",
    ).strip()
    or "gemini-3.5-transcribe"
)

# Kept for compatibility with the old V3 configuration.
OPENAI_API_KEY = (
    os.getenv("OPENAI_API_KEY", "")
    .strip()
)

OPENAI_MODEL = (
    os.getenv(
        "OPENAI_MODEL",
        "gpt-5.6-luna"
    ).strip()
    or "gpt-5.6-luna"
)

AI_MAX_HISTORY_MESSAGES = max(
    4,
    min(
        int(
            os.getenv(
                "AI_MAX_HISTORY_MESSAGES",
                "12"
            )
        ),
        30
    )
)

AI_MAX_OUTPUT_TOKENS = max(
    80,
    min(
        int(
            os.getenv(
                "AI_MAX_OUTPUT_TOKENS",
                "220"
            )
        ),
        800
    )
)

AI_TIMEOUT_SECONDS = max(
    5.0,
    min(
        float(
            os.getenv(
                "AI_TIMEOUT_SECONDS",
                "15"
            )
        ),
        60.0
    )
)

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

# Synthetic demonstration timetable only. It is not medication advice.
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

# Two clearly-labelled synthetic profiles for demonstrating profile isolation.
DEMO_PROFILES = [
    {
        "participant_id": "DEMO_MARY",
        "display_name": "Mary (Demo)",
        "default_condition": "HIGH",
        "about_me": "Enjoys gardening, tea, old movies and talking about flowers.",
        "schedule": [
            {**SYNTHETIC_SCHEDULE[0], "time_of_day": "07:45"},
            {**SYNTHETIC_SCHEDULE[1], "time_of_day": "08:15"},
            {**SYNTHETIC_SCHEDULE[2], "time_of_day": "10:00"},
            {**SYNTHETIC_SCHEDULE[3], "time_of_day": "12:00"},
            {**SYNTHETIC_SCHEDULE[4], "title": "Garden walk", "time_of_day": "14:30"},
            {**SYNTHETIC_SCHEDULE[5], "time_of_day": "17:45"},
            {**SYNTHETIC_SCHEDULE[6], "time_of_day": "18:15"},
            {**SYNTHETIC_SCHEDULE[8], "time_of_day": "21:00"},
        ],
    },
    {
        "participant_id": "DEMO_ROBERT",
        "display_name": "Robert (Demo)",
        "default_condition": "HIGH",
        "about_me": "Enjoys sport, jazz music, puzzles and morning walks.",
        "schedule": [
            {**SYNTHETIC_SCHEDULE[0], "time_of_day": "08:30"},
            {**SYNTHETIC_SCHEDULE[1], "time_of_day": "09:00"},
            {**SYNTHETIC_SCHEDULE[2], "time_of_day": "11:00"},
            {**SYNTHETIC_SCHEDULE[3], "time_of_day": "13:00"},
            {**SYNTHETIC_SCHEDULE[4], "title": "Puzzle and movement break", "time_of_day": "16:00"},
            {**SYNTHETIC_SCHEDULE[5], "time_of_day": "19:00"},
            {**SYNTHETIC_SCHEDULE[8], "time_of_day": "22:00"},
        ],
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
