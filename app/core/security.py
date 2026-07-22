import secrets

from fastapi import Header

from app.core.exceptions import internal_auth_failed
from app.core.settings import settings


def verify_internal_api_key(
    api_key: str | None = Header(default=None, alias="X-Internal-Api-Key"),
) -> None:
    if not api_key or not secrets.compare_digest(api_key, settings.internal_api_key):
        raise internal_auth_failed()
