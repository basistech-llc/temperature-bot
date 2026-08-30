"""Tests for the vendored logging helper."""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from app import clogging


def _run_python(source: str, *args: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", source, *(str(arg) for arg in args)],
        check=True,
        capture_output=True,
        text=True,
    )


def test_add_argument_preserves_logging_cli_contract() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--logfilename")
    clogging.add_argument(parser, loglevel_default="WARNING")

    defaults = parser.parse_args([])
    explicit = parser.parse_args(["--loglevel", "DEBUG", "--logfilename", "run.log"])

    assert defaults.loglevel == "WARNING"
    assert defaults.logfilename is None
    assert explicit.loglevel == "DEBUG"
    assert explicit.logfilename == "run.log"


def test_max_length_formatter_does_not_mutate_shared_record() -> None:
    record = logging.LogRecord("runner", logging.INFO, __file__, 1, "abcdefghijk", (), None)

    assert clogging.MaxLengthFormatter("%(message)s", max_length=8).format(record) == (
        "abcdefgh..."
    )
    assert record.getMessage() == "abcdefghijk"


def test_syslog_default_address_matches_host_or_fails_clearly() -> None:
    existing = [
        path for path in (clogging.DEVLOG, clogging.DEVLOG_MAC) if Path(path).exists()
    ]

    if existing:
        assert clogging.syslog_default_address() == existing[0]
    else:
        with pytest.raises(RuntimeError, match="Neither .+ nor .+ are present"):
            clogging.syslog_default_address()


def test_setup_writes_requested_log_file(tmp_path: Path) -> None:
    logfile = tmp_path / "runner.log"
    result = _run_python(
        "from app import clogging; import logging, sys; "
        "clogging.setup('INFO', filename=sys.argv[1]); "
        "logging.getLogger('runner').info('runner ready'); logging.shutdown()",
        logfile,
    )

    assert result.stderr == ""
    assert "runner ready" in logfile.read_text(encoding="utf-8")


def test_setup_syslog_uses_real_unix_socket_once() -> None:
    with tempfile.TemporaryDirectory(prefix="tb-syslog-", dir="/tmp") as directory:
        socket_path = Path(directory) / "socket"
        result = _run_python(
            "from app import clogging; import json, logging, socket, sys; "
            "server=socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM); "
            "server.bind(sys.argv[1]); server.settimeout(2); "
            "root=logging.getLogger(); before=len(root.handlers); "
            "clogging.setup_syslog(syslog_address=sys.argv[1], "
            "syslog_format='%(message)s', max_length=8); "
            "clogging.setup_syslog(syslog_address=sys.argv[1]); "
            "root.warning('abcdefghijk'); payload=server.recv(1024); "
            "print(json.dumps({'handlers': len(root.handlers)-before, "
            "'payload': payload.decode()}))",
            socket_path,
        )
        observed = json.loads(result.stdout)

    assert observed["handlers"] == 1
    assert "abcdefgh..." in observed["payload"]
