"""Small logging helpers used by the scheduled runner.

Derived from ``ctools/clogging.py`` at commit
7f4a3c0c251104007b63383d215f54a7cff31160. The source is a work of the
United States government and is also dedicated worldwide under CC0 1.0.
"""

from __future__ import annotations

import argparse
import datetime
import logging
import logging.handlers
import os
import socket
from dataclasses import dataclass
from typing import Literal

DEVLOG = "/dev/log"
DEVLOG_MAC = "/var/run/syslog"
YEAR = str(datetime.datetime.now().year)
SYSLOG_FORMAT = "%(filename)s:%(lineno)d (%(funcName)s) %(message)s"
LOG_FORMAT = "%(asctime)s " + SYSLOG_FORMAT
MAX_LENGTH = 1000


@dataclass
class _LoggingState:
    added_syslog: bool = False
    configured_logging: bool = False


_STATE = _LoggingState()


def add_argument(
    parser: argparse.ArgumentParser, *, loglevel_default: str = "INFO"
) -> None:
    """Add the runner's logging arguments to an argument parser."""
    parser.add_argument(
        "--loglevel",
        help="Set logging level",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        default=loglevel_default,
    )
    try:
        parser.add_argument("--logfilename", help="output filename for logfile")
    except argparse.ArgumentError:
        pass


def syslog_default_address() -> str:
    """Return the local Unix syslog socket."""
    if os.path.exists(DEVLOG):
        return DEVLOG
    if os.path.exists(DEVLOG_MAC):
        return DEVLOG_MAC
    raise RuntimeError(f"Neither {DEVLOG} nor {DEVLOG_MAC} are present.")


class MaxLengthFormatter(logging.Formatter):
    """Truncate oversized messages without mutating the shared log record."""

    def __init__(
        self,
        fmt: str | None = None,
        datefmt: str | None = None,
        style: Literal["%", "{", "$"] = "%",
        max_length: int = 100,
    ) -> None:
        super().__init__(fmt, datefmt, style)
        self.max_length = max_length

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        if len(message) <= self.max_length:
            return super().format(record)
        original_message = record.msg
        original_args = record.args
        record.msg = message[: self.max_length] + "..."
        record.args = ()
        try:
            return super().format(record)
        finally:
            record.msg = original_message
            record.args = original_args


def setup_syslog(
    facility: int = logging.handlers.SysLogHandler.LOG_LOCAL1,
    syslog_address: str | tuple[str, int] | None = None,
    syslog_format: str = YEAR + " " + SYSLOG_FORMAT,
    use_tcp: bool = False,
    max_length: int = MAX_LENGTH,
) -> None:
    """Install one root syslog handler."""
    if _STATE.added_syslog:
        return

    if use_tcp:
        address = syslog_address or ("localhost", 514)
        socktype = socket.SOCK_STREAM
        syslog_format += "\n"
        append_nul = False
    else:
        address = syslog_address or syslog_default_address()
        socktype = socket.SOCK_DGRAM
        append_nul = True

    handler = logging.handlers.SysLogHandler(
        address=address, facility=facility, socktype=socktype
    )
    handler.append_nul = append_nul
    handler.setFormatter(MaxLengthFormatter(syslog_format, max_length=max_length))
    logging.getLogger().addHandler(handler)
    _STATE.added_syslog = True


def setup(  # pylint: disable=too-many-arguments
    level: str | int = "INFO",
    *,
    syslog: bool = False,
    syslog_address: str | tuple[str, int] | None = None,
    filename: str | None = None,
    facility: int = logging.handlers.SysLogHandler.LOG_LOCAL1,
    log_format: str = LOG_FORMAT,
    syslog_format: str = SYSLOG_FORMAT,
) -> None:
    """Configure root logging once and optionally add syslog output."""
    loglevel = level if isinstance(level, int) else logging.getLevelNamesMapping()[level]
    root = logging.getLogger()
    if not _STATE.configured_logging:
        if root.hasHandlers():
            current_level = root.getEffectiveLevel()
            if current_level == logging.NOTSET or loglevel < current_level:
                root.setLevel(loglevel)
        else:
            logging.basicConfig(filename=filename, format=log_format, level=loglevel)
        _STATE.configured_logging = True

    if syslog:
        setup_syslog(
            facility=facility,
            syslog_address=syslog_address,
            syslog_format=syslog_format,
        )
