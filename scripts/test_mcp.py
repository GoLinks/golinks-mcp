import asyncio
import os
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
from fastmcp import Client


async def main() -> None:
    token = os.environ.get("TOKEN")
    if not token:
        raise SystemExit("Set TOKEN first (in a .env file or as a command line argument): TOKEN='your-token' uv run python scripts/test_mcp.py")

    async with Client(
        "http://127.0.0.1:8000/mcp/",
        auth=token,
    ) as client:
        tools = await client.list_tools()
        print("tools:", [tool.name for tool in tools])

        print("\n--- list_golinks ---")
        result = await client.call_tool("list_golinks", {"limit": 5})
        print(result)

        print("\n--- search_golinks ---")
        result = await client.call_tool("search_golinks", {"query": "karantestinggoogle"})
        print(result)

        # Unique-per-run name so the script is re-runnable without name collisions.
        test_name = f"test-mcp-{int(time.time())}"

        print(f"\n--- create_golink (name={test_name}) ---")
        result = await client.call_tool(
            "create_golink",
            {"name": test_name, "url": "https://google.com"},
        )
        print(result)

        print(f"\n--- get_golink (name={test_name}) ---")
        result = await client.call_tool("get_golink", {"name": test_name})
        print(result)

        print("\n--- get_golink (gid=5555751) ---")
        result = await client.call_tool("get_golink", {"gid": 5555751})
        print(result)


if __name__ == "__main__":
    asyncio.run(main())
