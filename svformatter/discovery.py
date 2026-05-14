from __future__ import annotations

from fnmatch import fnmatch
import os
from pathlib import Path

from svformatter.config import RuntimeConfig


def discover_sv_files(runtime: RuntimeConfig) -> list[Path]:
    if not runtime.target_dir.exists():
        raise FileNotFoundError(f"Target directory not found: {runtime.target_dir}")

    allowed_exts = {f".{extension.lower().lstrip('.')}" for extension in runtime.hdl_extensions}
    excluded_folders = {folder.strip("\\/").lower() for folder in runtime.exclude_folders if folder}
    discovered: list[Path] = []

    for root, dirs, files in os.walk(runtime.target_dir):
        dirs[:] = sorted(
            directory
            for directory in dirs
            if directory.lower() not in excluded_folders
        )

        for filename in sorted(files):
            path = (Path(root) / filename).resolve()
            if path.suffix.lower() not in allowed_exts:
                continue
            if _matches_excluded_glob(path, runtime):
                continue
            discovered.append(path)

    return discovered


def _matches_excluded_glob(path: Path, runtime: RuntimeConfig) -> bool:
    if not runtime.exclude_globs:
        return False

    try:
        relative = path.relative_to(runtime.target_dir).as_posix()
    except ValueError:
        relative = path.as_posix()

    return any(fnmatch(relative, pattern) or fnmatch(path.name, pattern) for pattern in runtime.exclude_globs)
