from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .common import CheckResult, load_json, resolve_from_config


def check_backups(config_path: Path) -> list[CheckResult]:
    config = load_json(config_path)
    backup_sets = config.get("backup_sets")
    if not isinstance(backup_sets, list) or not backup_sets:
        raise ValueError("backup config requires a non-empty backup_sets list")

    now = datetime.now(timezone.utc).timestamp()
    results: list[CheckResult] = []
    for backup_set in backup_sets:
        name = str(backup_set.get("name", "unnamed-backup"))
        root = resolve_from_config(config_path, str(backup_set["path"]))
        pattern = str(backup_set.get("pattern", "*"))
        minimum_files = int(backup_set.get("minimum_files", 1))
        maximum_age = float(backup_set.get("max_age_hours", 24))
        files = sorted((path for path in root.glob(pattern) if path.is_file()), key=lambda path: path.stat().st_mtime, reverse=True)

        if len(files) < minimum_files:
            results.append(CheckResult(
                "backup", name, "freshness", "FAIL",
                f"Found {len(files)} files; require at least {minimum_files}",
                f"path={root} pattern={pattern}",
            ))
            continue

        newest = files[0]
        age_hours = (now - newest.stat().st_mtime) / 3600
        status = "PASS" if age_hours <= maximum_age else "FAIL"
        results.append(CheckResult(
            "backup", name, "freshness", status,
            f"Newest backup is {age_hours:.1f}h old",
            f"file={newest} size_bytes={newest.stat().st_size} files_found={len(files)}",
        ))
    return results

