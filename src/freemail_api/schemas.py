from pydantic import BaseModel, ConfigDict, EmailStr, Field


def to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


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
    password_hash: str = Field(min_length=20, max_length=512)
    mailbox_local_part: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._%+-]+$")


class BootstrapAdminRecord(ApiModel):
    domain: DomainRecord
    user: "UserRecord"
    mailbox: "MailboxRecord"


class UserCreate(ApiModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=160)
    password_hash: str = Field(min_length=20, max_length=512)
    is_admin: bool = False


class UserRecord(ApiModel):
    id: int
    email: EmailStr
    display_name: str
    is_admin: bool
    status: str

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True, populate_by_name=True)


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


class MailboxSnapshotRecord(ApiModel):
    email: EmailStr
    folders: list[MailboxFolderSummary]
    messages: list[MailboxMessageSummary]


class MailboxSearchRecord(ApiModel):
    email: EmailStr
    folder: str
    query: str
    messages: list[MailboxMessageSummary]


class MailboxSessionCreate(ApiModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=512)


class MailboxSessionRecord(ApiModel):
    token: str
    email: EmailStr
    expires_at: int


class MailboxSessionDeleteRecord(ApiModel):
    revoked: bool


class MailboxSendCreate(ApiModel):
    recipients: list[EmailStr] = Field(min_length=1, max_length=50)
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1, max_length=20000)
    attachments: list["MailboxSendAttachmentCreate"] = Field(default_factory=list, max_length=5)


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
