import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    scope: str = Field(default="all", pattern="^(all|read|knowledge|chat)$")
    expires_at: datetime | None = None


class ApiKeyResponse(BaseModel):
    id: uuid.UUID
    name: str
    raw_key: str
    key_prefix: str
    scope: str
    is_active: bool
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class InitRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str
    password: str = Field(..., min_length=8, max_length=72)


class NotificationResponse(BaseModel):
    id: uuid.UUID
    type: str
    title: str
    content: str | None
    priority: str
    is_read: bool
    resource_type: str | None
    resource_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class QuotaConfig(BaseModel):
    max_kbs_per_user: int = 20
    max_docs_per_kb: int = 500
    max_storage_per_kb_mb: int = 2048


class SsoSettings(BaseModel):
    """OIDC SSO provider config — stored in SystemSettings.settings['sso'].

    Admin UI writes via POST /system/settings/update; OIDCAuthProvider reads
    via get_runtime_config. Secrets are stored as-is (plaintext) for the
    private-deployment model; refresh if you move to multi-tenant.
    """
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    issuer: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    redirect_uri: str | None = None
    scopes: str = "openid profile email"
    group_claim: str = "groups"
    role_map: dict[str, str] = Field(default_factory=dict)
    dept_map: dict[str, str] = Field(default_factory=dict)
    button_label: str = "使用 SSO 登录"
