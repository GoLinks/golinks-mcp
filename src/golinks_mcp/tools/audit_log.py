from typing import Annotated, Literal

import httpx
from fastmcp import Context
from fastmcp.tools import ToolResult
from pydantic import BaseModel, Field

from golinks_mcp.client import (
    external_params,
    format_timestamp,
    get_authorization_header,
    http_client,
    iso_timestamp,
    raise_for_status,
)

# ---------------------------------------------------------------------------
# Audit log literals
# ---------------------------------------------------------------------------

AuditLogGeneralType = Literal["Added", "Changed", "Removed"]

AuditLogSection = Literal[
    "Golinks",
    "UserManagement",
    "Settings",
    "DeveloperTools",
    "SCIM",
    "Collections",
    "Tags",
    "Jots",
]

AuditLogEventType = Literal[
    "APITokenCreated",
    "APITokenDeleted",
    "APITokenUpdated",
    "APITokenRevoked",
    "DomainRolesUpdated",
    "GoLinkCreated",
    "GoLinkDeleted",
    "GoLinkLocked",
    "GoLinkPinned",
    "GoLinkUnlocked",
    "GoLinkUnpinned",
    "GoLinkUpdated",
    "InviteRevoked",
    "SetAccessLevel",
    "SetActiveStatus",
    "SetAdminStatus",
    "UserInvited",
    "UserUpdated",
    "WebhookCreated",
    "WebhookDeleted",
    "WebhookUpdated",
    "OAuthAppCreated",
    "OAuthAppDeleted",
    "OAuthAppUpdated",
    "WorkspaceSettingsChanged",
    "SCIMUserCreated",
    "SCIMUserUpdated",
    "SCIMUserDeactivated",
    "SCIMTokenCreated",
    "SCIMTokenRevoked",
    "CollectionCreated",
    "CollectionDeleted",
    "CollectionUpdated",
    "TagCreated",
    "TagDeleted",
    "TagUpdated",
    "TagsMerged",
    "JotCreated",
    "JotDeleted",
    "ProvisionedUserRemoved",
    "CrossProductLoginTokenIssued",
]

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class AuditLogEntry(BaseModel):
    alid: int = 0
    uid: int | None = None
    email: str = ""
    event_type: str = ""
    general_type: str = ""
    section: str = ""
    api: str = ""
    method: str = ""
    message: str | None = None
    created_at: int | None = None
    updated_at: int | None = None


class AuditLogPaginationMetadata(BaseModel):
    limit: int = 0
    offset: int = 0
    total_results: int = 0
    count: int = 0


class AuditLogListResponse(BaseModel):
    metadata: AuditLogPaginationMetadata = AuditLogPaginationMetadata()
    results: list[AuditLogEntry] = []


# ---------------------------------------------------------------------------
# Tool output models
# ---------------------------------------------------------------------------


class AuditLogEntryOutput(BaseModel):
    alid: int = Field(description="Numeric audit log entry ID.")
    uid: int | None = Field(description="Numeric ID of the user who performed the action.")
    email: str | None = Field(description="Email of the user who performed the action.")
    event_type: str = Field(
        description=(
            "Display label (e.g. 'Go link created'), not the 'event_type' filter "
            "value. When chaining, pass the matching filter value instead (e.g. 'GoLinkCreated')."
        )
    )
    general_type: str = Field(description="'Added', 'Changed', or 'Removed'.")
    section: str = Field(
        description=(
            "Display label (e.g. 'Go links'), not the 'section' filter value. When "
            "chaining, pass the matching filter value instead (e.g. 'Golinks')."
        )
    )
    message: str | None = None
    created_at: str | None = Field(description="ISO 8601 UTC timestamp.")


class AuditLogListOutput(BaseModel):
    metadata: AuditLogPaginationMetadata
    results: list[AuditLogEntryOutput]


def _to_output(entry: AuditLogEntry) -> AuditLogEntryOutput:
    return AuditLogEntryOutput(
        alid=entry.alid,
        uid=entry.uid,
        email=entry.email or None,
        event_type=entry.event_type,
        general_type=entry.general_type,
        section=entry.section,
        message=entry.message or None,
        created_at=iso_timestamp(entry.created_at),
    )


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _format_entry(entry: AuditLogEntry) -> str:
    lines = [
        f"ALID:    {entry.alid}",
        f"Event:   {entry.event_type}",
        f"Type:    {entry.general_type}",
        f"Section: {entry.section}",
        f"User:    {entry.email or 'Unknown'}",
    ]
    if entry.message:
        lines.append(f"Message: {entry.message}")
    lines.append(f"When:    {format_timestamp(entry.created_at)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


async def get_audit_logs(
    general_type: Annotated[
        AuditLogGeneralType | None,
        Field(description="Filter by general change type: 'Added', 'Changed', or 'Removed'."),
    ] = None,
    section: Annotated[
        AuditLogSection | None,
        Field(
            description=(
                "Filter by workspace section, one of: 'Golinks', 'UserManagement', "
                "'Settings', 'DeveloperTools', 'SCIM', 'Collections', 'Tags', 'Jots'."
            )
        ),
    ] = None,
    event_type: Annotated[
        AuditLogEventType | None,
        Field(
            description=(
                "Filter by a specific audit event type (e.g. 'GoLinkCreated', "
                "'UserInvited', 'SetAdminStatus')."
            )
        ),
    ] = None,
    filter_uid: Annotated[
        int | None,
        Field(
            description=(
                "Filter logs to actions performed by a specific numeric user ID. Use "
                "search_users to look up a person's numeric uid by name/username/email."
            ),
            ge=1,
        ),
    ] = None,
    search: Annotated[
        str | None,
        Field(description="Free-text search term matched against the log message and event type."),
    ] = None,
    limit: Annotated[
        int, Field(description="Number of audit log entries to return (1–100).", ge=1, le=100)
    ] = 20,
    offset: Annotated[int, Field(description="Pagination offset (0-based).", ge=0)] = 0,
    ctx: Context | None = None,
) -> ToolResult:
    """Get audit log entries for the caller's GoLinks workspace (https://www.golinks.io).

    Returns a paginated, filterable history of admin-relevant changes such as
    go link creation/deletion, user management, SCIM, and developer tool
    events. The caller must be a workspace admin with permission to view the
    audit log, and the workspace must have the audit log feature enabled.
    Read-only.

    All filters (general_type, section, event_type, filter_uid, search) are
    optional. Call with no filters to get the most recent entries across the
    whole workspace, most recent first.

    Returned 'event_type' and 'section' values are display labels, not filter values.
    To filter a follow-up call, use the matching 'event_type'/'section' filter value instead.

    Requires admin:read scope.
    """
    if ctx is None:
        raise PermissionError("Missing request context.")
    authorization = get_authorization_header(ctx)

    raw_params: dict = {"limit": limit, "offset": offset}
    if general_type is not None:
        raw_params["general_type"] = general_type
    if section is not None:
        raw_params["section"] = section
    if event_type is not None:
        raw_params["event_type"] = event_type
    if filter_uid is not None:
        raw_params["filter_uid"] = filter_uid
    if search:
        raw_params["search"] = search

    params = external_params(raw_params, tool="get_audit_logs")

    try:
        response = await http_client.get(
            "/admin/audit_log",
            params=params,
            headers={"Authorization": authorization},
        )
    except httpx.TimeoutException:
        raise TimeoutError("Request to GoLinks API timed out.")
    except httpx.ConnectError:
        raise ConnectionError("Failed to connect to GoLinks API.")

    raise_for_status(response, "/admin/audit_log")

    data = AuditLogListResponse.model_validate(response.json())
    structured = AuditLogListOutput(
        metadata=data.metadata,
        results=[_to_output(e) for e in data.results],
    )

    if not data.results:
        return ToolResult(content="No audit log entries found.", structured_content=structured)

    m = data.metadata
    header = f"Audit log entries ({m.count} of {m.total_results} total, offset {m.offset}):\n"
    entries = [f"[{i}]\n{_format_entry(e)}" for i, e in enumerate(data.results, 1)]
    return ToolResult(content=header + "\n\n".join(entries), structured_content=structured)
