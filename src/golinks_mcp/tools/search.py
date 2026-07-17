from typing import Annotated, Literal

import httpx
from fastmcp import Context
from pydantic import BaseModel, Field

from golinks_mcp.client import (
    SortOrder,
    external_params,
    get_authorization_header,
    golink_path,
    http_client,
    raise_for_status,
)

# ---------------------------------------------------------------------------
# Filter/sort literals
# ---------------------------------------------------------------------------

SearchFilter = Literal[
    "public_links",
    "private_links",
    "my_links",
    "user_links",
    "variable_links",
    "non_variable_links",
    "locked_links",
    "unlisted_links",
    "favorite_links",
    "multi_links",
    "non_multi_links",
    "geo_links",
    "verified_links",
    "unverified_links",
]

SearchSort = Literal[
    "relevance",
    "daily",
    "weekly",
    "monthly",
    "alltime",
    "new",
    "created_at",
    "updated_at",
    "user_recently_used",
    "name",
]


SearchModified = Literal["today", "last_7_days", "last_30_days", "last_90_days", "last_year"]

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class SearchGoLink(BaseModel):
    gid: int = 0
    name: str = ""
    url: str | None = None
    description: str | None = None
    private: int = 0


class SearchPaginationMetadata(BaseModel):
    limit: int = 0
    offset: int = 0
    total_results: int = 0
    count: int = 0


class SearchResponse(BaseModel):
    search_term: str = Field("", alias="search-term")
    total_links: int = 0
    results: list[SearchGoLink] = []
    metadata: SearchPaginationMetadata = SearchPaginationMetadata()

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


async def search_golinks(
    query: Annotated[
        str | None,
        Field(
            description=(
                "Keyword or phrase to search for across go link names, URLs, and "
                "descriptions. Omit to browse/list all go links matching the given filters."
            )
        ),
    ] = None,
    limit: Annotated[
        int,
        Field(description="Maximum number of results to return (1–100).", ge=1, le=100),
    ] = 20,
    offset: Annotated[int, Field(description="Pagination offset (0-based).", ge=0)] = 0,
    sort: Annotated[
        SearchSort | None,
        Field(
            description=(
                "Sort order for results. One of: 'relevance' (default), 'daily', "
                "'weekly', 'monthly', 'alltime' (redirect hit counts), 'new'/'created_at', "
                "'updated_at', 'user_recently_used', or 'name'."
            )
        ),
    ] = None,
    order: Annotated[
        SortOrder | None, Field(description="Sort direction: 'asc' or 'desc'.")
    ] = None,
    filter: Annotated[
        list[SearchFilter] | None,
        Field(
            description=(
                "Filter flags to narrow results, e.g. 'my_links', 'public_links', "
                "'private_links', 'unlisted_links', 'locked_links', 'favorite_links', "
                "'variable_links', 'non_variable_links', 'multi_links', 'non_multi_links', "
                "'geo_links', 'verified_links', 'unverified_links'. Use 'user_links' with "
                "'username' to filter to a specific user's go links."
            )
        ),
    ] = None,
    username: Annotated[
        list[str] | None,
        Field(
            description=(
                "Exact username(s) to filter by (not a display name). Required when "
                "'user_links' is in filter. If you only know a person's name or email, "
                "use search_users first to resolve their exact username."
            )
        ),
    ] = None,
    tag: Annotated[
        list[str] | None, Field(description="Tag name(s) to filter results by.")
    ] = None,
    modified: Annotated[
        SearchModified | None,
        Field(
            description=(
                "Only include go links modified within this window: 'today', "
                "'last_7_days', 'last_30_days', 'last_90_days', or 'last_year'."
            )
        ),
    ] = None,
    collid: Annotated[
        int | None,
        Field(
            description=(
                "Restrict results to go links in this collection ID. Use "
                "search_collections to look up a collection's numeric ID by name."
            ),
            ge=1,
        ),
    ] = None,
    exclude_collid: Annotated[
        int | None,
        Field(
            description=(
                "Exclude go links in this collection ID from results. Use "
                "search_collections to look up a collection's numeric ID by name."
            ),
            ge=1,
        ),
    ] = None,
    ctx: Context | None = None,
) -> str:
    """Search for go links by keyword in the user's GoLinks workspace
    (https://www.golinks.io). Performs a fuzzy/relevance-ranked search
    across go link names, URLs, and descriptions, with optional filters
    for ownership/visibility, tags, collections, and recency.

    'query' is optional — omit it to browse/list all go links matching
    the given filters (e.g. all of a user's links, or all links in a
    collection) without keyword matching.

    For fetching a specific go link by exact name/ID, use get_golink
    instead. Read-only.

    Requires search:read scope.
    """
    if ctx is None:
        raise PermissionError("Missing request context.")
    if filter and "user_links" in filter and not username:
        raise ValueError("'username' is required when 'user_links' is included in filter.")
    authorization = get_authorization_header(ctx)

    params: dict = {
        "search-term": query or "",
        "result-type": "links",
        "limit": limit,
        "offset": offset,
    }
    if sort is not None:
        params["sort"] = sort
    if order is not None:
        params["order"] = order
    if filter:
        params["filter[]"] = list(filter)
    if username:
        params["username[]"] = list(username)
    if tag:
        params["tag[]"] = list(tag)
    if modified is not None:
        params["modified"] = modified
    if collid is not None:
        params["collid"] = collid
    if exclude_collid is not None:
        params["exclude_collid"] = exclude_collid
    params = external_params(params, tool="search_golinks")

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

    data = SearchResponse.model_validate(response.json())

    if not data.results:
        return f'No go links found for "{query}".' if query else "No go links found."

    header = (
        f'Go link search results for "{data.search_term or query}" '
        f"({len(data.results)} shown of {data.total_links} total):\n"
        if query
        else f"Go links ({len(data.results)} shown of {data.total_links} total):\n"
    )

    lines = []
    for i, gl in enumerate(data.results, 1):
        entry = f"[{i}] {golink_path(gl.name, gl.private)}"
        entry += f"\n    GID:  {gl.gid}"
        if gl.url:
            entry += f"\n    URL:  {gl.url}"
        if gl.description:
            entry += f"\n    Desc: {gl.description}"
        lines.append(entry)

    return header + "\n\n".join(lines)
