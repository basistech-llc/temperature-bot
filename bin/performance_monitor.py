"""One-shot AE-200 DNS, ICMP, and TCP-reject performance probe."""

import argparse
import logging
import os

from app import db
from app import performance_monitoring
from app.util import get_config

logger = logging.getLogger(__name__)


def setup_parser() -> argparse.ArgumentParser:
    """Return the command-line parser for the one-shot probe."""
    parser = argparse.ArgumentParser(
        description="Record independent network measurements to the AE-200."
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="collect one set of probes and exit (required)",
    )
    parser.add_argument("--host", help="AE-200 hostname; defaults to config")
    parser.add_argument(
        "--reject-port",
        type=int,
        default=int(
            os.getenv(
                performance_monitoring.AE200_REJECT_PORT_ENV,
                str(performance_monitoring.DEFAULT_REJECT_PORT),
            )
        ),
        help="TCP port expected to reject connections",
    )
    parser.add_argument("--ping-count", type=int, default=3)
    parser.add_argument("--loglevel", default="INFO")
    return parser


def main() -> int:
    """Collect and persist one set of independent network samples."""
    args = setup_parser().parse_args()
    if not args.once:
        raise SystemExit("--once is required; schedule this command once per minute")
    if not 1 <= args.reject_port <= 65535:
        raise SystemExit("--reject-port must be between 1 and 65535")
    if not 1 <= args.ping_count <= 10:
        raise SystemExit("--ping-count must be between 1 and 10")

    logging.basicConfig(level=args.loglevel.upper())
    db.validate_database_schema_on_startup()
    host = args.host or get_config()["ae200"]["host"]
    samples = performance_monitoring.collect_network_samples(
        host,
        reject_port=args.reject_port,
        ping_count=args.ping_count,
    )
    for sample in samples:
        performance_monitoring.record_sample(sample)
        logger.info(
            "%s %s success=%s outcome=%s total_ms=%.3f",
            sample.sample_type,
            sample.operation,
            sample.success,
            sample.outcome,
            sample.total_ms,
        )
    return 0 if any(sample.success for sample in samples) else 1


if __name__ == "__main__":
    raise SystemExit(main())
