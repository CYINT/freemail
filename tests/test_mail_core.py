import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from freemail_api.mail_core import probe_mail_core


@contextmanager
def banner_server(banner: bytes) -> Iterator[int]:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def serve_once() -> None:
        connection, _address = server.accept()
        with connection:
            connection.sendall(banner)
        server.close()

    thread = threading.Thread(target=serve_once, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        thread.join(timeout=2)
        try:
            server.close()
        except OSError:
            pass


def test_probe_reports_text_protocol_banner_ready():
    with banner_server(b"220 smtp.example ESMTP\r\n") as smtp_port:
        result = probe_mail_core(
            host="127.0.0.1",
            smtp_port=smtp_port,
            submission_port=1,
            imap_port=1,
            jmap_port=1,
            timeout_seconds=0.2,
        )

    smtp_probe = result["probes"][0]
    assert smtp_probe["name"] == "smtp"
    assert smtp_probe["tcp_connect"] is True
    assert smtp_probe["protocol_ready"] is True


def test_probe_distinguishes_tcp_connect_from_protocol_ready():
    with banner_server(b"") as smtp_port:
        result = probe_mail_core(
            host="127.0.0.1",
            smtp_port=smtp_port,
            submission_port=1,
            imap_port=1,
            jmap_port=1,
            timeout_seconds=0.2,
        )

    smtp_probe = result["probes"][0]
    assert smtp_probe["tcp_connect"] is True
    assert smtp_probe["protocol_ready"] is False
    assert result["protocolReady"] is False
