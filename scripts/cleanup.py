#!/usr/bin/env python3
"""
Post-test cleanup — remove development / test / build garbage.
Safe to run anytime; only touches gitignored artifacts.

Usage:
    python scripts/cleanup.py              # clean everything
    python scripts/cleanup.py --dry-run    # show what would be deleted
    python scripts/cleanup.py --verbose    # print every path removed
    python scripts/cleanup.py --keep-reflex  # skip .web/ (preserve hot-reload cache)
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration — dirs/files to clean, relative to project root
# ---------------------------------------------------------------------------

# Directories to remove entirely
DIRS_TO_REMOVE: list[str] = [
    # Python bytecode caches
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    # Test / coverage artifacts
    "htmlcov",
    # Build artifacts
    "dist",
    "build",
    "*.egg-info",
    # Reflex build output
    ".web",
    "reflex.lock",
    # LangGraph checkpoint state
    ".langgraph",
    # MCP browser automation session artifacts
    ".playwright-mcp",
]

# Glob patterns for stray files in project root (screenshots, logs, etc.)
ROOT_STRAY_PATTERNS: list[str] = [
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.svg",
    "*.log",
]

# Files to remove (project-root only, NOT recursive)
FILES_TO_REMOVE_ROOT: list[str] = [
    ".coverage",
    ".states",
    ".model-config.json",
]

# Patterns inside DIRS_TO_REMOVE that should not count as "garbage found"
# (these are internal gitignore/marker files, not actual garbage)
_IGNORE_MARKERS: set[str] = {".gitignore", "CACHEDIR.TAG"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _size_fmt(total_bytes: int) -> str:
    """Human-readable byte count."""
    for unit in ("B", "KB", "MB", "GB"):
        if total_bytes < 1024:
            return f"{total_bytes:.1f} {unit}"
        total_bytes /= 1024
    return f"{total_bytes:.1f} TB"


def _count_items(path: Path) -> tuple[int, int]:
    """Return (file_count, total_bytes) for a directory tree."""
    if not path.exists():
        return 0, 0
    file_count = 0
    total_bytes = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            if f not in _IGNORE_MARKERS:
                fp = Path(root) / f
                try:
                    total_bytes += fp.stat().st_size
                    file_count += 1
                except OSError:
                    pass
    return file_count, total_bytes


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def _find_pycache_dirs(root: Path) -> list[Path]:
    """Recursively find all __pycache__ directories, excluding venv."""
    results: list[Path] = []
    for dirpath, dirnames, _filenames in os.walk(root):
        # Never descend into virtual environments
        if "venv" in dirnames:
            dirnames.remove("venv")
        if ".git" in dirnames:
            dirnames.remove(".git")
        if "node_modules" in dirnames:
            dirnames.remove("node_modules")

        path = Path(dirpath)
        if path.name == "__pycache__":
            results.append(path)
    return results


def cleanup(
    project_root: Path,
    *,
    dry_run: bool = False,
    verbose: bool = False,
    keep_reflex: bool = False,
) -> None:
    """Run the full cleanup routine."""

    dirs = list(DIRS_TO_REMOVE)
    if keep_reflex:
        dirs = [d for d in dirs if d not in (".web", "reflex.lock")]

    total_files = 0
    total_bytes = 0

    # 1. Remove known directories ------------------------------------------
    for pattern in dirs:
        if "*" in pattern or "?" in pattern:
            # Glob pattern — match at root level
            for match in sorted(project_root.glob(pattern)):
                if match.is_dir():
                    fc, bc = _count_items(match)
                    total_files += fc
                    total_bytes += bc
                    if verbose or dry_run:
                        rel = match.relative_to(project_root)
                        print(f"  {'[DRY-RUN]' if dry_run else 'rm -rf':<12} {rel}  ({fc}f / {_size_fmt(bc)})")
                    if not dry_run:
                        shutil.rmtree(match, ignore_errors=True)
        else:
            # Literal directory name
            target = project_root / pattern
            if target.is_dir():
                fc, bc = _count_items(target)
                total_files += fc
                total_bytes += bc
                if verbose or dry_run:
                    print(f"  {'[DRY-RUN]' if dry_run else 'rm -rf':<12} {pattern}  ({fc} files, {_size_fmt(bc)})")
                if not dry_run:
                    shutil.rmtree(target, ignore_errors=True)

    # 2. __pycache__ directories (recursive, excluding venv) ----------------
    for pycache in _find_pycache_dirs(project_root):
        fc, bc = _count_items(pycache)
        total_files += fc
        total_bytes += bc
        if verbose or dry_run:
            rel = pycache.relative_to(project_root)
            print(f"  {'[DRY-RUN]' if dry_run else 'rm -rf':<12} {rel}  ({fc}f / {_size_fmt(bc)})")
        if not dry_run:
            shutil.rmtree(pycache, ignore_errors=True)

    # 3. Root stray files (screenshots, logs, etc.) -------------------------
    for pattern in ROOT_STRAY_PATTERNS:
        for match in sorted(project_root.glob(pattern)):
            if match.is_file():
                try:
                    sz = match.stat().st_size
                except OSError:
                    sz = 0
                total_files += 1
                total_bytes += sz
                if verbose or dry_run:
                    print(f"  {'[DRY-RUN]' if dry_run else 'rm':<12} {match.name}  ({_size_fmt(sz)})")
                if not dry_run:
                    match.unlink(missing_ok=True)

    # 4. Root-level config files ---------------------------------------------
    for fname in FILES_TO_REMOVE_ROOT:
        target = project_root / fname
        if target.is_file():
            try:
                sz = target.stat().st_size
            except OSError:
                sz = 0
            total_files += 1
            total_bytes += sz
            if verbose or dry_run:
                print(f"  {'[DRY-RUN]' if dry_run else 'rm':<12} {fname}  ({_size_fmt(sz)})")
            if not dry_run:
                target.unlink(missing_ok=True)

    # 5. Summary ------------------------------------------------------------
    print(f"\n{'Would clean' if dry_run else 'Cleaned'} {total_files} files ({_size_fmt(total_bytes)}).")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clean up test / dev / build garbage from the project.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without actually removing anything.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print every path that is removed.",
    )
    parser.add_argument(
        "--keep-reflex",
        action="store_true",
        help="Skip .web/ and reflex.lock/ (preserve Reflex hot-reload cache).",
    )
    args = parser.parse_args()

    # Locate project root (parent of this script)
    project_root = Path(__file__).resolve().parent.parent

    # Safety: refuse to run if the project root doesn't look right
    if not (project_root / "pyproject.toml").exists():
        print(f"ERROR: Project root not found at {project_root}", file=sys.stderr)
        print("This script must live in <project>/scripts/cleanup.py", file=sys.stderr)
        sys.exit(1)

    print(f"Project root: {project_root}")
    print(f"Mode: {'DRY-RUN' if args.dry_run else 'LIVE'}\n")

    cleanup(
        project_root,
        dry_run=args.dry_run,
        verbose=args.verbose,
        keep_reflex=args.keep_reflex,
    )


if __name__ == "__main__":
    main()
