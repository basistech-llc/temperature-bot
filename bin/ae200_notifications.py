"""Persistent collector for unsolicited AE-200 notifyRequest messages."""

from __future__ import annotations

import argparse
import asyncio
import html
import logging
import os
import random
import sqlite3
import string
import time
import xml.etree.ElementTree as ET

import websockets
from websockets.exceptions import WebSocketException
from websockets.extensions import permessage_deflate
from websockets.typing import Origin

from app import ae200, ae200_notifications, db
from app.util import get_config

logger = logging.getLogger(__name__)
AE200_USER_ENV = "AE200_NOTIFICATION_USER"
AE200_PASSWORD_ENV = "AE200_NOTIFICATION_PASSWORD"
AE200_RETENTION_DAYS_ENV = "AE200_NOTIFICATION_RETENTION_DAYS"
INITIAL_RECONNECT_SECONDS = 1
MAX_RECONNECT_SECONDS = 60
CLEANUP_INTERVAL_SECONDS = 3600


def _password_key() -> str:
    return f"{random.SystemRandom().randint(0, 9999):04d}{random.SystemRandom().randint(1, 4)}"


def _code_table() -> dict[int, str]:
    characters = string.ascii_lowercase + string.ascii_uppercase + string.digits
    return {index + 1: character for index, character in enumerate(characters)}


def encrypt_password(password: str, key: str) -> str:
    """Apply the substitution cipher used by the AE-200 web interface."""
    table = _code_table()
    reverse = {character: index for index, character in table.items()}
    if any(character not in reverse for character in password):
        raise ValueError("AE-200 notification password must be alphanumeric")
    insertion = int(key[4])
    delta = abs(
        (int(key[0]) + int(key[1])) % 10
        - (int(key[2]) + int(key[3])) % 10
    )
    padding = "".join(
        random.SystemRandom().choice(string.ascii_lowercase) for _ in range(delta)
    )
    previous = 0
    encoded = ""
    for character in password:
        shifted = (reverse[character] + delta + previous) % 62 or 62
        previous = shifted
        encoded += table[shifted]
    return encoded[: insertion - 1] + padding + encoded[insertion - 1 :]


def authentication_payload(user: str, password: str) -> str:
    """Build the in-band AdvancedWebServlet authentication request."""
    key = _password_key()
    encrypted = encrypt_password(password, key)
    return (
        "POST /servlet/AdvancedWebServlet HTTP/1.1\r\n\r\n"
        '<?xml version="1.0" encoding="UTF-8" ?>\r\n'
        "<Packet><Command>getRequest</Command><DatabaseManager>"
        f'<WebUserAuth User="{html.escape(user, quote=True)}" '
        f'Password="{encrypted}" PasswordKey="{key}" '
        'UserCategory="*" UserName="*" />'
        "</DatabaseManager></Packet>"
    )


def validate_authentication_response(raw: str) -> None:
    """Reject authentication responses without a usable user category."""
    xml_start = raw.find("<?xml")
    root = ET.fromstring(raw[xml_start:] if xml_start >= 0 else raw)
    if root.findtext("./Command") != "getResponse":
        raise ConnectionError("AE-200 authentication returned no getResponse")
    auth = root.find("./DatabaseManager/WebUserAuth")
    category = auth.get("UserCategory", "") if auth is not None else ""
    if not category or category.lower() == "none":
        raise ConnectionError("AE-200 notification authentication failed")


async def collect_notifications(
    host: str,
    user: str,
    password: str,
    *,
    stop_after: int | None = None,
    retention_days: int = ae200_notifications.DEFAULT_RETENTION_DAYS,
) -> int:
    """Collect and persist notifications until disconnected or bounded for testing."""
    count = 0
    next_cleanup = 0.0
    async with websockets.connect(
        f"ws://{host}/b_xmlproc/",
        extensions=[permessage_deflate.ClientPerMessageDeflateFactory()],
        origin=Origin(f"http://{host}"),
        subprotocols=[ae200.B_XMLPROC_SUBPROTOCOL],
    ) as websocket:
        await websocket.send(authentication_payload(user, password))
        auth_response = await asyncio.wait_for(websocket.recv(), timeout=10)
        if not isinstance(auth_response, str):
            raise ConnectionError("AE-200 authentication returned a binary frame")
        validate_authentication_response(auth_response)
        async for raw in websocket:
            if not isinstance(raw, str):
                logger.warning("Ignoring non-text AE-200 notification frame")
                continue
            try:
                events = ae200_notifications.parse_notification_frame(raw)
            except (ValueError, ET.ParseError) as error:
                logger.warning("Ignoring unexpected AE-200 frame: %s", error)
                continue
            if events:
                try:
                    with db.get_db_connection() as conn:
                        count += ae200_notifications.insert_notifications(conn, events)
                        now = time.monotonic()
                        if now >= next_cleanup:
                            deleted = ae200_notifications.delete_expired(
                                conn, retention_days=retention_days
                            )
                            next_cleanup = now + CLEANUP_INTERVAL_SECONDS
                            if deleted:
                                logger.info(
                                    "Deleted %d expired AE-200 observations", deleted
                                )
                        conn.commit()
                    logger.info("Recorded %d AE-200 observations", len(events))
                except sqlite3.Error as error:
                    logger.error("Could not record AE-200 observations: %s", error)
            if stop_after is not None and count >= stop_after:
                return count
    return count


async def run_forever(
    host: str, user: str, password: str, *, retention_days: int
) -> None:
    """Reconnect forever with bounded exponential backoff."""
    delay = INITIAL_RECONNECT_SECONDS
    while True:
        try:
            observed = await collect_notifications(
                host, user, password, retention_days=retention_days
            )
            if observed:
                delay = INITIAL_RECONNECT_SECONDS
        except (
            ConnectionError,
            OSError,
            TimeoutError,
            ValueError,
            ET.ParseError,
            WebSocketException,
        ) as error:
            logger.error("AE-200 notification connection failed: %s", error)
        await asyncio.sleep(delay)
        delay = min(delay * 2, MAX_RECONNECT_SECONDS)


def setup_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", help="AE-200 hostname; defaults to config")
    parser.add_argument("--once", action="store_true", help="exit after one observation")
    parser.add_argument("--loglevel", default="INFO")
    return parser


def main() -> int:
    args = setup_parser().parse_args()
    logging.basicConfig(level=args.loglevel.upper())
    db.validate_database_schema_on_startup()
    host = args.host or get_config()["ae200"]["host"]
    user = os.getenv(AE200_USER_ENV, "administrator")
    password = os.getenv(AE200_PASSWORD_ENV, "")
    retention_days = int(
        os.getenv(
            AE200_RETENTION_DAYS_ENV,
            str(ae200_notifications.DEFAULT_RETENTION_DAYS),
        )
    )
    if retention_days < 1:
        raise ValueError(f"{AE200_RETENTION_DAYS_ENV} must be at least 1")
    started = time.monotonic()
    if args.once:
        asyncio.run(
            collect_notifications(
                host,
                user,
                password,
                stop_after=1,
                retention_days=retention_days,
            )
        )
        logger.info("Collected first notification in %.3fs", time.monotonic() - started)
    else:
        asyncio.run(
            run_forever(host, user, password, retention_days=retention_days)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
