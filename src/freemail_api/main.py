import binascii
from collections.abc import Iterator
from contextlib import asynccontextmanager
import csv
from hashlib import sha256
import io
import base64
import imaplib
import secrets
import smtplib
import sqlite3
import time
from urllib.parse import quote

from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query, Response, status
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
from .mailbox_imap import apply_blocked_sender_rules
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
    AdminSessionRevokeRecord,
    AdminSessionsDeleteRecord,
    AdminSessionsRecord,
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
    MailboxRecipientRuleCreate,
    MailboxRecipientRuleDeleteRecord,
    MailboxRecipientRuleRecord,
    MailboxRecipientRulesRecord,
    MailCoreSyncPlanStatusCreate,
    MailCoreSyncPlanStatusRecord,
    MailboxPushDeviceCreate,
    MailboxPushDeviceDeleteRecord,
    MailboxPushDeviceRecord,
    MailboxPushNotificationCreate,
    MailboxPushNotificationRecord,
    PublicUserInvitationRecord,
    MailboxReadStateCreate,
    MailboxReadStateRecord,
    MailboxRecord,
    MailboxSearchRecord,
    MailboxSendCreate,
    MailboxSendRecord,
    MailboxSenderRuleCreate,
    MailboxSenderRuleDeleteRecord,
    MailboxSenderRuleRecord,
    MailboxSenderRulesApplyCreate,
    MailboxSenderRulesApplyRecord,
    MailboxSenderRulesRecord,
    MailboxSessionCreate,
    MailboxSessionDeleteRecord,
    MailboxSessionRecord,
    MailboxSessionRevokeRecord,
    MailboxSessionsDeleteRecord,
    MailboxSessionsRecord,
    MailboxSnapshotRecord,
    MailboxStarStateCreate,
    MailboxStarStateRecord,
    MailboxThreadRecord,
    SavedMailboxContactCreate,
    SavedMailboxContactDeleteRecord,
    SavedMailboxContactRecord,
    SavedMailboxContactsRecord,
    StoredUserCreate,
    StoredUserInvitationCreate,
    UserCreate,
    UserInvitationAccept,
    UserInvitationAcceptRecord,
    UserInvitationCreate,
    UserInvitationCreated,
    UserInvitationRecord,
    UserPasswordUpdate,
    UserRecord,
)
from .sessions import bearer_token
from .sessions import create_admin_session
from .sessions import create_mailbox_session
from .sessions import hash_session_token
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


SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; "
        "base-uri 'self'; "
        "connect-src 'self' http://127.0.0.1:18090 https://freemail.kuzuryu.ai; "
        "form-action 'self'; "
        "frame-ancestors 'none'; "
        "img-src 'self' data:; "
        "object-src 'none'; "
        "script-src 'self'; "
        "style-src 'self'; "
        "upgrade-insecure-requests"
    ),
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "camera=(), geolocation=(), microphone=(), payment=(), usb=()",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


COMPONENT_READINESS = {
    "adminApi": {
        "status": "ready",
        "evidence": [
            "administrator bootstrap, bearer-session login, and authenticator-app MFA",
            "domain, user, invitation-link signup, user-password rotation, suspension-triggered session revocation, admin session inspection/revocation, mailbox quota, alias, DKIM, DNS, status, and filterable/exportable audit APIs",
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
            "mailbox session login, session inspection, targeted and bulk session revocation, paginated and thread-aware folder navigation and search, conversation lookup, contacts, sender allow/block rules with current-folder block enforcement, recipient allow/block rules with pre-SMTP outbound enforcement, message read, header inspection, EML import/export, read/unread state, star state, compose, attachments, archive, move, delete, and empty-folder controls",
            "bulk message actions for read/unread, star/unstar, archive, spam, delete, and move",
            "persistent mailbox preferences with default compose signatures and saved address-book contacts",
            "server-side Drafts persistence and compose reopen support for saved drafts",
            "server-side Sent Items persistence for accepted outbound messages",
            "tab-scoped browser bearer-session storage, HTTP security headers, invite-link signup, and token-gated admin console for bootstrap, MFA setup, users, invitation links, password rotation, domains, mailboxes, aliases, DKIM, DNS guidance, status actions, sync status, and audit-log filtering, pagination, and CSV export",
            "browser and static QA in CI",
        ],
        "remainingReleaseEvidence": [
            "decision-owner private-beta acceptance",
        ],
    },
    "mobile": {
        "status": "source-ready",
        "evidence": [
            "Expo/React Native client with VPN API target, invitation signup, native invite-link routing, hosted app-link association endpoints, icon tab shell, mailbox sessions, targeted and bulk session revocation, paginated and thread-aware message workflows, conversation lookup, header inspection, EML import/export/share, draft saving/editing, read/unread and star state, archive/spam/delete actions, folder and empty-folder controls, extracted and saved contacts, sender allow/block rules with current-folder block enforcement, recipient allow/block rules with pre-SMTP outbound enforcement, attachments, offline metadata cache, SecureStore-backed development push identity, and push-device flows",
            "bulk read/star/archive/spam/delete/move client controls over the shared mailbox API",
            "mobile preference controls for default compose signatures",
            "compose/send path uses the shared mailbox API contract with Sent Items persistence status",
            "credential-free EAS build/submit profiles plus mobile static QA, config validation, native prebuild drill, typecheck, and dependency audit in CI",
        ],
        "remainingReleaseEvidence": [
            "real signed native mobile builds",
            "real store-submission evidence",
            "private-beta device validation",
            "app-store release execution",
        ],
    },
}

RELEASE_BLOCKER_ACTIONS = {
    "decision-owner private-beta acceptance": {
        "id": "record-private-beta-acceptance",
        "reason": "decision-owner private-beta acceptance evidence is incomplete",
        "command": ".\\.venv\\Scripts\\python.exe scripts\\collect_private_beta_acceptance.py --domain <domain> --output .freemail-qa\\private-beta\\private-beta-acceptance.<domain>.json --decision-owner <decision-owner> --accepted --accepted-at <iso-8601>",
    },
    "private-beta device validation": {
        "id": "record-mobile-device-validation",
        "reason": "iOS and Android private-beta device validation evidence is incomplete",
        "command": ".\\.venv\\Scripts\\python.exe scripts\\collect_mobile_device_validation.py --platform <ios-or-android> --tested --tested-at <iso-8601> --tester <tester> --device-model <device> --os-version <os-version> --app-version <app-version> --evidence-url <https-device-evidence-url> --all-checks-passed",
    },
    "real signed native mobile builds": {
        "id": "record-signed-mobile-build",
        "reason": "signed iOS and Android native build evidence is incomplete",
        "signingReadinessCommand": ".\\.venv\\Scripts\\python.exe scripts\\mobile_signing_readiness.py --repo CYINT/freemail",
        "prerequisiteCommand": "gh workflow run mobile-eas-private-beta.yml --repo CYINT/freemail -f platform=<ios-or-android> -f profile=private-beta -f submit_after_build=false -f confirmation=launch-mobile-private-beta",
        "command": ".\\.venv\\Scripts\\python.exe scripts\\collect_mobile_build_evidence.py --platform <ios-or-android> --signed --distribution private-beta --build-url <https-build-evidence-url> --native-build-id <native-build-id> --artifact-type <ipa-or-aab> --artifact-bytes <bytes> --artifact-sha256 <sha256>",
    },
    "real store-submission evidence": {
        "id": "record-mobile-store-submission",
        "reason": "iOS and Android store-submission evidence is incomplete",
        "command": ".\\.venv\\Scripts\\python.exe scripts\\collect_mobile_store_submission.py --platform <ios-or-android> --submitted --track <testflight-or-internal-testing> --submission-url <https-store-submission-url> --native-build-id <native-build-id> --submitted-at <iso-8601> --review-state <state>",
    },
    "app-store release execution": {
        "id": "complete-app-store-release-execution",
        "reason": "app-store release execution and final release-gate evidence are not complete",
        "command": ".\\.venv\\Scripts\\python.exe scripts\\release_gate.py --manifest .freemail-qa\\release\\release-evidence-manifest.json --require-mobile-store-submission",
    },
}


def release_blocker_next_actions(release_blockers: list[str]) -> list[dict[str, object]]:
    actions = []
    blocker_set = set(release_blockers)
    for blocker, action in RELEASE_BLOCKER_ACTIONS.items():
        if blocker not in blocker_set:
            continue
        actions.append({**action, "releaseBlockers": [blocker]})
    return actions


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

    @app.middleware("http")
    async def add_security_headers(request, call_next):
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response

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

    def _mailbox_bearer_token_or_raise(authorization: str | None) -> str:
        token = bearer_token(authorization)
        if not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Mailbox bearer session required")
        return token

    def _mailbox_credentials_from_token(
        *,
        connection: sqlite3.Connection,
        token: str,
        secret: str | None,
    ) -> MailboxCredentials:
        try:
            credentials = resolve_mailbox_session(connection, token=token, secret=secret)
            ensure_mailbox_access_allowed(connection, credentials.email)
            return credentials
        except SessionConfigurationError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Mailbox sessions are not configured",
            ) from error
        except InvalidSessionError as error:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid mailbox session") from error

    def _current_time() -> int:
        return int(time.time())

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
            "nextActions": release_blocker_next_actions(release_blockers),
        }

    @app.get("/api/v1/deployment")
    def deployment() -> dict[str, object]:
        return {
            "hostname": active_settings.hostname,
            "exposure": "vpn-only",
            "publicInternet": False,
            "requiredBoundary": "Dragonscale/VPN clients only",
        }

    @app.get("/.well-known/apple-app-site-association")
    def apple_app_site_association() -> dict[str, object]:
        team_id = _mobile_ios_team_id_or_raise(active_settings)
        app_id = f"{team_id}.{active_settings.mobile_ios_bundle_id}"
        return {
            "applinks": {
                "apps": [],
                "details": [
                    {
                        "appIDs": [app_id],
                        "components": [
                            {
                                "/": "/",
                                "?": {"invite": "*"},
                                "comment": "FreeMail invitation links",
                            }
                        ],
                    }
                ],
            }
        }

    @app.get("/.well-known/assetlinks.json")
    def android_asset_links() -> list[dict[str, object]]:
        fingerprints = _mobile_android_fingerprints_or_raise(active_settings)
        return [
            {
                "relation": ["delegate_permission/common.handle_all_urls"],
                "target": {
                    "namespace": "android_app",
                    "package_name": active_settings.mobile_android_package,
                    "sha256_cert_fingerprints": fingerprints,
                },
            }
        ]

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

    @app.get("/api/v1/admin/sessions", response_model=AdminSessionsRecord)
    def admin_sessions_list(
        authorization: str | None = Header(default=None),
        principal: AdminPrincipal = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        token = bearer_token(authorization)
        token_hash = hash_session_token(token) if token else ""
        rows = database.list_admin_sessions_for_user(
            connection,
            user_id=principal.user_id,
            now=_current_time(),
        )
        return {
            "email": principal.email,
            "sessions": [
                {
                    "id": int(row["id"]),
                    "email": str(row["email"]),
                    "expires_at": int(row["expires_at"]),
                    "created_at": str(row["created_at"]),
                    "current": str(row["token_hash"]) == token_hash,
                }
                for row in rows
            ],
        }

    @app.delete("/api/v1/admin/sessions", response_model=AdminSessionsDeleteRecord)
    def admin_sessions_delete(
        principal: AdminPrincipal = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, int]:
        return {"revoked": database.revoke_admin_sessions_for_user(connection, user_id=principal.user_id)}

    @app.delete("/api/v1/admin/sessions/{session_id}", response_model=AdminSessionRevokeRecord)
    def admin_session_revoke(
        session_id: int = Path(ge=1),
        principal: AdminPrincipal = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        revoked = database.revoke_admin_session_for_user(
            connection,
            user_id=principal.user_id,
            session_id=session_id,
        )
        return {"revoked": revoked, "session_id": session_id}

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

    @app.get("/api/v1/mailbox/sessions", response_model=MailboxSessionsRecord)
    def mailbox_sessions_list(
        authorization: str | None = Header(default=None),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        token = _mailbox_bearer_token_or_raise(authorization)
        credentials = _mailbox_credentials_from_token(
            connection=connection,
            token=token,
            secret=active_settings.session_secret,
        )
        token_hash = hash_session_token(token)
        rows = database.list_mailbox_sessions_for_email(connection, email=credentials.email, now=_current_time())
        return {
            "email": credentials.email,
            "sessions": [
                {
                    "id": int(row["id"]),
                    "email": str(row["email"]),
                    "expires_at": int(row["expires_at"]),
                    "created_at": str(row["created_at"]),
                    "current": str(row["token_hash"]) == token_hash,
                }
                for row in rows
            ],
        }

    @app.delete("/api/v1/mailbox/sessions", response_model=MailboxSessionsDeleteRecord)
    def mailbox_sessions_delete(
        authorization: str | None = Header(default=None),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, int]:
        token = _mailbox_bearer_token_or_raise(authorization)
        credentials = _mailbox_credentials_from_token(
            connection=connection,
            token=token,
            secret=active_settings.session_secret,
        )
        return {"revoked": database.revoke_mailbox_sessions_for_email(connection, email=credentials.email)}

    @app.delete("/api/v1/mailbox/sessions/{session_id}", response_model=MailboxSessionRevokeRecord)
    def mailbox_session_revoke(
        session_id: int = Path(ge=1),
        authorization: str | None = Header(default=None),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        token = _mailbox_bearer_token_or_raise(authorization)
        credentials = _mailbox_credentials_from_token(
            connection=connection,
            token=token,
            secret=active_settings.session_secret,
        )
        revoked = database.revoke_mailbox_session_for_email(
            connection,
            email=credentials.email,
            session_id=session_id,
        )
        return {"revoked": revoked, "session_id": session_id}

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

    @app.get("/api/v1/mailbox/sender-rules", response_model=MailboxSenderRulesRecord)
    def mailbox_sender_rules_list(
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
            "rules": _rows_to_dicts(database.list_mailbox_sender_rules(connection, email=normalized_email)),
        }

    @app.put("/api/v1/mailbox/sender-rules", response_model=MailboxSenderRuleRecord)
    def mailbox_sender_rule_upsert(
        payload: MailboxSenderRuleCreate,
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
        rule = database.upsert_mailbox_sender_rule(
            connection,
            email=credentials.email,
            sender_email=str(payload.sender_email),
            action=payload.action,
            notes=payload.notes,
        )
        return dict(rule)

    @app.delete("/api/v1/mailbox/sender-rules/{rule_id}", response_model=MailboxSenderRuleDeleteRecord)
    def mailbox_sender_rule_delete(
        rule_id: int,
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
            "deleted": database.delete_mailbox_sender_rule(
                connection,
                email=credentials.email,
                rule_id=rule_id,
            ),
            "rule_id": rule_id,
        }

    @app.post("/api/v1/mailbox/sender-rules/apply", response_model=MailboxSenderRulesApplyRecord)
    def mailbox_sender_rules_apply(
        payload: MailboxSenderRulesApplyCreate,
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
        rules = database.list_mailbox_sender_rules(connection, email=credentials.email)
        blocked_senders = [str(rule["sender_email"]) for rule in rules if rule["action"] == "block"]
        allowed_senders = [str(rule["sender_email"]) for rule in rules if rule["action"] == "allow"]
        try:
            result = apply_blocked_sender_rules(
                email=credentials.email,
                password=credentials.password,
                host=active_settings.mail_core_host,
                port=active_settings.imap_port,
                folder=payload.folder,
                target_folder=payload.target_folder,
                blocked_senders=blocked_senders,
                allowed_senders=allowed_senders,
            )
        except OSError as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
        except imaplib.IMAP4.error as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
        return result.as_dict()

    @app.get("/api/v1/mailbox/recipient-rules", response_model=MailboxRecipientRulesRecord)
    def mailbox_recipient_rules_list(
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
            "rules": _rows_to_dicts(database.list_mailbox_recipient_rules(connection, email=normalized_email)),
        }

    @app.put("/api/v1/mailbox/recipient-rules", response_model=MailboxRecipientRuleRecord)
    def mailbox_recipient_rule_upsert(
        payload: MailboxRecipientRuleCreate,
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
        rule = database.upsert_mailbox_recipient_rule(
            connection,
            email=credentials.email,
            recipient_email=str(payload.recipient_email),
            action=payload.action,
            notes=payload.notes,
        )
        return dict(rule)

    @app.delete("/api/v1/mailbox/recipient-rules/{rule_id}", response_model=MailboxRecipientRuleDeleteRecord)
    def mailbox_recipient_rule_delete(
        rule_id: int,
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
            "deleted": database.delete_mailbox_recipient_rule(
                connection,
                email=credentials.email,
                rule_id=rule_id,
            ),
            "rule_id": rule_id,
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
            recipients = [str(recipient) for recipient in payload.recipients]
            blocked_recipients = database.blocked_mailbox_recipients(
                connection,
                email=credentials.email,
                recipients=recipients,
            )
            if blocked_recipients:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Blocked recipient rule matched: {', '.join(blocked_recipients)}",
                )
            recipient_count = len(recipients)
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
                recipients=recipients,
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

    @app.get("/api/v1/admin/invitations", response_model=list[UserInvitationRecord])
    def list_user_invitations(
        principal: AdminPrincipal = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> list[dict[str, object]]:
        require_permission(principal, "admin.read")
        return [_invitation_record(row) for row in database.list_user_invitations(connection)]

    @app.post("/api/v1/admin/invitations", response_model=UserInvitationCreated, status_code=status.HTTP_201_CREATED)
    def create_user_invitation(
        payload: UserInvitationCreate,
        principal: AdminPrincipal = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        require_permission(principal, "admin.users")
        if payload.is_admin:
            require_permission(principal, "admin.grant")
        token = secrets.token_urlsafe(32)
        admin_role = _normalized_admin_role(payload.is_admin, payload.admin_role)
        invitation = _create_or_raise(
            lambda: database.create_user_invitation(
                connection,
                StoredUserInvitationCreate(
                    email=payload.email,
                    display_name=payload.display_name,
                    token_hash=_invitation_token_hash(token),
                    is_admin=payload.is_admin,
                    admin_role=admin_role,
                    expires_at=int(time.time()) + payload.expires_in_seconds,
                ),
                principal.actor,
            )
        )
        return {
            **_invitation_record(invitation),
            "token": token,
            "inviteUrl": _invitation_url(active_settings.hostname, token),
        }

    @app.get("/api/v1/invitations/{token}", response_model=PublicUserInvitationRecord)
    def get_user_invitation(
        token: str = Path(min_length=16, max_length=256),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        invitation = _public_invitation_or_raise(connection, token)
        return {
            "email": invitation["email"],
            "displayName": invitation["display_name"],
            "isAdmin": bool(invitation["is_admin"]),
            "adminRole": invitation["admin_role"],
            "expiresAt": invitation["expires_at"],
        }

    @app.post("/api/v1/invitations/{token}/accept", response_model=UserInvitationAcceptRecord)
    def accept_user_invitation(
        payload: UserInvitationAccept,
        token: str = Path(min_length=16, max_length=256),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, object]:
        _public_invitation_or_raise(connection, token)
        user = _create_or_raise(
            lambda: database.accept_user_invitation(
                connection,
                token_hash=_invitation_token_hash(token),
                password_hash=hash_initial_password(payload.password),
                display_name=payload.display_name,
                now=int(time.time()),
            )
        )
        return {"user": _row_to_dict(user)}

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

    @app.get("/api/v1/admin/audit-log/export")
    def audit_log_export(
        limit: int = Query(default=1000, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
        actor: str | None = Query(default=None, min_length=1, max_length=256),
        action: str | None = Query(default=None, min_length=1, max_length=128),
        target_type: str | None = Query(default=None, alias="targetType", min_length=1, max_length=64),
        target_id: int | None = Query(default=None, alias="targetId", ge=1),
        principal: AdminPrincipal = Depends(require_admin),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> Response:
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
        output = io.StringIO()
        fieldnames = ["id", "actor", "action", "target_type", "target_id", "created_at"]
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(_rows_to_dicts(page["items"]))
        return Response(
            content=output.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="freemail-audit-log.csv"'},
        )

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


def _invitation_record(row: sqlite3.Row) -> dict[str, object]:
    record = _row_to_dict(row)
    record["isAdmin"] = bool(record.pop("is_admin"))
    record["adminRole"] = record.pop("admin_role")
    record["displayName"] = record.pop("display_name")
    record["expiresAt"] = record.pop("expires_at")
    record["acceptedAt"] = record.pop("accepted_at")
    record["createdAt"] = record.pop("created_at")
    record.pop("token_hash", None)
    return record


def _public_invitation_or_raise(connection: sqlite3.Connection, token: str) -> sqlite3.Row:
    try:
        invitation = database.get_user_invitation_by_token_hash(connection, _invitation_token_hash(token))
    except database.MissingRecordError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found") from error
    if invitation["accepted_at"] is not None:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Invitation has already been accepted")
    if int(invitation["expires_at"]) < int(time.time()):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Invitation has expired")
    return invitation


def _invitation_token_hash(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def _invitation_url(hostname: str, token: str) -> str:
    return f"https://{hostname}/?invite={quote(token)}"


def _mobile_ios_team_id_or_raise(settings: Settings) -> str:
    team_id = str(settings.mobile_ios_team_id or "").strip().upper()
    if not team_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Mobile iOS associated domain is not configured",
        )
    if len(team_id) != 10 or not team_id.isalnum():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Mobile iOS team identifier is invalid",
        )
    return team_id


def _mobile_android_fingerprints_or_raise(settings: Settings) -> list[str]:
    raw_value = settings.mobile_android_sha256_cert_fingerprints or ""
    fingerprints = [
        candidate.strip().upper()
        for value in raw_value.replace("\n", ",").replace(";", ",").split(",")
        if (candidate := value.strip())
    ]
    if not fingerprints:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Mobile Android asset links are not configured",
        )
    if any(not _is_sha256_fingerprint(fingerprint) for fingerprint in fingerprints):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Mobile Android SHA-256 certificate fingerprint is invalid",
        )
    return fingerprints


def _is_sha256_fingerprint(value: str) -> bool:
    parts = value.split(":")
    return len(parts) == 32 and all(
        len(part) == 2 and all(character in "0123456789ABCDEF" for character in part) for part in parts
    )


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
