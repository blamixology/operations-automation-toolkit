from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Callable

from .common import CheckResult, load_json, utc_now

Executor = Callable[[list[str], int], subprocess.CompletedProcess[str]]


def default_executor(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _command_for(host: dict, check: dict) -> list[str]:
    command = check.get("command")
    if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
        raise ValueError(f"check {check.get('name', '<unnamed>')} requires a non-empty command list")

    transport = host.get("transport", "ssh")
    if transport == "local":
        return command
    if transport != "ssh":
        raise ValueError(f"unsupported transport: {transport}")

    address = host.get("address")
    user = host.get("user")
    if not address or not user:
        raise ValueError("SSH hosts require address and user")

    return [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", f"ConnectTimeout={int(host.get('connect_timeout_seconds', 8))}",
        "-p", str(int(host.get("port", 22))),
        f"{user}@{address}",
        "--",
        shlex.join(command),
    ]


def collect_fleet(config_path: Path, executor: Executor = default_executor) -> list[CheckResult]:
    config = load_json(config_path)
    hosts = config.get("hosts")
    if not isinstance(hosts, list) or not hosts:
        raise ValueError("inventory requires a non-empty hosts list")

    results: list[CheckResult] = []
    for host in hosts:
        name = str(host.get("name", "unnamed-host"))
        checks = host.get("checks", [])
        if not isinstance(checks, list) or not checks:
            results.append(CheckResult("fleet", name, "inventory", "UNKNOWN", "No checks configured"))
            continue

        unreachable = False
        for check in checks:
            check_name = str(check.get("name", "unnamed-check"))
            if unreachable:
                results.append(CheckResult("fleet", name, check_name, "UNKNOWN", "Host unreachable; check not attempted"))
                continue

            timeout = int(check.get("timeout_seconds", 15))
            try:
                completed = executor(_command_for(host, check), timeout)
                output = (completed.stdout or completed.stderr).strip()
                if completed.returncode == 0:
                    results.append(CheckResult("fleet", name, check_name, "PASS", "Command completed", output))
                else:
                    if completed.returncode == 255 and host.get("transport", "ssh") == "ssh":
                        unreachable = True
                        summary = "SSH connection failed"
                    else:
                        summary = f"Command exited with {completed.returncode}"
                    results.append(CheckResult("fleet", name, check_name, "FAIL", summary, output))
            except subprocess.TimeoutExpired:
                results.append(CheckResult("fleet", name, check_name, "FAIL", f"Timed out after {timeout}s"))
            except OSError as exc:
                unreachable = host.get("transport", "ssh") == "ssh"
                results.append(CheckResult("fleet", name, check_name, "FAIL", "Command could not start", str(exc)))
    return results


def write_markdown(path: Path, results: list[CheckResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Fleet health report",
        "",
        f"Generated: {utc_now().isoformat()}",
        "",
        "| Target | Check | Status | Summary |",
        "| --- | --- | --- | --- |",
    ]
    for result in results:
        summary = result.summary.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {result.target} | {result.check} | {result.status} | {summary} |")

    lines.extend(["", "## Evidence", ""])
    for result in results:
        lines.extend([
            f"### {result.target}: {result.check}",
            "",
            f"Status: **{result.status}** — {result.summary}",
            "",
            "```text",
            result.details or "No output captured.",
            "```",
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")

