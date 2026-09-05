#!/usr/bin/env python3
"""Download and verify a production SQLite snapshot."""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
from pathlib import Path

import requests
from pydantic import BaseModel, Field, ValidationError

CODE_KEY = "code"
ERROR_KEY = "error"
CONFLICT_CODE = "conflict"
CONTENT_TYPE = "application/vnd.sqlite3"
CONTENT_TYPE_HEADER = "Content-Type"
SIZE_HEADER = "X-Database-Size"
SHA256_HEADER = "X-Database-SHA256"
CHUNK_SIZE = 1024 * 1024


class SnapshotMetadata(BaseModel):
    """Validated metadata supplied with a snapshot response."""

    size: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def _error_payload(response: requests.Response) -> dict[str, object] | None:
    content_type = response.headers.get(CONTENT_TYPE_HEADER, "").partition(";")[0]
    if content_type != "application/json":
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def _is_conflict(response: requests.Response) -> bool:
    if response.status_code == 409:
        return True
    payload = _error_payload(response)
    return payload is not None and payload.get(CODE_KEY) == CONFLICT_CODE


def _response_error(response: requests.Response) -> str:
    payload = _error_payload(response)
    if payload is not None and isinstance(payload.get(ERROR_KEY), str):
        return f"HTTP {response.status_code}: {payload[ERROR_KEY]}"
    return f"HTTP {response.status_code}: {response.reason}"


def _metadata(response: requests.Response) -> SnapshotMetadata:
    content_type = response.headers.get(CONTENT_TYPE_HEADER, "").partition(";")[0]
    if content_type != CONTENT_TYPE:
        raise RuntimeError(f"snapshot response has unexpected content type {content_type!r}")
    try:
        return SnapshotMetadata(
            size=int(response.headers.get(SIZE_HEADER, "")),
            sha256=response.headers.get(SHA256_HEADER, "").lower(),
        )
    except (ValueError, ValidationError) as error:
        raise RuntimeError("snapshot response has invalid size or SHA-256 metadata") from error


def _progress(downloaded: int, total: int, previous_percent: int) -> int:
    width = 30
    filled = min(width, downloaded * width // total)
    percent = min(100, downloaded * 100 // total)
    if percent == previous_percent and downloaded != total:
        return previous_percent
    progress_bar = "#" * filled + "-" * (width - filled)
    sys.stderr.write(
        f"\rDownloading snapshot [{progress_bar}] {percent:3d}% "
        f"({downloaded:,}/{total:,} bytes)"
    )
    sys.stderr.flush()
    return percent


def download_snapshot(
    url: str,
    output: Path,
    *,
    retry_delay: float = 5,
    wait_timeout: float = 900,
    request_timeout: float = 600,
) -> SnapshotMetadata:
    """Wait for, download, and verify one snapshot."""
    started = time.monotonic()
    while True:
        print(
            "Waiting for the server to prepare a consistent SQLite snapshot; "
            "download progress will appear when it is ready.",
            flush=True,
        )
        response = requests.get(
            url,
            stream=True,
            timeout=(10, request_timeout),
        )
        if _is_conflict(response):
            response.close()
            remaining = wait_timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise RuntimeError("timed out waiting for the current snapshot")
            delay = min(retry_delay, remaining)
            print(
                "A database snapshot is already in progress; "
                f"waiting {delay:g} seconds before retrying.",
                flush=True,
            )
            time.sleep(delay)
            continue
        if response.status_code != 200:
            error = _response_error(response)
            response.close()
            raise RuntimeError(error)
        break

    try:
        metadata = _metadata(response)
        digest = hashlib.sha256()
        downloaded = 0
        progress_percent = _progress(downloaded, metadata.size, -1)
        with output.open("wb") as stream:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if not chunk:
                    continue
                stream.write(chunk)
                digest.update(chunk)
                downloaded += len(chunk)
                progress_percent = _progress(
                    downloaded, metadata.size, progress_percent
                )
        sys.stderr.write("\n")
        if downloaded != metadata.size:
            raise RuntimeError(
                f"snapshot size mismatch: expected {metadata.size}, got {downloaded}"
            )
        if digest.hexdigest() != metadata.sha256:
            raise RuntimeError("snapshot SHA-256 does not match the response header")
        return metadata
    except Exception:
        output.unlink(missing_ok=True)
        raise
    finally:
        response.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("output", type=Path)
    parser.add_argument("--retry-delay", type=float, default=5)
    parser.add_argument("--wait-timeout", type=float, default=900)
    parser.add_argument("--request-timeout", type=float, default=600)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if min(args.retry_delay, args.wait_timeout, args.request_timeout) < 0:
        raise SystemExit("timeouts and retry delay must not be negative")
    try:
        download_snapshot(
            args.url,
            args.output,
            retry_delay=args.retry_delay,
            wait_timeout=args.wait_timeout,
            request_timeout=args.request_timeout,
        )
    except (OSError, requests.RequestException, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
