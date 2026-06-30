import binascii
from collections.abc import Iterator
from contextlib import asynccontextmanager
from hashlib import sha256
import imaplib
import smtplib
import sqlite3
from urllib.parse import quote

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware

from . import database
from . import dkim
from .attachment_policy import AttachmentPolicy
from .attachment_policy import AttachmentPolicyError
from .attachment_policy import parse_allowed_content_types
from .attachment_policy import validate_attachments
from .dns_policy import domain_dns_records
from .dns_policy import verify_dns_posture
from .mail_core import probe_mail_core
from .mailbox_imap import archive_mailbox_message
from .mailbox_imap import create_mailbox_folder
from .mailbox_imap import delete_mailbox_folder
from .mailbox_imap import get_mailbox_attachment
from .mailbox_imap import get_mailbox_message
from .mailbox_imap import list_mailbox_contacts
from .mailbox_imap import list_mailbox_snapshot
from .mailbox_imap import move_mailbox_message
from .mailbox_imap import rename_mailbox_folder
from .mailbox_imap import search_mailbox_messages
from .mailbox_smtp import OutboundAttachment
from .mailbox_smtp import send_mailbox_message
from .outbound_policy import enforce_outbound_rate_limit
from .outbound_policy import OutboundRateLimitExceeded
from .outbound_policy import OutboundRatePolicy
from .outbound_policy import record_outbound_send
from .schemas import (
    AliasCreate,
    AliasRecord,
    AuditRecord,
    BootstrapAdminCreate,
    BootstrapAdminRecord,
    DkimKeyCreate,
    DkimKeyCreated,
    DkimKeyRecord,
    DomainDnsGuidance,
    DomainDnsPostureCreate,
    DomainDnsPostureRecord,
    DomainCreate,
    DomainRecord,
    MailboxArchiveCreate,
    MailboxArchiveRecord,
    MailboxContactsRecord,
    MailboxCreate,
    MailboxFolderCreate,
    MailboxFolderDelete,
    MailboxFolderMutationRecord,
    MailboxFolderRename,
    MailboxMessageDetailRecord,
    MailboxMoveCreate,
    MailboxMoveRecord,
    MailboxPushDeviceCreate,
    MailboxPushDeviceDeleteRecord,
    MailboxPushDeviceRecord,
    MailboxRecord,
    MailboxSearchRecord,
    MailboxSendCreate,
    MailboxSendRecord,
    MailboxSessionCreate,
    MailboxSessionDeleteRecord,
    MailboxSessionRecord,
    MailboxSnapshotRecord,
    UserCreate,
    UserRecord,
)
from .sessions import bearer_token
from .sessions import create_mailbox_session
from .sessions import InvalidSessionError
from .sessions import MailboxCredentials
from .sessions import resolve_mailbox_session
from .sessions import revoke_mailbox_session
from .sessions import SessionConfigurationError
from .settings import get_settings
from .settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    protected_folders = {"inbox", "sent items", "drafts", "junk mail", "deleted items", "archive"}

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
    cors_origins = [origin.strip() for origin in active_settings.web_cors_origins.split(",") if origin.strip()]
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_methods=["DELETE", "GET", "PATCH", "POST", "OPTIONS"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "X-FreeMail-Mailbox-Email",
                "X-FreeMail-Mailbox-Password",
            ],
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

    def attachment_policy() -> AttachmentPolicy:
        return AttachmentPolicy(
            max_bytes=active_settings.max_attachment_bytes,
            allowed_content_types=parse_allowed_content_types(active_settings.allowed_attachment_content_types),
        )

    def outbound_rate_policy() -> OutboundRatePolicy:
        return OutboundRatePolicy(
            window_seconds=active_settings.send_rate_window_seconds,
            max_messages=active_settings.send_rate_max_messages,
            max_recipients=active_settings.send_rate_max_recipients,
        )

    def mailbox_credentials(
        *,
        authorization: str | None,
        x_freemail_mailbox_email: str | None,
        x_freemail_mailbox_password: str | None,
        connection: sqlite3.Connection,
    ) -> MailboxCredentials:
        token = bearer_token(authorization)
        if token:
            try:
                return resolve_mailbox_session(
                    connection,
                    token=token,
                    secret=active_settings.session_secret,
                )
            except SessionConfigurationError as error:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Mailbox sessions are not configured",
                ) from error
            except InvalidSessionError as error:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid mailbox session") from error
        if not x_freemail_mailbox_email or not x_freemail_mailbox_password:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Mailbox credentials required")
        return MailboxCredentials(email=x_freemail_mailbox_email, password=x_freemail_mailbox_password)

    def reject_protected_folder(folder: str, *, action: str) -> None:
        if folder.strip().lower() in protected_folders:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Core mailbox folders cannot be {action}",
            )

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
                "mobile": "foundation",
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

    @app.post("/api/v1/mailbox/session", response_model=MailboxSessionRecord)
    def mailbox_session_create(
        payload: MailboxSessionCreate,
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        try:
            list_mailbox_snapshot(
                email=str(payload.email),
                password=payload.password,
                host=active_settings.mail_core_host,
                port=active_settings.imap_port,
                folder="INBOX",
                limit=1,
            )
            created = create_mailbox_session(
                connection,
                email=str(payload.email),
                password=payload.password,
                secret=active_settings.session_secret,
                ttl_seconds=active_settings.session_ttl_seconds,
            )
        except SessionConfigurationError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Mailbox sessions are not configured",
            ) from error
        except OSError as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
        except imaplib.IMAP4.error as error:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Mailbox authentication failed") from error
        return {"token": created.token, "email": created.email, "expires_at": created.expires_at}

    @app.delete("/api/v1/mailbox/session", response_model=MailboxSessionDeleteRecord)
    def mailbox_session_delete(
        authorization: str | None = Header(default=None),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, bool]:
        token = bearer_token(authorization)
        if token:
            revoke_mailbox_session(connection, token)
        return {"revoked": True}

    @app.post("/api/v1/mailbox/push/devices", response_model=MailboxPushDeviceRecord)
    def mailbox_push_device_register(
        payload: MailboxPushDeviceCreate,
        authorization: str | None = Header(default=None),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        credentials = mailbox_credentials(
            authorization=authorization,
            x_freemail_mailbox_email=None,
            x_freemail_mailbox_password=None,
            connection=connection,
        )
        row = database.upsert_mailbox_push_device(
            connection,
            email=credentials.email,
            device_id=payload.device_id,
            platform=payload.platform,
            push_token_hash=sha256(payload.push_token.encode("utf-8")).hexdigest(),
            provider=payload.provider,
        )
        return _row_to_dict(row)

    @app.get("/api/v1/mailbox/push/devices", response_model=list[MailboxPushDeviceRecord])
    def mailbox_push_device_list(
        authorization: str | None = Header(default=None),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> list[dict[str, object]]:
        credentials = mailbox_credentials(
            authorization=authorization,
            x_freemail_mailbox_email=None,
            x_freemail_mailbox_password=None,
            connection=connection,
        )
        return _rows_to_dicts(database.list_mailbox_push_devices(connection, email=credentials.email))

    @app.delete("/api/v1/mailbox/push/devices/{device_id}", response_model=MailboxPushDeviceDeleteRecord)
    def mailbox_push_device_delete(
        device_id: str,
        authorization: str | None = Header(default=None),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        credentials = mailbox_credentials(
            authorization=authorization,
            x_freemail_mailbox_email=None,
            x_freemail_mailbox_password=None,
            connection=connection,
        )
        return {
            "revoked": database.revoke_mailbox_push_device(connection, email=credentials.email, device_id=device_id),
            "device_id": device_id,
        }

    @app.get("/api/v1/mailbox/snapshot", response_model=MailboxSnapshotRecord)
    def mailbox_snapshot(
        folder: str = "INBOX",
        limit: int = 25,
        authorization: str | None = Header(default=None),
        x_freemail_mailbox_email: str | None = Header(default=None),
        x_freemail_mailbox_password: str | None = Header(default=None),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        credentials = mailbox_credentials(
            authorization=authorization,
            x_freemail_mailbox_email=x_freemail_mailbox_email,
            x_freemail_mailbox_password=x_freemail_mailbox_password,
            connection=connection,
        )
        if limit < 1 or limit > 100:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="limit must be between 1 and 100")
        try:
            snapshot = list_mailbox_snapshot(
                email=credentials.email,
                password=credentials.password,
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

    @app.get("/api/v1/mailbox/search", response_model=MailboxSearchRecord)
    def mailbox_search(
        query: str,
        folder: str = "INBOX",
        limit: int = 25,
        authorization: str | None = Header(default=None),
        x_freemail_mailbox_email: str | None = Header(default=None),
        x_freemail_mailbox_password: str | None = Header(default=None),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        credentials = mailbox_credentials(
            authorization=authorization,
            x_freemail_mailbox_email=x_freemail_mailbox_email,
            x_freemail_mailbox_password=x_freemail_mailbox_password,
            connection=connection,
        )
        clean_query = query.strip()
        if not clean_query:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="query is required")
        if limit < 1 or limit > 100:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="limit must be between 1 and 100")
        try:
            result = search_mailbox_messages(
                email=credentials.email,
                password=credentials.password,
                host=active_settings.mail_core_host,
                port=active_settings.imap_port,
                folder=folder,
                query=clean_query,
                limit=limit,
            )
        except OSError as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
        except imaplib.IMAP4.error as error:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Mailbox authentication failed") from error
        return result.as_dict()

    @app.get("/api/v1/mailbox/contacts", response_model=MailboxContactsRecord)
    def mailbox_contacts(
        folder: str = "INBOX",
        limit: int = 100,
        authorization: str | None = Header(default=None),
        x_freemail_mailbox_email: str | None = Header(default=None),
        x_freemail_mailbox_password: str | None = Header(default=None),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        credentials = mailbox_credentials(
            authorization=authorization,
            x_freemail_mailbox_email=x_freemail_mailbox_email,
            x_freemail_mailbox_password=x_freemail_mailbox_password,
            connection=connection,
        )
        if limit < 1 or limit > 500:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="limit must be between 1 and 500")
        try:
            result = list_mailbox_contacts(
                email=credentials.email,
                password=credentials.password,
                host=active_settings.mail_core_host,
                port=active_settings.imap_port,
                folder=folder,
                limit=limit,
            )
        except OSError as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
        except imaplib.IMAP4.error as error:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Mailbox authentication failed") from error
        return result.as_dict()

    @app.get("/api/v1/mailbox/message", response_model=MailboxMessageDetailRecord)
    def mailbox_message(
        folder: str,
        message_id: str,
        authorization: str | None = Header(default=None),
        x_freemail_mailbox_email: str | None = Header(default=None),
        x_freemail_mailbox_password: str | None = Header(default=None),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        credentials = mailbox_credentials(
            authorization=authorization,
            x_freemail_mailbox_email=x_freemail_mailbox_email,
            x_freemail_mailbox_password=x_freemail_mailbox_password,
            connection=connection,
        )
        try:
            message = get_mailbox_message(
                email=credentials.email,
                password=credentials.password,
                host=active_settings.mail_core_host,
                port=active_settings.imap_port,
                folder=folder,
                message_id=message_id,
            )
        except OSError as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
        except imaplib.IMAP4.error as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mailbox message not found") from error
        return message.as_dict()

    @app.post("/api/v1/mailbox/folder", response_model=MailboxFolderMutationRecord)
    def mailbox_folder_create(
        payload: MailboxFolderCreate,
        authorization: str | None = Header(default=None),
        x_freemail_mailbox_email: str | None = Header(default=None),
        x_freemail_mailbox_password: str | None = Header(default=None),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        credentials = mailbox_credentials(
            authorization=authorization,
            x_freemail_mailbox_email=x_freemail_mailbox_email,
            x_freemail_mailbox_password=x_freemail_mailbox_password,
            connection=connection,
        )
        try:
            created = create_mailbox_folder(
                email=credentials.email,
                password=credentials.password,
                host=active_settings.mail_core_host,
                port=active_settings.imap_port,
                folder=payload.folder,
            )
        except OSError as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
        except imaplib.IMAP4.error as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
        return created.as_dict()

    @app.patch("/api/v1/mailbox/folder", response_model=MailboxFolderMutationRecord)
    def mailbox_folder_rename(
        payload: MailboxFolderRename,
        authorization: str | None = Header(default=None),
        x_freemail_mailbox_email: str | None = Header(default=None),
        x_freemail_mailbox_password: str | None = Header(default=None),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        credentials = mailbox_credentials(
            authorization=authorization,
            x_freemail_mailbox_email=x_freemail_mailbox_email,
            x_freemail_mailbox_password=x_freemail_mailbox_password,
            connection=connection,
        )
        reject_protected_folder(payload.folder, action="renamed")
        try:
            renamed = rename_mailbox_folder(
                email=credentials.email,
                password=credentials.password,
                host=active_settings.mail_core_host,
                port=active_settings.imap_port,
                folder=payload.folder,
                target_folder=payload.target_folder,
            )
        except OSError as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
        except imaplib.IMAP4.error as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
        return renamed.as_dict()

    @app.api_route("/api/v1/mailbox/folder", methods=["DELETE"], response_model=MailboxFolderMutationRecord)
    def mailbox_folder_delete(
        payload: MailboxFolderDelete,
        authorization: str | None = Header(default=None),
        x_freemail_mailbox_email: str | None = Header(default=None),
        x_freemail_mailbox_password: str | None = Header(default=None),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        credentials = mailbox_credentials(
            authorization=authorization,
            x_freemail_mailbox_email=x_freemail_mailbox_email,
            x_freemail_mailbox_password=x_freemail_mailbox_password,
            connection=connection,
        )
        reject_protected_folder(payload.folder, action="deleted")
        try:
            deleted = delete_mailbox_folder(
                email=credentials.email,
                password=credentials.password,
                host=active_settings.mail_core_host,
                port=active_settings.imap_port,
                folder=payload.folder,
            )
        except OSError as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
        except imaplib.IMAP4.error as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
        return deleted.as_dict()

    @app.get("/api/v1/mailbox/message/attachment")
    def mailbox_attachment(
        folder: str,
        message_id: str,
        attachment_id: str,
        authorization: str | None = Header(default=None),
        x_freemail_mailbox_email: str | None = Header(default=None),
        x_freemail_mailbox_password: str | None = Header(default=None),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> Response:
        credentials = mailbox_credentials(
            authorization=authorization,
            x_freemail_mailbox_email=x_freemail_mailbox_email,
            x_freemail_mailbox_password=x_freemail_mailbox_password,
            connection=connection,
        )
        try:
            attachment = get_mailbox_attachment(
                email=credentials.email,
                password=credentials.password,
                host=active_settings.mail_core_host,
                port=active_settings.imap_port,
                folder=folder,
                message_id=message_id,
                attachment_id=attachment_id,
            )
        except OSError as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
        except imaplib.IMAP4.error as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mailbox attachment not found") from error
        return Response(
            content=attachment.content,
            media_type=attachment.content_type,
            headers={
                "Content-Disposition": (
                    f"attachment; filename=\"{quote(attachment.filename)}\"; "
                    f"filename*=UTF-8''{quote(attachment.filename)}"
                )
            },
        )

    @app.post("/api/v1/mailbox/message/archive", response_model=MailboxArchiveRecord)
    def mailbox_archive(
        payload: MailboxArchiveCreate,
        authorization: str | None = Header(default=None),
        x_freemail_mailbox_email: str | None = Header(default=None),
        x_freemail_mailbox_password: str | None = Header(default=None),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        credentials = mailbox_credentials(
            authorization=authorization,
            x_freemail_mailbox_email=x_freemail_mailbox_email,
            x_freemail_mailbox_password=x_freemail_mailbox_password,
            connection=connection,
        )
        try:
            archived = archive_mailbox_message(
                email=credentials.email,
                password=credentials.password,
                host=active_settings.mail_core_host,
                port=active_settings.imap_port,
                folder=payload.folder,
                message_id=payload.message_id,
                archive_folder=payload.archive_folder,
            )
        except OSError as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
        except imaplib.IMAP4.error as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mailbox message not found") from error
        return archived.as_dict()

    @app.post("/api/v1/mailbox/message/move", response_model=MailboxMoveRecord)
    def mailbox_move(
        payload: MailboxMoveCreate,
        authorization: str | None = Header(default=None),
        x_freemail_mailbox_email: str | None = Header(default=None),
        x_freemail_mailbox_password: str | None = Header(default=None),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        credentials = mailbox_credentials(
            authorization=authorization,
            x_freemail_mailbox_email=x_freemail_mailbox_email,
            x_freemail_mailbox_password=x_freemail_mailbox_password,
            connection=connection,
        )
        try:
            moved = move_mailbox_message(
                email=credentials.email,
                password=credentials.password,
                host=active_settings.mail_core_host,
                port=active_settings.imap_port,
                folder=payload.folder,
                message_id=payload.message_id,
                target_folder=payload.target_folder,
            )
        except OSError as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
        except imaplib.IMAP4.error as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mailbox message not found") from error
        return moved.as_dict()

    @app.post("/api/v1/mailbox/send", response_model=MailboxSendRecord)
    def mailbox_send(
        payload: MailboxSendCreate,
        authorization: str | None = Header(default=None),
        x_freemail_mailbox_email: str | None = Header(default=None),
        x_freemail_mailbox_password: str | None = Header(default=None),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        credentials = mailbox_credentials(
            authorization=authorization,
            x_freemail_mailbox_email=x_freemail_mailbox_email,
            x_freemail_mailbox_password=x_freemail_mailbox_password,
            connection=connection,
        )
        try:
            validate_attachments(payload.attachments, attachment_policy())
            recipient_count = len(payload.recipients)
            enforce_outbound_rate_limit(
                connection,
                email=credentials.email,
                recipient_count=recipient_count,
                policy=outbound_rate_policy(),
            )
            sent = send_mailbox_message(
                email=credentials.email,
                password=credentials.password,
                host=active_settings.mail_core_host,
                port=active_settings.submission_port,
                recipients=[str(recipient) for recipient in payload.recipients],
                subject=payload.subject,
                body=payload.body,
                attachments=[
                    OutboundAttachment(
                        filename=attachment.filename,
                        content_type=attachment.content_type,
                        content_base64=attachment.content_base64,
                    )
                    for attachment in payload.attachments
                ],
            )
            record_outbound_send(connection, email=credentials.email, recipient_count=recipient_count)
        except AttachmentPolicyError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
        except OutboundRateLimitExceeded as error:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(error)) from error
        except (ValueError, binascii.Error) as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid attachment payload") from error
        except smtplib.SMTPAuthenticationError as error:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Mailbox authentication failed") from error
        except smtplib.SMTPRecipientsRefused as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Recipient refused") from error
        except (OSError, smtplib.SMTPException) as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
        return {"accepted": True, **sent.as_dict()}

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
        records = domain_dns_records(
            domain=str(domain["name"]),
            hostname=active_settings.hostname,
            dkim_keys=dkim_keys,
        )
        return DomainDnsGuidance(domain=str(domain["name"]), records=records)

    @app.post("/api/v1/admin/domains/{domain_id}/dns/verify", response_model=DomainDnsPostureRecord)
    def domain_dns_verify(
        domain_id: int,
        payload: DomainDnsPostureCreate,
        _actor: str = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        try:
            domain = database.get_domain(connection, domain_id)
            dkim_keys = database.list_dkim_keys_for_domain(connection, domain_id)
        except database.MissingRecordError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
        records = domain_dns_records(
            domain=str(domain["name"]),
            hostname=active_settings.hostname,
            dkim_keys=dkim_keys,
        )
        return verify_dns_posture(
            domain=str(domain["name"]),
            expected_records=records,
            observed_records=[record.model_dump() for record in payload.observed_records],
        ).as_dict()

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
