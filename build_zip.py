#!/usr/bin/env python3
"""Create the repo skeleton (if missing) and package it as dist/aws-neo4j-auradb.zip.
Excludes macOS metadata (__MACOSX, .DS_Store, ._* files), caches, git data and terraform state."""
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME = "aws-neo4j-auradb"
DIRS = ["docker", "terraform", "scripts", "web", "data"]
EXCLUDE_DIRS = {"__MACOSX", "__pycache__", ".git", ".terraform", "dist", "node_modules"}
EXCLUDE_FILES = {".DS_Store"}
EXCLUDE_SUFFIX = (".zip", ".pyc", ".tfstate", ".tfstate.backup")


def skip(p):
    rel = p.relative_to(ROOT)
    return (any(part in EXCLUDE_DIRS for part in rel.parts) or p.name in EXCLUDE_FILES
            or p.name.startswith("._") or p.name.endswith(EXCLUDE_SUFFIX))


def main():
    for d in DIRS:
        (ROOT / d).mkdir(exist_ok=True)
    out = ROOT / "dist"
    out.mkdir(exist_ok=True)
    target = out / f"{NAME}.zip"
    files = sorted(p for p in ROOT.rglob("*") if p.is_file() and not skip(p))
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, f"{NAME}/{p.relative_to(ROOT).as_posix()}")
    print(f"Wrote {target} ({len(files)} files)")


if __name__ == "__main__":
    main()
