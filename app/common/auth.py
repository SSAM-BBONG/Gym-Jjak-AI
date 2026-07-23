"""내부 API Key 검증. Spring이 보내는 X-Internal-Api-Key를 확인한다.
diet 도메인은 동일한 검증을 app/diet/router.py에 자체적으로 갖고 있다 — 지금은 각
도메인이 이 함수의 사본을 갖는 상태이며, 전역 인증 미들웨어로 통합하는 건 diet 쪽
리팩터링(TRAINER_REPORT_REFACTOR_PROPOSAL.md류)과 함께 다룰 후속 정리 항목이다."""

import secrets

from fastapi import Header

from app.core.exceptions import internal_auth_failed
from app.core.settings import get_settings


def verify_internal_api_key(
    api_key: str | None = Header(default=None, alias="X-Internal-Api-Key"),
) -> None:
    settings = get_settings()
    if not api_key or not secrets.compare_digest(api_key, settings.internal_api_key):
        raise internal_auth_failed()
