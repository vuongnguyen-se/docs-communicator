"""Build the Lambda deployment zip. Offline-safe: it only downloads wheels from PyPI.

Usage (from backend/):  python scripts/build_lambda.py [--arch arm64|x86_64] [--out dist]

One zip serves all three functions; Terraform selects the entry point per function:
  clouddocs.handlers.documents.handler | clouddocs.handlers.chat.handler | clouddocs.handlers.health.handler

- Dependencies come from [project].dependencies in pyproject.toml, installed as Linux
  wheels for the chosen architecture (pydantic-core is a compiled extension), so the zip can
  be built on Windows or macOS.
- boto3/botocore are NOT bundled: the Lambda Python runtime provides them. The runtime copy
  must be recent enough for the bedrock-agent KnowledgeBaseDocuments APIs; check at the spike.
- The zip is reproducible (fixed timestamps, sorted entries).
This script never uploads or deploys anything.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLATFORMS = {
    "arm64": "manylinux2014_aarch64",
    "x86_64": "manylinux2014_x86_64",
}
FIXED_TIME = (2026, 1, 1, 0, 0, 0)
SKIP_DIRS = {"__pycache__", "tests", "test"}
SKIP_SUFFIXES = {".pyc", ".pyo"}


def runtime_dependencies() -> list[str]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    deps: list[str] = data["project"]["dependencies"]
    return [d for d in deps if d.split("[")[0].strip().lower() not in {"boto3", "botocore"}]


def install(deps: list[str], target: Path, arch: str) -> None:
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--quiet",
        "--no-input",
        "--only-binary=:all:",
        "--platform",
        PLATFORMS[arch],
        "--python-version",
        "3.12",
        "--implementation",
        "cp",
        "--target",
        str(target),
        *deps,
    ]
    subprocess.run(cmd, check=True)


def add_tree(zf: zipfile.ZipFile, base: Path) -> int:
    count = 0
    for path in sorted(base.rglob("*")):
        rel = path.relative_to(base)
        if path.is_dir() or SKIP_DIRS & set(rel.parts) or path.suffix in SKIP_SUFFIXES:
            continue
        info = zipfile.ZipInfo(rel.as_posix(), FIXED_TIME)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        zf.writestr(info, path.read_bytes())
        count += 1
    return count


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--arch", choices=sorted(PLATFORMS), default="arm64")
    ap.add_argument("--out", type=Path, default=ROOT / "dist")
    args = ap.parse_args()

    out: Path = args.out
    build = out / "build"
    if build.exists():
        shutil.rmtree(build)
    build.mkdir(parents=True)

    deps = runtime_dependencies()
    install(deps, build, args.arch)
    shutil.copytree(ROOT / "src" / "clouddocs", build / "clouddocs")

    zip_path = out / f"clouddocs-lambda-{args.arch}.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        files = add_tree(zf, build)
    shutil.rmtree(build)
    size_mb = zip_path.stat().st_size / 1024 / 1024
    print(f"built {zip_path} ({files} files, {size_mb:.1f} MiB, arch={args.arch}, deps={deps})")
    if size_mb > 50:
        sys.exit("zip exceeds the 50 MB direct-upload limit; use S3 upload or trim dependencies")


if __name__ == "__main__":
    main()
