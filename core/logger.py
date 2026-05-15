"""
Structured JSON logger. Each agent logs to logs/{job_id}.json + console.
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import colorlog

from core.config import LOGS_DIR


def get_logger(agent_name: str, job_id: str = "system") -> logging.Logger:
    logger = logging.getLogger(f"{agent_name}:{job_id}")
    if logger.handlers:
        return logger  # already configured

    logger.setLevel(logging.DEBUG)

    # ── Console handler (colored) ──────────────────────────────────────────
    console = colorlog.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s [%(name)s] %(levelname)s%(reset)s — %(message)s",
        datefmt="%H:%M:%S",
        log_colors={
            "DEBUG":    "cyan",
            "INFO":     "green",
            "WARNING":  "yellow",
            "ERROR":    "red",
            "CRITICAL": "red,bg_white",
        }
    ))
    logger.addHandler(console)

    # ── File handler (JSON lines) ──────────────────────────────────────────
    log_file = LOGS_DIR / f"{job_id}.jsonl"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(_JsonFormatter(agent_name))
    logger.addHandler(file_handler)

    return logger


class _JsonFormatter(logging.Formatter):
    def __init__(self, agent_name: str):
        super().__init__()
        self.agent_name = agent_name

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "ts":       datetime.utcnow().isoformat(),
            "agent":    self.agent_name,
            "level":    record.levelname,
            "msg":      record.getMessage(),
            "file":     f"{record.filename}:{record.lineno}",
        })
