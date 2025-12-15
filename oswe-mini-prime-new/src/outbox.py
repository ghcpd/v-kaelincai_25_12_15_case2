import asyncio
import logging
from typing import List, Dict, Any

logger = logging.getLogger("outbox")

_outbox: List[Dict[str, Any]] = []

async def push(event: Dict[str, Any]):
    _outbox.append(event)
    logger.info("outbox push", extra={"event_id": event.get("id")})

async def flush():
    # In a real implementation we'd persist & deliver; here we simulate delivery
    ready = list(_outbox)
    _outbox.clear()
    logger.info("outbox flushed", extra={"count": len(ready)})
    return ready

def peek_all():
    return list(_outbox)
