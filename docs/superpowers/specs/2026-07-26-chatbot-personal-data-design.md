# Chatbot Personal Data Design

## Goal

Use the personal-data snapshot sent by Spring for member routine recommendations without a duplicate FastAPI-to-Spring data lookup.

## Design

- `ChatRequest` accepts an optional `personal_data` object containing onboarding, recent detailed workouts, a 28-day workout summary, and InBody records.
- The graph stores that object in `ChatState` and passes it to `RoutineRequest` only on the chatbot routine route.
- `RoutineService` uses the supplied snapshot when present. It falls back to `UserDataClient` only when the request has no snapshot, preserving rolling-deployment compatibility.
- The routine prompt receives the detailed-workout analysis and the separate authoritative 28-day summary. The summary is not reconstructed from the capped 30 detailed workouts.

## Constraints

- No database schema change.
- No direct production database access from FastAPI.
- Spring remains the owner of actor identity and member personal-data retrieval.
- The member route remains restricted to `USER`; trainer routine recommendation remains unchanged.

## Verification

- Schema test: snake_case Spring payload parses into the request model.
- Service test: a supplied snapshot prevents calls to `UserDataClient` and is present in the generated prompt.
- Graph test: chatbot routine requests pass the snapshot through to the routine service.
