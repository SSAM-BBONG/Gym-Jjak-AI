# RAG General Knowledge Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** RAG 검색 결과가 없는 운동 관련 요청도 개인 데이터와 Gemini 일반 지식으로 루틴을 생성하되, 의료 안전 차단과 서버 기반 출처 정책을 유지한다.

**Architecture:** `RoutineService`의 검색·안전·출처 결정 흐름은 그대로 둔다. 프롬프트에 일반 지식 보완 규칙을 명시하고, RAG 0건 루틴 생성·고위험 차단·출처 정책은 사용자가 배포 서버에서 직접 확인한다.

**Tech Stack:** Python 3.12, FastAPI, pytest, Pydantic

## Global Constraints

- `.env` 파일과 비밀 값은 읽거나 수정하거나 커밋하지 않는다.
- Spring Boot 코드와 DB 스키마를 수정하지 않는다.
- 외부 웹 검색, Google Search Grounding, 새 임베딩 모델, 새 벡터 DB 컬렉션을 추가하지 않는다.
- RAG 문서는 일반 지식보다 우선하며, 서버가 검색한 문서만 `RoutineResult.sources`에 넣는다.
- RAG 결과가 없다는 이유만으로 일반 운동 루틴 요청을 차단하지 않는다.
- 고위험 의료 신호는 LLM 호출 전에 계속 `BLOCKED` 처리한다.
- 사용자가 요청한 대로 RAG 0건·고위험 차단·출처 정책의 자동 회귀 테스트는 이번 변경에서 추가하지 않는다.

---

## Target File Structure

| 파일 | 책임 |
| --- | --- |
| `app/routine/prompts.py` | RAG 부재·부족 상황의 일반 지식 보완 규칙 고정 |
| `.docs/RAG_GENERAL_KNOWLEDGE_FALLBACK.md` | 리팩터링 근거와 캡처 절차 최신화 |

### Task 1: Document and Strengthen the General-Knowledge Fallback Policy

**Files:**
- Modify: `app/routine/prompts.py:10-35`
- Modify: `.docs/RAG_GENERAL_KNOWLEDGE_FALLBACK.md`

**Interfaces:**
- Consumes: `_SHARED_RULES`와 `_format_documents()`가 조립하는 회원·트레이너 루틴 프롬프트.
- Produces: RAG 문서 부재·부족 시 일반 지식 보완과 출처 비위조 원칙이 명시된 프롬프트 정책 및 배포 서버 수동 확인 절차.

- [ ] **Step 1: Strengthen only the shared routine prompt policy**

Add these two rules immediately after the evidence-priority rule in `_SHARED_RULES`.

```python
    "- RAG 문서가 없거나 요청을 충분히 다루지 못해도, 운동 관련 루틴 요청을 거절하지 말고 "
    "회원 기록과 일반 지식으로 신중하게 보완합니다.\n"
    "- 일반 지식으로 보완한 내용을 참고 문서 출처처럼 표기하지 않습니다.\n"
```

Do not change `_format_documents`, `RoutineService._finalize`, or `app/routine/safety.py`.

- [ ] **Step 2: Update the refactoring-evidence document**

Change the state line to `- 상태: 구현·검증 완료` and append this manual capture procedure under `## 📸 증빙 캡처 계획`.

```markdown
### 수동 확인 요청

`집에서 할 수 있는 주 3회 전신 루틴 추천해줘`

`routine` 검색 결과가 0건인 테스트 환경에서도 루틴 응답이 생성되고, 응답 출처에는 임의의 일반 지식 출처가 추가되지 않는지 확인한다. 흉통·실신·호흡곤란 표현을 포함한 요청은 이 시나리오와 별개로 차단되어야 한다.
```

- [ ] **Step 3: Inspect the change and commit**

Run: `git diff --check`

Expected: no whitespace errors.

```bash
git add -- app/routine/prompts.py .docs/RAG_GENERAL_KNOWLEDGE_FALLBACK.md
git commit -m "feat: support routine fallback with general knowledge"
```

## Completion Checklist

- [ ] Prompt states RAG-first priority and general-knowledge fallback without fabricated document sources.
- [ ] Deployment-server manual checks cover RAG 0건 루틴 생성, 출처 정책, 고위험 의료 요청 차단.
- [ ] The refactoring rationale and capture procedure are current in `.docs/RAG_GENERAL_KNOWLEDGE_FALLBACK.md`.
