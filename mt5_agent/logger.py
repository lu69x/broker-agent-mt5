"""Logging configuration"""
import logging
import sys

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
        handler.setFormatter("%(asctime)s [%(levelname).1s] %(name)s: %(message)s")

    logger.addHandler(handler)
    return logger
