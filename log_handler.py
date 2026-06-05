"""Irrigation Planner log handler — in-memory circular buffer + rotating file."""
from __future__ import annotations

import logging
import logging.handlers
from collections import deque

MAX_BUFFER_ENTRIES = 150
LOG_FILE_MAX_BYTES = 500_000   # 500 KB per file
LOG_FILE_BACKUP_COUNT = 2      # keeps .log + .log.1 + .log.2

# Both the planner and the irrigation controller logs are captured.
CAPTURED_LOGGERS = [
    "custom_components.irrigation_planner",
    "custom_components.irrigationprogram",
]

_LOG_FORMAT = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class IrrigationLogBuffer(logging.Handler):
    """Captures log records into an in-memory buffer and a rotating file."""

    def __init__(self, log_file_path: str) -> None:
        super().__init__(level=logging.DEBUG)
        self._log_file_path = log_file_path
        self._buffer: deque[str] = deque(maxlen=MAX_BUFFER_ENTRIES)

        formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)
        self.setFormatter(formatter)

        self._file_handler = logging.handlers.RotatingFileHandler(
            log_file_path,
            maxBytes=LOG_FILE_MAX_BYTES,
            backupCount=LOG_FILE_BACKUP_COUNT,
            encoding="utf-8",
        )
        self._file_handler.setFormatter(formatter)

    def emit(self, record: logging.LogRecord) -> None:
        """Write record to in-memory buffer and rotating file."""
        try:
            msg = self.format(record)
            self._buffer.append(msg)
            self._file_handler.emit(record)
        except Exception:
            self.handleError(record)

    def prepopulate_from_file(self) -> None:
        """Seed the in-memory buffer from the existing log file on startup.

        Called via executor so file I/O doesn't block the event loop.
        """
        try:
            with open(self._log_file_path, encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
            for line in lines[-MAX_BUFFER_ENTRIES:]:
                self._buffer.append(line.rstrip())
        except (FileNotFoundError, OSError):
            pass  # No previous log file — start fresh

    @property
    def log_file_path(self) -> str:
        return self._log_file_path

    def get_recent_logs(self) -> list[str]:
        """Return log entries oldest-first."""
        return list(self._buffer)

    def close(self) -> None:
        self._file_handler.close()
        super().close()


def attach_log_handler(handler: IrrigationLogBuffer) -> None:
    """Add handler to all captured loggers and ensure INFO records flow through.

    HA's default root logger is WARNING, so custom component loggers inherit
    that level (NOTSET → WARNING) and silently drop INFO/DEBUG records before
    any handler sees them.  We set INFO explicitly so our handler receives
    meaningful operational messages without touching the root logger.
    """
    for name in CAPTURED_LOGGERS:
        logger = logging.getLogger(name)
        if logger.level == logging.NOTSET:
            logger.setLevel(logging.INFO)
        logger.addHandler(handler)


def detach_log_handler(handler: IrrigationLogBuffer) -> None:
    """Remove handler and restore loggers to inherited level."""
    for name in CAPTURED_LOGGERS:
        logger = logging.getLogger(name)
        logger.removeHandler(handler)
        # Restore inheritance from root — only safe if we were the ones who set
        # the level (i.e. it was NOTSET before we changed it to INFO).
        if logger.level == logging.INFO and not logger.handlers:
            logger.setLevel(logging.NOTSET)
