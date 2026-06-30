from pydantic import BaseModel, ConfigDict, EmailStr, Field


def to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class AdminStatusUpdate(ApiModel):
    status: str = Field(pattern=r"^(active|invited|suspended)$")


class DomainCreate(ApiModel):
    name: str = Field(min_length=1, max_length=253, pattern=r"^[A-Za-z0-9.-]+$")


class DomainRecord(ApiModel):
    id: int
    name: str
    status: str

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True, populate_by_name=True)


class BootstrapAdminCreate(ApiModel):
    domain_name: str = Field(min_length=1, max_length=253, pattern=r"^[A-Za-z0-9.-]+$")
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=160)
    initial_password: str = Field(min_length=12, max_length=512)
    mailbox_local_part: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._%+-]+$")


class BootstrapAdminRecord(ApiModel):
    domain: DomainRecord
    user: "UserRecord"
    mailbox: "MailboxRecord"


class UserCreate(ApiModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=160)
    initial_password: str = Field(min_length=12, max_length=512)
    is_admin: bool = False
    admin_role: str = Field(default="member", pattern=r"^(member|auditor|operator|admin|owner)$")


class StoredUserCreate(ApiModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=160)
    password_hash: str = Field(min_length=20, max_length=512)
    is_admin: bool = False
    admin_role: str = Field(default="member", pattern=r"^(member|auditor|operator|admin|owner)$")


class UserRecord(ApiModel):
    id: int
    email: EmailStr
    display_name: str
    is_admin: bool
    admin_role: str
    status: str

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True, populate_by_name=True)


class AdminSessionCreate(ApiModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=512)


class AdminSessionRecord(ApiModel):
    token: str
    email: EmailStr
    expires_at: int


class AdminSessionDeleteRecord(ApiModel):
    revoked: bool


class MailboxCreate(ApiModel):
    user_id: int = Field(gt=0)
    local_part: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._%+-]+$")
    domain_id: int = Field(gt=0)


class MailboxRecord(ApiModel):
    id: int
    user_id: int
    address: EmailStr
    status: str

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True, populate_by_name=True)


class AliasCreate(ApiModel):
    source: EmailStr
    destination: EmailStr


class AliasRecord(ApiModel):
    id: int
    source: EmailStr
    destination: EmailStr
    status: str

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True, populate_by_name=True)


class DkimKeyCreate(ApiModel):
    selector: str = Field(min_length=1, max_length=63, pattern=r"^[A-Za-z0-9_-]+$")
    domain_id: int = Field(gt=0)


class DkimKeyRecord(ApiModel):
    id: int
    domain_id: int
    selector: str
    dns_name: str
    public_txt: str
    status: str

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True, populate_by_name=True)


class DkimKeyCreated(DkimKeyRecord):
    private_key_pem: str


class DnsRecord(ApiModel):
    type: str
    name: str
    value: str
    ttl: int = 3600
    purpose: str


class DomainDnsGuidance(ApiModel):
    domain: str
    records: list[DnsRecord]


class ObservedDnsRecord(ApiModel):
    type: str = Field(min_length=1, max_length=16)
    name: str = Field(min_length=1, max_length=253)
    values: list[str] = Field(min_length=1)


class DomainDnsPostureCreate(ApiModel):
    observed_records: list[ObservedDnsRecord]


class DnsCheckRecord(ApiModel):
    type: str
    name: str
    expected: str
    found: bool
    observed: list[str]


class DomainDnsPostureRecord(ApiModel):
    domain: str
    ready: bool
    checks: list[DnsCheckRecord]


class MailCoreSyncPlanStatusCreate(ApiModel):
    available_user_secrets: list[EmailStr] = Field(default_factory=list)


class MailCoreSyncPlanStatusRecord(ApiModel):
    ready: bool
    operation_types: list[str]
    domains: int
    dkim_keys: int
    accounts: int
    aliases: int
    missing_provisioning_secrets: list[EmailStr]


class AuditRecord(ApiModel):
    id: int
    actor: str
    action: str
    target_type: str
    target_id: int
    created_at: str

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True, populate_by_name=True)


class MailboxFolderSummary(ApiModel):
    name: str
    message_count: int
    unread_count: int


class MailboxMessageSummary(ApiModel):
    folder: str
    message_id: str
    subject: str
    sender: str
    recipients: str
    date: str
    unread: bool
    starred: bool = False
    thread_id: str
    thread_subject: str
    in_reply_to: str | None = None


class MailboxAttachmentRecord(ApiModel):
    attachment_id: str
    filename: str
    content_type: str
    size: int


class MailboxMessageDetailRecord(MailboxMessageSummary):
    body: str
    attachments: list[MailboxAttachmentRecord] = []


class MailboxArchiveCreate(ApiModel):
    folder: str = Field(min_length=1, max_length=160)
    message_id: str = Field(min_length=1, max_length=64)
    archive_folder: str = Field(default="Archive", min_length=1, max_length=160)


class MailboxArchiveRecord(ApiModel):
    archived: bool
    folder: str
    message_id: str
    archive_folder: str


class MailboxMoveCreate(ApiModel):
    folder: str = Field(min_length=1, max_length=160)
    message_id: str = Field(min_length=1, max_length=64)
    target_folder: str = Field(min_length=1, max_length=160)


class MailboxMoveRecord(ApiModel):
    moved: bool
    folder: str
    message_id: str
    target_folder: str


class MailboxReadStateCreate(ApiModel):
    folder: str = Field(min_length=1, max_length=160)
    message_id: str = Field(min_length=1, max_length=64)
    read: bool


class MailboxReadStateRecord(ApiModel):
    folder: str
    message_id: str
    read: bool
    unread: bool


class MailboxStarStateCreate(ApiModel):
    folder: str = Field(min_length=1, max_length=160)
    message_id: str = Field(min_length=1, max_length=64)
    starred: bool


class MailboxStarStateRecord(ApiModel):
    folder: str
    message_id: str
    starred: bool


class MailboxBulkActionCreate(ApiModel):
    folder: str = Field(min_length=1, max_length=160)
    message_ids: list[str] = Field(min_length=1, max_length=100)
    action: str = Field(pattern=r"^(read|unread|star|unstar|archive|spam|delete|move)$")
    target_folder: str | None = Field(default=None, min_length=1, max_length=160)


class MailboxBulkActionRecord(ApiModel):
    folder: str
    action: str
    message_ids: list[str]
    succeeded: int
    target_folder: str | None = None


class MailboxFolderCreate(ApiModel):
    folder: str = Field(min_length=1, max_length=160, pattern=r'^[^"/\\\r\n]+$')


class MailboxFolderRename(ApiModel):
    folder: str = Field(min_length=1, max_length=160, pattern=r'^[^"/\\\r\n]+$')
    target_folder: str = Field(min_length=1, max_length=160, pattern=r'^[^"/\\\r\n]+$')


class MailboxFolderDelete(ApiModel):
    folder: str = Field(min_length=1, max_length=160, pattern=r'^[^"/\\\r\n]+$')


class MailboxFolderMutationRecord(ApiModel):
    folder: str
    action: str
    success: bool
    target_folder: str | None = None


class MailboxSnapshotRecord(ApiModel):
    email: EmailStr
    folders: list[MailboxFolderSummary]
    messages: list[MailboxMessageSummary]
    limit: int = 25
    offset: int = 0
    next_offset: int | None = None
    has_more: bool = False


class MailboxSearchRecord(ApiModel):
    email: EmailStr
    folder: str
    query: str
    messages: list[MailboxMessageSummary]
    limit: int = 25
    offset: int = 0
    next_offset: int | None = None
    has_more: bool = False


class MailboxThreadRecord(ApiModel):
    email: EmailStr
    folder: str
    thread_id: str
    thread_subject: str
    messages: list[MailboxMessageSummary]


class MailboxContactRecord(ApiModel):
    name: str
    email: EmailStr
    message_count: int


class MailboxContactsRecord(ApiModel):
    email: EmailStr
    folder: str
    contacts: list[MailboxContactRecord]


class MailboxSessionCreate(ApiModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=512)


class MailboxSessionRecord(ApiModel):
    token: str
    email: EmailStr
    expires_at: int


class MailboxSessionDeleteRecord(ApiModel):
    revoked: bool


class MailboxPreferencesUpdate(ApiModel):
    display_name: str = Field(default="", max_length=160)
    signature: str = Field(default="", max_length=4000)


class MailboxPreferencesRecord(ApiModel):
    mailbox_email: EmailStr
    display_name: str
    signature: str
    updated_at: str

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True, populate_by_name=True)


class MailboxPushDeviceCreate(ApiModel):
    device_id: str = Field(min_length=8, max_length=160, pattern=r"^[A-Za-z0-9._:-]+$")
    platform: str = Field(min_length=3, max_length=20, pattern=r"^(ios|android|web|development)$")
    push_token: str = Field(min_length=8, max_length=512)
    provider: str = Field(default="contract-only", min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")


class MailboxPushDeviceRecord(ApiModel):
    id: int
    mailbox_email: EmailStr
    device_id: str
    platform: str
    provider: str
    enabled: bool
    created_at: str
    updated_at: str

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True, populate_by_name=True)


class MailboxPushDeviceDeleteRecord(ApiModel):
    revoked: bool
    device_id: str


class MailboxPushNotificationCreate(ApiModel):
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=240)


class MailboxPushNotificationRecord(ApiModel):
    id: int
    mailbox_email: EmailStr
    device_id: str
    provider: str
    title: str
    body: str
    status: str
    provider_message_id: str | None = None
    last_error: str | None = None
    created_at: str
    delivered_at: str | None = None

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True, populate_by_name=True)


class MailboxSendCreate(ApiModel):
    recipients: list[EmailStr] = Field(min_length=1, max_length=50)
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1, max_length=20000)
    attachments: list["MailboxSendAttachmentCreate"] = Field(default_factory=list, max_length=5)


class MailboxDraftCreate(ApiModel):
    recipients: list[EmailStr] = Field(default_factory=list, max_length=50)
    subject: str = Field(default="", max_length=255)
    body: str = Field(default="", max_length=20000)
    attachments: list["MailboxSendAttachmentCreate"] = Field(default_factory=list, max_length=5)
    draft_folder: str = Field(default="Drafts", min_length=1, max_length=160)


class MailboxSendAttachmentCreate(ApiModel):
    filename: str = Field(min_length=1, max_length=180)
    content_type: str = Field(default="application/octet-stream", min_length=1, max_length=120)
    content_base64: str = Field(min_length=1, max_length=2_800_000)


class MailboxSendRecord(ApiModel):
    accepted: bool
    message_id: str
    sender: EmailStr
    recipients: list[EmailStr]
    subject: str
    sent_folder: str
    sent_folder_saved: bool


class MailboxDraftRecord(ApiModel):
    saved: bool
    message_id: str
    sender: EmailStr
    recipients: list[EmailStr]
    subject: str
    draft_folder: str
