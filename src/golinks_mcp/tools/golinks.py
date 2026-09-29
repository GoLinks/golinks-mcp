from typing import Annotated

import httpx
from fastmcp import Context
from fastmcp.tools import ToolResult
from pydantic import BaseModel, Field

from golinks_mcp.client import (
    external_params,
    format_timestamp,
    get_authorization_header,
    golink_path,
    http_client,
    iso_timestamp,
    raise_for_status,
)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class GoLinkUser(BaseModel):
    uid: int = 0
    first_name: str = ""
    last_name: str = ""
    username: str = ""
    email: str = ""
    user_image_url: str = ""


class GoLinkTag(BaseModel):
    tid: int = 0
    name: str = ""


class RedirectHits(BaseModel):
    daily: int = 0
    weekly: int = 0
    monthly: int = 0
    alltime: int = 0


class GoLink(BaseModel):
    gid: int = 0
    name: str = ""
    url: str | None = None
    description: str | None = None
    user: GoLinkUser = GoLinkUser()
    tags: list[GoLinkTag] = []
    private: int = 0
    unlisted: int = 0
    variable_link: int = 0
    pinned: int = 0
    redirect_hits: RedirectHits | None = None
    created_at: int | None = None
    updated_at: int | None = None


class PaginationMetadata(BaseModel):
    limit: int = 0
    offset: int = 0
    total_results: int = 0
    count: int = 0


class GoLinksListResponse(BaseModel):
    metadata: PaginationMetadata = PaginationMetadata()
    results: list[GoLink] = []


# ---------------------------------------------------------------------------
# Tool output models
# ---------------------------------------------------------------------------


class GoLinkOwnerOutput(BaseModel):
    uid: int
    name: str = Field(description="Display name, falling back to username or email.")
    email: str | None = None


class GoLinkOutput(BaseModel):
    gid: int = Field(description="Numeric go link ID.")
    name: str = Field(description="Go link keyword.")
    path: str = Field(description="Resolvable path, e.g. 'go/foo' or 'go/my/foo' for private links.")
    url: str | None = Field(description="Destination URL; null for multilinks.")
    description: str | None = None
    owner: GoLinkOwnerOutput
    tags: list[str] = []
    private: bool
    unlisted: bool
    variable_link: bool
    pinned: bool
    redirect_hits: RedirectHits | None = None
    created_at: str | None = Field(description="ISO 8601 UTC timestamp.")
    updated_at: str | None = Field(description="ISO 8601 UTC timestamp.")


class GoLinksListOutput(BaseModel):
    metadata: PaginationMetadata
    results: list[GoLinkOutput]


def owner_name(owner: GoLinkUser) -> str:
    return (
        f"{owner.first_name} {owner.last_name}".strip()
        or owner.username
        or owner.email
        or "Unknown"
    )


def _to_output(gl: GoLink) -> GoLinkOutput:
    return GoLinkOutput(
        gid=gl.gid,
        name=gl.name,
        path=golink_path(gl.name, gl.private),
        url=gl.url,
        description=gl.description or None,
        owner=GoLinkOwnerOutput(
            uid=gl.user.uid,
            name=owner_name(gl.user),
            email=gl.user.email or None,
        ),
        tags=[t.name for t in gl.tags],
        private=bool(gl.private),
        unlisted=bool(gl.unlisted),
        variable_link=bool(gl.variable_link),
        pinned=bool(gl.pinned),
        redirect_hits=gl.redirect_hits,
        created_at=iso_timestamp(gl.created_at),
        updated_at=iso_timestamp(gl.updated_at),
    )


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _format_golink(gl: GoLink) -> str:
    lines = [
        f"GID:     {gl.gid}",
        f"Name:    {golink_path(gl.name, gl.private)}",
        f"URL:     {gl.url or '(none — multilink)'}",
    ]
    if gl.description:
        lines.append(f"Desc:    {gl.description}")
    lines.append(f"Owner:   {owner_name(gl.user)}")
    if gl.tags:
        lines.append(f"Tags:    {', '.join(t.name for t in gl.tags)}")

    flags = []
    if gl.private:
        flags.append("private")
    if gl.unlisted:
        flags.append("unlisted")
    if gl.variable_link:
        flags.append("variable")
    if gl.pinned:
        flags.append("pinned")
    if flags:
        lines.append(f"Flags:   {', '.join(flags)}")

    if gl.redirect_hits:
        h = gl.redirect_hits
        lines.append(
            f"Hits:    daily={h.daily}  weekly={h.weekly}  monthly={h.monthly}  all-time={h.alltime}"
        )

    lines.append(f"Created: {format_timestamp(gl.created_at)}")
    lines.append(f"Updated: {format_timestamp(gl.updated_at)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


async def list_golinks(
    limit: Annotated[
        int, Field(description="Number of go links to return (1–1000).", ge=1, le=1000)
    ] = 50,
    offset: Annotated[int, Field(description="Pagination offset (0-based).", ge=0)] = 0,
    sort: Annotated[
        str | None,
        Field(
            description="Sort order: 'created_at' or 'updated_at'. Defaults to relevance when omitted."
        ),
    ] = None,
    ctx: Context | None = None,
) -> ToolResult:
    """List go links in the user's GoLinks workspace (https://www.golinks.io).

    Returns a paginated list of company go links the token has access to.
    External OAuth tokens do not include private or unlisted links unless
    specifically granted. Use search_golinks for keyword-based lookup.

    Pinned go links are always listed first, regardless of 'sort'. For
    "most recent" questions, rank by each link's 'updated_at'/'created_at'
    rather than by result order.

    Read-only.
    """
    if ctx is None:
        raise PermissionError("Missing request context.")
    authorization = get_authorization_header(ctx)

    params: dict = {"limit": limit, "offset": offset}
    if sort in ("created_at", "updated_at"):
        params["sort"] = sort
    params = external_params(params, tool="list_golinks")

    try:
        response = await http_client.get(
            "/golinks",
            params=params,
            headers={"Authorization": authorization},
        )
    except httpx.TimeoutException:
        raise TimeoutError("Request to GoLinks API timed out.")
    except httpx.ConnectError:
        raise ConnectionError("Failed to connect to GoLinks API.")

    raise_for_status(response, "/golinks", not_found_message="The go link does not exist.")

    data = GoLinksListResponse.model_validate(response.json())
    structured = GoLinksListOutput(
        metadata=data.metadata,
        results=[_to_output(gl) for gl in data.results],
    )

    if not data.results:
        return ToolResult(content="No go links found.", structured_content=structured)

    m = data.metadata
    header = f"Go links ({m.count} of {m.total_results} total, offset {m.offset}):\n"
    entries = [f"[{i}]\n{_format_golink(gl)}" for i, gl in enumerate(data.results, 1)]
    return ToolResult(content=header + "\n\n".join(entries), structured_content=structured)


async def get_golink(
    name: Annotated[
        str | None, Field(description="The go link keyword/name (e.g. 'eng-docs').")
    ] = None,
    gid: Annotated[
        int | None, Field(description="The numeric go link ID.", ge=1)
    ] = None,
    ctx: Context | None = None,
) -> ToolResult:
    """Get details for a single go link by name (keyword) or numeric ID.

    Exactly one of 'name' or 'gid' must be provided. Returns full details
    including owner, tags, redirect hit counts, and timestamps. Read-only.
    """
    if ctx is None:
        raise PermissionError("Missing request context.")

    if name is not None:
        name = name.strip()

    if not name and gid is None:
        raise ValueError("Provide either 'name' or 'gid'.")
    if name and gid is not None:
        raise ValueError("Provide either 'name' or 'gid', not both.")

    authorization = get_authorization_header(ctx)

    raw_params: dict = {}
    if name:
        raw_params["name"] = name.lower()
    else:
        raw_params["gid"] = gid

    params = external_params(raw_params, tool="get_golink")

    try:
        response = await http_client.get(
            "/golinks",
            params=params,
            headers={"Authorization": authorization},
        )
    except httpx.TimeoutException:
        raise TimeoutError("Request to GoLinks API timed out.")
    except httpx.ConnectError:
        raise ConnectionError("Failed to connect to GoLinks API.")

    raise_for_status(response, "/golinks", not_found_message="The go link does not exist.")

    # Single-lookup always returns a dict on success
    raw = response.json()
    if not isinstance(raw, dict) or "gid" not in raw:
        raise LookupError("The go link does not exist.")

    gl = GoLink.model_validate(raw)
    return ToolResult(content=_format_golink(gl), structured_content=_to_output(gl))


async def create_golink(
    name: Annotated[
        str,
        Field(
            description="The go link keyword (e.g. 'eng-docs'). Letters, numbers, - and _ only; max 50 chars.",
            min_length=1,
        ),
    ],
    url: Annotated[str, Field(description="Destination URL. Required.", min_length=1)],
    description: Annotated[
        str | None, Field(description="Optional description (max 500 chars).")
    ] = None,
    public: Annotated[
        bool | None,
        Field(
            description=(
                "Make the go link public (visible to anyone with the link). If "
                "'public', 'private', and 'unlisted' are all omitted/false, the go "
                "link defaults to company visibility (visible to everyone in the workspace)."
            )
        ),
    ] = None,
    private: Annotated[
        bool | None,
        Field(
            description=(
                "Make the go link private (visible only to the owner). Private go "
                "links resolve at 'go/my/<name>', not 'go/<name>'. If 'public', "
                "'private', and 'unlisted' are all omitted/false, the go link defaults "
                "to company visibility (visible to everyone in the workspace)."
            )
        ),
    ] = None,
    unlisted: Annotated[
        bool | None,
        Field(
            description=(
                "Make the go link unlisted (not shown in company listings, but still "
                "resolvable/accessible company-wide). If 'public', 'private', and "
                "'unlisted' are all omitted/false, the go link defaults to company "
                "visibility (visible to everyone in the workspace)."
            )
        ),
    ] = None,
    tags: Annotated[
        list[str] | None, Field(description="List of tag names to apply.")
    ] = None,
    aliases: Annotated[
        list[str] | None,
        Field(description="Alternate names for this go link (max 10)."),
    ] = None,
    ctx: Context | None = None,
) -> ToolResult:
    """Create a new, standard go link in the user's GoLinks workspace (https://www.golinks.io).

    Both 'name' and 'url' are required. The API enforces name uniqueness,
    character restrictions (letters/numbers/-/_/emoji, max 50), reserved
    names, and plan/permission limits — validation errors are returned as
    descriptive messages.

    Only standard go links can be created through this tool.

    Visibility defaults to 'company' (visible to everyone in the workspace)
    if 'public', 'private', and 'unlisted' are all left unset.

    Requires golinks:write scope.
    """
    if ctx is None:
        raise PermissionError("Missing request context.")
    authorization = get_authorization_header(ctx)

    # Build form data
    data: dict[str, str | list[str]] = {
        "name": name,
        "url": url,
        "create_source": "mcp",
    }
    if description is not None:
        data["description"] = description
    if public is not None:
        data["public"] = "1" if public else "0"
    if private is not None:
        data["private"] = "1" if private else "0"
    if unlisted is not None:
        data["unlisted"] = "1" if unlisted else "0"
    if tags:
        data["tags[]"] = list(tags)
    if aliases:
        data["aliases[]"] = list(aliases)

    params = external_params(tool="create_golink")

    try:
        response = await http_client.post(
            "/golinks",
            data=data,
            params=params,
            headers={"Authorization": authorization},
        )
    except httpx.TimeoutException:
        raise TimeoutError("Request to GoLinks API timed out.")
    except httpx.ConnectError:
        raise ConnectionError("Failed to connect to GoLinks API.")

    raise_for_status(response, "/golinks (create)")

    # Create returns a single flat golink object (not wrapped in an array)
    raw = response.json()
    if not isinstance(raw, dict) or "gid" not in raw:
        raise RuntimeError("Unexpected response from GoLinks create API.")

    gl = GoLink.model_validate(raw)
    return ToolResult(
        content=f"Go link created successfully.\n\n{_format_golink(gl)}",
        structured_content=_to_output(gl),
    )
