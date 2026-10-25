"""Lambda code assets built from the backend checkout.

Third-party wheels are installed for the Lambda platform (arm64 manylinux, CPython 3.13) and cached by the
hash of ``backend/uv.lock``; boto3 is left to the runtime. The tasklane package and SQL migrations are copied.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from functools import cache
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BUILD = REPO / "infra" / ".build"
RUNTIME_PROVIDED = {"boto3", "botocore", "s3transfer", "jmespath", "python-dateutil", "six", "urllib3"}


def _deps_dir() -> Path:
    lock = (REPO / "backend" / "uv.lock").read_bytes()
    out = BUILD / f"deps-{hashlib.sha256(lock).hexdigest()[:16]}"
    if (out / ".complete").exists():
        return out
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    req = subprocess.run(
        ["uv", "export", "--frozen", "--no-dev", "--no-hashes", "--no-emit-project", "--no-header"],
        cwd=REPO / "backend",
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    keep = [
        ln
        for ln in req.splitlines()
        if ln.strip() and not ln.startswith("#") and ln.split("==")[0].strip().lower() not in RUNTIME_PROVIDED
    ]
    (out.parent / f"{out.name}.txt").write_text("\n".join(keep) + "\n")
    res = subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--target",
            str(out),
            "--python-platform",
            "aarch64-manylinux2014",
            "--python-version",
            "3.13",
            "--only-binary",
            ":all:",
            "-r",
            str(out.parent / f"{out.name}.txt"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        raise RuntimeError(f"installing Lambda dependencies failed:\n{res.stderr[-3000:]}")
    (out / ".complete").write_text("ok")
    return out


@cache
def backend_asset() -> str:
    out = BUILD / "backend"
    if out.exists():
        shutil.rmtree(out)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".complete")
    shutil.copytree(_deps_dir(), out, ignore=ignore)
    shutil.copytree(REPO / "backend" / "src" / "tasklane", out / "tasklane", ignore=ignore)
    shutil.copytree(REPO / "backend" / "migrations", out / "tasklane" / "migrations_sql", ignore=ignore)
    return str(out)


@cache
def web_asset() -> str:
    dist = REPO / "web" / "dist"
    if (dist / "index.html").exists():
        return str(dist)
    placeholder = BUILD / "web-placeholder"
    placeholder.mkdir(parents=True, exist_ok=True)
    (placeholder / "index.html").write_text("<!doctype html><title>Tasklane</title><p>Web app not built.</p>")
    return str(placeholder)
