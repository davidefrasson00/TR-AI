"""
Structured Logging Module for TR-AI.
Ensures every trading decision, filter, rejection, and order is logged with
full contextual rationale, measured values, and applied thresholds.
"""

import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, Optional

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
DEFAULT_LOG_FILE = os.path.join(LOG_DIR, "tr_ai_decisions.log")


class DecisionLogger:
    """Specialized logger for recording strategy and risk decisions."""

    def __init__(self, name: str = "TR-AI", log_file: str = DEFAULT_LOG_FILE):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)

        # Avoid duplicate handlers if already configured
        if not self.logger.handlers:
            # Console handler
            c_handler = logging.StreamHandler(sys.stdout)
            c_format = logging.Formatter(
                "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
            )
            c_handler.setFormatter(c_format)
            self.logger.addHandler(c_handler)

            # File handler
            f_handler = logging.FileHandler(log_file, encoding="utf-8")
            f_format = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s"
            )
            f_handler.setFormatter(f_format)
            self.logger.addHandler(f_handler)

    def log_decision(
        self,
        event_type: str,
        symbol: str,
        action: str,
        reason: str,
        details: Optional[Dict[str, Any]] = None,
        level: int = logging.INFO
    ) -> None:
        """
        Records a structured decision event with all relevant parameters.
        """
        record = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event_type": event_type,
            "symbol": symbol,
            "action": action,
            "reason": reason,
            "details": details or {}
        }
        msg = f"[{event_type}] {symbol} -> {action}: {reason} | details={json.dumps(details or {})}"
        self.logger.log(level, msg)

    def info(self, msg: str) -> None:
        self.logger.info(msg)

    def warning(self, msg: str) -> None:
        self.logger.warning(msg)

    def error(self, msg: str) -> None:
        self.logger.error(msg)


# Global singleton instance
decision_logger = DecisionLogger()
