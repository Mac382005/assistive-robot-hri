from __future__ import annotations

import threading
from copy import deepcopy
from datetime import datetime, timezone

from flask import Flask, Response, jsonify, render_template, request

import config
from database import RobotDatabase
from experiment.conditions import CONDITIONS, get_condition
from experiment.response_timer import ResponseTimer
from robot import MockHardwareController

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

database = RobotDatabase()
database.initialise()
response_timer = ResponseTimer()
hardware = MockHardwareController()
state_lock = threading.RLock()

robot_state = {
    "mode": "idle",
    "active_reminder": None,
    "last_result": None,
    "hardware_mode": hardware.mode,
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def clean_text(value: object, *, fallback: str = "", max_length: int = 80) -> str:
    text = str(value or fallback).strip()
    return text[:max_length]


def state_snapshot() -> dict:
    with state_lock:
        return deepcopy(robot_state)


@app.get("/")
def index():
    return render_template(
        "index.html",
        app_name=config.APP_NAME,
        ack_seconds=config.ACKNOWLEDGEMENT_DISPLAY_SECONDS,
    )


@app.get("/api/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "app": config.APP_NAME,
            "hardware_mode": hardware.mode,
            "time_utc": utc_now_iso(),
        }
    )


@app.get("/api/config")
def public_config():
    return jsonify(
        {
            "app_name": config.APP_NAME,
            "default_participant_id": config.DEFAULT_PARTICIPANT_ID,
            "default_display_name": config.DEFAULT_DISPLAY_NAME,
            "default_condition": config.DEFAULT_CONDITION,
            "acknowledgement_display_seconds": config.ACKNOWLEDGEMENT_DISPLAY_SECONDS,
            "conditions": {name: condition.to_dict() for name, condition in CONDITIONS.items()},
            "reminders": config.REMINDERS,
            "hardware_mode": hardware.mode,
        }
    )


@app.get("/api/state")
def get_state():
    return jsonify(state_snapshot())


@app.post("/api/reminder/start")
def start_reminder():
    payload = request.get_json(silent=True) or {}
    participant_id = clean_text(
        payload.get("participant_id"), fallback=config.DEFAULT_PARTICIPANT_ID, max_length=30
    )
    display_name = clean_text(payload.get("display_name"), max_length=40)
    reminder_type = clean_text(payload.get("reminder_type"), fallback="medication", max_length=30).lower()
    condition_name = clean_text(
        payload.get("condition"), fallback=config.DEFAULT_CONDITION, max_length=20
    ).upper()

    if reminder_type not in config.REMINDERS:
        return jsonify({"error": "Unknown reminder type."}), 400

    try:
        condition = get_condition(condition_name)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    with state_lock:
        if robot_state["mode"] == "reminder":
            return jsonify({"error": "A reminder is already active."}), 409

        response_timer.reset()
        started_at = response_timer.start()
        reminder = config.REMINDERS[reminder_type]

        greeting = ""
        if condition.personalised_greeting:
            greeting = f"Hello, {display_name}." if display_name else "Hello."

        active = {
            "participant_id": participant_id,
            "display_name": display_name,
            "reminder_type": reminder_type,
            "title": reminder["title"],
            "message": reminder["message"],
            "voice_message": f"{greeting} {reminder['voice_message']}".strip(),
            "symbol": reminder["symbol"],
            "condition": condition.to_dict(),
            "started_at": started_at,
        }
        robot_state["mode"] = "reminder"
        robot_state["active_reminder"] = active
        robot_state["last_result"] = None

    hardware_events = hardware.begin_reminder(condition, active["voice_message"])
    result = state_snapshot()
    result["hardware_events"] = hardware_events
    return jsonify(result), 201


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
        cue_flags = {
            "face_animation": condition.face_animation,
            "voice_reminder": condition.voice_reminder,
            "head_orientation": condition.head_orientation,
            "personalised_greeting": condition.personalised_greeting,
            "acknowledgement": condition.acknowledgement,
            "arm_gesture": condition.arm_gesture,
        }

        trial_id = database.save_trial(
            participant_id=active["participant_id"],
            display_name=active["display_name"],
            reminder_type=active["reminder_type"],
            condition_name=condition.name,
            social_cue_count=condition.social_cue_count,
            cue_flags=cue_flags,
            started_at=timing["started_at"],
            acknowledged_at=timing["acknowledged_at"],
            response_time_ms=timing["response_time_ms"],
        )

        result = {
            "trial_id": trial_id,
            "participant_id": active["participant_id"],
            "reminder_type": active["reminder_type"],
            "condition": condition.name,
            "social_cue_count": condition.social_cue_count,
            **timing,
        }
        robot_state["mode"] = "acknowledgement"
        robot_state["last_result"] = result

    hardware_events = hardware.acknowledge(condition)
    snapshot = state_snapshot()
    snapshot["hardware_events"] = hardware_events
    return jsonify(snapshot)


@app.post("/api/reminder/reset")
def reset_reminder():
    with state_lock:
        response_timer.reset()
        robot_state["mode"] = "idle"
        robot_state["active_reminder"] = None
    hardware_events = hardware.reset()
    snapshot = state_snapshot()
    snapshot["hardware_events"] = hardware_events
    return jsonify(snapshot)


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
    print(f"\n{config.APP_NAME}")
    print(f"Open http://{config.HOST}:{config.PORT} in your browser")
    print(f"Hardware mode: {hardware.mode}\n")
    app.run(
        host=config.HOST,
        port=config.PORT,
        debug=config.DEBUG,
        use_reloader=False,
    )
