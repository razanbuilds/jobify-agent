"""Minimal MCP client: spawns the job-database server over stdio for each call.

Simple and robust (one process per call, ~1s overhead) - fine for a demo. For production, keep one
long-lived session instead. See lab D2_4_mcp if the SDK API differs from what is used here.
"""
from __future__ import annotations

import asyncio
import os
import sys

from . import config


async def _call(name: str, args: dict) -> str:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = {k: v for k, v in os.environ.items() if k.startswith("JOBIFY_")}
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "jobify.mcp_server"], env=env, cwd=str(config.ROOT)
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, args)
            text = "".join(getattr(c, "text", "") for c in result.content)
            if getattr(result, "isError", False):
                return f"ERROR: {text}"
            return text


def call_tool(name: str, args: dict) -> str:
    return asyncio.run(_call(name, args))
