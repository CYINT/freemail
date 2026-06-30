from collections.abc import Iterator
from contextlib import asynccontextmanager
import imaplib
import sqlite3

from fastapi import Depends, FastAPI, Header, HTTPException, status

from . import database
from . import dkim
from .mail_core import probe_mail_core
from .mailbox_imap import list_mailbox_snapshot
from .schemas import (
    AliasCreate,
    AliasRecord,
    AuditRecord,
    BootstrapAdminCreate,
    BootstrapAdminRecord,
    DkimKeyCreate,
    DkimKeyCreated,
    DkimKeyRecord,
    DnsRecord,
    DomainDnsGuidance,
    DomainCreate,
    DomainRecord,
    MailboxCreate,
    MailboxRecord,
    MailboxSnapshotRecord,
    UserCreate,
    UserRecord,
)
from .settings import get_settings
from .settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        database.initialize(active_settings.database_path)
        yield

    app = FastAPI(
        title="FreeMail API",
        version=active_settings.release_version,
        description="Admin and runtime API for the AGPL FreeMail mail platform.",
        lifespan=lifespan,
    )

    def require_admin(x_freemail_admin_token: str | None = Header(default=None)) -> str:
        if not active_settings.admin_api_token:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Admin API token is not configured",
            )
        if x_freemail_admin_token != active_settings.admin_api_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin API token")
        return "admin-api"

    def require_bootstrap(x_freemail_bootstrap_token: str | None = Header(default=None)) -> str:
        if not active_settings.bootstrap_token:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Bootstrap token is not configured",
            )
        if x_freemail_bootstrap_token != active_settings.bootstrap_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bootstrap token")
        return "bootstrap-api"

    def get_connection() -> Iterator[sqlite3.Connection]:
        with database.connect(active_settings.database_path) as connection:
            yield connection

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "service": "freemail",
            "hostname": active_settings.hostname,
            "vpnOnly": active_settings.vpn_only,
            "release": {
                "version": active_settings.release_version,
                "commit": active_settings.release_commit,
            },
            "components": {
                "adminApi": "ready",
                "mailCore": "candidate-spike",
                "webmail": "scaffolded",
                "mobile": "planned",
            },
        }

    @app.get("/api/v1/product")
    def product() -> dict[str, object]:
        return {
            "name": active_settings.app_name,
            "license": "AGPL-3.0-or-later",
            "scope": [
                "mail-core",
                "admin-api",
                "webmail",
                "mobile-client",
                "deliverability-controls",
                "backup-restore",
            ],
        }

    @app.get("/api/v1/deployment")
    def deployment() -> dict[str, object]:
        return {
            "hostname": active_settings.hostname,
            "exposure": "vpn-only",
            "publicInternet": False,
            "requiredBoundary": "Dragonscale/VPN clients only",
        }

    @app.get("/api/v1/mail-core/readiness")
    def mail_core_readiness() -> dict[str, object]:
        return probe_mail_core(
            host=active_settings.mail_core_host,
            smtp_port=active_settings.smtp_port,
            submission_port=active_settings.submission_port,
            imap_port=active_settings.imap_port,
            jmap_port=active_settings.jmap_port,
        )

    @app.get("/api/v1/mailbox/snapshot", response_model=MailboxSnapshotRecord)
    def mailbox_snapshot(
        folder: str = "INBOX",
        limit: int = 25,
        x_freemail_mailbox_email: str | None = Header(default=None),
        x_freemail_mailbox_password: str | None = Header(default=None),
    ) -> dict[str, object]:
        if not x_freemail_mailbox_email or not x_freemail_mailbox_password:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Mailbox credentials required")
        if limit < 1 or limit > 100:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="limit must be between 1 and 100")
        try:
            snapshot = list_mailbox_snapshot(
                email=x_freemail_mailbox_email,
                password=x_freemail_mailbox_password,
                host=active_settings.mail_core_host,
                port=active_settings.imap_port,
                folder=folder,
                limit=limit,
            )
        except OSError as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
        except imaplib.IMAP4.error as error:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Mailbox authentication failed") from error
        return snapshot.as_dict()

    @app.post("/api/v1/bootstrap/admin", response_model=BootstrapAdminRecord, status_code=status.HTTP_201_CREATED)
    def bootstrap_admin(
        payload: BootstrapAdminCreate,
        actor: str = Depends(require_bootstrap),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, dict[str, object]]:
        result = _create_or_raise(lambda: database.bootstrap_admin(connection, payload, actor))
        return {
            "domain": _row_to_dict(result["domain"]),
            "user": _row_to_dict(result["user"]),
            "mailbox": _row_to_dict(result["mailbox"]),
        }

    @app.get("/api/v1/admin/domains", response_model=list[DomainRecord])
    def list_domains(
        _actor: str = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> list[dict[str, object]]:
        return _rows_to_dicts(database.list_rows(connection, "domains"))

    @app.post("/api/v1/admin/domains", response_model=DomainRecord, status_code=status.HTTP_201_CREATED)
    def add_domain(
        payload: DomainCreate,
        actor: str = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        return _row_to_dict(_create_or_raise(lambda: database.create_domain(connection, payload, actor)))

    @app.get("/api/v1/admin/users", response_model=list[UserRecord])
    def list_users(
        _actor: str = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> list[dict[str, object]]:
        return _rows_to_dicts(database.list_rows(connection, "users"))

    @app.post("/api/v1/admin/users", response_model=UserRecord, status_code=status.HTTP_201_CREATED)
    def add_user(
        payload: UserCreate,
        actor: str = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        return _row_to_dict(_create_or_raise(lambda: database.create_user(connection, payload, actor)))

    @app.get("/api/v1/admin/mailboxes", response_model=list[MailboxRecord])
    def list_mailboxes(
        _actor: str = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> list[dict[str, object]]:
        return _rows_to_dicts(database.list_rows(connection, "mailboxes"))

    @app.post("/api/v1/admin/mailboxes", response_model=MailboxRecord, status_code=status.HTTP_201_CREATED)
    def add_mailbox(
        payload: MailboxCreate,
        actor: str = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        return _row_to_dict(_create_or_raise(lambda: database.create_mailbox(connection, payload, actor)))

    @app.get("/api/v1/admin/aliases", response_model=list[AliasRecord])
    def list_aliases(
        _actor: str = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> list[dict[str, object]]:
        return _rows_to_dicts(database.list_rows(connection, "aliases"))

    @app.post("/api/v1/admin/aliases", response_model=AliasRecord, status_code=status.HTTP_201_CREATED)
    def add_alias(
        payload: AliasCreate,
        actor: str = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        return _row_to_dict(_create_or_raise(lambda: database.create_alias(connection, payload, actor)))

    @app.get("/api/v1/admin/dkim-keys", response_model=list[DkimKeyRecord])
    def list_dkim_keys(
        _actor: str = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> list[dict[str, object]]:
        return _rows_to_dicts(database.list_rows(connection, "dkim_keys"))

    @app.post("/api/v1/admin/dkim-keys", response_model=DkimKeyCreated, status_code=status.HTTP_201_CREATED)
    def add_dkim_key(
        payload: DkimKeyCreate,
        actor: str = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        public_txt, private_key_pem = dkim.generate_dkim_key_pair()
        row = _create_or_raise(
            lambda: database.create_dkim_key(connection, payload, public_txt, private_key_pem, actor)
        )
        return _row_to_dict(row)

    @app.get("/api/v1/admin/domains/{domain_id}/dns", response_model=DomainDnsGuidance)
    def domain_dns_guidance(
        domain_id: int,
        _actor: str = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> DomainDnsGuidance:
        try:
            domain = database.get_domain(connection, domain_id)
            dkim_keys = database.list_dkim_keys_for_domain(connection, domain_id)
        except database.MissingRecordError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
        records = [
            DnsRecord(
                type="MX",
                name=str(domain["name"]),
                value=f"10 {active_settings.hostname}.",
                purpose="Route inbound mail to the FreeMail host.",
            ),
            DnsRecord(
                type="TXT",
                name=str(domain["name"]),
                value="v=spf1 mx -all",
                purpose="Authorize MX hosts for outbound mail during the controlled deployment phase.",
            ),
            DnsRecord(
                type="TXT",
                name=f"_dmarc.{domain['name']}",
                value="v=DMARC1; p=quarantine; rua=mailto:postmaster@{domain}".format(domain=domain["name"]),
                purpose="Enable DMARC reporting and quarantine policy for spoofing protection.",
            ),
        ]
        records.extend(
            DnsRecord(
                type="TXT",
                name=str(row["dns_name"]),
                value=str(row["public_txt"]),
                purpose="Publish DKIM public key for message signature verification.",
            )
            for row in dkim_keys
        )
        return DomainDnsGuidance(domain=str(domain["name"]), records=records)

    @app.get("/api/v1/admin/audit-log", response_model=list[AuditRecord])
    def audit_log(
        _actor: str = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> list[dict[str, object]]:
        return _rows_to_dicts(database.list_rows(connection, "audit_log"))

    return app


def _create_or_raise(create_record):
    try:
        return create_record()
    except database.DuplicateRecordError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except database.MissingRecordError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


def _row_to_dict(row: sqlite3.Row) -> dict[str, object]:
    return dict(row)


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, object]]:
    return [_row_to_dict(row) for row in rows]


app = create_app()
