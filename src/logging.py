"""Logging configuration. Call configure_logging() once in main()."""

import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler


def configure_logging(level: int = logging.INFO) -> None:
    """Set up structured logging to stdout and file."""
    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers on repeated calls
    if root.handlers:
        return

    formatter = logging.Formatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    log_dir = "/app/logs"
    os.makedirs(log_dir, exist_ok=True)
    file_handler = TimedRotatingFileHandler(
        os.path.join(log_dir, "viewstats.log"),
        when="MIDNIGHT",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
