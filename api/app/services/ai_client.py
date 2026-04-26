import asyncio
import logging

import httpx

from app.core.config import settings


logger = logging.getLogger(__name__)


async def analyze_frame(
    image_base64: str,
    include_advanced: bool = False,
    reference_face_image_base64: str | None = None,
) -> dict:
    last_error = None
    max_retries = max(1, settings.ai_http_max_retries)

    async with httpx.AsyncClient(timeout=settings.ai_http_timeout_seconds) as client:
        for attempt in range(1, max_retries + 1):
            try:
                response = await client.post(
                    f"{settings.ai_engine_url}/analyze",
                    json={
                        "image_base64": image_base64,
                        "include_advanced": include_advanced,
                        "reference_face_image_base64": reference_face_image_base64,
                    },
                )
                response.raise_for_status()
                return response.json()
            except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as exc:
                last_error = exc
                should_retry = attempt < max_retries
                if not should_retry:
                    break

                backoff = settings.ai_http_retry_backoff_seconds * (2 ** (attempt - 1))
                await asyncio.sleep(backoff)

    logger.warning("AI engine analyze retry exhausted: %s", last_error)
    raise last_error
