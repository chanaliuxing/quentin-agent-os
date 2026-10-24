import json
import structlog
from datetime import datetime
from pathlib import Path
from app.config import settings


def setup_logging():
    settings.ensure_dirs()

    processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


def log_event(event_type: str, **kwargs):
    logger = get_logger("autoloop")

    from opentelemetry import trace
    span = trace.get_current_span()
    span_context = span.get_span_context()
    trace_id = span_context.trace_id
    span_id = span_context.span_id

    log_data = {
        "event_type": event_type,
        "timestamp": datetime.now().isoformat(),
        "trace_id": format(trace_id, "032x") if trace_id else None,
        "span_id": format(span_id, "016x") if span_id else None,
        **kwargs,
    }

    if settings.log_format == "json":
        log_file = settings.logs_dir / f"{event_type}_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, "a") as f:
            f.write(json.dumps(log_data) + "\n")

    logger.info(event_type, **log_data)
