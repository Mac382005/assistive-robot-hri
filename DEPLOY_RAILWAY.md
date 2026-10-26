# HRI Robot V4.5 — Railway Cloud Deployment

V4.5 can run the Flask/Gemini/database side of the robot continuously on Railway, so the iPad no longer needs the development laptop to host the app.

## Architecture

`iPad / phone -> public HTTPS Railway service -> Flask + Gemini + SQLite`

Real motors and sensors are still a later local Raspberry Pi/ESP32 layer. Do not try to drive physical GPIO directly from the cloud service.

## 1. Generate private cloud credentials

From the project root:

```powershell
python .\tools\generate_cloud_secrets.py
```

Keep the two generated values private. Do not put them in `.env.example`, screenshots, Git commits, or a report appendix.

## 2. Deploy the GitHub repository

In Railway create a project and choose **Deploy from GitHub repo**, then select `Mac382005/assistive-robot-hri` and the `main` branch.

The included `Dockerfile` starts Gunicorn automatically. Do not enable multiple replicas: V4.5 deliberately uses one process/replica because it has one in-process reminder scheduler and one SQLite database.

## 3. Add Railway variables

Add these in the service **Variables** page:

```text
AI_ENABLED=true
AI_PROVIDER=gemini
GEMINI_API_KEY=<your real Gemini API key>
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_TRANSCRIBE_MODEL=gemini-3.5-transcribe
APP_TIMEZONE=Australia/Sydney
CLOUD_MODE=true
CLOUD_AUTH_REQUIRED=true
CLOUD_ACCESS_CODE=<generated access code>
APP_SECRET_KEY=<generated secret key>
```

Optional tuning variables remain supported, including `AI_MAX_HISTORY_MESSAGES`, `AI_MAX_OUTPUT_TOKENS`, `AI_TIMEOUT_SECONDS`, `REMINDER_FOLLOWUP_SECONDS`, `REMINDER_MAX_FOLLOWUPS`, and `TABLET_AUDIO_MAX_BYTES`.

## 4. Attach persistent storage

Attach a Railway Volume to the web service and mount it at:

```text
/data
```

V4.5 automatically detects Railway's `RAILWAY_VOLUME_MOUNT_PATH` and stores `robot.db` there. Without a volume, profiles, schedules, conversations and trial data can disappear when the service is redeployed.

## 5. Keep the reminder service awake

Use one replica and leave Railway **Serverless / App Sleeping disabled** for this service. The in-process scheduler needs the service to stay running for scheduled reminders.

## 6. Healthcheck and public domain

In the service settings, set the healthcheck path to:

```text
/health
```

Then enable Public Networking / Generate Domain. Railway provides normal public HTTPS, so the iPad does not need the project's local certificate profile when using the Railway URL.

## 7. Use it as an iPad app

Open the Railway HTTPS URL on the iPad, enter the private robot access code, then use Safari **Share -> Add to Home Screen -> Open as Web App**. The existing V4.4 display mode, microphone capture and speech output continue to work.

## Important limitations

- The cloud version removes the laptop/same-Wi-Fi hosting requirement, but it requires internet connectivity.
- If the iPad web app is fully closed or suspended, the current project does not yet send native push notifications. For the research/demo robot, keep the mounted display app open.
- Physical motors/servos/sensors should later run through a Raspberry Pi + ESP32 local hardware layer. The cloud service can sync/assist it, but should not directly generate raw motor PWM.
- SQLite + APScheduler means **one Railway replica only** for V4.5. A future multi-user version should move state to PostgreSQL and scheduled work to a dedicated worker.
