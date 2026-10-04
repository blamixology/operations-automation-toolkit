from __future__ import annotations

import fnmatch
from datetime import datetime, timezone
from pathlib import Path

from .common import CheckResult, load_json, resolve_from_config

CONFIRMATION = "DELETE_EXPIRED_FILES"


def _is_protected(path: Path, root: Path, patterns: list[str]) -> bool:
    relative = path.relative_to(root).as_posix()
    return any(fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(path.name, pattern) for pattern in patterns)


def clean_expired(config_path: Path, apply: bool = False, confirmation: str = "") -> list[CheckResult]:
    if apply and confirmation != CONFIRMATION:
        raise ValueError(f"apply mode requires --confirm {CONFIRMATION}")

    config = load_json(config_path)
    rules = config.get("rules")
    if not isinstance(rules, list) or not rules:
        raise ValueError("cleanup config requires a non-empty rules list")

    now = datetime.now(timezone.utc).timestamp()
    results: list[CheckResult] = []
    for rule in rules:
        name = str(rule.get("name", "unnamed-rule"))
        root = resolve_from_config(config_path, str(rule["path"]))
        pattern = str(rule.get("pattern", "*"))
        older_than_days = float(rule["older_than_days"])
        protected = [str(item) for item in rule.get("protect", [])]

        if not root.exists() or not root.is_dir():
            results.append(CheckResult("cleanup", name, "path", "FAIL", "Cleanup root is not a directory", str(root)))
            continue

        candidates: list[Path] = []
        for path in root.glob(pattern):
            if not path.is_file() or path.is_symlink() or _is_protected(path, root, protected):
                continue
            age_days = (now - path.stat().st_mtime) / 86400
            if age_days >= older_than_days:
                candidates.append(path)

        if apply:
            for path in candidates:
                path.unlink()
            action = "Deleted"
        else:
            action = "Would delete"

        details = "\n".join(str(path) for path in candidates) or "No expired files."
        results.append(CheckResult(
            "cleanup", name, "retention", "PASS",
            f"{action} {len(candidates)} file(s)", details,
        ))
    return results

