from __future__ import annotations

import threading
from datetime import datetime, timedelta
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from tzlocal import get_localzone

from database import RobotDatabase

DAY_CODES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class ReminderScheduler:
    """Schedules reminders for the one currently active profile."""

    def __init__(
        self,
        database: RobotDatabase,
        on_due: Callable[[dict, str], None],
        active_profile_id: Callable[[], int] | None = None,
    ) -> None:
        self.database = database
        self.on_due = on_due
        self.active_profile_id = active_profile_id or database.get_active_profile_id
        self.timezone = get_localzone()
        self.scheduler = BackgroundScheduler(timezone=self.timezone, daemon=True)
        self._lock = threading.RLock()

    @property
    def running(self) -> bool:
        return bool(self.scheduler.running)

    def start(self) -> None:
        with self._lock:
            if not self.scheduler.running:
                self.scheduler.start()
            self.reload()

    def shutdown(self) -> None:
        with self._lock:
            if self.scheduler.running:
                self.scheduler.shutdown(wait=False)

    def _fire_schedule(self, schedule_id: int) -> None:
        schedule = self.database.get_schedule(schedule_id)
        if not schedule or not schedule["enabled"]:
            return
        if int(schedule.get("profile_id") or 0) != int(self.active_profile_id()):
            return
        self.on_due(schedule, "scheduled")

    def reload(self) -> None:
        if not self.scheduler.running:
            return
        with self._lock:
            for job in list(self.scheduler.get_jobs()):
                if job.id.startswith("schedule-"):
                    self.scheduler.remove_job(job.id)

            profile_id = int(self.active_profile_id())
            for schedule in self.database.list_schedules(
                enabled_only=True,
                profile_id=profile_id,
            ):
                hour, minute = (int(part) for part in schedule["time_of_day"].split(":", 1))
                day_codes = ",".join(DAY_CODES[int(day)] for day in schedule["days_of_week"])
                trigger = CronTrigger(
                    day_of_week=day_codes,
                    hour=hour,
                    minute=minute,
                    second=0,
                    timezone=self.timezone,
                )
                self.scheduler.add_job(
                    self._fire_schedule,
                    trigger=trigger,
                    args=[schedule["id"]],
                    id=f"schedule-{schedule['id']}",
                    replace_existing=True,
                    coalesce=True,
                    max_instances=1,
                    misfire_grace_time=60,
                )

    def schedule_snooze(self, active_reminder: dict, minutes: int) -> str:
        safe_minutes = max(1, min(int(minutes), 120))
        run_at = datetime.now(self.timezone) + timedelta(minutes=safe_minutes)
        payload = {
            "id": active_reminder.get("schedule_id"),
            "profile_id": active_reminder.get("profile_id", self.active_profile_id()),
            "title": active_reminder.get("title", "Reminder"),
            "reminder_type": active_reminder.get("reminder_type", "appointment"),
            "time_of_day": run_at.strftime("%H:%M"),
            "days_of_week": [run_at.weekday()],
            "message": active_reminder.get("message", "It is time for your reminder."),
            "condition_name": active_reminder.get("condition", {}).get("name", "HIGH"),
            "enabled": True,
            "participant_id": active_reminder.get("participant_id", "P001"),
            "display_name": active_reminder.get("display_name", ""),
        }
        job_id = f"snooze-{datetime.now().timestamp()}"
        self.scheduler.add_job(
            self.on_due,
            trigger="date",
            run_date=run_at,
            args=[payload, "snooze"],
            id=job_id,
            replace_existing=False,
            misfire_grace_time=120,
        )
        return run_at.isoformat(timespec="minutes")

    def next_run_map(self) -> dict[int, str | None]:
        results: dict[int, str | None] = {}
        if not self.scheduler.running:
            return results
        for job in self.scheduler.get_jobs():
            if not job.id.startswith("schedule-"):
                continue
            schedule_id = int(job.id.split("-", 1)[1])
            results[schedule_id] = (
                job.next_run_time.isoformat(timespec="minutes") if job.next_run_time else None
            )
        return results
