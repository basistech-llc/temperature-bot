"""Build the complete Temperature Bot deployment ZIP."""

from __future__ import annotations

import argparse
import os
import subprocess
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from app.deployment_package import PackageIdentity, PayloadSource, build_package

REPO_ROOT = Path(__file__).resolve().parents[1]


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def collect_payloads(requirements: Path, wheel: Path) -> list[PayloadSource]:
    payloads = [
        PayloadSource(source=wheel, path=f"wheel/{wheel.name}", role="wheel"),
        PayloadSource(
            source=requirements,
            path="requirements/runtime.txt",
            role="requirements",
        ),
        PayloadSource(
            source=REPO_ROOT / "bin/install_deployment_package.py",
            path="installer/install_deployment_package.py",
            role="installer",
            mode=0o755,
        ),
        PayloadSource(
            source=REPO_ROOT / "doc/DEPLOYMENT.md",
            path="documentation/DEPLOYMENT.md",
            role="documentation",
        ),
        PayloadSource(
            source=REPO_ROOT / "VERSION", path="metadata/VERSION", role="metadata"
        ),
        PayloadSource(
            source=REPO_ROOT / "pyproject.toml",
            path="metadata/pyproject.toml",
            role="metadata",
        ),
    ]
    for migration in sorted((REPO_ROOT / "etc/flyway/sql").glob("*.sql")):
        payloads.append(
            PayloadSource(
                source=migration,
                path=f"migrations/{migration.name}",
                role="migration",
            )
        )
    for unit in sorted((REPO_ROOT / "etc/systemd").iterdir()):
        if unit.is_file():
            is_unit = unit.suffix in {".service", ".timer"}
            payloads.append(
                PayloadSource(
                    source=unit,
                    path=(
                        f"systemd/{unit.name}"
                        if is_unit
                        else f"configuration/{unit.name}"
                    ),
                    role="systemd" if is_unit else "configuration",
                )
            )
    for nginx_config in sorted((REPO_ROOT / "etc/nginx").iterdir()):
        if nginx_config.is_file():
            payloads.append(
                PayloadSource(
                    source=nginx_config,
                    path=f"nginx/{nginx_config.name}",
                    role="configuration",
                )
            )
    return payloads


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "dist")
    parser.add_argument("--flyway-version", required=True)
    args = parser.parse_args()

    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if project["version"] != version:
        raise SystemExit(
            f"VERSION ({version}) does not match pyproject.toml ({project['version']})"
        )
    wheels = sorted((REPO_ROOT / "dist").glob(f"temperature_bot-{version}-*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"expected one wheel for {version}, found {len(wheels)}")

    commit = os.getenv("GITHUB_SHA") or _git("rev-parse", "HEAD")
    dirty = bool(_git("status", "--porcelain"))
    identity = PackageIdentity(
        version=version,
        commit=commit,
        built_at=datetime.now(timezone.utc),
        dirty=dirty,
        requires_python=project["requires-python"],
        flyway_version=args.flyway_version,
    )
    output = args.output_dir / f"temperature-bot-deployment-{version}-{commit[:12]}.zip"
    build_package(output, identity, collect_payloads(args.requirements, wheels[0]))
    print(output)


if __name__ == "__main__":
    main()
