from typing import Annotated, Literal

import httpx
from fastmcp import Context
from fastmcp.tools import ToolResult
from pydantic import BaseModel, Field

from golinks_mcp.client import (
    SortOrder,
    external_params,
    format_timestamp,
    get_authorization_header,
    http_client,
    iso_timestamp,
    raise_for_status,
)

# ---------------------------------------------------------------------------
# Filter/sort literals
# ---------------------------------------------------------------------------

UserAccessLevel = Literal["admin", "member", "moderator", "limited_member"]

UserStatus = Literal["active", "inactive"]

UserSort = Literal["name", "created_at", "updated_at"]

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class GoLinksUserResult(BaseModel):
    uid: int = 0
    username: str = ""
    email: str = ""
    first_name: str = ""
    last_name: str = ""
    role: str | None = None
    admin: int = 0
    active: int | None = None
    total_nonprivate_links: int = 0
    created_at: int | None = None
    updated_at: int | None = None


class UsersPaginationMetadata(BaseModel):
    limit: int = 0
    offset: int = 0
    total_results: int = 0
    count: int = 0


class UsersListResponse(BaseModel):
    metadata: UsersPaginationMetadata = UsersPaginationMetadata()
    results: list[GoLinksUserResult] = []


# ---------------------------------------------------------------------------
# Tool output models
# ---------------------------------------------------------------------------


class UserOutput(BaseModel):
    uid: int = Field(description="Numeric user ID; pass as 'filter_uid' to get_audit_logs.")
    name: str = Field(description="Display name, falling back to username or email.")
    username: str | None = Field(description="Exact username; pass as 'username' to search_golinks.")
    email: str | None = None
    role: str | None = None
    admin: bool
    active: bool | None = Field(description="Whether the user is active; null if unknown.")
    total_nonprivate_links: int
    created_at: str | None = Field(description="ISO 8601 UTC timestamp.")


class UsersListOutput(BaseModel):
    metadata: UsersPaginationMetadata
    results: list[UserOutput]


def _display_name(u: GoLinksUserResult) -> str:
    return f"{u.first_name} {u.last_name}".strip() or u.username or u.email or "Unknown"


def _to_output(u: GoLinksUserResult) -> UserOutput:
    return UserOutput(
        uid=u.uid,
        name=_display_name(u),
        username=u.username or None,
        email=u.email or None,
        role=u.role or None,
        admin=bool(u.admin),
        active=None if u.active is None else bool(u.active),
        total_nonprivate_links=u.total_nonprivate_links,
        created_at=iso_timestamp(u.created_at),
    )


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _format_user(u: GoLinksUserResult) -> str:
    lines = [
        f"UID:      {u.uid}",
        f"Name:     {_display_name(u)}",
        f"Username: {u.username or 'Unknown'}",
        f"Email:    {u.email or 'Unknown'}",
    ]

    flags = []
    if u.admin:
        flags.append("admin")
    if u.active == 0:
        flags.append("inactive")
    if flags:
        lines.append(f"Flags:    {', '.join(flags)}")

    lines.append(f"Links:    {u.total_nonprivate_links} non-private go links")
    lines.append(f"Created:  {format_timestamp(u.created_at)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


async def search_users(
    search: Annotated[
        str | None,
        Field(description="Search term matched against first name, last name, full name, or email (substring match)."),
    ] = None,
    access_level: Annotated[
        list[UserAccessLevel] | None,
        Field(
            description=(
                "Restrict results to users with one of these access levels: 'admin', "
                "'member', 'moderator', or 'limited_member'."
            )
        ),
    ] = None,
    status: Annotated[
        UserStatus | None,
        Field(description="Restrict results to 'active' or 'inactive' users."),
    ] = None,
    limit: Annotated[
        int, Field(description="Number of users to return (1–100).", ge=1, le=100)
    ] = 20,
    offset: Annotated[int, Field(description="Pagination offset (0-based).", ge=0)] = 0,
    sort: Annotated[
        UserSort | None,
        Field(description="Sort order: 'name', 'created_at', or 'updated_at'."),
    ] = None,
    order: Annotated[
        SortOrder | None, Field(description="Sort direction: 'asc' or 'desc'.")
    ] = None,
    ctx: Context | None = None,
) -> ToolResult:
    """Search for or list users in the user's GoLinks workspace
    (https://www.golinks.io). Returns each user's numeric 'uid', name,
    username, email, and access level.

    Use this to resolve a person's name/email/username to their numeric uid
    before passing it as 'filter_uid' to get_audit_logs. Read-only.

    Requires users:read scope.
    """
    if ctx is None:
        raise PermissionError("Missing request context.")
    authorization = get_authorization_header(ctx)

    raw_params: dict = {"limit": limit, "offset": offset}
    if search:
        raw_params["search"] = search
    if access_level:
        raw_params["access-level[]"] = list(access_level)
    if status is not None:
        raw_params["status"] = status
    if sort is not None:
        raw_params["sort"] = sort
    if order is not None:
        raw_params["order"] = order

    params = external_params(raw_params, tool="search_users")

    try:
        response = await http_client.get(
            "/users",
            params=params,
            headers={"Authorization": authorization},
        )
    except httpx.TimeoutException:
        raise TimeoutError("Request to GoLinks API timed out.")
    except httpx.ConnectError:
        raise ConnectionError("Failed to connect to GoLinks API.")

    raise_for_status(response, "/users")

    data = UsersListResponse.model_validate(response.json())
    structured = UsersListOutput(
        metadata=data.metadata,
        results=[_to_output(u) for u in data.results],
    )

    if not data.results:
        return ToolResult(content="No users found.", structured_content=structured)

    m = data.metadata
    header = f"Users ({m.count} of {m.total_results} total, offset {m.offset}):\n"
    entries = [f"[{i}]\n{_format_user(u)}" for i, u in enumerate(data.results, 1)]
    return ToolResult(content=header + "\n\n".join(entries), structured_content=structured)
