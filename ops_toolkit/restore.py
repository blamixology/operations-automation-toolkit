from __future__ import annotations

import shutil
import stat
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from .common import CheckResult, load_json, resolve_from_config


def _safe_target(root: Path, member_name: str) -> Path:
    normalized = PurePosixPath(member_name.replace("\\", "/"))
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ValueError(f"unsafe archive path: {member_name}")
    target = root.joinpath(*normalized.parts).resolve()
    resolved_root = root.resolve()
    if target != resolved_root and resolved_root not in target.parents:
        raise ValueError(f"archive path escapes restore root: {member_name}")
    return target


def _extract_zip(archive_path: Path, destination: Path, max_files: int, max_bytes: int) -> tuple[int, int]:
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        files = [member for member in members if not member.is_dir()]
        total_bytes = sum(member.file_size for member in files)
        if len(files) > max_files:
            raise ValueError(f"archive contains {len(files)} files; limit is {max_files}")
        if total_bytes > max_bytes:
            raise ValueError(f"expanded size {total_bytes} exceeds limit {max_bytes}")

        for member in members:
            mode = (member.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                raise ValueError(f"symbolic links are not allowed: {member.filename}")
            target = _safe_target(destination, member.filename)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
    return len(files), total_bytes


def _extract_tar(archive_path: Path, destination: Path, max_files: int, max_bytes: int) -> tuple[int, int]:
    with tarfile.open(archive_path, mode="r:*") as archive:
        members = archive.getmembers()
        files = [member for member in members if member.isfile()]
        total_bytes = sum(member.size for member in files)
        if len(files) > max_files:
            raise ValueError(f"archive contains {len(files)} files; limit is {max_files}")
        if total_bytes > max_bytes:
            raise ValueError(f"expanded size {total_bytes} exceeds limit {max_bytes}")

        for member in members:
            if member.issym() or member.islnk():
                raise ValueError(f"archive links are not allowed: {member.name}")
            if not member.isdir() and not member.isfile():
                raise ValueError(f"unsupported archive member: {member.name}")
            target = _safe_target(destination, member.name)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            source = archive.extractfile(member)
            if source is None:
                raise ValueError(f"could not read archive member: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
    return len(files), total_bytes


def _extract(archive_path: Path, destination: Path, max_files: int, max_bytes: int) -> tuple[int, int]:
    if zipfile.is_zipfile(archive_path):
        return _extract_zip(archive_path, destination, max_files, max_bytes)
    if tarfile.is_tarfile(archive_path):
        return _extract_tar(archive_path, destination, max_files, max_bytes)
    raise ValueError("unsupported or corrupt archive; expected ZIP or TAR-compatible input")


def run_restore_drills(config_path: Path) -> list[CheckResult]:
    config = load_json(config_path)
    archives = config.get("archives")
    if not isinstance(archives, list) or not archives:
        raise ValueError("restore config requires a non-empty archives list")

    results: list[CheckResult] = []
    for definition in archives:
        name = str(definition.get("name", "unnamed-archive"))
        root = resolve_from_config(config_path, str(definition["path"]))
        pattern = str(definition.get("pattern", "*"))
        max_files = int(definition.get("max_files", 10_000))
        max_bytes = int(definition.get("max_expanded_bytes", 1_073_741_824))
        required_paths = [str(path) for path in definition.get("required_paths", [])]
        candidates = sorted(
            (path for path in root.glob(pattern) if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            results.append(CheckResult(
                "restore", name, "archive", "FAIL", "No archive matched",
                f"path={root} pattern={pattern}",
            ))
            continue

        archive_path = candidates[0]
        try:
            with tempfile.TemporaryDirectory(prefix="ops-restore-") as temporary:
                destination = Path(temporary)
                file_count, expanded_bytes = _extract(archive_path, destination, max_files, max_bytes)
                missing = [
                    path for path in required_paths
                    if not _safe_target(destination, path).exists()
                ]
                if missing:
                    raise ValueError(f"required restored paths are missing: {', '.join(missing)}")
                details = (
                    f"archive={archive_path}\nfiles={file_count}\n"
                    f"expanded_bytes={expanded_bytes}\nrequired_paths={len(required_paths)}"
                )
                results.append(CheckResult(
                    "restore", name, "archive", "PASS",
                    "Archive restored and required paths verified", details,
                ))
        except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile) as exc:
            results.append(CheckResult(
                "restore", name, "archive", "FAIL", "Restore drill failed",
                f"archive={archive_path}\nerror={exc}",
            ))
    return results

