from datetime import datetime, timezone
from typing import Annotated

import httpx
from fastmcp import Context
from pydantic import BaseModel, Field

from golinks_mcp.client import (
    external_params,
    get_authorization_header,
    http_client,
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
# Formatting helpers
# ---------------------------------------------------------------------------

def _format_timestamp(ts: int | None) -> str:
    if ts is None:
        return "Unknown"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def _format_golink(gl: GoLink) -> str:
    owner = gl.user
    owner_str = f"{owner.first_name} {owner.last_name}".strip() or owner.username or owner.email or "Unknown"

    lines = [
        f"Name:    go/{gl.name}",
        f"URL:     {gl.url or '(none — multilink)'}",
    ]
    if gl.description:
        lines.append(f"Desc:    {gl.description}")
    lines.append(f"Owner:   {owner_str}")
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
        lines.append(f"Hits:    daily={h.daily}  weekly={h.weekly}  monthly={h.monthly}  all-time={h.alltime}")

    lines.append(f"Created: {_format_timestamp(gl.created_at)}")
    lines.append(f"Updated: {_format_timestamp(gl.updated_at)}")
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

async def list_golinks(
    limit: Annotated[int, Field(description="Number of go links to return (1–1000).", ge=1, le=1000)] = 50,
    offset: Annotated[int, Field(description="Pagination offset (0-based).", ge=0)] = 0,
    sort: Annotated[
        str | None,
        Field(description="Sort order: 'created_at' or 'updated_at'. Defaults to relevance when omitted."),
    ] = None,
    ctx: Context | None = None,
) -> str:
    """List go links in the user's GoLinks workspace (https://www.golinks.io).

    Returns a paginated list of company go links the token has access to.
    External OAuth tokens do not include private or unlisted links unless
    specifically granted. Use search_golinks for keyword-based lookup.
    Read-only.
    """
    if ctx is None:
        raise PermissionError("Missing request context.")
    authorization = get_authorization_header(ctx)

    params: dict = {"limit": limit, "offset": offset}
    if sort in ("created_at", "updated_at"):
        params["sort"] = sort
    params = external_params(params)

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

    raise_for_status(response, "/golinks")

    data = GoLinksListResponse.model_validate(response.json())

    if not data.results:
        return "No go links found."

    m = data.metadata
    header = f"Go links ({m.count} of {m.total_results} total, offset {m.offset}):\n"
    entries = [f"[{i}]\n{_format_golink(gl)}" for i, gl in enumerate(data.results, 1)]
    return header + "\n\n".join(entries)

async def get_golink(
    name: Annotated[str | None, Field(description="The go link keyword/name (e.g. 'eng-docs').")] = None,
    gid: Annotated[int | None, Field(description="The numeric go link ID.", ge=1)] = None,
    ctx: Context | None = None,
) -> str:
    """Get details for a single go link by name (keyword) or numeric ID.

    Exactly one of 'name' or 'gid' must be provided. Returns full details
    including owner, tags, redirect hit counts, and timestamps. Read-only.
    """
    if ctx is None:
        raise PermissionError("Missing request context.")
    if name is None and gid is None:
        raise ValueError("Provide either 'name' or 'gid'.")
    if name is not None and gid is not None:
        raise ValueError("Provide either 'name' or 'gid', not both.")

    authorization = get_authorization_header(ctx)

    raw_params: dict = {}
    if name is not None:
        raw_params["name"] = name.lower().strip()
    else:
        raw_params["gid"] = gid

    params = external_params(raw_params)

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

    raise_for_status(response, "/golinks")

    # Single-lookup always returns a dict on success
    raw = response.json()
    if not isinstance(raw, dict) or "gid" not in raw:
        raise LookupError("The go link does not exist.")

    gl = GoLink.model_validate(raw)
    return _format_golink(gl)

async def create_golink(
    name: Annotated[str, Field(description="The go link keyword (e.g. 'eng-docs'). Letters, numbers, - and _ only; max 50 chars.", min_length=1)],
    url: Annotated[str, Field(description="Destination URL. Required.", min_length=1)],
    description: Annotated[str | None, Field(description="Optional description (max 500 chars).")] = None,
    public: Annotated[bool | None, Field(description="Make the go link public (visible to anyone with the link).")] = None,
    private: Annotated[bool | None, Field(description="Make the go link private (visible only to the owner).")] = None,
    unlisted: Annotated[bool | None, Field(description="Make the go link unlisted (not shown in company listings).")] = None,
    tags: Annotated[list[str] | None, Field(description="List of tag names to apply.")] = None,
    aliases: Annotated[list[str] | None, Field(description="Alternate names for this go link (max 10).")] = None,
    ctx: Context | None = None,
) -> str:
    """Create a new, standard go link in the user's GoLinks workspace (https://www.golinks.io).

    Both 'name' and 'url' are required. The API enforces name uniqueness,
    character restrictions (letters/numbers/-/_/emoji, max 50), reserved
    names, and plan/permission limits — validation errors are returned as
    descriptive messages.

    Only standard go links can be created through this tool.

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

    params = external_params()

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
    return f"Go link created successfully.\n\n{_format_golink(gl)}"
