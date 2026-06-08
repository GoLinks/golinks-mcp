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

class SearchGoLink(BaseModel):
    gid: int = 0
    name: str = ""
    url: str | None = None
    description: str | None = None


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
    query: Annotated[str, Field(description="Keyword or phrase to search for across go link names, URLs, and descriptions.", min_length=1)],
    limit: Annotated[int, Field(description="Maximum number of results to return (1–100).", ge=1, le=100)] = 20,
    offset: Annotated[int, Field(description="Pagination offset (0-based).", ge=0)] = 0,
    ctx: Context | None = None,
) -> str:
    """Search for go links by keyword in the user's GoLinks workspace
    (https://www.golinks.io). Performs a fuzzy/relevance-ranked search
    across go link names, URLs, and descriptions.

    Use this when you want to find go links matching a search term.
    For listing all go links or fetching a specific one by exact name/ID,
    use list_golinks or get_golink instead. Read-only.

    Requires search:read scope.
    """
    if ctx is None:
        raise PermissionError("Missing request context.")
    authorization = get_authorization_header(ctx)

    params: dict = {
        "search-term": query,
        "result-type": "links",
        "limit": limit,
        "offset": offset,
    }
    params = external_params(params)

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
        return f'No go links found for "{query}".'

    header = (
        f'Go link search results for "{data.search_term or query}" '
        f"({len(data.results)} shown of {data.total_links} total):\n"
    )

    lines = []
    for i, gl in enumerate(data.results, 1):
        entry = f"[{i}] go/{gl.name}"
        if gl.url:
            entry += f"\n    URL:  {gl.url}"
        if gl.description:
            entry += f"\n    Desc: {gl.description}"
        lines.append(entry)

    return header + "\n\n".join(lines)
