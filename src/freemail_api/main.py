import binascii
from collections.abc import Iterator
from contextlib import asynccontextmanager
from hashlib import sha256
import base64
import imaplib
import smtplib
import sqlite3
from urllib.parse import quote

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response, status
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
from .mailbox_imap import bulk_mailbox_message_action
from .mailbox_imap import create_mailbox_folder
from .mailbox_imap import delete_mailbox_folder
from .mailbox_imap import empty_mailbox_folder
from .mailbox_imap import get_mailbox_attachment
from .mailbox_imap import get_mailbox_message
from .mailbox_imap import get_mailbox_message_headers
from .mailbox_imap import get_mailbox_message_source
from .mailbox_imap import import_mailbox_message_source
from .mailbox_imap import list_mailbox_contacts
from .mailbox_imap import list_mailbox_snapshot
from .mailbox_imap import list_mailbox_thread
from .mailbox_imap import move_mailbox_message
from .mailbox_imap import rename_mailbox_folder
from .mailbox_imap import search_mailbox_messages
from .mailbox_imap import set_mailbox_message_read_state
from .mailbox_imap import set_mailbox_message_star_state
from .mailbox_smtp import OutboundAttachment
from .mailbox_smtp import save_mailbox_draft
from .mailbox_smtp import send_mailbox_message
from .outbound_policy import enforce_outbound_rate_limit
from .outbound_policy import OutboundRateLimitExceeded
from .outbound_policy import OutboundRatePolicy
from .outbound_policy import record_outbound_send
from .passwords import hash_initial_password
from .passwords import verify_password_hash
from .push_delivery import dispatch_push_notification
from .push_delivery import PushDeliveryConfig
from .schemas import (
    AdminSessionCreate,
    AdminSessionDeleteRecord,
    AdminSessionRecord,
    AdminStatusUpdate,
    AdminTotpSetupRecord,
    AdminTotpStatusRecord,
    AdminTotpVerifyCreate,
    AliasCreate,
    AliasRecord,
    AuditLogPage,
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
    MailboxBulkActionCreate,
    MailboxBulkActionRecord,
    MailboxContactsRecord,
    MailboxCreate,
    MailboxDraftCreate,
    MailboxDraftRecord,
    MailboxFolderCreate,
    MailboxFolderDelete,
    MailboxFolderEmpty,
    MailboxFolderEmptyRecord,
    MailboxFolderMutationRecord,
    MailboxFolderRename,
    MailboxMessageDetailRecord,
    MailboxMessageHeadersRecord,
    MailboxMessageImportCreate,
    MailboxMessageImportRecord,
    MailboxMoveCreate,
    MailboxMoveRecord,
    MailboxPreferencesRecord,
    MailboxPreferencesUpdate,
    MailboxQuotaUpdate,
    MailCoreSyncPlanStatusCreate,
    MailCoreSyncPlanStatusRecord,
    MailboxPushDeviceCreate,
    MailboxPushDeviceDeleteRecord,
    MailboxPushDeviceRecord,
    MailboxPushNotificationCreate,
    MailboxPushNotificationRecord,
    MailboxReadStateCreate,
    MailboxReadStateRecord,
    MailboxRecord,
    MailboxSearchRecord,
    MailboxSendCreate,
    MailboxSendRecord,
    MailboxSessionCreate,
    MailboxSessionDeleteRecord,
    MailboxSessionRecord,
    MailboxSnapshotRecord,
    MailboxStarStateCreate,
    MailboxStarStateRecord,
    MailboxThreadRecord,
    SavedMailboxContactCreate,
    SavedMailboxContactDeleteRecord,
    SavedMailboxContactRecord,
    SavedMailboxContactsRecord,
    StoredUserCreate,
    UserCreate,
    UserPasswordUpdate,
    UserRecord,
)
from .sessions import bearer_token
from .sessions import create_admin_session
from .sessions import create_mailbox_session
from .sessions import InvalidSessionError
from .sessions import AdminPrincipal
from .sessions import MailboxCredentials
from .sessions import resolve_admin_session
from .sessions import resolve_mailbox_session
from .sessions import revoke_admin_session
from .sessions import revoke_mailbox_session
from .sessions import SessionConfigurationError
from .secret_box import decrypt_text
from .secret_box import encrypt_text
from .secret_box import SecretBoxConfigurationError
from .secret_box import SecretBoxDecryptionError
from .settings import get_settings
from .settings import Settings
from .stalwart_plan import build_apply_plan_status
from .totp import generate_totp_secret
from .totp import totp_uri
from .totp import verify_totp_code


ROLE_PERMISSIONS = {
    "owner": {
        "admin.read",
        "admin.manage",
        "admin.users",
        "admin.grant",
    },
    "admin": {
        "admin.read",
        "admin.manage",
        "admin.users",
    },
    "operator": {
        "admin.read",
        "admin.manage",
    },
    "auditor": {
        "admin.read",
    },
}


COMPONENT_READINESS = {
    "adminApi": {
        "status": "ready",
        "evidence": [
            "administrator bootstrap, bearer-session login, and authenticator-app MFA",
            "domain, user, user-password rotation, mailbox quota, alias, DKIM, DNS, status, and filterable audit APIs",
            "metadata readiness endpoint and backup/restore coverage",
        ],
        "remainingReleaseEvidence": [],
    },
    "mailCore": {
        "status": "runtime-ready",
        "evidence": [
            "Stalwart candidate starts through Docker Compose",
            "SMTP, submission, IMAP, and JMAP protocol readiness checks",
            "loopback-only port bindings and backup/restore drill evidence",
            "controlled-domain DNS, quota-aware Stalwart apply-plan status, mail-flow, queue, and deliverability evidence packet support",
        ],
        "remainingReleaseEvidence": [],
    },
    "webmail": {
        "status": "beta-ready",
        "evidence": [
            "mailbox session login, paginated and thread-aware folder navigation and search, conversation lookup, contacts, message read, header inspection, EML import/export, read/unread state, star state, compose, attachments, archive, move, delete, and empty-folder controls",
            "bulk message actions for read/unread, star/unstar, archive, spam, delete, and move",
            "persistent mailbox preferences with default compose signatures and saved address-book contacts",
            "server-side Drafts persistence and compose reopen support for saved drafts",
            "server-side Sent Items persistence for accepted outbound messages",
            "token-gated admin console for bootstrap, MFA setup, users, password rotation, domains, mailboxes, aliases, DKIM, DNS guidance, status actions, sync status, and audit logs",
            "browser and static QA in CI",
        ],
        "remainingReleaseEvidence": [
            "decision-owner private-beta acceptance",
        ],
    },
    "mobile": {
        "status": "source-ready",
        "evidence": [
            "Expo/React Native client with VPN API target, mailbox sessions, paginated and thread-aware message workflows, conversation lookup, header inspection, EML import/export/share, draft saving/editing, read/unread and star state, archive/spam/delete actions, folder and empty-folder controls, extracted and saved contacts, attachments, offline metadata cache, and push-device flows",
            "bulk read/star/archive/spam/delete/move client controls over the shared mailbox API",
            "mobile preference controls for default compose signatures",
            "compose/send path uses the shared mailbox API contract with Sent Items persistence status",
            "mobile static QA, config validation, native prebuild drill, typecheck, and dependency audit in CI",
        ],
        "remainingReleaseEvidence": [
            "real signed native mobile builds",
            "real store-submission evidence",
            "private-beta device validation",
        ],
    },
}


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    protected_folders = {"inbox", "sent items", "drafts", "junk mail", "deleted items", "archive"}
    empty_protected_folders = {"inbox", "sent items", "drafts", "archive"}

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
            allow_methods=["DELETE", "GET", "PATCH", "POST", "PUT", "OPTIONS"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "X-FreeMail-Admin-Token",
                "X-FreeMail-Bootstrap-Token",
                "X-FreeMail-Mailbox-Email",
                "X-FreeMail-Mailbox-Password",
            ],
        )

    def get_connection() -> Iterator[sqlite3.Connection]:
        with database.connect(active_settings.database_path) as connection:
            yield connection

    def require_admin(
        authorization: str | None = Header(default=None),
        x_freemail_admin_token: str | None = Header(default=None),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> AdminPrincipal:
        token = bearer_token(authorization)
        if token:
            try:
                return resolve_admin_session(connection, token=token)
            except InvalidSessionError as error:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin session") from error
        if not active_settings.admin_api_token:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Admin API token is not configured and no valid admin session was provided",
            )
        if x_freemail_admin_token != active_settings.admin_api_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin API token")
        return AdminPrincipal(user_id=0, email="admin-token", actor="admin-api", role="owner")

    def require_permission(principal: AdminPrincipal, permission: str) -> None:
        if permission not in ROLE_PERMISSIONS.get(principal.role, set()):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Admin role lacks {permission} permission")

    def require_bootstrap(x_freemail_bootstrap_token: str | None = Header(default=None)) -> str:
        if not active_settings.bootstrap_token:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Bootstrap token is not configured",
            )
        if x_freemail_bootstrap_token != active_settings.bootstrap_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bootstrap token")
        return "bootstrap-api"

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

    def push_delivery_config() -> PushDeliveryConfig:
        return PushDeliveryConfig(
            fcm_project_id=active_settings.fcm_project_id,
            fcm_service_account_json=active_settings.fcm_service_account_json,
            apns_team_id=active_settings.apns_team_id,
            apns_key_id=active_settings.apns_key_id,
            apns_private_key_pem=active_settings.apns_private_key_pem,
            apns_bundle_id=active_settings.apns_bundle_id,
            apns_use_sandbox=active_settings.apns_use_sandbox,
            timeout_seconds=active_settings.push_delivery_timeout_seconds,
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
                credentials = resolve_mailbox_session(
                    connection,
                    token=token,
                    secret=active_settings.session_secret,
                )
                ensure_mailbox_access_allowed(connection, credentials.email)
                return credentials
            except SessionConfigurationError as error:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Mailbox sessions are not configured",
                ) from error
            except InvalidSessionError as error:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid mailbox session") from error
        if not x_freemail_mailbox_email or not x_freemail_mailbox_password:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Mailbox credentials required")
        ensure_mailbox_access_allowed(connection, x_freemail_mailbox_email)
        return MailboxCredentials(email=x_freemail_mailbox_email, password=x_freemail_mailbox_password)

    def ensure_mailbox_access_allowed(connection: sqlite3.Connection, email: str) -> None:
        if not database.is_mailbox_access_allowed(connection, email):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Mailbox is suspended")

    def reject_protected_folder(folder: str, *, action: str) -> None:
        if folder.strip().lower() in protected_folders:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Core mailbox folders cannot be {action}",
            )

    def reject_empty_protected_folder(folder: str) -> None:
        if folder.strip().lower() in empty_protected_folders:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="This mailbox folder cannot be emptied",
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
            "components": {name: details["status"] for name, details in COMPONENT_READINESS.items()},
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

    @app.get("/api/v1/product/readiness")
    def product_readiness() -> dict[str, object]:
        release_blockers = sorted(
            {
                blocker
                for details in COMPONENT_READINESS.values()
                for blocker in details["remainingReleaseEvidence"]
            }
        )
        return {
            "project": active_settings.app_name,
            "license": "AGPL-3.0-or-later",
            "credentialFreePublicRepo": True,
            "vpnOnly": active_settings.vpn_only,
            "releaseReady": not release_blockers,
            "components": COMPONENT_READINESS,
            "releaseBlockers": release_blockers,
        }

    @app.get("/api/v1/deployment")
    def deployment() -> dict[str, object]:
        return {
            "hostname": active_settings.hostname,
            "exposure": "vpn-only",
            "publicInternet": False,
            "requiredBoundary": "Dragonscale/VPN clients only",
        }

    @app.get("/api/v1/metadata/readiness")
    def metadata_readiness(connection: sqlite3.Connection = Depends(get_connection)) -> dict[str, object]:
        return database.metadata_readiness(connection)

    @app.get("/api/v1/mail-core/readiness")
    def mail_core_readiness() -> dict[str, object]:
        return probe_mail_core(
            host=active_settings.mail_core_host,
            smtp_port=active_settings.smtp_port,
            submission_port=active_settings.submission_port,
            imap_port=active_settings.imap_port,
            jmap_port=active_settings.jmap_port,
        )

    @app.post("/api/v1/admin/session", response_model=AdminSessionRecord)
    def admin_session_create(
        payload: AdminSessionCreate,
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        user = database.get_active_admin_user_by_email(connection, str(payload.email))
        if user is None or not verify_password_hash(str(user["password_hash"]), payload.password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin authentication failed")
        _verify_admin_mfa_if_enabled(
            connection=connection,
            user_id=int(user["id"]),
            code=payload.totp_code,
            secret=active_settings.session_secret,
        )
        created = create_admin_session(
            connection,
            user_id=int(user["id"]),
            email=str(user["email"]),
            ttl_seconds=active_settings.session_ttl_seconds,
        )
        return {"token": created.token, "email": created.email, "expires_at": created.expires_at}

    @app.delete("/api/v1/admin/session", response_model=AdminSessionDeleteRecord)
    def admin_session_delete(
        authorization: str | None = Header(default=None),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, bool]:
        token = bearer_token(authorization)
        if token:
            revoke_admin_session(connection, token)
        return {"revoked": True}

    @app.post("/api/v1/admin/mfa/totp/setup", response_model=AdminTotpSetupRecord)
    def admin_totp_setup(
        principal: AdminPrincipal = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        secret = generate_totp_secret()
        try:
            encrypted_secret = encrypt_text(secret, active_settings.session_secret)
        except SecretBoxConfigurationError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Admin MFA setup requires FREEMAIL_SESSION_SECRET",
            ) from error
        database.upsert_admin_totp_secret(
            connection,
            user_id=principal.user_id,
            encrypted_secret=encrypted_secret,
            actor=principal.actor,
        )
        return {
            "secret": secret,
            "otpauth_uri": totp_uri(issuer=active_settings.app_name, account=principal.email, secret=secret),
            "enabled": False,
        }

    @app.post("/api/v1/admin/mfa/totp/verify", response_model=AdminTotpStatusRecord)
    def admin_totp_verify(
        payload: AdminTotpVerifyCreate,
        principal: AdminPrincipal = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, bool]:
        secret = _admin_totp_secret_or_raise(
            connection=connection,
            user_id=principal.user_id,
            secret=active_settings.session_secret,
        )
        if not verify_totp_code(secret, payload.code):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin MFA code")
        database.enable_admin_totp(connection, user_id=principal.user_id, actor=principal.actor)
        return {"enabled": True}

    @app.delete("/api/v1/admin/mfa/totp", response_model=AdminTotpStatusRecord)
    def admin_totp_disable(
        principal: AdminPrincipal = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, bool]:
        database.delete_admin_totp(connection, user_id=principal.user_id, actor=principal.actor)
        return {"enabled": False}

    @app.post("/api/v1/mailbox/session", response_model=MailboxSessionRecord)
    def mailbox_session_create(
        payload: MailboxSessionCreate,
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        try:
            ensure_mailbox_access_allowed(connection, str(payload.email))
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

    @app.get("/api/v1/mailbox/preferences", response_model=MailboxPreferencesRecord)
    def mailbox_preferences_get(
        authorization: str | None = Header(default=None),
        x_freemail_mailbox_email: str | None = Header(default=None),
        x_freemail_mailbox_password: str | None = Header(default=None),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, str]:
        credentials = mailbox_credentials(
            authorization=authorization,
            x_freemail_mailbox_email=x_freemail_mailbox_email,
            x_freemail_mailbox_password=x_freemail_mailbox_password,
            connection=connection,
        )
        return database.get_mailbox_preferences(connection, email=credentials.email)

    @app.put("/api/v1/mailbox/preferences", response_model=MailboxPreferencesRecord)
    def mailbox_preferences_update(
        payload: MailboxPreferencesUpdate,
        authorization: str | None = Header(default=None),
        x_freemail_mailbox_email: str | None = Header(default=None),
        x_freemail_mailbox_password: str | None = Header(default=None),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, str]:
        credentials = mailbox_credentials(
            authorization=authorization,
            x_freemail_mailbox_email=x_freemail_mailbox_email,
            x_freemail_mailbox_password=x_freemail_mailbox_password,
            connection=connection,
        )
        return database.upsert_mailbox_preferences(
            connection,
            email=credentials.email,
            display_name=payload.display_name,
            signature=payload.signature,
        )

    @app.get("/api/v1/mailbox/saved-contacts", response_model=SavedMailboxContactsRecord)
    def mailbox_saved_contacts_list(
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
        normalized_email = credentials.email.lower()
        return {
            "mailbox_email": normalized_email,
            "contacts": _rows_to_dicts(database.list_saved_mailbox_contacts(connection, email=normalized_email)),
        }

    @app.put("/api/v1/mailbox/saved-contacts", response_model=SavedMailboxContactRecord)
    def mailbox_saved_contact_upsert(
        payload: SavedMailboxContactCreate,
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
        contact = database.upsert_saved_mailbox_contact(
            connection,
            email=credentials.email,
            contact_email=str(payload.email),
            display_name=payload.display_name,
            notes=payload.notes,
        )
        return dict(contact)

    @app.delete("/api/v1/mailbox/saved-contacts/{contact_id}", response_model=SavedMailboxContactDeleteRecord)
    def mailbox_saved_contact_delete(
        contact_id: int,
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
        return {
            "deleted": database.delete_saved_mailbox_contact(
                connection,
                email=credentials.email,
                contact_id=contact_id,
            ),
            "contact_id": contact_id,
        }

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
            encrypted_push_token=_encrypted_push_token(payload.push_token, active_settings.push_token_secret),
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

    @app.post("/api/v1/mailbox/push/notifications", response_model=list[MailboxPushNotificationRecord])
    def mailbox_push_notification_create(
        payload: MailboxPushNotificationCreate,
        authorization: str | None = Header(default=None),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> list[dict[str, object]]:
        credentials = mailbox_credentials(
            authorization=authorization,
            x_freemail_mailbox_email=None,
            x_freemail_mailbox_password=None,
            connection=connection,
        )
        rows = database.create_mailbox_push_notifications(
            connection,
            email=credentials.email,
            title=payload.title,
            body=payload.body,
        )
        dispatched = []
        for row in rows:
            result = dispatch_push_notification(
                provider=str(row["provider"]),
                device_id=str(row["device_id"]),
                title=str(row["title"]),
                body=str(row["body"]),
                push_token=_decrypted_push_token(row, active_settings.push_token_secret),
                config=push_delivery_config(),
            )
            if result.delivered and result.provider_message_id:
                dispatched.append(
                    database.mark_mailbox_push_notification_delivered(
                        connection,
                        notification_id=int(row["id"]),
                        provider_message_id=result.provider_message_id,
                    )
                )
            else:
                dispatched.append(
                    database.mark_mailbox_push_notification_pending_provider(
                        connection,
                        notification_id=int(row["id"]),
                        last_error=result.error or "push provider adapter is not configured",
                    )
                )
        return _rows_to_dicts(dispatched)

    @app.get("/api/v1/mailbox/push/notifications", response_model=list[MailboxPushNotificationRecord])
    def mailbox_push_notification_list(
        limit: int = 25,
        authorization: str | None = Header(default=None),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> list[dict[str, object]]:
        credentials = mailbox_credentials(
            authorization=authorization,
            x_freemail_mailbox_email=None,
            x_freemail_mailbox_password=None,
            connection=connection,
        )
        if limit < 1 or limit > 100:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="limit must be between 1 and 100")
        return _rows_to_dicts(database.list_mailbox_push_notifications(connection, email=credentials.email, limit=limit))

    @app.get("/api/v1/mailbox/snapshot", response_model=MailboxSnapshotRecord)
    def mailbox_snapshot(
        folder: str = "INBOX",
        limit: int = 25,
        offset: int = 0,
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
        if offset < 0:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="offset must be zero or greater")
        try:
            snapshot = list_mailbox_snapshot(
                email=credentials.email,
                password=credentials.password,
                host=active_settings.mail_core_host,
                port=active_settings.imap_port,
                folder=folder,
                limit=limit,
                offset=offset,
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
        offset: int = 0,
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
        if offset < 0:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="offset must be zero or greater")
        try:
            result = search_mailbox_messages(
                email=credentials.email,
                password=credentials.password,
                host=active_settings.mail_core_host,
                port=active_settings.imap_port,
                folder=folder,
                query=clean_query,
                limit=limit,
                offset=offset,
            )
        except OSError as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
        except imaplib.IMAP4.error as error:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Mailbox authentication failed") from error
        return result.as_dict()

    @app.get("/api/v1/mailbox/thread", response_model=MailboxThreadRecord)
    def mailbox_thread(
        thread_id: str,
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
        clean_thread_id = thread_id.strip()
        if not clean_thread_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="thread_id is required")
        if limit < 1 or limit > 500:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="limit must be between 1 and 500")
        try:
            result = list_mailbox_thread(
                email=credentials.email,
                password=credentials.password,
                host=active_settings.mail_core_host,
                port=active_settings.imap_port,
                folder=folder,
                thread_id=clean_thread_id,
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

    @app.post("/api/v1/mailbox/folder/empty", response_model=MailboxFolderEmptyRecord)
    def mailbox_folder_empty(
        payload: MailboxFolderEmpty,
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
        reject_empty_protected_folder(payload.folder)
        try:
            emptied = empty_mailbox_folder(
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
        return emptied.as_dict()

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

    @app.get("/api/v1/mailbox/message/headers", response_model=MailboxMessageHeadersRecord)
    def mailbox_message_headers(
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
            headers = get_mailbox_message_headers(
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
        return headers.as_dict()

    @app.get("/api/v1/mailbox/message/source")
    def mailbox_message_source(
        folder: str,
        message_id: str,
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
            source = get_mailbox_message_source(
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
        quoted_filename = quote(source.filename)
        return Response(
            content=source.content,
            media_type="message/rfc822",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{quoted_filename}"; filename*=UTF-8\'\'{quoted_filename}'
                )
            },
        )

    @app.post("/api/v1/mailbox/message/import", response_model=MailboxMessageImportRecord)
    def mailbox_message_import(
        payload: MailboxMessageImportCreate,
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
            content = base64.b64decode(payload.content_base64, validate=True)
            imported = import_mailbox_message_source(
                email=credentials.email,
                password=credentials.password,
                host=active_settings.mail_core_host,
                port=active_settings.imap_port,
                folder=payload.folder,
                filename=payload.filename,
                content=content,
            )
        except (ValueError, binascii.Error) as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid EML payload") from error
        except OSError as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
        except imaplib.IMAP4.error as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
        return imported.as_dict()

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

    @app.post("/api/v1/mailbox/message/read-state", response_model=MailboxReadStateRecord)
    def mailbox_read_state(
        payload: MailboxReadStateCreate,
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
            state = set_mailbox_message_read_state(
                email=credentials.email,
                password=credentials.password,
                host=active_settings.mail_core_host,
                port=active_settings.imap_port,
                folder=payload.folder,
                message_id=payload.message_id,
                read=payload.read,
            )
        except OSError as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
        except imaplib.IMAP4.error as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mailbox message not found") from error
        return state.as_dict()

    @app.post("/api/v1/mailbox/message/star-state", response_model=MailboxStarStateRecord)
    def mailbox_star_state(
        payload: MailboxStarStateCreate,
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
            state = set_mailbox_message_star_state(
                email=credentials.email,
                password=credentials.password,
                host=active_settings.mail_core_host,
                port=active_settings.imap_port,
                folder=payload.folder,
                message_id=payload.message_id,
                starred=payload.starred,
            )
        except OSError as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
        except imaplib.IMAP4.error as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mailbox message not found") from error
        return state.as_dict()

    @app.post("/api/v1/mailbox/message/bulk", response_model=MailboxBulkActionRecord)
    def mailbox_bulk_action(
        payload: MailboxBulkActionCreate,
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
            result = bulk_mailbox_message_action(
                email=credentials.email,
                password=credentials.password,
                host=active_settings.mail_core_host,
                port=active_settings.imap_port,
                folder=payload.folder,
                message_ids=payload.message_ids,
                action=payload.action,
                target_folder=payload.target_folder,
            )
        except OSError as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
        except imaplib.IMAP4.error as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
        return result.as_dict()

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
                imap_host=active_settings.mail_core_host,
                imap_port=active_settings.imap_port,
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

    @app.post("/api/v1/mailbox/draft", response_model=MailboxDraftRecord)
    def mailbox_draft_save(
        payload: MailboxDraftCreate,
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
            draft = save_mailbox_draft(
                email=credentials.email,
                password=credentials.password,
                host=active_settings.mail_core_host,
                port=active_settings.imap_port,
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
                draft_folder=payload.draft_folder,
            )
        except AttachmentPolicyError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
        except (ValueError, binascii.Error) as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid attachment payload") from error
        except (OSError, imaplib.IMAP4.error) as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
        return draft.as_dict()

    @app.post("/api/v1/bootstrap/admin", response_model=BootstrapAdminRecord, status_code=status.HTTP_201_CREATED)
    def bootstrap_admin(
        payload: BootstrapAdminCreate,
        actor: str = Depends(require_bootstrap),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, dict[str, object]]:
        password_hash = hash_initial_password(payload.initial_password)
        result = _create_or_raise(
            lambda: database.bootstrap_admin(
                connection,
                domain_name=payload.domain_name,
                email=str(payload.email),
                display_name=payload.display_name,
                password_hash=password_hash,
                mailbox_local_part=payload.mailbox_local_part,
                actor=actor,
            )
        )
        return {
            "domain": _row_to_dict(result["domain"]),
            "user": _row_to_dict(result["user"]),
            "mailbox": _row_to_dict(result["mailbox"]),
        }

    @app.get("/api/v1/admin/domains", response_model=list[DomainRecord])
    def list_domains(
        principal: AdminPrincipal = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> list[dict[str, object]]:
        require_permission(principal, "admin.read")
        return _rows_to_dicts(database.list_rows(connection, "domains"))

    @app.post("/api/v1/admin/domains", response_model=DomainRecord, status_code=status.HTTP_201_CREATED)
    def add_domain(
        payload: DomainCreate,
        principal: AdminPrincipal = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        require_permission(principal, "admin.manage")
        return _row_to_dict(_create_or_raise(lambda: database.create_domain(connection, payload, principal.actor)))

    @app.patch("/api/v1/admin/domains/{domain_id}/status", response_model=DomainRecord)
    def update_domain_status(
        domain_id: int,
        payload: AdminStatusUpdate,
        principal: AdminPrincipal = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        require_permission(principal, "admin.manage")
        return _row_to_dict(
            _create_or_raise(
                lambda: database.update_status(connection, "domains", domain_id, payload.status, principal.actor)
            )
        )

    @app.get("/api/v1/admin/users", response_model=list[UserRecord])
    def list_users(
        principal: AdminPrincipal = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> list[dict[str, object]]:
        require_permission(principal, "admin.read")
        return _rows_to_dicts(database.list_rows(connection, "users"))

    @app.post("/api/v1/admin/users", response_model=UserRecord, status_code=status.HTTP_201_CREATED)
    def add_user(
        payload: UserCreate,
        principal: AdminPrincipal = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        require_permission(principal, "admin.users")
        if payload.is_admin:
            require_permission(principal, "admin.grant")
        admin_role = _normalized_admin_role(payload.is_admin, payload.admin_role)
        stored_payload = StoredUserCreate(
            email=payload.email,
            display_name=payload.display_name,
            password_hash=hash_initial_password(payload.initial_password),
            is_admin=payload.is_admin,
            admin_role=admin_role,
        )
        return _row_to_dict(_create_or_raise(lambda: database.create_user(connection, stored_payload, principal.actor)))

    @app.patch("/api/v1/admin/users/{user_id}/status", response_model=UserRecord)
    def update_user_status(
        user_id: int,
        payload: AdminStatusUpdate,
        principal: AdminPrincipal = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        require_permission(principal, "admin.users")
        target = _create_or_raise(lambda: database.get_user(connection, user_id))
        if int(target["is_admin"]):
            require_permission(principal, "admin.grant")
        return _row_to_dict(
            _create_or_raise(lambda: database.update_status(connection, "users", user_id, payload.status, principal.actor))
        )

    @app.patch("/api/v1/admin/users/{user_id}/password", response_model=UserRecord)
    def update_user_password(
        user_id: int,
        payload: UserPasswordUpdate,
        principal: AdminPrincipal = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        require_permission(principal, "admin.users")
        target = _create_or_raise(lambda: database.get_user(connection, user_id))
        if int(target["is_admin"]):
            require_permission(principal, "admin.grant")
        password_hash = hash_initial_password(payload.new_password)
        return _row_to_dict(
            _create_or_raise(
                lambda: database.update_user_password(
                    connection,
                    user_id=user_id,
                    password_hash=password_hash,
                    actor=principal.actor,
                )
            )
        )

    @app.get("/api/v1/admin/mailboxes", response_model=list[MailboxRecord])
    def list_mailboxes(
        principal: AdminPrincipal = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> list[dict[str, object]]:
        require_permission(principal, "admin.read")
        return _rows_to_dicts(database.list_rows(connection, "mailboxes"))

    @app.post("/api/v1/admin/mailboxes", response_model=MailboxRecord, status_code=status.HTTP_201_CREATED)
    def add_mailbox(
        payload: MailboxCreate,
        principal: AdminPrincipal = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        require_permission(principal, "admin.manage")
        return _row_to_dict(_create_or_raise(lambda: database.create_mailbox(connection, payload, principal.actor)))

    @app.patch("/api/v1/admin/mailboxes/{mailbox_id}/status", response_model=MailboxRecord)
    def update_mailbox_status(
        mailbox_id: int,
        payload: AdminStatusUpdate,
        principal: AdminPrincipal = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        require_permission(principal, "admin.manage")
        return _row_to_dict(
            _create_or_raise(
                lambda: database.update_status(connection, "mailboxes", mailbox_id, payload.status, principal.actor)
            )
        )

    @app.patch("/api/v1/admin/mailboxes/{mailbox_id}/quota", response_model=MailboxRecord)
    def update_mailbox_quota(
        mailbox_id: int,
        payload: MailboxQuotaUpdate,
        principal: AdminPrincipal = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        require_permission(principal, "admin.manage")
        return _row_to_dict(
            _create_or_raise(
                lambda: database.update_mailbox_quota(
                    connection,
                    mailbox_id=mailbox_id,
                    quota_bytes=payload.quota_bytes,
                    actor=principal.actor,
                )
            )
        )

    @app.get("/api/v1/admin/aliases", response_model=list[AliasRecord])
    def list_aliases(
        principal: AdminPrincipal = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> list[dict[str, object]]:
        require_permission(principal, "admin.read")
        return _rows_to_dicts(database.list_rows(connection, "aliases"))

    @app.post("/api/v1/admin/aliases", response_model=AliasRecord, status_code=status.HTTP_201_CREATED)
    def add_alias(
        payload: AliasCreate,
        principal: AdminPrincipal = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        require_permission(principal, "admin.manage")
        return _row_to_dict(_create_or_raise(lambda: database.create_alias(connection, payload, principal.actor)))

    @app.patch("/api/v1/admin/aliases/{alias_id}/status", response_model=AliasRecord)
    def update_alias_status(
        alias_id: int,
        payload: AdminStatusUpdate,
        principal: AdminPrincipal = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        require_permission(principal, "admin.manage")
        return _row_to_dict(
            _create_or_raise(lambda: database.update_status(connection, "aliases", alias_id, payload.status, principal.actor))
        )

    @app.get("/api/v1/admin/dkim-keys", response_model=list[DkimKeyRecord])
    def list_dkim_keys(
        principal: AdminPrincipal = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> list[dict[str, object]]:
        require_permission(principal, "admin.read")
        return _rows_to_dicts(database.list_rows(connection, "dkim_keys"))

    @app.post("/api/v1/admin/dkim-keys", response_model=DkimKeyCreated, status_code=status.HTTP_201_CREATED)
    def add_dkim_key(
        payload: DkimKeyCreate,
        principal: AdminPrincipal = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        require_permission(principal, "admin.manage")
        public_txt, private_key_pem = dkim.generate_dkim_key_pair()
        row = _create_or_raise(
            lambda: database.create_dkim_key(connection, payload, public_txt, private_key_pem, principal.actor)
        )
        return _row_to_dict(row)

    @app.patch("/api/v1/admin/dkim-keys/{dkim_key_id}/status", response_model=DkimKeyRecord)
    def update_dkim_key_status(
        dkim_key_id: int,
        payload: AdminStatusUpdate,
        principal: AdminPrincipal = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        require_permission(principal, "admin.manage")
        return _row_to_dict(
            _create_or_raise(
                lambda: database.update_status(connection, "dkim_keys", dkim_key_id, payload.status, principal.actor)
            )
        )

    @app.get("/api/v1/admin/domains/{domain_id}/dns", response_model=DomainDnsGuidance)
    def domain_dns_guidance(
        domain_id: int,
        principal: AdminPrincipal = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> DomainDnsGuidance:
        require_permission(principal, "admin.read")
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
        principal: AdminPrincipal = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        require_permission(principal, "admin.read")
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

    @app.post("/api/v1/admin/mail-core/sync-plan/status", response_model=MailCoreSyncPlanStatusRecord)
    def mail_core_sync_plan_status(
        payload: MailCoreSyncPlanStatusCreate,
        principal: AdminPrincipal = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        require_permission(principal, "admin.manage")
        available = {str(email).lower() for email in payload.available_user_secrets}
        return build_apply_plan_status(connection, available)

    @app.get("/api/v1/admin/audit-log", response_model=list[AuditRecord])
    def audit_log(
        principal: AdminPrincipal = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> list[dict[str, object]]:
        require_permission(principal, "admin.read")
        return _rows_to_dicts(database.list_rows(connection, "audit_log"))

    @app.get("/api/v1/admin/audit-log/page", response_model=AuditLogPage)
    def audit_log_page(
        limit: int = Query(default=25, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        actor: str | None = Query(default=None, min_length=1, max_length=256),
        action: str | None = Query(default=None, min_length=1, max_length=128),
        target_type: str | None = Query(default=None, alias="targetType", min_length=1, max_length=64),
        target_id: int | None = Query(default=None, alias="targetId", ge=1),
        principal: AdminPrincipal = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        require_permission(principal, "admin.read")
        page = database.list_audit_log(
            connection,
            limit=limit,
            offset=offset,
            actor=actor,
            action=action,
            target_type=target_type,
            target_id=target_id,
        )
        return {**page, "items": _rows_to_dicts(page["items"])}

    return app


def _create_or_raise(create_record):
    try:
        return create_record()
    except database.DuplicateRecordError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except database.MissingRecordError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except database.InvalidStatusError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error


def _row_to_dict(row: sqlite3.Row) -> dict[str, object]:
    return dict(row)


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, object]]:
    return [_row_to_dict(row) for row in rows]


def _normalized_admin_role(is_admin: bool, requested_role: str) -> str:
    if not is_admin:
        return "member"
    return "operator" if requested_role == "member" else requested_role


def _verify_admin_mfa_if_enabled(
    *,
    connection: sqlite3.Connection,
    user_id: int,
    code: str | None,
    secret: str | None,
) -> None:
    row = database.get_admin_totp_secret(connection, user_id)
    if row is None or not int(row["enabled"]):
        return
    if not code:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin MFA code required")
    totp_secret = _decrypt_admin_totp_secret(str(row["encrypted_secret"]), secret)
    if not verify_totp_code(totp_secret, code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin MFA code")


def _admin_totp_secret_or_raise(
    *,
    connection: sqlite3.Connection,
    user_id: int,
    secret: str | None,
) -> str:
    row = database.get_admin_totp_secret(connection, user_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin MFA setup does not exist")
    return _decrypt_admin_totp_secret(str(row["encrypted_secret"]), secret)


def _decrypt_admin_totp_secret(encrypted_secret: str, secret: str | None) -> str:
    try:
        return decrypt_text(encrypted_secret, secret)
    except SecretBoxConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin MFA requires FREEMAIL_SESSION_SECRET",
        ) from error
    except SecretBoxDecryptionError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin MFA secret is invalid") from error


def _encrypted_push_token(push_token: str, secret: str | None) -> str | None:
    try:
        return encrypt_text(push_token, secret)
    except SecretBoxConfigurationError:
        return None


def _decrypted_push_token(row: sqlite3.Row, secret: str | None) -> str | None:
    encrypted = row["encrypted_push_token"]
    if not encrypted:
        return None
    try:
        return decrypt_text(str(encrypted), secret)
    except (SecretBoxConfigurationError, SecretBoxDecryptionError):
        return None


app = create_app()
