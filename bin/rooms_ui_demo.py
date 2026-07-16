#!/usr/bin/env python3
"""Run the room matrix UI against disposable synthetic data."""

import argparse
from pathlib import Path

from bin.render_web_ui_pages import (
    configure_environment,
    create_database,
    install_offline_integrations,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    args.database.parent.mkdir(parents=True, exist_ok=True)
    args.database.unlink(missing_ok=True)
    configure_environment(args.database)
    create_database(args.database)
    install_offline_integrations()

    from app.main import app

    print(f"Room matrix demo: http://{args.host}:{args.port}/")
    app.run(host=args.host, port=args.port, debug=False, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
