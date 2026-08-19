from __future__ import annotations

import json
from io import StringIO

from dubito.mcp import handle_message, read_message, serve, write_message


def test_initialize_advertises_tools_and_instructions() -> None:
    response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        }
    )
    assert response is not None
    result = response["result"]
    assert result["serverInfo"]["name"] == "dubito"
    assert "tools" in result["capabilities"]
    assert "dubito_spec" in result["instructions"]
    assert "verification" in result["instructions"].lower()


def test_initialized_notification_has_no_response() -> None:
    assert handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_tools_list_matches_descriptors() -> None:
    response = handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert response is not None
    names = {item["name"] for item in response["result"]["tools"]}
    assert "dubito_playbook" in names
    assert "dubito_spec" in names
    assert "dubito_check" in names


def test_tools_call_playbook_returns_text_json() -> None:
    response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "dubito_playbook", "arguments": {}},
        }
    )
    assert response is not None
    assert response["result"]["isError"] is False
    text = response["result"]["content"][0]["text"]
    envelope = json.loads(text)
    assert envelope["ok"] is True
    assert envelope["result"]["schema"] == "dubito.playbook/v1"


def test_tools_call_unknown_is_error() -> None:
    response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "dubito_missing", "arguments": {}},
        }
    )
    assert response is not None
    assert response["result"]["isError"] is True


def test_content_length_roundtrip() -> None:
    buf = StringIO()
    write_message(buf, {"jsonrpc": "2.0", "id": 1, "method": "ping"})
    buf.seek(0)
    message = read_message(buf)
    assert message == {"jsonrpc": "2.0", "id": 1, "method": "ping"}


def test_serve_initialize_then_eof() -> None:
    stdin = StringIO()
    write_message(
        stdin,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}},
        },
    )
    stdin.seek(0)
    stdout = StringIO()
    serve(stdin, stdout)
    stdout.seek(0)
    response = read_message(stdout)
    assert response is not None
    assert response["result"]["serverInfo"]["name"] == "dubito"
