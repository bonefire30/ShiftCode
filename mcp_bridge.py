"""
Optional MCP (Model Context Protocol) bridge for the migration agent.

Set `MIGRATION_MCP_COMMAND` to a JSON array, e.g. (PowerShell):
  $env:MIGRATION_MCP_COMMAND = '["npx","-y","@modelcontextprotocol/server-filesystem","/tmp"]'

Optional dependency: `pip install mcp`
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from typing import Any

_lock = threading.Lock()
_cached: dict[str, str] = {}


def mcp_list_servers() -> str:
    cmd = (os.environ.get("MIGRATION_MCP_COMMAND") or "").strip()
    cfg = (os.environ.get("MIGRATION_MCP_CONFIG") or "").strip()
    if cfg:
        return f"MIGRATION_MCP_CONFIG: {cfg!r} (for your docs; stdio uses MIGRATION_MCP_COMMAND)"
    if cmd:
        return f"MIGRATION_MCP_COMMAND (JSON) is set (length {len(cmd)}). pip install mcp to use mcp_invoke."
    return (
        "MCP: not configured. Set MIGRATION_MCP_COMMAND to a JSON string array, "
        "then `pip install mcp`, then the agent can call mcp_invoke."
    )


def mcp_invoke(tool_name: str, arguments_json: str) -> str:
    cache_key = f"{tool_name}|{arguments_json}"
    with _lock:
        if cache_key in _cached:
            return _cached[cache_key]

    cmd_src = (os.environ.get("MIGRATION_MCP_COMMAND") or "").strip()
    if not cmd_src:
        msg = mcp_list_servers()
        with _lock:
            _cached[cache_key] = msg
        return msg

    try:
        command = json.loads(cmd_src)
    except json.JSONDecodeError as e:
        return f"MIGRATION_MCP_COMMAND is not valid JSON: {e}"
    if not isinstance(command, list) or not command or not all(
        isinstance(x, str) for x in command
    ):
        return "MIGRATION_MCP_COMMAND must be a non-empty JSON array of strings (program and args)."

    try:
        args_dict = json.loads((arguments_json or "").strip() or "{}")
    except json.JSONDecodeError as e:
        return f"arguments_json is not valid JSON: {e}"
    if not isinstance(args_dict, dict):
        return "arguments_json must decode to a JSON object (dict)."

    try:
        msg = asyncio.run(
            _call_mcp_tool_stdio(
                program=command[0],
                argv=command[1:],
                name=tool_name,
                arguments=args_dict,
            )
        )
    except Exception as e:  # noqa: BLE001
        msg = f"MCP call failed: {e}"

    with _lock:
        _cached[cache_key] = msg
    return msg


async def _call_mcp_tool_stdio(
    *,
    program: str,
    argv: list[str],
    name: str,
    arguments: dict[str, Any],
) -> str:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    sp = StdioServerParameters(command=program, args=argv, env=None)
    async with stdio_client(sp) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            res = await session.call_tool(name=name, arguments=arguments)
    return _format_mcp_result(res)


def _format_mcp_result(res: Any) -> str:
    parts: list[str] = []
    for c in res.content or []:
        t = getattr(c, "text", None)
        if t is not None:
            parts.append(str(t))
        else:
            parts.append(str(c))
    if parts:
        return "\n".join(parts)
    return str(res)
