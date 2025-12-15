import os
import asyncio
import httpx
import logging
from typing import Any, Dict, Optional

CLIENT_TIMEOUT = float(os.getenv("LEGACY_TIMEOUT", "3.0"))
MAX_RETRIES = int(os.getenv("LEGACY_MAX_RETRIES", "3"))
BASE_URL = os.getenv("LEGACY_BASE_URL", "http://localhost:8001")

logger = logging.getLogger("legacy_client")

async def schedule_legacy(payload: Dict[str, Any], request_id: Optional[str] = None, mode: Optional[str] = None) -> Dict[str, Any]:
    """Call the legacy scheduling endpoint with retry+backoff and timeout.

    mode allows tests to request immediate/pending/delayed behavior.
    """
    backoff = 0.5
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=CLIENT_TIMEOUT) as client:
                params = {"mode": mode} if mode else None
                resp = await client.post(f"{BASE_URL}/legacy/schedule", json=payload, params=params)
                resp.raise_for_status()
                logger.info("legacy call success", extra={"request_id": request_id, "status_code": resp.status_code})
                return resp.json()
        except (httpx.RequestError, httpx.HTTPStatusError) as ex:
            logger.warning("legacy call attempt failed", extra={"attempt": attempt, "err": str(ex), "request_id": request_id})
            if attempt < MAX_RETRIES:
                await asyncio.sleep(backoff)
                backoff *= 2
                continue
            logger.error("legacy call final failure", extra={"request_id": request_id})
            raise
