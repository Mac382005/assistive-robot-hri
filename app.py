from __future__ import annotations

import atexit
import random
import re
import threading
from copy import deepcopy
from datetime import datetime

from flask import Flask, Response, jsonify, render_template, request
from tzlocal import get_localzone

import config
from companion import AICompanion
from database import RobotDatabase
from experiment.conditions import CONDITIONS, get_condition
from experiment.response_timer import ResponseTimer
from reminders import ReminderScheduler
from robot import MockHardwareController

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

local_timezone = get_localzone()
database = RobotDatabase()
database.initialise()
database.seed_schedules_if_needed(config.SYNTHETIC_SCHEDULE)
response_timer = ResponseTimer()
hardware = MockHardwareController()
companion_ai = AICompanion()
state_lock = threading.RLock()

robot_state = {
    "mode": "idle",
    "active_reminder": None,
    "last_result": None,
    "hardware_mode": hardware.mode,
    "state_version": 0,
}


def clean_text(value: object, *, fallback: str = "", max_length: int = 120) -> str:
    text = str(value or fallback).strip()
    return text[:max_length]


def clean_time(value: object) -> str:
    text = clean_text(value, max_length=5)
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", text):
        raise ValueError("Time must use 24-hour HH:MM format.")
    return text


def clean_days(value: object) -> list[int]:
    if not isinstance(value, list):
        raise ValueError("Select at least one day.")
    days: list[int] = []
    for item in value:
        day = int(item)
        if 0 <= day <= 6:
            days.append(day)
    days = sorted(set(days))
    if not days:
        raise ValueError("Select at least one day.")
    return days


def profile() -> dict:
    active = database.get_active_profile()
    condition = str(active.get("default_condition") or config.DEFAULT_CONDITION).upper()
    if condition not in CONDITIONS:
        condition = config.DEFAULT_CONDITION
    return {
        "id": int(active["id"]),
        "participant_id": active.get("participant_id", config.DEFAULT_PARTICIPANT_ID),
        "display_name": active.get("display_name", config.DEFAULT_DISPLAY_NAME),
        "default_condition": condition,
        "about_me": active.get("about_me", ""),
    }


def profile_payload(payload: dict, *, fallback: dict | None = None) -> dict:
    fallback = fallback or {}
    participant_id = clean_text(
        payload.get("participant_id"),
        fallback=fallback.get("participant_id", config.DEFAULT_PARTICIPANT_ID),
        max_length=30,
    )
    if not participant_id:
        raise ValueError("Participant / User ID is required.")
    display_name = clean_text(
        payload.get("display_name"),
        fallback=fallback.get("display_name", ""),
        max_length=40,
    )
    condition = clean_text(
        payload.get("default_condition"),
        fallback=fallback.get("default_condition", config.DEFAULT_CONDITION),
        max_length=20,
    ).upper()
    get_condition(condition)
    about_me = clean_text(
        payload.get("about_me"),
        fallback=fallback.get("about_me", ""),
        max_length=500,
    )
    return {
        "participant_id": participant_id,
        "display_name": display_name,
        "default_condition": condition,
        "about_me": about_me,
    }


def seed_demo_profiles_if_needed() -> None:
    settings = database.get_settings()
    if settings.get("v3_demo_profiles_seeded") == "1":
        return
    existing = {item["participant_id"] for item in database.list_profiles()}
    for demo in config.DEMO_PROFILES:
        if demo["participant_id"] in existing:
            continue
        profile_id = database.create_profile(
            participant_id=demo["participant_id"],
            display_name=demo["display_name"],
            default_condition=demo["default_condition"],
            about_me=demo.get("about_me", ""),
        )
        database.replace_schedules(demo.get("schedule", []), profile_id=profile_id)
    database.set_settings({"v3_demo_profiles_seeded": "1"})


seed_demo_profiles_if_needed()


def touch_state() -> None:
    robot_state["state_version"] = int(robot_state.get("state_version", 0)) + 1


def state_snapshot() -> dict:
    with state_lock:
        return deepcopy(robot_state)


def cue_flags(condition) -> dict:
    return {
        "face_animation": condition.face_animation,
        "voice_reminder": condition.voice_reminder,
        "head_orientation": condition.head_orientation,
        "personalised_greeting": condition.personalised_greeting,
        "acknowledgement": condition.acknowledgement,
        "arm_gesture": condition.arm_gesture,
    }


def start_reminder_core(
    *,
    reminder_type: str,
    condition_name: str,
    participant_id: str,
    display_name: str,
    title: str | None = None,
    message: str | None = None,
    source: str = "manual",
    schedule_id: int | None = None,
    profile_id: int | None = None,
) -> tuple[dict | None, str | None]:
    reminder_type = reminder_type.lower()
    if reminder_type not in config.REMINDERS:
        return None, "Unknown reminder type."

    try:
        condition = get_condition(condition_name)
    except ValueError as exc:
        return None, str(exc)

    base = config.REMINDERS[reminder_type]
    display_title = clean_text(title, fallback=base["title"], max_length=80)
    display_message = clean_text(message, fallback=base["message"], max_length=240)
    profile_id = int(profile_id or database.get_active_profile_id())

    with state_lock:
        if robot_state["mode"] == "reminder":
            return None, "A reminder is already active."

        response_timer.reset()
        started_at = response_timer.start()

        greeting = ""
        if condition.personalised_greeting:
            greeting = f"Hello, {display_name}." if display_name else "Hello."

        voice_message = f"{greeting} {display_message}".strip()
        if display_message == base["message"]:
            voice_message = f"{greeting} {base['voice_message']}".strip()

        active = {
            "profile_id": profile_id,
            "participant_id": participant_id,
            "display_name": display_name,
            "reminder_type": reminder_type,
            "title": display_title,
            "message": display_message,
            "voice_message": voice_message,
            "symbol": base["symbol"],
            "expression": base.get("expression", "caring"),
            "condition": condition.to_dict(),
            "started_at": started_at,
            "source": source,
            "schedule_id": schedule_id,
            "followup_count": 0,
        }
        robot_state["mode"] = "reminder"
        robot_state["active_reminder"] = active
        robot_state["last_result"] = None
        touch_state()

    hardware_events = hardware.begin_reminder(condition, active["voice_message"])
    snapshot = state_snapshot()
    snapshot["hardware_events"] = hardware_events
    return snapshot, None


def on_scheduled_reminder_due(schedule: dict, source: str) -> None:
    user = profile()
    schedule_profile_id = int(schedule.get("profile_id") or user["id"])
    if schedule_profile_id != user["id"]:
        print("[SCHEDULER] Reminder skipped because its profile is not active.")
        return

    participant_id = clean_text(
        schedule.get("participant_id"), fallback=user["participant_id"], max_length=30
    )
    display_name = clean_text(
        schedule.get("display_name"), fallback=user["display_name"], max_length=40
    )
    state, error = start_reminder_core(
        reminder_type=schedule.get("reminder_type", "appointment"),
        condition_name=schedule.get("condition_name", user["default_condition"]),
        participant_id=participant_id,
        display_name=display_name,
        title=schedule.get("title"),
        message=schedule.get("message"),
        source=source,
        schedule_id=schedule.get("id"),
        profile_id=schedule_profile_id,
    )
    if error:
        print(f"[SCHEDULER] Reminder skipped: {error}")
    elif state:
        print(f"[SCHEDULER] Activated: {schedule.get('title', 'Reminder')}")


reminder_scheduler = ReminderScheduler(
    database,
    on_scheduled_reminder_due,
    active_profile_id=database.get_active_profile_id,
)
atexit.register(reminder_scheduler.shutdown)


def schedule_payload_from_request(payload: dict) -> dict:
    reminder_type = clean_text(
        payload.get("reminder_type"), fallback="medication", max_length=30
    ).lower()
    if reminder_type not in config.REMINDERS:
        raise ValueError("Unknown reminder type.")
    condition_name = clean_text(
        payload.get("condition_name"), fallback=profile()["default_condition"], max_length=20
    ).upper()
    get_condition(condition_name)
    return {
        "title": clean_text(
            payload.get("title"), fallback=config.REMINDERS[reminder_type]["title"], max_length=80
        ),
        "reminder_type": reminder_type,
        "time_of_day": clean_time(payload.get("time_of_day")),
        "days_of_week": clean_days(payload.get("days_of_week")),
        "message": clean_text(
            payload.get("message"), fallback=config.REMINDERS[reminder_type]["message"], max_length=240
        ),
        "condition_name": condition_name,
        "enabled": bool(payload.get("enabled", True)),
    }


def schedules_with_runtime() -> list[dict]:
    active_profile_id = database.get_active_profile_id()
    next_runs = reminder_scheduler.next_run_map()
    rows = database.list_schedules(profile_id=active_profile_id)
    for row in rows:
        row["next_run_time"] = next_runs.get(row["id"])
    return rows


def next_occurrence() -> dict | None:
    rows = schedules_with_runtime()
    with_next = [row for row in rows if row.get("enabled") and row.get("next_run_time")]
    if with_next:
        return min(with_next, key=lambda item: item["next_run_time"])

    now = datetime.now(local_timezone)
    candidates: list[tuple[int, int, dict]] = []
    for row in rows:
        if not row["enabled"]:
            continue
        hour, minute = (int(part) for part in row["time_of_day"].split(":"))
        for offset in range(8):
            weekday = (now.weekday() + offset) % 7
            if weekday not in row["days_of_week"]:
                continue
            if offset == 0 and (hour, minute) <= (now.hour, now.minute):
                continue
            candidates.append((offset, hour * 60 + minute, row))
            break
    if not candidates:
        return None
    _, _, row = min(candidates, key=lambda item: (item[0], item[1]))
    return row


def upcoming_schedule_context(limit: int = 4) -> list[dict]:
    rows = schedules_with_runtime()
    active = [item for item in rows if item.get("enabled")]
    active.sort(key=lambda item: (item.get("next_run_time") or "9999", item["time_of_day"]))
    if not any(item.get("next_run_time") for item in active):
        now = datetime.now(local_timezone)
        today = [
            item
            for item in active
            if now.weekday() in item["days_of_week"]
            and tuple(int(part) for part in item["time_of_day"].split(":")) >= (now.hour, now.minute)
        ]
        if today:
            active = today
    return [
        {
            "title": item["title"],
            "time_of_day": item["time_of_day"],
            "reminder_type": item["reminder_type"],
        }
        for item in active[:limit]
    ]


@app.get("/")
def index():
    return render_template(
        "index.html",
        app_name=config.APP_NAME,
        app_version=config.APP_VERSION,
        ack_seconds=config.ACKNOWLEDGEMENT_DISPLAY_SECONDS,
        snooze_minutes=config.DEFAULT_SNOOZE_MINUTES,
        poll_seconds=config.STATE_POLL_SECONDS,
    )


@app.get("/api/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "app": config.APP_NAME,
            "version": config.APP_VERSION,
            "hardware_mode": hardware.mode,
            "scheduler_running": reminder_scheduler.running,
            "timezone": str(local_timezone),
            "active_profile": profile(),
            "companion_ai": companion_ai.status(),
        }
    )


@app.get("/api/config")
def public_config():
    return jsonify(
        {
            "app_name": config.APP_NAME,
            "app_version": config.APP_VERSION,
            "profile": profile(),
            "acknowledgement_display_seconds": config.ACKNOWLEDGEMENT_DISPLAY_SECONDS,
            "snooze_minutes": config.DEFAULT_SNOOZE_MINUTES,
            "state_poll_seconds": config.STATE_POLL_SECONDS,
            "reminder_followup_seconds": config.REMINDER_FOLLOWUP_SECONDS,
            "reminder_max_followups": config.REMINDER_MAX_FOLLOWUPS,
            "conditions": {name: condition.to_dict() for name, condition in CONDITIONS.items()},
            "reminders": config.REMINDERS,
            "hardware_mode": hardware.mode,
            "timezone": str(local_timezone),
            "companion_ai": companion_ai.status(),
        }
    )


@app.get("/api/state")
def get_state():
    return jsonify(state_snapshot())


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

@app.get("/api/profile")
def get_profile():
    return jsonify(profile())


@app.put("/api/profile")
def update_profile():
    active = profile()
    payload = request.get_json(silent=True) or {}
    try:
        values = profile_payload(payload, fallback=active)
        database.update_profile(active["id"], **values)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(profile())


@app.get("/api/profiles")
def get_profiles():
    return jsonify(
        {
            "active_profile_id": database.get_active_profile_id(),
            "profiles": database.list_profiles(),
        }
    )


@app.post("/api/profiles")
def create_profile_route():
    payload = request.get_json(silent=True) or {}
    try:
        values = profile_payload(payload)
        profile_id = database.create_profile(**values)
        if bool(payload.get("copy_demo_schedule", True)):
            database.replace_schedules(config.SYNTHETIC_SCHEDULE, profile_id=profile_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(database.get_profile(profile_id)), 201


@app.put("/api/profiles/<int:profile_id>")
def update_profile_route(profile_id: int):
    current = database.get_profile(profile_id)
    if not current:
        return jsonify({"error": "Profile not found."}), 404
    payload = request.get_json(silent=True) or {}
    try:
        values = profile_payload(payload, fallback=current)
        database.update_profile(profile_id, **values)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(database.get_profile(profile_id))


@app.post("/api/profiles/<int:profile_id>/activate")
def activate_profile(profile_id: int):
    with state_lock:
        if robot_state["mode"] == "reminder":
            return jsonify({"error": "Finish or snooze the active reminder before switching profile."}), 409
    try:
        active = database.set_active_profile(profile_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    reminder_scheduler.reload()
    with state_lock:
        response_timer.reset()
        robot_state["mode"] = "idle"
        robot_state["active_reminder"] = None
        robot_state["last_result"] = None
        touch_state()
    return jsonify({"active_profile": active, "profile": profile()})


@app.delete("/api/profiles/<int:profile_id>")
def delete_profile_route(profile_id: int):
    with state_lock:
        if robot_state["mode"] == "reminder":
            return jsonify({"error": "Finish or snooze the active reminder before deleting a profile."}), 409
    try:
        active_profile_id = database.delete_profile(profile_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    reminder_scheduler.reload()
    return jsonify({"ok": True, "active_profile_id": active_profile_id, "profile": profile()})


# ---------------------------------------------------------------------------
# Reminder interactions
# ---------------------------------------------------------------------------

@app.post("/api/reminder/start")
def start_reminder():
    payload = request.get_json(silent=True) or {}
    user = profile()
    participant_id = clean_text(
        payload.get("participant_id"), fallback=user["participant_id"], max_length=30
    )
    display_name = clean_text(
        payload.get("display_name"), fallback=user["display_name"], max_length=40
    )
    reminder_type = clean_text(
        payload.get("reminder_type"), fallback="medication", max_length=30
    ).lower()
    condition_name = clean_text(
        payload.get("condition"), fallback=user["default_condition"], max_length=20
    ).upper()

    state, error = start_reminder_core(
        reminder_type=reminder_type,
        condition_name=condition_name,
        participant_id=participant_id,
        display_name=display_name,
        source="manual",
        profile_id=user["id"],
    )
    if error:
        status = 409 if "already active" in error else 400
        return jsonify({"error": error}), status
    return jsonify(state), 201


@app.post("/api/reminder/acknowledge")
def acknowledge_reminder():
    with state_lock:
        if robot_state["mode"] != "reminder" or not robot_state["active_reminder"]:
            return jsonify({"error": "There is no active reminder to acknowledge."}), 409

        active = deepcopy(robot_state["active_reminder"])
        try:
            timing = response_timer.stop()
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 409

        condition = get_condition(active["condition"]["name"])
        trial_id = database.save_trial(
            profile_id=active.get("profile_id"),
            participant_id=active["participant_id"],
            display_name=active["display_name"],
            reminder_type=active["reminder_type"],
            condition_name=condition.name,
            social_cue_count=condition.social_cue_count,
            cue_flags=cue_flags(condition),
            started_at=timing["started_at"],
            acknowledged_at=timing["acknowledged_at"],
            response_time_ms=timing["response_time_ms"],
            notes=f"Reminder follow-ups: {int(active.get('followup_count') or 0)}",
            acknowledged=True,
            action="acknowledged",
            schedule_id=active.get("schedule_id"),
            source=active.get("source", "manual"),
        )

        result = {
            "trial_id": trial_id,
            "participant_id": active["participant_id"],
            "reminder_type": active["reminder_type"],
            "condition": condition.name,
            "social_cue_count": condition.social_cue_count,
            "action": "acknowledged",
            "followup_count": int(active.get("followup_count") or 0),
            **timing,
        }
        robot_state["mode"] = "acknowledgement"
        robot_state["last_result"] = result
        touch_state()

    hardware_events = hardware.acknowledge(condition)
    snapshot = state_snapshot()
    snapshot["hardware_events"] = hardware_events
    return jsonify(snapshot)


@app.post("/api/reminder/snooze")
def snooze_reminder():
    payload = request.get_json(silent=True) or {}
    minutes = int(payload.get("minutes", config.DEFAULT_SNOOZE_MINUTES))
    minutes = max(1, min(minutes, 120))

    with state_lock:
        if robot_state["mode"] != "reminder" or not robot_state["active_reminder"]:
            return jsonify({"error": "There is no active reminder to snooze."}), 409

        active = deepcopy(robot_state["active_reminder"])
        try:
            timing = response_timer.stop()
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 409

        condition = get_condition(active["condition"]["name"])
        trial_id = database.save_trial(
            profile_id=active.get("profile_id"),
            participant_id=active["participant_id"],
            display_name=active["display_name"],
            reminder_type=active["reminder_type"],
            condition_name=condition.name,
            social_cue_count=condition.social_cue_count,
            cue_flags=cue_flags(condition),
            started_at=timing["started_at"],
            acknowledged_at=timing["acknowledged_at"],
            response_time_ms=timing["response_time_ms"],
            acknowledged=False,
            action="snoozed",
            schedule_id=active.get("schedule_id"),
            source=active.get("source", "manual"),
            notes=(
                f"Snoozed for {minutes} minutes; "
                f"reminder follow-ups: {int(active.get('followup_count') or 0)}"
            ),
        )
        run_at = reminder_scheduler.schedule_snooze(active, minutes)
        result = {
            "trial_id": trial_id,
            "action": "snoozed",
            "snooze_minutes": minutes,
            "snooze_until": run_at,
            "followup_count": int(active.get("followup_count") or 0),
            **timing,
        }
        robot_state["mode"] = "acknowledgement"
        robot_state["last_result"] = result
        touch_state()

    hardware_events = hardware.snooze(condition)
    snapshot = state_snapshot()
    snapshot["hardware_events"] = hardware_events
    return jsonify(snapshot)


@app.post("/api/reminder/reset")
def reset_reminder():
    with state_lock:
        response_timer.reset()
        robot_state["mode"] = "idle"
        robot_state["active_reminder"] = None
        touch_state()
    hardware_events = hardware.reset()
    snapshot = state_snapshot()
    snapshot["hardware_events"] = hardware_events
    return jsonify(snapshot)



# ---------------------------------------------------------------------------
# V4.2 adaptive reminder follow-up
# ---------------------------------------------------------------------------

def _adaptive_followup_text(active: dict, attempt: int) -> dict:
    """Return a natural follow-up, or the exact original cue when cloud AI is unavailable."""
    original = clean_text(
        active.get("voice_message") or active.get("message"),
        fallback="It is time for your reminder.",
        max_length=500,
    )
    condition = active.get("condition") or {}
    voice_enabled = bool(condition.get("voice_reminder"))
    expression = "attentive" if attempt <= 1 else "caring"

    # Preserve the experimental LOW condition: repeat the same non-social cue.
    # Also use this exact-repeat path whenever Gemini is unavailable/offline.
    if not voice_enabled or not companion_ai.api_available:
        return {
            "text": original,
            "mode": "repeat",
            "model": None,
            "expression": expression,
            "emoji": "🔔",
        }

    reminder_type = clean_text(active.get("reminder_type"), max_length=30)
    title = clean_text(active.get("title"), max_length=80)
    configured_message = clean_text(active.get("message"), max_length=240)

    prompt = f"""
This is an INTERNAL reminder follow-up task for a socially assistive robot.
The person has not yet acknowledged a configured reminder after the first prompt.

Attempt number: {attempt}
Reminder type: {reminder_type}
Reminder title: {title}
Configured reminder: {configured_message}
Original spoken reminder: {original}

Write ONLY the one short sentence the robot should say now.
Rules:
- Keep it warm, natural and under about 22 words.
- Do not use the person's name.
- Gently regain attention and repeat the purpose of the configured reminder.
- On the first follow-up, wording like "Are you there?" or "Can you hear me?" is appropriate.
- On later follow-ups, it may gently ask "Are you okay?" before restating the reminder.
- Vary the wording; do not simply repeat the exact original when cloud AI is working.
- Do not invent new tasks, facts, medication names, doses or medical instructions.
- For medication, only remind the person to follow the already-configured medication reminder.
- Do not claim an emergency or that the robot detected a medical problem.
- Do not shame, pressure or frighten the person.
- No markdown, labels, quotation marks or explanation.
""".strip()

    reply = companion_ai.reply(
        profile=profile(),
        message=prompt,
        history=[],
        schedule_context=[],
    )

    # The companion automatically falls back to BASIC if Gemini cannot be
    # reached. In that case the requirement is to repeat the original sentence.
    if reply.mode == "basic":
        return {
            "text": original,
            "mode": "repeat",
            "model": None,
            "expression": expression,
            "emoji": "🔔",
        }

    generated = clean_text(reply.text, max_length=240).strip(' "\'')
    if not generated:
        generated = original
        mode = "repeat"
        model = None
    else:
        mode = reply.mode
        model = reply.model

    return {
        "text": generated,
        "mode": mode,
        "model": model,
        "expression": expression,
        "emoji": "💛" if attempt >= 2 else "🔔",
    }


@app.post("/api/reminder/followup")
def reminder_followup():
    with state_lock:
        if robot_state["mode"] != "reminder" or not robot_state["active_reminder"]:
            return jsonify({"error": "There is no active reminder to follow up."}), 409

        current = robot_state["active_reminder"]
        completed = int(current.get("followup_count") or 0)
        maximum = int(config.REMINDER_MAX_FOLLOWUPS)

        if completed >= maximum:
            return jsonify(
                {
                    "done": True,
                    "attempt": completed,
                    "max_followups": maximum,
                    "followup_seconds": config.REMINDER_FOLLOWUP_SECONDS,
                }
            )

        attempt = completed + 1
        current["followup_count"] = attempt
        active = deepcopy(current)
        reminder_started_at = active.get("started_at")
        touch_state()

    result = _adaptive_followup_text(active, attempt)

    # The participant may acknowledge while Gemini is producing the re-prompt.
    # Never speak a stale follow-up after the reminder has already ended.
    with state_lock:
        still_active = (
            robot_state["mode"] == "reminder"
            and robot_state["active_reminder"]
            and robot_state["active_reminder"].get("started_at") == reminder_started_at
        )
    if not still_active:
        return jsonify({"error": "The reminder was already completed."}), 409

    return jsonify(
        {
            **result,
            "done": False,
            "attempt": attempt,
            "max_followups": int(config.REMINDER_MAX_FOLLOWUPS),
            "followup_seconds": float(config.REMINDER_FOLLOWUP_SECONDS),
            "voice_enabled": bool((active.get("condition") or {}).get("voice_reminder")),
            "reminder_started_at": reminder_started_at,
        }
    )


# ---------------------------------------------------------------------------
# Per-profile schedules
# ---------------------------------------------------------------------------

@app.get("/api/schedules")
def get_schedules():
    return jsonify(
        {
            "profile_id": database.get_active_profile_id(),
            "schedules": schedules_with_runtime(),
            "timezone": str(local_timezone),
        }
    )


@app.post("/api/schedules")
def create_schedule():
    payload = request.get_json(silent=True) or {}
    try:
        values = schedule_payload_from_request(payload)
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400
    profile_id = database.get_active_profile_id()
    schedule_id = database.create_schedule(profile_id=profile_id, **values)
    reminder_scheduler.reload()
    return jsonify(database.get_schedule(schedule_id)), 201


def _active_owned_schedule(schedule_id: int) -> dict | None:
    row = database.get_schedule(schedule_id)
    if not row:
        return None
    if int(row.get("profile_id") or 0) != database.get_active_profile_id():
        return None
    return row


@app.put("/api/schedules/<int:schedule_id>")
def update_schedule(schedule_id: int):
    if not _active_owned_schedule(schedule_id):
        return jsonify({"error": "Schedule not found for the active profile."}), 404
    payload = request.get_json(silent=True) or {}
    try:
        values = schedule_payload_from_request(payload)
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400
    database.update_schedule(schedule_id, **values)
    reminder_scheduler.reload()
    return jsonify(database.get_schedule(schedule_id))


@app.delete("/api/schedules/<int:schedule_id>")
def delete_schedule(schedule_id: int):
    if not _active_owned_schedule(schedule_id):
        return jsonify({"error": "Schedule not found for the active profile."}), 404
    database.delete_schedule(schedule_id)
    reminder_scheduler.reload()
    return jsonify({"ok": True})


@app.post("/api/schedules/<int:schedule_id>/trigger")
def trigger_schedule_now(schedule_id: int):
    schedule = _active_owned_schedule(schedule_id)
    if not schedule:
        return jsonify({"error": "Schedule not found for the active profile."}), 404
    user = profile()
    state, error = start_reminder_core(
        reminder_type=schedule["reminder_type"],
        condition_name=schedule["condition_name"],
        participant_id=user["participant_id"],
        display_name=user["display_name"],
        title=schedule["title"],
        message=schedule["message"],
        source="schedule_test",
        schedule_id=schedule_id,
        profile_id=user["id"],
    )
    if error:
        return jsonify({"error": error}), 409
    return jsonify(state)


@app.post("/api/schedules/reset-demo")
def reset_demo_schedule():
    profile_id = database.get_active_profile_id()
    database.replace_schedules(config.SYNTHETIC_SCHEDULE, profile_id=profile_id)
    reminder_scheduler.reload()
    return jsonify({"schedules": schedules_with_runtime()})


@app.get("/api/today")
def today_schedule():
    now = datetime.now(local_timezone)
    weekday = now.weekday()
    rows = [
        row
        for row in schedules_with_runtime()
        if row["enabled"] and weekday in row["days_of_week"]
    ]
    upcoming = [
        row
        for row in rows
        if tuple(int(part) for part in row["time_of_day"].split(":")) >= (now.hour, now.minute)
    ]
    return jsonify(
        {
            "profile_id": database.get_active_profile_id(),
            "date": now.date().isoformat(),
            "weekday": weekday,
            "timezone": str(local_timezone),
            "today": rows,
            "upcoming": upcoming,
            "next": next_occurrence(),
        }
    )


# ---------------------------------------------------------------------------
# Simple quick companion actions from V2
# ---------------------------------------------------------------------------

@app.post("/api/companion/respond")
def companion_respond():
    payload = request.get_json(silent=True) or {}
    intent = clean_text(payload.get("intent"), max_length=30).lower()
    user = profile()
    # V4: avoid repeating the user's name in routine companion replies.
    # The explicit hello greeting below can still use it naturally once.
    name_prefix = ""

    if intent == "next":
        next_item = next_occurrence()
        if next_item:
            text = (
                f"{name_prefix}your next reminder is {next_item['title']} at "
                f"{next_item['time_of_day']}. I will let you know when it is time."
            )
            response = {"text": text, "expression": "attentive", "emoji": "🗓️"}
        else:
            response = {
                "text": f"{name_prefix}you do not have any enabled reminders coming up yet.",
                "expression": "happy",
                "emoji": "✅",
            }
    elif intent == "hello":
        hour = datetime.now(local_timezone).hour
        period = "morning" if hour < 12 else "afternoon" if hour < 18 else "evening"
        response = {
            "text": f"Good {period}{', ' + user['display_name'] if user['display_name'] else ''}. It is nice to see you. What can I help you with?",
            "expression": "excited",
            "emoji": "👋",
        }
    elif intent in config.COMPANION_RESPONSES:
        expression, emoji, text = random.choice(config.COMPANION_RESPONSES[intent])
        response = {
            "text": f"{name_prefix}{text}" if name_prefix else text,
            "expression": expression,
            "emoji": emoji,
        }
    else:
        return jsonify({"error": "Unknown companion interaction."}), 400
    return jsonify(response)


# ---------------------------------------------------------------------------
# V3 conversational companion
# ---------------------------------------------------------------------------

@app.get("/api/ai/status")
def ai_status():
    return jsonify(companion_ai.status())


@app.get("/api/chat/history")
def chat_history():
    active_profile = profile()
    limit = request.args.get("limit", default=30, type=int) or 30
    rows = database.chat_history(active_profile["id"], limit=limit)
    return jsonify({"profile": active_profile, "messages": rows})


@app.delete("/api/chat/history")
def clear_chat_history():
    active_profile = profile()
    database.clear_chat(active_profile["id"])
    return jsonify({"ok": True})


@app.post("/api/chat")
def chat():
    payload = request.get_json(silent=True) or {}
    message = clean_text(payload.get("message"), max_length=600)
    if not message:
        return jsonify({"error": "Type a message first."}), 400

    active_profile = profile()
    history = database.chat_history(
        active_profile["id"],
        limit=config.AI_MAX_HISTORY_MESSAGES,
    )
    reply = companion_ai.reply(
        profile=active_profile,
        message=message,
        history=history,
        schedule_context=upcoming_schedule_context(limit=4),
    )
    database.add_chat_message(active_profile["id"], "user", message)
    database.add_chat_message(active_profile["id"], "assistant", reply.text)

    return jsonify(
        {
            **reply.to_dict(),
            "profile_id": active_profile["id"],
            "profile_name": active_profile["display_name"],
            "ai_status": companion_ai.status(),
        }
    )


# ---------------------------------------------------------------------------
# Trials + hardware
# ---------------------------------------------------------------------------

@app.get("/api/trials")
def trials():
    limit = request.args.get("limit", default=20, type=int) or 20
    profile_id = database.get_active_profile_id()
    rows = database.recent_trials(limit=limit, profile_id=profile_id)
    return jsonify({"count": database.count_trials(profile_id=profile_id), "trials": rows})


@app.get("/api/export.csv")
def export_csv():
    active = profile()
    csv_text = database.export_csv(profile_id=active["id"])
    safe_id = re.sub(r"[^A-Za-z0-9_-]+", "_", active["participant_id"])
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=assistive_robot_trials_{safe_id}.csv"
        },
    )


@app.post("/api/hardware/test")
def test_hardware():
    payload = request.get_json(silent=True) or {}
    action = clean_text(payload.get("action"), max_length=30)
    try:
        message = hardware.test_action(action)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "message": message, "hardware_mode": hardware.mode})


if __name__ == "__main__":
    reminder_scheduler.start()
    ai_status_line = companion_ai.status()
    print(f"\n{config.APP_NAME} v{config.APP_VERSION}")
    print(f"Open http://{config.HOST}:{config.PORT} in your browser")
    print(f"Hardware mode: {hardware.mode}")
    print(f"Scheduler: {'RUNNING' if reminder_scheduler.running else 'STOPPED'}")
    print(f"Active profile: {profile()['display_name'] or profile()['participant_id']}")
    if ai_status_line["api_available"]:
        provider = (
            ai_status_line.get("provider")
            or ai_status_line.get("mode")
            or "cloud"
        ).upper()

        print(
            f"Companion AI: {provider} "
            f"({ai_status_line['model']})"
        )
    else:
        print("Companion AI: BASIC FALLBACK")
    print(f"Timezone: {local_timezone}\n")
    app.run(
        host=config.HOST,
        port=config.PORT,
        debug=config.DEBUG,
        use_reloader=False,
    )
