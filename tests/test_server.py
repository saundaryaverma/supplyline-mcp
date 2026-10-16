"""Starts the real MCP server over stdio and talks to it the way Claude Desktop or an agent would."""
import json
import sys

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = StdioServerParameters(command=sys.executable, args=["-m", "supplyline.server"])


async def _session_run(fn):
    async with stdio_client(SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await fn(session)


def test_server_lists_all_tools():
    async def check(s):
        return {t.name for t in (await s.list_tools()).tools}
    names = anyio.run(_session_run, check)
    assert names == {"search_parts", "supplier_scorecard", "purchase_orders", "bom_cost", "supply_risks", "simulate_delay"}


def test_tool_call_over_mcp_returns_cited_json():
    async def check(s):
        return await s.call_tool("supply_risks", {"product": "Aurora Headset", "limit": 3})
    result = anyio.run(_session_run, check)
    assert not result.isError
    data = json.loads(result.content[0].text)
    assert data["risks"][0]["part_id"] == "P115" and data["sources"]


def test_bad_input_comes_back_as_tool_error_not_crash():
    async def check(s):
        return await s.call_tool("supplier_scorecard", {"supplier_id": "S99"})
    result = anyio.run(_session_run, check)
    assert result.isError and "Unknown supplier" in result.content[0].text


def test_prompt_and_resource():
    async def check(s):
        prompt = await s.get_prompt("weekly_supply_review", {"product": "Aurora Watch"})
        res = await s.read_resource("supplyline://products")
        return prompt, res
    prompt, res = anyio.run(_session_run, check)
    assert "Aurora Watch" in prompt.messages[0].content.text
    assert "Aurora Headset" in res.contents[0].text
