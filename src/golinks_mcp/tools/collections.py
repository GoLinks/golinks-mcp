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
# Filter/sort/department literals
# ---------------------------------------------------------------------------

CollectionFilter = Literal["favorite", "my_collections", "unlisted"]

CollectionSort = Literal["relevance", "created_at", "updated_at", "name"]

CollectionDepartment = Literal[
    "general",
    "engineering",
    "it & devops",
    "operations",
    "hr & recruiting",
    "product",
    "sales & business dev",
    "marketing",
    "executive",
    "design",
    "data & analytics",
    "customer support",
    "finance",
    "analytics / data science",
    "customer success",
    "hr / people / recruiting",
]

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class Collection(BaseModel):
    collid: int = 0
    uid: int = 0
    name: str = ""
    description: str | None = None
    icon: str | None = None
    pinned: int = 0
    unlisted: int = 0
    is_favorited: int = 0
    golinks_count: int = 0
    golinks_app_count: int = 0
    golinks_app_domains: list[str] = []
    created_at: int | None = None
    updated_at: int | None = None


class CollectionsPaginationMetadata(BaseModel):
    limit: int = 0
    offset: int = 0
    total_results: int = 0
    count: int = 0


class CollectionsSearchResponse(BaseModel):
    collections: list[Collection] = []
    metadata: CollectionsPaginationMetadata = CollectionsPaginationMetadata()


# ---------------------------------------------------------------------------
# Tool output models
# ---------------------------------------------------------------------------


class CollectionOutput(BaseModel):
    collid: int = Field(description="Numeric collection ID; pass as 'collid' to search_golinks.")
    name: str
    description: str | None = None
    owner_uid: int = Field(description="Numeric ID of the collection's owner.")
    golinks_count: int = Field(description="Number of go links in the collection.")
    golinks_app_count: int = Field(description="Number of app go links in the collection.")
    golinks_app_domains: list[str] = []
    pinned: bool
    unlisted: bool
    favorited: bool = Field(description="Whether the caller has favorited this collection.")
    created_at: str | None = Field(description="ISO 8601 UTC timestamp.")
    updated_at: str | None = Field(description="ISO 8601 UTC timestamp.")


class CollectionsListOutput(BaseModel):
    metadata: CollectionsPaginationMetadata
    results: list[CollectionOutput]


def _to_output(c: Collection) -> CollectionOutput:
    return CollectionOutput(
        collid=c.collid,
        name=c.name,
        description=c.description or None,
        owner_uid=c.uid,
        golinks_count=c.golinks_count,
        golinks_app_count=c.golinks_app_count,
        golinks_app_domains=c.golinks_app_domains,
        pinned=bool(c.pinned),
        unlisted=bool(c.unlisted),
        favorited=bool(c.is_favorited),
        created_at=iso_timestamp(c.created_at),
        updated_at=iso_timestamp(c.updated_at),
    )


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _format_collection(c: Collection) -> str:
    lines = [
        f"Collid:  {c.collid}",
        f"Name:    {c.name}",
    ]
    if c.description:
        lines.append(f"Desc:    {c.description}")
    lines.append(f"Owner:   uid {c.uid}")
    lines.append(f"Links:   {c.golinks_count} ({c.golinks_app_count} apps)")
    if c.golinks_app_domains:
        lines.append(f"Domains: {', '.join(c.golinks_app_domains)}")

    flags = []
    if c.pinned:
        flags.append("pinned")
    if c.unlisted:
        flags.append("unlisted")
    if c.is_favorited:
        flags.append("favorited")
    if flags:
        lines.append(f"Flags:   {', '.join(flags)}")

    lines.append(f"Created: {format_timestamp(c.created_at)}")
    lines.append(f"Updated: {format_timestamp(c.updated_at)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


async def search_collections(
    query: Annotated[
        str | None,
        Field(
            description=(
                "Keyword or phrase to search for by collection name/description. "
                "Omit to browse/list all collections."
            )
        ),
    ] = None,
    limit: Annotated[
        int, Field(description="Maximum number of results to return (1–100).", ge=1, le=100)
    ] = 20,
    offset: Annotated[int, Field(description="Pagination offset (0-based).", ge=0)] = 0,
    sort: Annotated[
        CollectionSort | None,
        Field(
            description=(
                "Sort order for results: 'relevance' (default), 'created_at', "
                "'updated_at', or 'name'."
            )
        ),
    ] = None,
    order: Annotated[
        SortOrder | None, Field(description="Sort direction: 'asc' or 'desc'.")
    ] = None,
    department: Annotated[
        CollectionDepartment | None,
        Field(description="Restrict results to collections tagged with this department."),
    ] = None,
    filter: Annotated[
        list[CollectionFilter] | None,
        Field(
            description=(
                "Filter flags to narrow results: 'favorite' (your favorited collections), "
                "'my_collections' (collections you own), or 'unlisted'."
            )
        ),
    ] = None,
    ctx: Context | None = None,
) -> ToolResult:
    """Search for or list collections of go links in the user's GoLinks
    workspace (https://www.golinks.io). Returns the collection's numeric
    'collid', name, description, and link counts.

    Use this to find a collection's numeric ID by name before passing it as
    'collid' to search_golinks. Read-only.

    Requires search:read scope.
    """
    if ctx is None:
        raise PermissionError("Missing request context.")
    authorization = get_authorization_header(ctx)

    params: dict = {
        "search-term": query or "",
        "result-type": "collections",
        "limit": limit,
        "offset": offset,
    }
    if sort is not None:
        params["sort"] = sort
    if order is not None:
        params["order"] = order
    if department is not None:
        params["collection_department"] = department
    if filter:
        params["filter[]"] = list(filter)
    params = external_params(params, tool="search_collections")

    try:
        response = await http_client.get(
            "/search.php",
            params=params,
            headers={"Authorization": authorization},
        )
    except httpx.TimeoutException:
        raise TimeoutError("Request to GoLinks API timed out.")
    except httpx.ConnectError:
        raise ConnectionError("Failed to connect to GoLinks API.")

    raise_for_status(response, "/search.php")

    data = CollectionsSearchResponse.model_validate(response.json())
    structured = CollectionsListOutput(
        metadata=data.metadata,
        results=[_to_output(c) for c in data.collections],
    )

    if not data.collections:
        return ToolResult(content="No collections found.", structured_content=structured)

    m = data.metadata
    header = f"Collections ({m.count} of {m.total_results} total, offset {m.offset}):\n"
    entries = [f"[{i}]\n{_format_collection(c)}" for i, c in enumerate(data.collections, 1)]
    return ToolResult(content=header + "\n\n".join(entries), structured_content=structured)
