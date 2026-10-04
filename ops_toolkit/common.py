from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CheckResult:
    category: str
    target: str
    check: str
    status: str
    summary: str
    details: str = ""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def resolve_from_config(config_path: Path, configured_path: str) -> Path:
    path = Path(configured_path)
    if not path.is_absolute():
        path = config_path.resolve().parent / path
    return path.resolve()


def write_json_report(path: Path, results: list[CheckResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": utc_now().isoformat(),
        "results": [asdict(result) for result in results],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def exit_code(results: list[CheckResult]) -> int:
    return 1 if any(result.status == "FAIL" for result in results) else 0

