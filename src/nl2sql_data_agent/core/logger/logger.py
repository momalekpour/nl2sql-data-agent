from loguru import logger
import json
import sys
from threading import Lock


class Logger:
    _configured = False
    _config_lock = Lock()

    def __init__(self, name=__name__, level="DEBUG"):
        with Logger._config_lock:
            if not Logger._configured:
                logger.remove()
                logger.add(
                    sys.stdout,
                    level=str(level).upper(),
                    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{module}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <level>{message}</level>",
                    colorize=True,
                )
                Logger._configured = True
        self.logger = logger.bind(logger_name=name)

    def log(self, level, action, details=None):
        message = {"action": action}
        if details is not None:
            if isinstance(details, dict):
                message.update(details)
            else:
                message["details"] = details

        normalized_level = str(level).strip().lower()
        level_map = {
            "debug": self.logger.opt(depth=1).debug,
            "info": self.logger.opt(depth=1).info,
            "warning": self.logger.opt(depth=1).warning,
            "error": self.logger.opt(depth=1).error,
            "critical": self.logger.opt(depth=1).critical,
        }

        if normalized_level not in level_map:
            message["invalid_level"] = level
            normalized_level = "warning"

        message_str = json.dumps(message, default=str)
        level_map[normalized_level](message_str)
