from __future__ import annotations

import http.client
import socket
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PortProbe:
    name: str
    host: str
    port: int
    tcp_connect: bool
    protocol_ready: bool
    detail: str


def probe_mail_core(
    host: str,
    smtp_port: int,
    submission_port: int,
    imap_port: int,
    jmap_port: int,
    timeout_seconds: float = 2.0,
) -> dict[str, object]:
    probes = [
        _probe_text_protocol("smtp", host, smtp_port, expected_prefixes=("220",), timeout_seconds=timeout_seconds),
        _probe_text_protocol(
            "submission",
            host,
            submission_port,
            expected_prefixes=("220",),
            timeout_seconds=timeout_seconds,
        ),
        _probe_text_protocol("imap", host, imap_port, expected_prefixes=("* OK",), timeout_seconds=timeout_seconds),
        _probe_http("jmap", host, jmap_port, timeout_seconds=timeout_seconds),
    ]
    return {
        "status": "ready" if all(probe.protocol_ready for probe in probes) else "bootstrap-or-not-configured",
        "tcpReachable": all(probe.tcp_connect for probe in probes),
        "protocolReady": all(probe.protocol_ready for probe in probes),
        "probes": [asdict(probe) for probe in probes],
    }


def _probe_text_protocol(
    name: str,
    host: str,
    port: int,
    expected_prefixes: tuple[str, ...],
    timeout_seconds: float,
) -> PortProbe:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds) as sock:
            sock.settimeout(timeout_seconds)
            try:
                banner = sock.recv(512).decode("utf-8", errors="replace").strip()
            except TimeoutError:
                banner = ""
            ready = any(banner.startswith(prefix) for prefix in expected_prefixes)
            detail = banner if banner else "TCP connected but no protocol banner was received"
            return PortProbe(name, host, port, tcp_connect=True, protocol_ready=ready, detail=detail)
    except OSError as error:
        return PortProbe(name, host, port, tcp_connect=False, protocol_ready=False, detail=str(error))


def _probe_http(name: str, host: str, port: int, timeout_seconds: float) -> PortProbe:
    try:
        connection = http.client.HTTPConnection(host, port, timeout=timeout_seconds)
        connection.request("GET", "/admin")
        response = connection.getresponse()
        response.read()
        ready = response.status in {200, 302, 401}
        return PortProbe(
            name,
            host,
            port,
            tcp_connect=True,
            protocol_ready=ready,
            detail=f"HTTP {response.status}",
        )
    except OSError as error:
        return PortProbe(name, host, port, tcp_connect=False, protocol_ready=False, detail=str(error))
    finally:
        try:
            connection.close()
        except UnboundLocalError:
            pass
