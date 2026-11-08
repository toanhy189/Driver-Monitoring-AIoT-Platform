"""Cau hinh log JSON tap trung va loc thong tin credential khoi message."""

import json
import logging
import logging.config
import re
from contextvars import ContextVar
from datetime import datetime, timezone


# ContextVar giup log va audit trong cung request dung chung correlation ID ma khong doi chu ky ham.
correlation_id_context: ContextVar[str] = ContextVar("correlation_id", default="-")
request_method_context: ContextVar[str] = ContextVar("request_method", default="-")
request_path_context: ContextVar[str] = ContextVar("request_path", default="-")

# Cac mau nay loai credential thuong gap khoi noi dung log truoc khi serialize.
_BEARER_SECRET = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*")
_BASIC_SECRET = re.compile(r"(?i)\bBasic\s+[A-Za-z0-9+/]+=*")
_KEYED_SECRET = re.compile(
    r"""(?i)(?<![A-Za-z0-9])(["']?[A-Za-z0-9_-]*(?:password|passwd|token|secret|authorization|credential|api[_-]?key)[A-Za-z0-9_-]*["']?)(\s*[:=]\s*)("[^"]*"|'[^']*'|[^\s,;}\]]+)"""
)
# Chi cac truong metadata khong nhay cam duoc dua tu LogRecord vao JSON.
_SAFE_FIELDS = {
    "action",
    "device_code",
    "duration_ms",
    "entity_id",
    "entity_type",
    "error_code",
    "method",
    "path",
    "request_id",
    "result",
    "role",
    "status_code",
    "user_id",
}


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Formatter tao schema log thong nhat va redact message truoc khi ghi ra stdout.
        message = record.getMessage()
        message = _BEARER_SECRET.sub("Bearer [REDACTED]", message)
        message = _BASIC_SECRET.sub("Basic [REDACTED]", message)
        message = _KEYED_SECRET.sub(
            lambda match: match.group(1)
            + match.group(2)
            + (match.group(3)[0] + "[REDACTED]" + match.group(3)[0]
               if match.group(3)[0] in {"'", '"'} else "[REDACTED]"),
            message,
        )
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "service": "backend",
            "event": getattr(record, "event", record.name),
            "correlation_id": correlation_id_context.get(),
            "message": message,
        }
        for field in _SAFE_FIELDS:
            value = getattr(record, field, None)
            if isinstance(value, (str, int, float, bool)) or value is None:
                if value is not None:
                    payload[field] = value
        if record.exc_info:
            # Khong ghi exception message/traceback vi co the chua URL hoac credential.
            error = record.exc_info[1]
            payload["error_type"] = type(error).__name__
            payload["error_code"] = type(error).__name__
            candidate = error
            visited = set()
            error_chain = []
            while candidate is not None and id(candidate) not in visited:
                visited.add(id(candidate))
                error_chain.append(type(candidate).__name__)
                sqlstate = getattr(candidate, "sqlstate", None) or getattr(candidate, "pgcode", None)
                if isinstance(sqlstate, str) and re.fullmatch(r"[0-9A-Z]{5}", sqlstate):
                    payload["error_code"] = sqlstate
                    break
                candidate = (
                    getattr(candidate, "orig", None)
                    or getattr(candidate, "__cause__", None)
                    or getattr(candidate, "__context__", None)
                )
            payload["error_chain"] = error_chain
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging() -> None:
    # Dung cung formatter cho logger goc va Uvicorn de Docker nhan tung dong JSON.
    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {"()": "app.core.logging_config.JsonLogFormatter"},
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "json",
                "stream": "ext://sys.stdout",
            },
        },
        "root": {"level": "INFO", "handlers": ["console"]},
        "loggers": {
            "uvicorn": {"level": "INFO", "handlers": ["console"], "propagate": False},
            "uvicorn.error": {"level": "INFO", "handlers": ["console"], "propagate": False},
            "uvicorn.access": {"level": "INFO", "handlers": ["console"], "propagate": False},
        },
    })
