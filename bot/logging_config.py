import logging
import os
import json
from datetime import datetime


class StructuredFormatter(logging.Formatter):
    """
    Outputs structured JSON log lines to file for traceability.
    Console gets clean human-readable format.
    """
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "level": record.levelname,
            "module": record.module,
            "function": record.funcName,
            "message": record.getMessage(),
        }
        # Attach any extra fields passed via logger.info(..., extra={...})
        for key in ("symbol", "side", "order_type", "quantity", "price",
                    "order_id", "status", "error_code"):
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)

        return json.dumps(log_entry)


class HumanFormatter(logging.Formatter):
    """Clean readable format for console warnings/errors only."""
    def format(self, record: logging.LogRecord) -> str:
        return f"{record.levelname}: {record.getMessage()}"


def setup_logger(name: str = "trading_bot") -> logging.Logger:
    os.makedirs("logs", exist_ok=True)
    log_filename = f"logs/trading_bot_{datetime.now().strftime('%Y%m%d')}.log"

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    # --- File Handler: structured JSON, all levels ---
    file_handler = logging.FileHandler(log_filename, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(StructuredFormatter())

    # --- Console Handler: human readable, WARNING+ only ---
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(HumanFormatter())

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger