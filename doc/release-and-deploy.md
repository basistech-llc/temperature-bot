# Release and deploy a version

This checklist is for maintainers. A release is an immutable GitHub Release,
not a server-side `git pull`. Never tag a commit that has not passed review and
CI.

1. On a branch from current `main`, set the same canonical PEP 440 version in
   `VERSION` and `pyproject.toml`, refresh `uv.lock`, and move all meaningful
   entries from **Unreleased** into a dated version section in
   `doc/RELEASE_NOTES.md`.

2. Validate the proposed release through the Makefile:

   ```bash
   make check
   make test
   make build-check
   make deployment-package-check
   make systemd-verify
   ```

3. Merge the reviewed pull request and verify that CI passed on the resulting
   `main` commit. Start from a clean, current checkout of that exact commit.

4. Validate, create, and push a signed tag. For the current prerelease target,
   the commands will be:

   ```bash
   make release-tag-check GITHUB_REF_NAME=1.0.0b1
   git tag -s 1.0.0b1 -m "Temperature Bot 1.0.0b1"
   git push origin 1.0.0b1
   ```

5. Wait for the **Release** workflow. It must publish one
   `temperature-bot-deployment-*.zip` and its `.sha256` sidecar. Verify both:

   ```bash
   gh run list --workflow Release --limit 5
   gh release view 1.0.0b1
   ```

6. Connect to `air` using a normal maintainer account, never direct root SSH.
   Verify that the pinned updater dependency is root-owned and is version
   `0.11.26`:

   ```bash
   sudo stat -c '%U %G %a %n' /usr/local/bin/uv
   sudo /usr/local/bin/uv --version
   ```

   If it is absent, complete the root-owned uv bootstrap in issue #44 before
   continuing; do not point the root updater at a user-writable executable.

   If the active installation already provides `temperature-bot-release-update`,
   check the exact release without changing staging:

   ```bash
   ssh air.basistech.net
   sudo /opt/temperature-bot-stage/current/venv/bin/temperature-bot-release-update \
     staging --channel prerelease --tag 1.0.0b1 --check-only
   ```

   For the first release after the old checkout-based deployment, the active
   wheel does not contain that command. Bootstrap only the trusted updater from
   the signed tag into a root-owned checkout, using the already installed
   production environment. The destination must not already exist:

   ```bash
   sudo git clone --config core.hooksPath=/dev/null \
     --branch 1.0.0b1 --single-branch \
     https://github.com/basistech-llc/temperature-bot.git \
     /opt/temperature-bot-release-tools-1.0.0b1
   sudo git -C /opt/temperature-bot-release-tools-1.0.0b1 verify-tag 1.0.0b1
   sudo git -C /opt/temperature-bot-release-tools-1.0.0b1 status --porcelain
   sudo /usr/bin/env \
     PYTHONPATH=/opt/temperature-bot-release-tools-1.0.0b1 \
     /opt/temperature-bot/current/venv/bin/python \
     -m bin.github_release_update staging --channel prerelease \
     --tag 1.0.0b1 --check-only
   ```

   The status command must print nothing. Do not run a root updater from a
   normal user's checkout, even after tag verification, because that user could
   replace imported Python files between verification and execution.

7. Stage the verified release, then activate it only after reviewing the
   reported manifest and the staging environment policy:

   `air-stage` is intentionally live control with every integration simulator
   flag disabled. Verify that the persistent host environment still matches
   that selected policy; activation preflight rejects any future drift.

   ```bash
   sudo /opt/temperature-bot-stage/current/venv/bin/temperature-bot-release-update \
     staging --channel prerelease --tag 1.0.0b1
   sudo /opt/temperature-bot-stage/current/venv/bin/temperature-bot-release-update \
     staging --channel prerelease --tag 1.0.0b1 --activate
   curl --fail https://air-stage.basistech.net/api/v1/version
   ```

   During the one-time bootstrap, substitute the verified source-checkout
   Python command from step 6 for the console command shown here.

   Activation refuses releases with changed migration hashes and restores the
   previous release pointer and unit state if health checks fail. Use the
   transactional migration procedure tracked in issue #216 when migrations
   differ.

   Before a tag exists, an explicitly authorized staging test may select a
   branch or exact commit instead. The updater resolves a branch to one commit
   before building, and performs the source build as an unprivileged account:

   ```bash
   sudo /opt/temperature-bot/current/venv/bin/python \
     -m bin.github_release_update staging \
     --branch codex/release-readiness-a2 --check-only
   sudo /opt/temperature-bot/current/venv/bin/python \
     -m bin.github_release_update staging \
     --commit FULL_OR_ABBREVIATED_SHA --activate
   ```

   The installed updater can be used directly. During the first-release
   bootstrap, resolve the branch to a commit, clone that exact commit into a
   new root-owned `/opt/temperature-bot-release-tools-COMMIT` directory, verify
   that `HEAD` is the expected commit and the checkout is clean, and use that
   directory as `PYTHONPATH`, as in step 6. Branch/commit builds are for staging
   validation only and do not replace the signed tag, GitHub Release artifact,
   or attestation required for production.

8. After staging has been exercised, repeat check, stage, and activation with
   target `production`. Production deployment requires a separate explicit
   decision; a staging test never authorizes it.

For the full trust model, target table, rollback behavior, and first-install
bootstrap boundary, see `doc/DEPLOYMENT.md`.
