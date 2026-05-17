"""Logging configuration"""
import logging
import sys
from pathlib import Path

try:
    import colorlog
except ImportError:
    colorlog = None


def get_logger(name: str) -> logging.Logger:
    """Get a configured logger."""
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # Console handler
    if colorlog:
        handler = colorlog.StreamHandler(sys.stdout)
        handler.setFormatter(
            colorlog.ColoredFormatter(
                "%(log_color)s%(asctime)s [%(levelname).1s] %(name)s: %(message)s",
                datefmt="%H:%M:%S",
                log_colors={
                    "DEBUG": "cyan",
                    "INFO": "green",
                    "WARNING": "yellow",
                    "ERROR": "red",
                    "CRITICAL": "red,bg_white",
                },
            )
        )
    else:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname).1s] %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )

    logger.addHandler(handler)

    # Always persist logs to file (useful for packaged .exe troubleshooting).
    try:
        if getattr(sys, "frozen", False):
            log_dir = Path(sys.executable).resolve().parent
        else:
            log_dir = Path(__file__).resolve().parent.parent
        file_handler = logging.FileHandler(log_dir / "agent.log", encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(file_handler)
    except Exception:
        pass

    logger.propagate = False
    return logger
