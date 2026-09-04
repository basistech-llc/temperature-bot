# Clean macOS setup

This is the shortest safe path from a clean Mac to the local simulator. It does
not grant access to live hardware and does not copy production secrets. The
simulator target selects the checked-in test configuration automatically.

## Tools that must be present

- Git and Apple Command Line Tools (including `make`)
- Homebrew
- Python 3.12
- Node.js 24 and npm
- Flyway 12.8.1
- SQLite 3, `curl`, and `shasum`

The project setup target manages pipx, the pinned uv version, Python packages,
and browser-test dependencies. The external tools above must already be
available; this document deliberately does not prescribe how to install them.

## Numbered setup

1. Clone the repository and enter it:

   ```bash
   git clone https://github.com/basistech-llc/temperature-bot.git
   cd temperature-bot
   ```

2. Verify the external tools, then install the project environment:

   ```bash
   git --version
   make --version
   python3.12 --version
   node --version
   flyway -v
   sqlite3 --version
   make install-macos
   ```

3. Choose one database:

   ```bash
   make make-dev-db    # empty schema; no historical devices or readings
   ```

   Or, while connected to the company VPN:

   ```bash
   make fetch-dev-db   # verified production snapshot; no SSH login
   ```

   An existing local database is moved to a timestamped directory under
   `var/db/backups` before the replacement is downloaded and migrated.

4. Start the safe simulator and open <http://localhost:8000>:

   ```bash
   make local-dev
   ```

5. Before proposing a change, run:

   ```bash
   make check
   make test
   ```

## Why a clean simulator can show no devices

Simulator mode replaces calls to AE-200, Hubitat, Airthings, and AQICN; it does
not invent database history. Pages and the **Database Devices** section of
`/all_devices` are empty after `make make-dev-db` because that database contains
zero device rows. Use `make fetch-dev-db` for a realistic read-only copy of
production history. The lower AE-200 and Hubitat debug sections may still show
the simulator's canned API devices.

Do not use `make local-dev-live` merely to populate the UI. Live mode requires
separately managed configuration, the VPN, and deliberate permission to reach
real building hardware.
