# HRI Socially Assistive Robot — Version 2

Version 2 develops the prototype from a simple reminder demonstrator into a more realistic tabletop companion. It remains local/offline-first and keeps Windows-safe mock hardware so the UI and scheduling system can be developed before the Raspberry Pi, arms and rotating base are connected.

## What Version 2 adds

- More expressive robot face with blinking, eyebrows, cheeks, smiles, idle gestures and emoji reactions
- Talking animation while browser speech is playing
- Touch-based companion interactions: Say hello, What's next?, How are you?, Encourage me
- Context-aware response for the next scheduled task
- Persistent user profile with display name and default social mode
- Full timetable editor with recurring day selection, time, task type, message, enable/disable, edit and delete
- APScheduler recurring reminder jobs
- Synthetic daily/weekly schedule seeded automatically for demonstration
- Today's routine and next-reminder view on the main screen
- `Done` and `Remind me in 10 min` actions
- Snoozed interactions recorded separately in SQLite
- Schedule-trigger testing from the caregiver panel
- Existing HRI LOW/HIGH experiment mode retained
- Existing mock hardware controls retained for later physical simulation

## Important design note

The Version 2 companion feels more conversational, but it is **not using a cloud LLM yet**. It uses reliable local interaction rules, schedule context and browser text-to-speech. This is intentional for the current prototype stage. Version 3 can map voice recognition onto the same interaction intents without replacing the reminder architecture.

Browser text-to-speech is still a development feature. For formal HRI data collection, use controlled recorded audio so all participants receive the same wording and voice.

The included timetable is synthetic demonstration data only and is not medical advice.

## Install / update

From the existing project folder:

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m unittest discover -s tests -v
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

## Version roadmap

- **V2:** expressive companion + professional timetable/scheduler
- **V3:** voice recognition and spoken intent input
- **V4:** hardware simulation/integration for arms, head and rotating base
