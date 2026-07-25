# Spring Personal Data Snapshot

## Ownership

Spring authenticates the actor and reads member onboarding, workout, and InBody data. FastAPI does not read a production database directly for this chatbot path.

## Internal request contract

`POST /api/v1/chatbot/messages` accepts an optional `personal_data` field.

- `onboarding`: exercise goal, period, frequency, and preferred exercise
- `recent_workouts`: latest detailed workout records, capped at 30 by Spring
- `workout_summary`: authoritative 28-day workout days, part-session counts, and part total volumes
- `inbodies`: current InBody records

## Routine recommendation behavior

When `personal_data` is present, the member routine path uses the snapshot and makes no `UserDataClient` call. The recent-workout details are used for exercise and load analysis; `workout_summary` is inserted separately into the prompt and is not recalculated from the capped records.

When `personal_data` is absent, FastAPI preserves the old `UserDataClient` lookup as a rolling-deployment fallback.

Trainer routine recommendation is unchanged.
