import logging
import json
import time
from typing import Dict, Any


def get_logger(logfile_path: str = None) -> logging.Logger:
    """Return a structured JSON-like logger that writes to a file and stderr."""
    logger = logging.getLogger("ranking_v2")
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        formatter = logging.Formatter("%(message)s")

        sh = logging.StreamHandler()
        sh.setLevel(logging.INFO)
        sh.setFormatter(formatter)
        logger.addHandler(sh)

        if logfile_path:
            fh = logging.FileHandler(logfile_path, mode="a", encoding="utf-8")
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(formatter)
            logger.addHandler(fh)

    return logger


def log_structured(logger: logging.Logger, level: int, msg: str, **kwargs: Any) -> None:
    """Emit a one-line JSON-ish structured log. Sensitive fields should be masked by caller."""
    payload: Dict[str, Any] = {
        "ts": int(time.time() * 1000),
        "msg": msg,
    }
    payload.update(kwargs)
    logger.log(level, json.dumps(payload, ensure_ascii=False))


def mask_sensitive(data: Dict[str, Any], fields=("name",)) -> Dict[str, Any]:
    out = {}
    for k, v in data.items():
        if k in fields and v is not None:
            if isinstance(v, str) and len(v) > 1:
                out[k] = v[0] + "*" * (len(v) - 1)
            else:
                out[k] = "*"
        else:
            out[k] = v
    return out
