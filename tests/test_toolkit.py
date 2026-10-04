from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ops_toolkit.backups import check_backups
from ops_toolkit.certificates import check_certificates
from ops_toolkit.cleanup import CONFIRMATION, clean_expired
from ops_toolkit.fleet import collect_fleet
from ops_toolkit.restore import run_restore_drills


class ToolkitTests(unittest.TestCase):
    def write_config(self, directory: Path, name: str, value: dict) -> Path:
        path = directory / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_fleet_marks_remaining_checks_unknown_after_ssh_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = self.write_config(root, "inventory.json", {
                "hosts": [{
                    "name": "offline-node", "transport": "ssh", "address": "192.0.2.1", "user": "ops",
                    "checks": [
                        {"name": "uptime", "command": ["uptime"]},
                        {"name": "disk", "command": ["df", "-h"]},
                    ],
                }]
            })

            def failed_ssh(command, timeout):
                return subprocess.CompletedProcess(command, 255, "", "connection refused")

            results = collect_fleet(config, executor=failed_ssh)
            self.assertEqual([result.status for result in results], ["FAIL", "UNKNOWN"])
            self.assertIn("unreachable", results[1].summary.lower())

    def test_backup_freshness_passes_for_recent_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            backups = root / "backups"
            backups.mkdir()
            (backups / "database.dump").write_bytes(b"verified-test-backup")
            config = self.write_config(root, "backups.json", {
                "backup_sets": [{"name": "database", "path": "backups", "pattern": "*.dump", "max_age_hours": 1}]
            })
            self.assertEqual(check_backups(config)[0].status, "PASS")

    def test_backup_freshness_fails_for_stale_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            backups = root / "backups"
            backups.mkdir()
            backup = backups / "database.dump"
            backup.write_bytes(b"stale-test-backup")
            old = (datetime.now(timezone.utc) - timedelta(hours=48)).timestamp()
            os.utime(backup, (old, old))
            config = self.write_config(root, "backups.json", {
                "backup_sets": [{"name": "database", "path": "backups", "pattern": "*.dump", "max_age_hours": 24}]
            })
            self.assertEqual(check_backups(config)[0].status, "FAIL")

    def test_cleanup_is_dry_run_by_default_and_protects_matches(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            logs = root / "logs"
            logs.mkdir()
            expired = logs / "app.log.1.gz"
            protected = logs / "audit-app.log.1.gz"
            expired.write_text("old", encoding="utf-8")
            protected.write_text("important", encoding="utf-8")
            old = (datetime.now(timezone.utc) - timedelta(days=30)).timestamp()
            os.utime(expired, (old, old))
            os.utime(protected, (old, old))
            config = self.write_config(root, "cleanup.json", {
                "rules": [{
                    "name": "logs", "path": "logs", "pattern": "*.gz",
                    "older_than_days": 14, "protect": ["audit-*"]
                }]
            })

            result = clean_expired(config)[0]
            self.assertTrue(expired.exists())
            self.assertTrue(protected.exists())
            self.assertIn("Would delete 1", result.summary)

            clean_expired(config, apply=True, confirmation=CONFIRMATION)
            self.assertFalse(expired.exists())
            self.assertTrue(protected.exists())

    def test_certificate_thresholds(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = self.write_config(root, "certificates.json", {
                "endpoints": [{"name": "api", "host": "example.test", "warning_days": 30, "critical_days": 14}]
            })
            expiry = datetime.now(timezone.utc) + timedelta(days=20)
            results = check_certificates(config, probe=lambda host, port, timeout: expiry)
            self.assertEqual(results[0].status, "WARN")

    def test_restore_drill_extracts_and_verifies_required_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            backups = root / "backups"
            backups.mkdir()
            with zipfile.ZipFile(backups / "export.zip", mode="w") as archive:
                archive.writestr("metadata.json", "{}")
                archive.writestr("data/export.json", "[]")
            config = self.write_config(root, "restore.json", {
                "archives": [{
                    "name": "export", "path": "backups", "pattern": "*.zip",
                    "max_files": 10, "max_expanded_bytes": 1024,
                    "required_paths": ["metadata.json", "data/export.json"]
                }]
            })
            result = run_restore_drills(config)[0]
            self.assertEqual(result.status, "PASS")
            self.assertIn("files=2", result.details)

    def test_restore_drill_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            backups = root / "backups"
            backups.mkdir()
            with zipfile.ZipFile(backups / "malicious.zip", mode="w") as archive:
                archive.writestr("../../escape.txt", "unsafe")
            config = self.write_config(root, "restore.json", {
                "archives": [{"name": "malicious", "path": "backups", "pattern": "*.zip"}]
            })
            result = run_restore_drills(config)[0]
            self.assertEqual(result.status, "FAIL")
            self.assertIn("unsafe archive path", result.details)
            self.assertFalse((root.parent / "escape.txt").exists())


if __name__ == "__main__":
    unittest.main()
