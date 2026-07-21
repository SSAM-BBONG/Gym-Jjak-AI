import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

import filetype
import httpx
from pydantic import ValidationError

from app.core.exceptions import AppError
from app.diet.errors import (
    image_download_failed,
    image_too_large,
    invalid_analysis_result,
    llm_error,
    llm_timeout,
    unsafe_image_url,
    unsupported_image_type,
)
from app.core.settings import settings
from app.diet.prompts import MEAL_IMAGE_ANALYSIS_PROMPT
from app.diet.schemas import RawMealAnalysis
from app.llm.port import LLMPort


ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


@dataclass(frozen=True, slots=True)
class DownloadedImage:
    content: bytes
    mime_type: str


class MealImageAnalyzer:
    def __init__(self, llm: LLMPort) -> None:
        self._llm = llm

    async def analyze(self, image_url: str) -> RawMealAnalysis:
        image = await self._download_image(image_url)
        try:
            return await self._llm.generate_structured_image(
                prompt=MEAL_IMAGE_ANALYSIS_PROMPT,
                image_bytes=image.content,
                mime_type=image.mime_type,
                output_schema=RawMealAnalysis,
            )
        except asyncio.TimeoutError as exc:
            raise llm_timeout() from exc
        except ValidationError as exc:
            raise invalid_analysis_result() from exc
        except AppError:
            raise
        except Exception as exc:
            raise llm_error() from exc

    async def _download_image(self, image_url: str) -> DownloadedImage:
        await self._validate_public_https_url(image_url)
        timeout = httpx.Timeout(settings.image_download_timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                async with client.stream("GET", image_url) as response:
                    response.raise_for_status()
                    length = response.headers.get("content-length")
                    if length and int(length) > settings.image_max_bytes:
                        raise image_too_large()
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > settings.image_max_bytes:
                            raise image_too_large()
        except AppError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise image_download_failed() from exc

        kind = filetype.guess(bytes(content))
        mime_type = kind.mime if kind else ""
        if mime_type not in ALLOWED_IMAGE_TYPES:
            raise unsupported_image_type()
        return DownloadedImage(bytes(content), mime_type)

    async def _validate_public_https_url(self, image_url: str) -> None:
        parsed = urlsplit(image_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise unsafe_image_url()
        try:
            addresses = await asyncio.to_thread(
                socket.getaddrinfo, parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM
            )
        except socket.gaierror as exc:
            raise image_download_failed() from exc
        if not addresses:
            raise unsafe_image_url()
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if not ip.is_global:
                raise unsafe_image_url()
