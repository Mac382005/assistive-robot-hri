"""Production WSGI entry point for the HRI robot cloud deployment."""

from app import app, reminder_scheduler

# app.py only starts APScheduler when run directly. Production WSGI servers
# import the Flask application instead, so start the single scheduler here.
# The production container intentionally runs one Gunicorn worker to prevent
# duplicate reminder jobs against the same SQLite database.
if not reminder_scheduler.running:
    reminder_scheduler.start()

application = app
