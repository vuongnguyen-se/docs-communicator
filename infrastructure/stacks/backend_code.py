"""Packages backend/src/clouddocs plus its pip dependencies as one Lambda asset.

Bundling tries a local, Docker-free build first:
`pip install --platform manylinux2014_aarch64 --only-binary=:all:` downloads
Linux/ARM wheels even on Windows, so compiled packages such as pydantic-core
match the Lambda runtime. If that fails, CDK falls back to the official
Lambda Python build image (requires Docker running).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import aws_cdk as cdk
import jsii
from aws_cdk import aws_lambda as lambda_

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
SOURCE_DIR = BACKEND_DIR / "src"
PACKAGE = "clouddocs"

RUNTIME = lambda_.Runtime.PYTHON_3_12
ARCHITECTURE = lambda_.Architecture.ARM_64
PIP_PLATFORM = "manylinux2014_aarch64"


def backend_dependencies() -> list[str]:
    """Runtime dependencies exactly as declared in backend/pyproject.toml."""
    data = tomllib.loads((BACKEND_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    return list(data["project"]["dependencies"])


@jsii.implements(cdk.ILocalBundling)
class _LocalPipBundling:
    def try_bundle(self, output_dir: str, _options: Any = None) -> bool:
        deps = backend_dependencies()
        cmd = [
            sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
            "--target", output_dir,
            "--platform", PIP_PLATFORM,
            "--implementation", "cp",
            "--python-version", "3.12",
            "--only-binary=:all:",
            *deps,
        ]
        try:
            subprocess.run(cmd, check=True)
        except (subprocess.CalledProcessError, OSError) as exc:
            print(f"[clouddocs] local bundling failed, falling back to Docker: {exc}")
            return False
        shutil.copytree(
            SOURCE_DIR / PACKAGE,
            Path(output_dir) / PACKAGE,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            dirs_exist_ok=True,
        )
        return True


def backend_code() -> lambda_.Code:
    deps = " ".join(f"'{d}'" for d in backend_dependencies())
    return lambda_.Code.from_asset(
        str(SOURCE_DIR),
        exclude=["**/__pycache__", "*.egg-info"],
        bundling=cdk.BundlingOptions(
            image=RUNTIME.bundling_image,
            platform="linux/arm64",
            local=_LocalPipBundling(),
            command=[
                "bash", "-c",
                f"pip install --target /asset-output {deps} && cp -r /asset-input/{PACKAGE} /asset-output/",
            ],
        ),
    )
