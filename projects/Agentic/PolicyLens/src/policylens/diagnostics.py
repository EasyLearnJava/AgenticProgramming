"""Useful local stack traces without logging exception messages or request bodies."""

import traceback


def log_exception(logger, operation: str, error: Exception):
    # Omit source lines too: a source literal or SDK expression may contain data.
    frames = "\n".join(f'  File "{frame.filename}", line {frame.lineno}, in {frame.name}'
                       for frame in traceback.extract_tb(error.__traceback__))
    logger.error("%s (%s). Traceback:\n%s", operation, type(error).__name__, frames)

