import logging
import sys

import structlog

from app.config import settings


def configure_logging() -> None:

    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    structlog.configure(
        processors=[
            # contextvars can help us bind a request_id once and have every log line in that request automatically carry it
            
            structlog.contextvars.merge_contextvars, #binds requestg ID to all logs to make things logs clearer
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:   #helper that every module will use 
    """Return a logger bound to the given module/component name."""
    return structlog.get_logger(name)


#structlog helps us get logs in json format which is better queryoable