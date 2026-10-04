from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .backups import check_backups
from .certificates import check_certificates
from .cleanup import CONFIRMATION, clean_expired
from .common import CheckResult, exit_code, write_json_report
from .fleet import collect_fleet, write_markdown
from .restore import run_restore_drills


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="opsctl", description="Safety-first operational checks and housekeeping")
    commands = root.add_subparsers(dest="command", required=True)

    fleet = commands.add_parser("fleet", help="Run declared local or SSH health checks")
    fleet.add_argument("--inventory", type=Path, required=True)
    fleet.add_argument("--output", type=Path, default=Path("reports/fleet-health.md"))

    certificates = commands.add_parser("certificates", help="Check public TLS certificate expiry")
    certificates.add_argument("--config", type=Path, required=True)
    certificates.add_argument("--output", type=Path, default=Path("reports/certificates.json"))

    backups = commands.add_parser("backups", help="Check backup presence and freshness")
    backups.add_argument("--config", type=Path, required=True)
    backups.add_argument("--output", type=Path, default=Path("reports/backups.json"))

    restore = commands.add_parser("restore", help="Safely restore and inspect the newest archive backup")
    restore.add_argument("--config", type=Path, required=True)
    restore.add_argument("--output", type=Path, default=Path("reports/restore.json"))

    cleanup = commands.add_parser("cleanup", help="Preview or apply file-retention rules")
    cleanup.add_argument("--config", type=Path, required=True)
    cleanup.add_argument("--output", type=Path, default=Path("reports/cleanup.json"))
    cleanup.add_argument("--apply", action="store_true", help="Delete candidates; default is preview only")
    cleanup.add_argument("--confirm", default="", help=f"Apply mode requires the exact value {CONFIRMATION}")
    return root


def _print_summary(results: list[CheckResult]) -> None:
    for result in results:
        print(f"{result.status:7} {result.category}/{result.target}/{result.check}: {result.summary}")


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if arguments.command == "fleet":
            results = collect_fleet(arguments.inventory)
            write_markdown(arguments.output, results)
        elif arguments.command == "certificates":
            results = check_certificates(arguments.config)
            write_json_report(arguments.output, results)
        elif arguments.command == "backups":
            results = check_backups(arguments.config)
            write_json_report(arguments.output, results)
        elif arguments.command == "restore":
            results = run_restore_drills(arguments.config)
            write_json_report(arguments.output, results)
        else:
            results = clean_expired(arguments.config, arguments.apply, arguments.confirm)
            write_json_report(arguments.output, results)
    except (KeyError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    _print_summary(results)
    return exit_code(results)
