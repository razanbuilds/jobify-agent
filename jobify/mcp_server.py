"""MCP server: the job database as tools over stdio.

Run directly:  python -m jobify.mcp_server
The agent connects to it through jobify/mcp_client.py when USE_MCP=1 / --mcp.

NOTE: written against the official `mcp` Python SDK (FastMCP helper). If the course's SDK v2 changed the
import path, compare with lab D2_4_mcp - only this file and mcp_client.py need to change.
"""
from mcp.server.fastmcp import FastMCP

from . import jobdb

mcp = FastMCP("jobify-jobdb")


@mcp.tool()
def search_jobs(query: str = "", location: str = "", limit: int = 5) -> dict:
    """Search the job database. Returns job summaries."""
    return jobdb.search_jobs(query, location, limit)


@mcp.tool()
def get_job(job_id: str) -> dict:
    """Get the full record of one job by id."""
    return jobdb.get_job(job_id)


@mcp.tool()
def save_application(job_id: str, cover_letter: str, notes: str = "") -> dict:
    """WRITE: save an application to the tracker. The agent harness gates this behind user approval."""
    return jobdb.save_application(job_id, cover_letter, notes)


if __name__ == "__main__":
    mcp.run()  # stdio transport
