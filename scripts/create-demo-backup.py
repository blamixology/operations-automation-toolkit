from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path


repository = Path(__file__).resolve().parent.parent
backup_directory = repository / "examples" / "backups"
backup_directory.mkdir(parents=True, exist_ok=True)
timestamp = datetime.now(timezone.utc)
archive_path = backup_directory / f"application-export-{timestamp:%Y%m%dT%H%M%SZ}.zip"

metadata = {
    "created_at": timestamp.isoformat(),
    "format_version": 1,
    "records": 2,
}
records = [
    {"id": 1, "status": "active"},
    {"id": 2, "status": "archived"},
]

with zipfile.ZipFile(archive_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
    archive.writestr("metadata.json", json.dumps(metadata, indent=2) + "\n")
    archive.writestr("data/export.json", json.dumps(records, indent=2) + "\n")

print(archive_path)

