from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import stat
import time


@dataclass(frozen=True)
class CachePruneResult:
    removed_files: int = 0
    removed_bytes: int = 0


@dataclass(frozen=True)
class CacheUsage:
    file_count: int = 0
    total_bytes: int = 0


@dataclass(frozen=True)
class CacheClearResult:
    removed_files: int = 0
    removed_bytes: int = 0
    skipped_files: int = 0
    skipped_bytes: int = 0


def _unlink(path: Path) -> tuple[int, int]:
    try:
        size = path.stat().st_size
        path.unlink()
    except OSError:
        return 0, 0
    return 1, size


def audio_cache_usage(directory: Path) -> CacheUsage:
    """Return the space used by regular files directly in an audio cache directory."""
    if not directory.exists():
        return CacheUsage()

    try:
        paths = list(directory.iterdir())
    except OSError:
        return CacheUsage()

    file_count = 0
    total_bytes = 0
    for path in paths:
        try:
            info = path.lstat()
        except OSError:
            continue
        if not stat.S_ISREG(info.st_mode):
            continue
        file_count += 1
        total_bytes += info.st_size

    return CacheUsage(file_count=file_count, total_bytes=total_bytes)


def clear_audio_cache(
    directory: Path,
    *,
    protected_paths: set[Path] | None = None,
) -> CacheClearResult:
    """Remove regular cache files while leaving protected files untouched."""
    if not directory.exists():
        return CacheClearResult()

    protected = {path.resolve(strict=False) for path in (protected_paths or set())}
    try:
        paths = list(directory.iterdir())
    except OSError:
        return CacheClearResult()

    removed_files = 0
    removed_bytes = 0
    skipped_files = 0
    skipped_bytes = 0
    for path in paths:
        try:
            info = path.lstat()
        except OSError:
            continue
        if not stat.S_ISREG(info.st_mode):
            continue

        if path.resolve(strict=False) in protected:
            skipped_files += 1
            skipped_bytes += info.st_size
            continue

        try:
            path.unlink()
        except OSError:
            continue
        removed_files += 1
        removed_bytes += info.st_size

    return CacheClearResult(
        removed_files=removed_files,
        removed_bytes=removed_bytes,
        skipped_files=skipped_files,
        skipped_bytes=skipped_bytes,
    )


def prune_audio_cache(
    directory: Path,
    *,
    max_bytes: int = 0,
    ttl_seconds: float = 0,
    partial_ttl_seconds: float = 3600,
    protected_paths: set[Path] | None = None,
    now: float | None = None,
) -> CachePruneResult:
    if not directory.exists():
        return CachePruneResult()

    now = time.time() if now is None else now
    protected = {path.resolve(strict=False) for path in (protected_paths or set())}
    retained: list[tuple[Path, int, float]] = []
    removed_files = 0
    removed_bytes = 0

    try:
        paths = list(directory.iterdir())
    except OSError:
        return CachePruneResult()

    for path in paths:
        try:
            if not path.is_file():
                continue
            stat = path.stat()
        except OSError:
            continue

        resolved = path.resolve(strict=False)
        age = max(0.0, now - stat.st_mtime)
        is_partial = path.name.endswith(".part")
        if is_partial:
            if partial_ttl_seconds > 0 and age >= partial_ttl_seconds:
                files, size = _unlink(path)
                removed_files += files
                removed_bytes += size
            continue

        if ttl_seconds > 0 and age >= ttl_seconds:
            files, size = _unlink(path)
            removed_files += files
            removed_bytes += size
            continue

        retained.append((path, stat.st_size, stat.st_mtime))

    total_bytes = sum(size for _, size, _ in retained)
    if max_bytes > 0 and total_bytes > max_bytes:
        for path, size, _ in sorted(retained, key=lambda item: (item[2], item[0].name)):
            if total_bytes <= max_bytes:
                break
            if path.resolve(strict=False) in protected:
                continue
            files, removed_size = _unlink(path)
            if files:
                total_bytes -= removed_size
                removed_files += files
                removed_bytes += removed_size

    return CachePruneResult(removed_files=removed_files, removed_bytes=removed_bytes)
