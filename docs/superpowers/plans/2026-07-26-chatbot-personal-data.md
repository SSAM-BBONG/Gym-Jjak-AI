# Chatbot Personal Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make chatbot routine recommendations consume Spring's personal-data snapshot.

**Architecture:** Parse the internal Spring snapshot at the FastAPI boundary, retain it in graph state, and let `RoutineService` choose it over `UserDataClient`. Pass the uncapped 28-day summary separately to the member routine prompt.

**Tech Stack:** FastAPI, Pydantic v2, LangGraph, pytest.

## Global Constraints

- Keep `personal_data` optional for rolling deployment compatibility.
- Do not add a database migration or production data-store access.
- Preserve the existing trainer routine request contract.

---

### Task 1: Parse and propagate the Spring snapshot

**Files:**
- Modify: `app/chatbot/schemas.py`, `app/chatbot/state.py`, `app/chatbot/service.py`, `app/chatbot/nodes.py`
- Test: `tests/integration/chatbot/test_chat_api.py`, `tests/graph/test_chatbot_graph.py`

- [ ] Write tests that send `personal_data.recent_workouts` and `workout_summary` in snake_case and assert the routine graph receives them.
- [ ] Run the tests and confirm they fail because `personal_data` is absent from the request/state contract.
- [ ] Add the Pydantic models, state field, service state construction, and routine-node forwarding.
- [ ] Re-run the focused API and graph tests.

### Task 2: Consume the snapshot in member routine recommendation

**Files:**
- Modify: `app/routine/schemas.py`, `app/routine/service.py`, `app/routine/prompts.py`
- Test: `tests/unit/routine/test_service.py`

- [ ] Write a service test asserting a supplied snapshot makes no `UserDataClient` call and appears in the routine prompt.
- [ ] Run the test and confirm it fails because the service always reads `UserDataClient`.
- [ ] Add a snapshot-aware member-data selection path and pass the 28-day summary to the prompt.
- [ ] Re-run the focused service test.

### Task 3: Verify the contract

**Files:**
- Modify: `app/chatbot/docs/REVISION.md`
- Test: `tests/unit/routine/test_service.py`, `tests/graph/test_chatbot_graph.py`, `tests/integration/chatbot/test_chat_api.py`

- [ ] Run the focused tests together.
- [ ] Record the final request-contract ownership and fallback behavior in the chatbot revision log.
