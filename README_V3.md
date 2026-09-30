# HRI Socially Assistive Robot — Version 3

Version 3 adds two major systems without replacing the hand-tuned V2 face/UI code:

1. **Multiple user profiles** — only one profile is active at a time. Every profile has its own timetable, reminder trials, profile notes and chat history.
2. **Conversational companion** — a text-chat layer that can use the OpenAI Responses API when configured, with a basic local fallback when no API key is present.

## Profile behaviour

- The existing V2 user becomes the first V3 profile automatically.
- Existing V2 schedules and trials are migrated to that first profile.
- Two clearly-labelled synthetic demo profiles are added for demonstration: `Mary (Demo)` and `Robert (Demo)`.
- Switching profile reloads the scheduler, timetable, trial list and chat history.
- Only schedules belonging to the active profile are armed by APScheduler.

## Companion AI

V3 defaults to `gpt-5.6-luna` when an OpenAI API key is configured. The cloud AI is optional: without a key the app stays fully operational and provides simple deterministic conversation.

Chat history is stored locally in SQLite per profile. For cloud responses, only recent chat context, the active profile's user-provided profile notes and a small upcoming-schedule summary are sent to the API. API calls use `store=False`.

The companion is intentionally constrained for the elderly-care prototype: it can discuss everyday topics and routines but should not diagnose illness, change medication, choose dosages or replace professional/human care.

## Later versions

The `/api/chat` endpoint is deliberately independent of the input method. A future speech-recognition version can transcribe speech and send the resulting text to the same endpoint. Likewise, the current mock hardware layer can later be replaced with real servos/base rotation without changing the profile/chat architecture.
