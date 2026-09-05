"""Build the complete Temperature Bot deployment ZIP."""

from __future__ import annotations

import argparse
import os
import subprocess
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.deployment_package import PackageIdentity, PayloadSource, build_package

REPO_ROOT = Path(__file__).resolve().parents[1]


class CheckoutPackageOptions(BaseModel):
    """Provenance supplied by the trusted checkout caller."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    flyway_version: str
    commit: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    built_at: datetime
    dirty: bool


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def collect_payloads(
    requirements: Path, wheel: Path, *, repo_root: Path = REPO_ROOT
) -> list[PayloadSource]:
    payloads = [
        PayloadSource(source=wheel, path=f"wheel/{wheel.name}", role="wheel"),
        PayloadSource(
            source=requirements,
            path="requirements/runtime.txt",
            role="requirements",
        ),
        PayloadSource(
            source=repo_root / "bin/install_deployment_package.py",
            path="installer/install_deployment_package.py",
            role="installer",
            mode=0o755,
        ),
        PayloadSource(
            source=repo_root / "doc/DEPLOYMENT.md",
            path="documentation/DEPLOYMENT.md",
            role="documentation",
        ),
        PayloadSource(
            source=repo_root / "VERSION", path="metadata/VERSION", role="metadata"
        ),
        PayloadSource(
            source=repo_root / "pyproject.toml",
            path="metadata/pyproject.toml",
            role="metadata",
        ),
    ]
    for migration in sorted((repo_root / "etc/flyway/sql").glob("*.sql")):
        payloads.append(
            PayloadSource(
                source=migration,
                path=f"migrations/{migration.name}",
                role="migration",
            )
        )
    for unit in sorted((repo_root / "etc/systemd").iterdir()):
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
    for nginx_config in sorted((repo_root / "etc/nginx").iterdir()):
        if nginx_config.is_file():
            payloads.append(
                PayloadSource(
                    source=nginx_config,
                    path=f"nginx/{nginx_config.name}",
                    role="configuration",
                )
            )
    return payloads


def build_checkout_package(
    repo_root: Path,
    output_dir: Path,
    requirements: Path,
    wheel: Path,
    options: CheckoutPackageOptions,
) -> Path:
    """Build a deployment ZIP from explicit, already-built checkout inputs."""
    project = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    version = (repo_root / "VERSION").read_text(encoding="utf-8").strip()
    if project["version"] != version:
        raise ValueError(
            f"VERSION ({version}) does not match pyproject.toml ({project['version']})"
        )
    expected_wheel_prefix = f"temperature_bot-{version}-"
    if not wheel.name.startswith(expected_wheel_prefix) or wheel.suffix != ".whl":
        raise ValueError(f"wheel does not match checkout version {version}: {wheel.name}")
    identity = PackageIdentity(
        version=version,
        commit=options.commit,
        built_at=options.built_at,
        dirty=options.dirty,
        requires_python=project["requires-python"],
        flyway_version=options.flyway_version,
    )
    output = (
        output_dir
        / f"temperature-bot-deployment-{version}-{options.commit[:12]}.zip"
    )
    build_package(
        output,
        identity,
        collect_payloads(requirements, wheel, repo_root=repo_root),
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "dist")
    parser.add_argument("--flyway-version", required=True)
    args = parser.parse_args()

    version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    wheels = sorted((REPO_ROOT / "dist").glob(f"temperature_bot-{version}-*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"expected one wheel for {version}, found {len(wheels)}")

    commit = os.getenv("GITHUB_SHA") or _git("rev-parse", "HEAD")
    dirty = bool(_git("status", "--porcelain"))
    output = build_checkout_package(
        REPO_ROOT,
        args.output_dir,
        args.requirements,
        wheels[0],
        CheckoutPackageOptions(
            flyway_version=args.flyway_version,
            commit=commit,
            built_at=datetime.now(timezone.utc),
            dirty=dirty,
        ),
    )
    print(output)


if __name__ == "__main__":
    main()
