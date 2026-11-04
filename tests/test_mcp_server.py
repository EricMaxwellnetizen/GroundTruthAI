from __future__ import annotations

import json
import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from groundtruth.mcp import McpHttpClient, McpManager, McpProtocolError, McpServerConfig, McpToolRegistry


class _State:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.tools = [
            {
                "name": "get_workspace",
                "description": "Read one workspace",
                "inputSchema": {
                    "type": "object",
                    "properties": {"workspace_id": {"type": "string"}},
                },
                "annotations": {"readOnlyHint": True},
            },
            {
                "name": "delete_workspace",
                "description": "Delete a workspace",
                "inputSchema": {"type": "object"},
            },
            {
                "name": "run_command",
                "description": "Run a shell command",
                "inputSchema": {"type": "object"},
            },
        ]
        self.paginated = False
        self.tool_text = '{"workspace":"orders","owner":"platform"}'
        self.tool_is_error = False
        self.malformed = False
        self.http_error = False
        self.sse = False


class _Handler(BaseHTTPRequestHandler):
    state: _State

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return

    def _send(self, code: int, payload: object | None = None, *, malformed: bool = False) -> None:
        body = b""
        if payload is not None:
            body = b"{not-json" if malformed else json.dumps(payload).encode("utf-8")
        self.send_response(code)
        if body:
            if self.state.sse:
                event = f"event: message\ndata: {body.decode('utf-8')}\n\n".encode()
                self.send_header("Content-Type", "text/event-stream")
                body = event
            else:
                self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Mcp-Session-Id", "test-session")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            payload = {}
        self.state.requests.append(payload)
        if self.state.http_error:
            self._send(500, {"error": "server failure"})
            return
        method = payload.get("method")
        request_id = payload.get("id")
        if method == "initialize":
            if self.state.malformed:
                self._send(200, malformed=True)
                return
            self._send(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "fake-mcp", "version": "1.0.0"},
                    },
                },
            )
            return
        if method == "notifications/initialized":
            self._send(202)
            return
        if method == "tools/list":
            cursor = (payload.get("params") or {}).get("cursor")
            if self.state.paginated:
                if cursor == "page-2":
                    tools = self.state.tools[2:]
                    self._send(200, {"jsonrpc": "2.0", "id": request_id, "result": {"tools": tools}})
                else:
                    tools = self.state.tools[:2]
                    self._send(
                        200,
                        {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "result": {"tools": tools, "nextCursor": "page-2"},
                        },
                    )
                return
            self._send(200, {"jsonrpc": "2.0", "id": request_id, "result": {"tools": self.state.tools}})
            return
        if method == "tools/call":
            params = payload.get("params") or {}
            self._send(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [{"type": "text", "text": self.state.tool_text}],
                        "isError": self.state.tool_is_error,
                        "structuredContent": {"name": params.get("name"), "arguments": params.get("arguments")},
                    },
                },
            )
            return
        self._send(200, {"jsonrpc": "2.0", "id": request_id, "error": {"message": "unknown method"}})


@pytest.fixture()
def mcp_server():
    state = _State()
    handler = type("Handler", (_Handler,), {"state": state})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/mcp", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _manager(settings, url: str, allowlist: list[str]) -> McpManager:
    configured = replace(
        settings,
        mcp_servers=[
            {
                "name": "fake",
                "url": url,
                "transport": "streamable_http",
                "headers": {"Authorization": "Bearer test-token"},
            }
        ],
        mcp_allowlist=allowlist,
        request_timeout_seconds=5,
    )
    return McpManager(configured)


def test_initialize_and_default_deny(settings, mcp_server) -> None:
    url, state = mcp_server
    manager = _manager(settings, url, [])
    assert manager.enabled
    discovered = manager.discover()
    assert discovered == []
    assert manager.statuses[0].connected is True
    assert manager.statuses[0].tools == 3
    assert manager.statuses[0].approved_tools == 0
    assert len(manager.registry.all_tools()) == 3
    with pytest.raises(PermissionError):
        manager.call("fake:get_workspace", {"workspace_id": "ws-orders-prod"})
    initialize = next(item for item in state.requests if item.get("method") == "initialize")
    assert initialize["params"]["protocolVersion"] == "2025-03-26"
    assert initialize["params"]["clientInfo"]["name"] == "GroundTruth"
    assert not any(item.get("method") == "tools/call" for item in state.requests)


def test_allowlisted_read_call_succeeds(settings, mcp_server) -> None:
    url, state = mcp_server
    manager = _manager(settings, url, ["fake:get_workspace"])
    manager.discover()
    result = manager.call("fake:get_workspace", {"workspace_id": "ws-orders-prod"})
    assert result.text == state.tool_text
    assert result.is_error is False
    assert result.structured
    calls = manager.calls()
    assert len(calls) == 1
    assert calls[0].status == "ok"
    assert calls[0].arguments == {"workspace_id": "ws-orders-prod"}
    tool_call = next(item for item in state.requests if item.get("method") == "tools/call")
    assert tool_call["params"]["name"] == "get_workspace"


def test_allowlisted_write_tool_stays_blocked(settings, mcp_server) -> None:
    url, _state = mcp_server
    manager = _manager(settings, url, ["fake:delete_workspace", "fake:run_command"])
    manager.discover()
    assert manager.registry.approved_tools() == []
    for name in ("fake:delete_workspace", "fake:run_command"):
        with pytest.raises(PermissionError):
            manager.call(name, {})
    assert manager.calls() == []


def test_tool_error_result_is_returned_not_raised(settings, mcp_server) -> None:
    url, state = mcp_server
    state.tool_is_error = True
    manager = _manager(settings, url, ["fake:get_workspace"])
    manager.discover()
    result = manager.call("fake:get_workspace", {})
    assert result.is_error is True
    assert manager.calls()[0].status == "error"


def test_malformed_json_is_rejected(settings, mcp_server) -> None:
    url, state = mcp_server
    state.malformed = True
    manager = _manager(settings, url, ["fake:get_workspace"])
    manager.discover()
    assert manager.statuses[0].connected is False
    assert manager.statuses[0].error
    client = McpHttpClient(McpServerConfig(name="fake", url=url), timeout_seconds=5)
    with pytest.raises(McpProtocolError):
        client.initialize()


def test_http_error_is_rejected(settings, mcp_server) -> None:
    url, state = mcp_server
    state.http_error = True
    client = McpHttpClient(McpServerConfig(name="fake", url=url), timeout_seconds=5)
    with pytest.raises(McpProtocolError):
        client.initialize()


def test_sse_transport_is_supported(settings, mcp_server) -> None:
    url, state = mcp_server
    state.sse = True
    manager = _manager(settings, url, ["fake:get_workspace"])
    manager.discover()
    assert manager.statuses[0].connected is True
    result = manager.call("fake:get_workspace", {})
    assert result.text == state.tool_text


def test_tools_list_pagination(settings, mcp_server) -> None:
    url, state = mcp_server
    state.paginated = True
    manager = _manager(settings, url, ["fake:get_workspace"])
    manager.discover()
    assert len(manager.registry.all_tools()) == 3
    list_requests = [item for item in state.requests if item.get("method") == "tools/list"]
    assert len(list_requests) == 2
    assert (list_requests[1].get("params") or {}).get("cursor") == "page-2"


def test_oversized_tool_result_is_capped(settings, mcp_server) -> None:
    url, state = mcp_server
    state.tool_text = "x" * 120_000
    manager = _manager(settings, url, ["fake:get_workspace"])
    manager.discover()
    result = manager.call("fake:get_workspace", {})
    assert len(result.text) <= 100_000
    assert manager.calls()[0].result_chars == len(result.text)


def test_registry_requires_discovered_tool_for_call() -> None:
    registry = McpToolRegistry(["fake:get_workspace"])
    with pytest.raises(PermissionError):
        registry.authorize("fake", "get_workspace")
    registry.add_discovered("fake", {"name": "get_workspace", "description": "read"})
    assert registry.authorize("fake", "get_workspace").name == "get_workspace"
