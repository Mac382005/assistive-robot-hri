# HRI Socially Assistive Robot — Version 1

A local, offline-first prototype for a tabletop socially assistive robot. Version 1 focuses on the HRI experiment workflow: show a reminder, vary the social-cue condition, record acknowledgement latency, and store the trial in SQLite.

## Stack

- Python 3.13
- Flask
- HTML / CSS / JavaScript
- SQLite
- Mock hardware layer for Windows development
- APScheduler installed for the next scheduling stage

## Version 1 features

- Friendly idle robot face and clock
- LOW and HIGH social-cue conditions
- Medication, hydration, meal and appointment test reminders
- Large touchscreen-friendly acknowledgement button
- Response timing using Python `time.monotonic()`
- SQLite trial logging
- Recent-trial table and CSV export
- Developer panel
- Mock head, LED and arm actions for development without Raspberry Pi hardware
- No internet or external web assets required

## Run

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

## Tests

```powershell
python -m unittest discover -s tests -v
```

## Important experiment note

Version 1 uses browser-generated speech as a development fallback so the HIGH condition can be demonstrated immediately. Before formal participant testing, replace this with fixed WAV recordings so wording, voice and timing are consistent across participants.

## Next development stages

1. Add scheduled reminders with APScheduler.
2. Replace browser speech with fixed audio recordings.
3. Add Raspberry Pi GPIO Zero hardware implementation.
4. Connect proximity sensor and servos.
5. Add kiosk-mode auto-start on Raspberry Pi OS.
