"""JSON-RPC MCP stdio server. No MCP SDK.

Same tools as `python -m dubito tools`. Framing is LSP Content-Length,
with a JSON-line fallback for tests.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Mapping, TextIO

from dubito import __version__
from dubito.agent import INSTRUCTIONS
from dubito.faces import call_tool, tool_descriptors

PROTOCOL_VERSION = "2024-11-05"


def handle_message(message: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return a JSON-RPC response, or None for notifications."""

    method = message.get("method")
    msg_id = message.get("id")
    params = message.get("params") if isinstance(message.get("params"), dict) else {}
    if method is None:
        if msg_id is None:
            return None
        return _error(msg_id, -32600, "invalid request")
    if method == "initialize":
        return _result(
            msg_id,
            {
                "protocolVersion": str(params.get("protocolVersion") or PROTOCOL_VERSION),
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "dubito", "version": __version__},
                "instructions": INSTRUCTIONS,
            },
        )
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return _result(msg_id, {})
    if method == "tools/list":
        return _result(msg_id, {"tools": tool_descriptors()})
    if method == "tools/call":
        name = str(params.get("name") or "")
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        envelope = call_tool(name, arguments)
        text = json.dumps(envelope, sort_keys=True, default=str)
        return _result(
            msg_id,
            {
                "content": [{"type": "text", "text": text}],
                "isError": not bool(envelope.get("ok")),
            },
        )
    if msg_id is None:
        return None
    return _error(msg_id, -32601, f"method not found: {method}")


def read_message(stream: TextIO) -> dict[str, Any] | None:
    first = stream.readline()
    if first == "":
        return None
    stripped = first.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return json.loads(first)
    headers: dict[str, str] = {}
    line = first
    while line not in ("", "\n", "\r\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
        line = stream.readline()
        if line == "":
            return None
    length = int(headers.get("content-length", "0"))
    body = stream.read(length)
    if not body:
        return None
    return json.loads(body)


def write_message(stream: TextIO, message: Mapping[str, Any]) -> None:
    body = json.dumps(message, ensure_ascii=True, separators=(",", ":"))
    stream.write(f"Content-Length: {len(body)}\r\n\r\n")
    stream.write(body)
    stream.flush()


def serve(stdin: TextIO | None = None, stdout: TextIO | None = None) -> None:
    incoming = stdin or sys.stdin
    outgoing = stdout or sys.stdout
    while True:
        try:
            message = read_message(incoming)
        except json.JSONDecodeError:
            write_message(
                outgoing,
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}},
            )
            continue
        if message is None:
            return
        response = handle_message(message)
        if response is not None:
            write_message(outgoing, response)


def _result(msg_id: object, result: object) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id: object, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}
