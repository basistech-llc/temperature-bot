# Deployment Specification

Temperature Bot deployment packages are endpoint-neutral immutable ZIP files.
They carry one tested application wheel, its locked dependencies, migrations,
and reviewed host-configuration references. A host installs the application
into a new versioned directory; it never updates the active virtual environment
or a Git checkout in place.

Application release activation and host configuration are separate change
planes. The package installer never writes `/etc`, installs systemd or nginx
files, runs `systemctl`, or changes unit enablement. This is intentional: one
artifact can be installed under production, staging, or the shared developer
root, while each endpoint retains explicitly selected service, socket, timer,
environment, routing, identity, and database configuration.

This document defines package format version 1. Issue #213 owns release
publication, #214 owns immutable installation, #216 owns the complete
database-safe activation transaction, and #225 owns the initial cron-to-systemd
migration.

## Endpoint and host-configuration contract

All current public endpoints run on the same physical host, but they are not
interchangeable deployment targets:

| Endpoint | Application root | Web unit and listener | Scheduled units | Environment and database |
|---|---|---|---|---|
| `air.basistech.net` | `/opt/temperature-bot` | `air_basistech_net.service`, `127.0.0.1:8100` | `temperature-bot-{minute,hourly,daily}.{service,timer}`; separate notification and performance-probe units | `/etc/temperature-bot/runtime.env`; `/var/db/temperature_bot/temperature-bot.db` |
| `air-stage.basistech.net` | `/opt/temperature-bot-stage` | `air-stage_basistech_net.service`, `127.0.0.1:8101` | `temperature-bot-stage-minute.{service,timer}`; notification service remains separately enabled or disabled | `/etc/temperature-bot/air-stage.env`; `/home/air-stage/var/db/temperature-bot.db` |
| `slg1.basistech.net` | `/opt/temperature-bot-dev` | `slg1_basistech_net.{service,socket}`, `127.0.0.1:8003` | none | `/etc/temperature-bot/slg1.env`; `/home/simsong/var/db/temperature-bot.db` |
| `deg1.basistech.net` | `/opt/temperature-bot-dev` | `deg1_basistech_net.{service,socket}`, `127.0.0.1:8004` | none | `/etc/temperature-bot/deg1.env`; `/home/deg/var/db/temperature-bot.db` |

The deployment command must require one named target: `production`, `staging`,
or `developers`. Each maps to exactly one application root. It must fail if the
installed endpoint identity, database identity/root, unit paths, or active
release do not match that target. `slg1` and `deg1` intentionally share the
`developers` root, so neither developer endpoint is a valid individual
application-deployment target. Activating a developer release changes the code
used by both endpoints; both must be stopped, restarted, and accepted together.
Their host units, environment files, sockets, and databases remain distinct.

Host configuration is never an application-deployment side effect. Checked-in
`.service`, `.socket`, `.timer`, environment examples, and nginx files are
reviewed references and test inputs. The installed files under `/etc` and their
enabled/active states remain authoritative. A release may be activated only if
those installed files are compatible with its declared target; otherwise the
application deployment fails before quiescing or activation and reports that a
separate host-configuration change is required.

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
configuration/air-stage.env.example
systemd/slg1_basistech_net.socket
systemd/deg1_basistech_net.socket
nginx/air-stage.basistech.net
systemd/slg1_basistech_net.service
systemd/deg1_basistech_net.service
systemd/air-stage_basistech_net.service
systemd/temperature-bot-stage-minute.service
systemd/temperature-bot-stage-minute.timer
systemd/temperature-bot-stage-ae200-notifications.service
systemd/temperature-bot-minute.service
systemd/temperature-bot-minute.timer
systemd/temperature-bot-hourly.service
systemd/temperature-bot-hourly.timer
systemd/temperature-bot-daily.service
systemd/temperature-bot-daily.timer
systemd/temperature-bot-release-update@.service
systemd/temperature-bot-release-update@.timer
installer/install_deployment_package.py
documentation/DEPLOYMENT.md
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
time, and whether the source tree was dirty. The tag-triggered release workflow
refuses dirty input; local and ephemeral PR packages retain the flag for
diagnosis.

The example environment files, socket units, services, and timers are
host-configuration references. They remain in the package so a candidate's
expectations are integrity-checked, reviewable, and available for compatibility
preflight. The installer does not copy any of them into `/etc`. Socket units
retain the configuration role for package-format-1 compatibility; that role
does not imply installation. The `slg1` and `deg1` examples define separate
private databases and the complete simulator-only policy. A separate targeted
host-configuration procedure must replace `GIT_COMMIT` with the verified
manifest commit when it deliberately installs an environment file.

The `nginx/` directory has the same reference-only status. It contains reviewed
virtual-host configuration captured from the live deployment, but the installer
never writes nginx configuration or reloads nginx.

The developer web units run one worker so their in-memory Hubitat simulators
provide deterministic read-after-write behavior. Systemd socket units own the
host-loopback ports and pass their listening descriptors to Gunicorn; the web
processes run with `PrivateNetwork=yes`, so an application regression has no
route to live controller command endpoints. They also retain the systemd IP
allowlist as defense in depth. They do not install or enable scheduled
collection/rules timers. Their shared immutable activation root is
`/opt/temperature-bot-dev`; `/opt/temperature-bot` remains reserved for
production services and scheduled jobs.

The live staging release has its own `/opt/temperature-bot-stage` root,
database, web service on loopback port 8101, minute collector, writer lock, and
notification collector. Its web process uses the real integrations, so UI
commands affect building equipment; a persistent banner makes that boundary
explicit. The minute job is limited to AE-200 reads and cannot run alerts or
HVAC rules. Production fires at second 00; staging fires 5–20 seconds later
using `RandomizedDelaySec=15s`.

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
checkout, executes an installed console script after atomic activation, checks
the packaged host-configuration inventory, and proves that no `/etc` tree was
created. The virtual environment is created as relocatable
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
`--activate` changes only the selected root's `current` symlink. There is no
systemd or nginx installation option. The installer result reports
`host_configuration_installed: false` so automation cannot mistake staging or
activation for a host-configuration update.

An existing trusted release environment runs the installer. First-host
bootstrap remains an operations procedure under #44. A package may carry a
new installer for the next transaction, but the currently trusted verifier
must validate that package before candidate code is executed.

## GitHub Releases and target-aware updates

Pushing a tag whose normalized PEP 440 value matches `VERSION` and
`pyproject.toml` runs `.github/workflows/release.yml`. The workflow repeats the
Linux checks and tests, builds and installs the immutable package in a
disposable root, verifies clean commit provenance, attests the ZIP and checksum
sidecar, and creates the GitHub Release. A prerelease project version, such as
canonical `1.0.0b1`, produces a prerelease even when the tag uses the equivalent
human spelling `1.0.0-beta1`.

The trusted currently installed environment can inspect the release channel and
stage a newer application for exactly one application root:

```bash
# Stable releases only; report without installing.
/opt/temperature-bot/current/venv/bin/python \
  -m bin.github_release_update production --check-only

# Include prereleases and stage the newest verified release.
sudo /opt/temperature-bot/current/venv/bin/python \
  -m bin.github_release_update production --channel prerelease
```

Pass `--tag <tag>` to select a specific published application release instead
of the newest eligible release. Discovery skips web-screenshot and other
GitHub Releases that do not contain exactly one deployment ZIP and its SHA-256
sidecar.

For an explicitly authorized pre-release test, `--branch <name>` or
`--commit <sha>` resolves the selector through GitHub to one immutable commit,
checks out that detached commit, and builds the deployment package locally.
The source build runs as the unprivileged `nobody` account with no supplementary
groups. Root staging accepts binary dependency artifacts only and verifies
installed metadata and files without importing the candidate application or
executing its entry points. A branch is resolved once at the start, so a
concurrent push cannot change the commit being installed. Source builds do not
have GitHub Release attestations and must not replace the signed-tag release
path for production promotion.

The target must be `production`, `staging`, or `developers`. `slg1` and `deg1`
are intentionally not individual choices because both use
`/opt/temperature-bot-dev/current`. Discovery resolves the release tag through
the GitHub Git-data API and requires its commit to match the package manifest.
Downloads have time and size bounds. The outer SHA-256 sidecar, ZIP structure,
payload inventory and hashes, canonical version, dirty flag, and monotonic
version ordering must all pass before staging. Results are written atomically
to `<target-root>/release-update-state.json`; concurrent runs serialize on
`<target-root>/.release-update.lock`. GitHub unavailability or malformed assets
leave the active release untouched.

The packaged `temperature-bot-release-update@.service` and `.timer` are
reference host configuration for periodic stable-channel staging. As with all
host configuration, an operator must explicitly install and enable the selected
instance; the package installer does not modify `/etc` or systemd.

The staging process runs as root because the immutable `/opt` application
roots are root-owned. Its systemd sandbox permits writes only to those roots;
it never activates a release unless `--activate` is explicit.
It uses a pinned, root-owned uv executable at `/usr/local/bin/uv`; never run a
root updater through a service-account-owned executable. Override that audited
path explicitly with `--uv` if the host layout changes.

Activation is deliberately narrower than staging:

```bash
sudo /opt/temperature-bot/current/venv/bin/python \
  -m bin.github_release_update production --channel prerelease --activate
```

`--activate` requires root and refuses the candidate unless every packaged
migration path and SHA-256 is identical to the active release. It records which
target units are active, quiesces only that target, switches `current`
atomically, restores the previously active long-running units/timers, and
requires every loopback version endpoint to report the candidate version,
commit, instance identity, and expected control mode. Before stopping anything,
it also verifies the active endpoint's instance and control mode, so stale host
configuration fails closed. Failure before health success restores the prior
release pointer and unit state. A candidate with any migration change remains
staged and must use the database snapshot/migration transaction in #216; this
command never modifies a database.

The selected `air-stage` policy is live control with all integration simulator
flags disabled. Activation preflight rejects future host/source drift; verify
that the persistent host environment retains this policy rather than weakening
the preflight or rewriting the environment implicitly.

## Legacy Make targets

`make deploy` and `make deploy-stage` predate this artifact contract. They
update server Git checkouts and have hard-coded production or staging behavior;
they are not the endpoint-aware immutable deployment transaction specified
here. Neither target may be generalized to another endpoint by overriding a
path or service variable. Until they are retired, use them only under their
existing runbooks and guards. They must not install host configuration or be
used for `slg1` or `deg1` application activation.

## Upgrade transaction design

The endpoint-aware upgrade command will compose the installer with a durable
state machine. It must record every transition and be safely restartable.

1. **Discover** — select an approved channel/version, enforce hold/pin/failed
   release policy, and download the ZIP plus provenance with bounded size and
   time limits.
2. **Verify target** — resolve one endpoint from the table above. Validate the
   installed instance/database identity, application root, unit definitions,
   routing assumptions, and enabled/active states. Fail if the endpoint is
   ambiguous or incompatible; never repair host configuration implicitly.
3. **Verify package** — validate release provenance, outer SHA-256, safe ZIP
   structure, manifest inventory, every payload SHA-256, version/tag agreement,
   Python, Flyway, disk space, configuration, and target instance identity.
4. **Stage** — install into a new immutable release directory and virtual
   environment. Run package-resource and non-mutating application preflight checks
   without changing the active release.
5. **Lock** — acquire the target root's deployment lock. Record the active release,
   installed unit bytes, unit enabled/active states, database identity/schema,
   and intended rollback paths.
6. **Quiesce** — stop only the target's writer timers first so no new jobs
   start. Then wait for or stop their oneshot services and stop Gunicorn/other
   database writers. Verify with systemd state and open-file/process checks that
   no writer remains.
   Developer deployment stops both `slg1` and `deg1`; it must not stop production
   or staging. Production and staging use their own timer inventories.
7. **Snapshot** — create a consistent SQLite snapshot with the backup API or
   `VACUUM INTO`; never raw-copy a live WAL database. Run `PRAGMA quick_check`
   and record size, SHA-256, Flyway schema, release, and timestamp. The
   `developers` target snapshots both private databases independently.
8. **Migrate** — use the candidate package's complete migration directory and
   manifest-pinned Flyway version. Validate, migrate, validate again, and record
   before/after schema versions. The `developers` target must migrate both
   databases successfully or roll back both before activation.
9. **Activate application** — atomically point only the target root's `current`
   symlink at the candidate. Do not write `/etc` or run `daemon-reload`.
10. **Prove health** — start only the target web service or developer pair, then
    run bounded loopback and public health/root/API checks. Scheduled writers
    remain stopped.
11. **Commit** — after health succeeds, restore only the target units that were
    active before deployment and verify their schedules. Exposure plus writer
    resumption is the commit point.
12. **Report** — persist structured results and email the configured
    maintainers with release, commit, backup, migration, unit, smoke, duration,
    and disposition evidence.

Before the commit point, any failure restores the previous database snapshot,
release symlink, and prior service/timer states. Unit bytes are unchanged by an
application deployment.
After the commit point, automatic database restoration is forbidden because it
could discard new writes. The transaction enters maintenance/failed state,
preserves all evidence, notifies maintainers, and requires an explicit forward
fix or operator-approved restore.

Power loss and process termination are ordinary state-machine resumptions, not
special cases. Durable checkpoints distinguish downloaded, verified, staged,
quiesced, snapshotted, migrated, activated, committed, rolled back, and failed
states. Fault-injection tests under #216 must exercise every boundary.

## Separate host-configuration transaction

A systemd, nginx, environment, account, certificate, port, or firewall change
is a different operation from application deployment. It must:

1. name exactly one endpoint and enumerate the exact installed files and units
   it is allowed to change;
2. verify the candidate files against that endpoint's root, identity, database,
   listener, and scheduler policy;
3. preserve the installed bytes, symlink targets, ownership/mode, and unit
   enabled/active state as the rollback set;
4. install only the selected endpoint's files atomically; never bulk-copy the
   package's entire `systemd/` or `configuration/` directory;
5. run `systemd-analyze verify` or `nginx -t` before reload, then reload the
   relevant daemon and restart only the selected endpoint's units;
6. verify loopback and public identity, database identity, control/simulator
   mode, scheduler state, logs, and restart count; and
7. restore the preserved files and states on failure.

Because `slg1` and `deg1` share an application root, a host-configuration change
may still target one developer endpoint, but an application release activation
always treats the pair as one deployment target. Production, staging, and the
developer pair are never activated in one transaction.

## Pull-request artifacts

Every pull request builds and checks one deployment ZIP on Ubuntu, then uploads
the ZIP and its `.sha256` sidecar as a GitHub Actions artifact. These packages
are test evidence, not releases and not authorized for production deployment.
They expire after five days. Version tags publish retained, attested assets
through the immutable GitHub Release workflow implemented for #213.
