# Deployment Package

Temperature Bot deployment packages are immutable ZIP files that carry one
tested application wheel together with the exact migrations and operating
system integration files that belong to that revision. A host installs a
package into a new versioned directory; it never updates the active virtual
environment or a Git checkout in place.

This document defines package format version 1. Issue #213 owns release
publication, #214 owns immutable installation, #216 owns the complete
database-safe activation transaction, and #225 owns the initial cron-to-systemd
migration.

## Why ZIP

ZIP was selected over `.tar.gz` for this application bundle because its central
directory makes listing members fast without decompressing the archive, and
because standard Python can create, inspect, and validate it without another
host dependency. Use `unzip -l PACKAGE.zip` or `python -m zipfile -l PACKAGE.zip`
to inspect a package.

ZIP CRCs detect accidental corruption but are not a cryptographic integrity or
authenticity mechanism. The builder therefore adds:

- a `manifest.json` containing the SHA-256, size, mode, and role of every
  payload file;
- a `PACKAGE.zip.sha256` sidecar covering the exact ZIP bytes;
- release provenance/attestation as a publication requirement in #213.

The verifier rejects duplicate names, absolute paths, `..` traversal, backslash
paths, unlisted files, missing files, symlinks, mode mismatches, CRC failures,
and SHA-256 mismatches. The installer writes each verified file itself and does
not call `ZipFile.extractall()`.

## Package name and layout

An ephemeral pull-request build is named from the application version and
source commit:

```text
temperature-bot-deployment-0.11.0-0123456789ab.zip
temperature-bot-deployment-0.11.0-0123456789ab.zip.sha256
```

The ZIP has this layout:

```text
manifest.json
wheel/temperature_bot-<version>-py3-none-any.whl
requirements/runtime.txt
migrations/V*.sql
migrations/R*.sql
configuration/temperature-bot.env.example
configuration/slg1.env.example
configuration/deg1.env.example
systemd/slg1_basistech_net.service
systemd/deg1_basistech_net.service
systemd/slg1_basistech_net.socket
systemd/deg1_basistech_net.socket
systemd/temperature-bot-minute.service
systemd/temperature-bot-minute.timer
systemd/temperature-bot-hourly.service
systemd/temperature-bot-hourly.timer
systemd/temperature-bot-daily.service
systemd/temperature-bot-daily.timer
installer/install_deployment_package.py
documentation/DEPLOYMENT_PACKAGE.md
metadata/VERSION
metadata/pyproject.toml
```

`runtime.txt` is exported from the committed `uv.lock`, without development
dependencies or the local project, and retains distribution hashes. The
application wheel is installed separately with `--no-deps`. This makes the
locked third-party environment and application artifact independently visible.

The migration directory is the complete Flyway history from the same commit,
not only migrations newer than the currently deployed schema. The manifest
records the required Flyway version, Python constraint, exact Git commit, build
time, and whether the source tree was dirty. A future immutable release job
must refuse dirty input; local and ephemeral PR packages retain the flag for
diagnosis.

The example environment files are configuration documentation and are never
copied to the systemd unit directory. The `slg1` and `deg1` examples define
separate private databases and the complete simulator-only policy; deployment
must replace `GIT_COMMIT` with the verified manifest commit. Systemd `.service`
and `.timer` files are
payload, not trusted instructions merely because they are in a ZIP. The
deployment transaction verifies the package before copying units, runs
`systemd-analyze verify`, preserves the previously installed units, and
restores them on pre-commit rollback.

The developer web units run one worker so their in-memory Hubitat simulators
provide deterministic read-after-write behavior. Systemd socket units own the
host-loopback ports and pass their listening descriptors to Gunicorn; the web
processes run with `PrivateNetwork=yes`, so an application regression has no
route to live controller command endpoints. They also retain the systemd IP
allowlist as defense in depth. They do not install or enable scheduled
collection/rules timers. Their shared immutable activation root is
`/opt/temperature-bot-dev`; `/opt/temperature-bot` remains reserved for
production services and scheduled jobs.

## Build and inspect

All project commands go through the Makefile:

```bash
make deployment-package
make deployment-package-verify
make deployment-package-check
```

`deployment-package` builds the wheel, exports locked runtime requirements,
and writes the ZIP and sidecar under `dist/`. `deployment-package-verify`
checks the whole-ZIP sidecar and every manifest entry. The stronger
`deployment-package-check` installs the package into a disposable versioned
root, creates a fresh virtual environment, installs the locked dependencies
and wheel, imports the installed web application and runner outside the source
checkout, executes an installed console script after atomic activation, and
checks the systemd inventory. The virtual environment is created as relocatable
so its entry points remain valid when the staging directory is renamed to the
immutable release directory. This requires `uv` 0.10.8 or newer. The check does
not touch `/opt`, `/etc`, systemd, or a real database.

## Installer contract

The current installer is the safe package-verification and immutable-staging
primitive for the future upgrade transaction:

```bash
uv run --locked python -m bin.install_deployment_package \
  dist/temperature-bot-deployment-<version>-<commit>.zip \
  --require-checksum \
  --root /opt/temperature-bot
```

By default it verifies and stages
`/opt/temperature-bot/releases/<version>-<commit>/` but does not change
`current`, copy systemd units, migrate a database, or restart anything.
`--activate` and `--systemd-dir` are explicit primitives used by tests and by
the future transaction after its safety gates pass; they are not a complete
production upgrade command.

An existing trusted release environment runs the installer. First-host
bootstrap remains an operations procedure under #44. A package may carry a
new installer for the next transaction, but the currently trusted verifier
must validate that package before candidate code is executed.

## Upgrade transaction design

The production upgrade command will compose the installer with a durable state
machine. It must record every transition and be safely restartable.

1. **Discover** — select an approved channel/version, enforce hold/pin/failed
   release policy, and download the ZIP plus provenance with bounded size and
   time limits.
2. **Verify** — validate release provenance, outer SHA-256, safe ZIP structure,
   manifest inventory, every payload SHA-256, version/tag agreement, Python,
   Flyway, disk space, configuration, and target instance identity.
3. **Stage** — install into a new immutable release directory and virtual
   environment. Run package-resource and read-only application preflight checks
   without changing the active release.
4. **Lock** — acquire the host deployment lock. Record the active release,
   installed unit bytes, unit enabled/active states, database identity/schema,
   and intended rollback paths.
5. **Quiesce** — stop writer timers first so no new jobs start. Then wait for or
   stop their oneshot services and stop Gunicorn/other database writers. Verify
   with systemd state and open-file/process checks that no writer remains.
6. **Snapshot** — create a consistent SQLite snapshot with the backup API or
   `VACUUM INTO`; never raw-copy a live WAL database. Run `PRAGMA quick_check`
   and record size, SHA-256, Flyway schema, release, and timestamp.
7. **Migrate** — use the candidate package's complete migration directory and
   manifest-pinned Flyway version. Validate, migrate, validate again, and record
   before/after schema versions.
8. **Prepare activation** — back up installed systemd units, copy candidate
   units atomically, run `systemd-analyze verify`, execute `daemon-reload`, and
   atomically point `current` at the candidate.
9. **Prove health** — start only the web candidate, then run bounded loopback
   and public health/root/API checks. Scheduled writers remain stopped.
10. **Commit** — after health succeeds, start the writer timers and verify their
    schedules. Exposure plus writer resumption is the commit point.
11. **Report** — persist structured results and email the configured
    maintainers with release, commit, backup, migration, unit, smoke, duration,
    and disposition evidence.

Before the commit point, any failure restores the previous database snapshot,
release symlink, systemd units, daemon state, and prior service/timer states.
After the commit point, automatic database restoration is forbidden because it
could discard new writes. The transaction enters maintenance/failed state,
preserves all evidence, notifies maintainers, and requires an explicit forward
fix or operator-approved restore.

Power loss and process termination are ordinary state-machine resumptions, not
special cases. Durable checkpoints distinguish downloaded, verified, staged,
quiesced, snapshotted, migrated, activated, committed, rolled back, and failed
states. Fault-injection tests under #216 must exercise every boundary.

## Pull-request artifacts

Every pull request builds and checks one deployment ZIP on Ubuntu, then uploads
the ZIP and its `.sha256` sidecar as a GitHub Actions artifact. These packages
are test evidence, not releases and not authorized for production deployment.
They expire after five days. Stable release assets will instead be published
and retained through the immutable GitHub Release workflow tracked by #213.
