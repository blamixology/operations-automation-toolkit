from __future__ import annotations

import socket
import ssl
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .common import CheckResult, load_json

Probe = Callable[[str, int, int], datetime]


def probe_expiry(host: str, port: int, timeout: int) -> datetime:
    context = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=timeout) as connection:
        with context.wrap_socket(connection, server_hostname=host) as tls_socket:
            certificate = tls_socket.getpeercert()
    not_after = certificate.get("notAfter")
    if not not_after:
        raise ValueError("peer certificate has no notAfter value")
    timestamp = ssl.cert_time_to_seconds(not_after)
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def check_certificates(config_path: Path, probe: Probe = probe_expiry) -> list[CheckResult]:
    config = load_json(config_path)
    endpoints = config.get("endpoints")
    if not isinstance(endpoints, list) or not endpoints:
        raise ValueError("certificate config requires a non-empty endpoints list")

    now = datetime.now(timezone.utc)
    results: list[CheckResult] = []
    for endpoint in endpoints:
        name = str(endpoint.get("name", endpoint.get("host", "unnamed-endpoint")))
        host = str(endpoint["host"])
        port = int(endpoint.get("port", 443))
        warning_days = int(endpoint.get("warning_days", 30))
        critical_days = int(endpoint.get("critical_days", 14))
        timeout = int(endpoint.get("timeout_seconds", 8))
        try:
            expires_at = probe(host, port, timeout)
            remaining = (expires_at - now).total_seconds() / 86400
            if remaining < critical_days:
                status = "FAIL"
            elif remaining < warning_days:
                status = "WARN"
            else:
                status = "PASS"
            results.append(CheckResult(
                "certificate", name, "expiry", status,
                f"{remaining:.1f} days remaining",
                f"expires_at={expires_at.isoformat()} host={host} port={port}",
            ))
        except (OSError, ssl.SSLError, ValueError) as exc:
            results.append(CheckResult("certificate", name, "expiry", "FAIL", "TLS probe failed", str(exc)))
    return results

