import json
import logging
import traceback

logger = logging.getLogger("archy")


class JsonFormatter(logging.Formatter):
    def format(self, record):
        data = record.msg if isinstance(record.msg, dict) else {"event": "application"}
        return json.dumps({"time": self.formatTime(record), "level": record.levelname, **data})


def configure_logging():
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("sqlalchemy.engine").setLevel(logging.CRITICAL)
    for name in ("httpx", "httpx2", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)


def report_error(error, request_id):
    frames = [
        {"file": frame.filename, "line": frame.lineno, "function": frame.name}
        for frame in traceback.extract_tb(error.__traceback__)
    ]
    logger.error(
        {
            "event": "error",
            "request_id": request_id,
            "error_type": type(error).__name__,
            "frames": frames,
        }
    )
