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
    settings = database.get_settings()
    condition = settings.get("default_condition", config.DEFAULT_CONDITION).upper()
    if condition not in CONDITIONS:
        condition = config.DEFAULT_CONDITION
    return {
        "participant_id": settings.get("participant_id", config.DEFAULT_PARTICIPANT_ID),
        "display_name": settings.get("display_name", config.DEFAULT_DISPLAY_NAME),
        "default_condition": condition,
    }


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
    participant_id = clean_text(
        schedule.get("participant_id"),
        fallback=user["participant_id"],
        max_length=30,
    )
    display_name = clean_text(
        schedule.get("display_name"),
        fallback=user["display_name"],
        max_length=40,
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
    )
    if error:
        print(f"[SCHEDULER] Reminder skipped: {error}")
    elif state:
        print(f"[SCHEDULER] Activated: {schedule.get('title', 'Reminder')}")


reminder_scheduler = ReminderScheduler(database, on_scheduled_reminder_due)
atexit.register(reminder_scheduler.shutdown)


def schedule_payload_from_request(payload: dict) -> dict:
    reminder_type = clean_text(payload.get("reminder_type"), fallback="medication", max_length=30).lower()
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
    next_runs = reminder_scheduler.next_run_map()
    rows = database.list_schedules()
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
            "conditions": {name: condition.to_dict() for name, condition in CONDITIONS.items()},
            "reminders": config.REMINDERS,
            "hardware_mode": hardware.mode,
            "timezone": str(local_timezone),
        }
    )


@app.get("/api/state")
def get_state():
    return jsonify(state_snapshot())


@app.get("/api/profile")
def get_profile():
    return jsonify(profile())


@app.put("/api/profile")
def update_profile():
    payload = request.get_json(silent=True) or {}
    participant_id = clean_text(
        payload.get("participant_id"), fallback=config.DEFAULT_PARTICIPANT_ID, max_length=30
    )
    display_name = clean_text(payload.get("display_name"), max_length=40)
    condition = clean_text(
        payload.get("default_condition"), fallback=config.DEFAULT_CONDITION, max_length=20
    ).upper()
    try:
        get_condition(condition)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    database.set_settings(
        {
            "participant_id": participant_id,
            "display_name": display_name,
            "default_condition": condition,
        }
    )
    return jsonify(profile())


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
    reminder_type = clean_text(payload.get("reminder_type"), fallback="medication", max_length=30).lower()
    condition_name = clean_text(
        payload.get("condition"), fallback=user["default_condition"], max_length=20
    ).upper()

    state, error = start_reminder_core(
        reminder_type=reminder_type,
        condition_name=condition_name,
        participant_id=participant_id,
        display_name=display_name,
        source="manual",
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
            participant_id=active["participant_id"],
            display_name=active["display_name"],
            reminder_type=active["reminder_type"],
            condition_name=condition.name,
            social_cue_count=condition.social_cue_count,
            cue_flags=cue_flags(condition),
            started_at=timing["started_at"],
            acknowledged_at=timing["acknowledged_at"],
            response_time_ms=timing["response_time_ms"],
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
            notes=f"Snoozed for {minutes} minutes",
        )
        run_at = reminder_scheduler.schedule_snooze(active, minutes)
        result = {
            "trial_id": trial_id,
            "action": "snoozed",
            "snooze_minutes": minutes,
            "snooze_until": run_at,
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


@app.get("/api/schedules")
def get_schedules():
    return jsonify({"schedules": schedules_with_runtime(), "timezone": str(local_timezone)})


@app.post("/api/schedules")
def create_schedule():
    payload = request.get_json(silent=True) or {}
    try:
        values = schedule_payload_from_request(payload)
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400
    schedule_id = database.create_schedule(**values)
    reminder_scheduler.reload()
    return jsonify(database.get_schedule(schedule_id)), 201


@app.put("/api/schedules/<int:schedule_id>")
def update_schedule(schedule_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        values = schedule_payload_from_request(payload)
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400
    if not database.update_schedule(schedule_id, **values):
        return jsonify({"error": "Schedule not found."}), 404
    reminder_scheduler.reload()
    return jsonify(database.get_schedule(schedule_id))


@app.delete("/api/schedules/<int:schedule_id>")
def delete_schedule(schedule_id: int):
    if not database.delete_schedule(schedule_id):
        return jsonify({"error": "Schedule not found."}), 404
    reminder_scheduler.reload()
    return jsonify({"ok": True})


@app.post("/api/schedules/<int:schedule_id>/trigger")
def trigger_schedule_now(schedule_id: int):
    schedule = database.get_schedule(schedule_id)
    if not schedule:
        return jsonify({"error": "Schedule not found."}), 404
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
    )
    if error:
        return jsonify({"error": error}), 409
    return jsonify(state)


@app.post("/api/schedules/reset-demo")
def reset_demo_schedule():
    database.replace_schedules(config.SYNTHETIC_SCHEDULE)
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
            "date": now.date().isoformat(),
            "weekday": weekday,
            "timezone": str(local_timezone),
            "today": rows,
            "upcoming": upcoming,
            "next": next_occurrence(),
        }
    )


@app.post("/api/companion/respond")
def companion_respond():
    payload = request.get_json(silent=True) or {}
    intent = clean_text(payload.get("intent"), max_length=30).lower()
    user = profile()
    name_prefix = f"{user['display_name']}, " if user["display_name"] else ""

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
        response = {"text": f"{name_prefix}{text}" if name_prefix else text, "expression": expression, "emoji": emoji}
    else:
        return jsonify({"error": "Unknown companion interaction."}), 400

    return jsonify(response)


@app.get("/api/trials")
def trials():
    limit = request.args.get("limit", default=20, type=int) or 20
    rows = database.recent_trials(limit=limit)
    return jsonify({"count": database.count_trials(), "trials": rows})


@app.get("/api/export.csv")
def export_csv():
    csv_text = database.export_csv()
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=assistive_robot_trials.csv"},
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
    print(f"\n{config.APP_NAME} v{config.APP_VERSION}")
    print(f"Open http://{config.HOST}:{config.PORT} in your browser")
    print(f"Hardware mode: {hardware.mode}")
    print(f"Scheduler: {'RUNNING' if reminder_scheduler.running else 'STOPPED'}")
    print(f"Timezone: {local_timezone}\n")
    app.run(
        host=config.HOST,
        port=config.PORT,
        debug=config.DEBUG,
        use_reloader=False,
    )
