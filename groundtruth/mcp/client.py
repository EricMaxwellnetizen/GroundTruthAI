from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

from groundtruth.mcp.tool_registry import McpServerConfig, McpToolRegistry
from groundtruth.utils.redaction import SENSITIVE_KEY_PATTERN, safe_text, strip_sensitive_url_parts

PROTOCOL_VERSION = "2025-03-26"
MAX_RESPONSE_CHARS = 100_000
MAX_ARGUMENT_CHARS = 20_000


class McpProtocolError(RuntimeError):
    pass


@dataclass
class McpCallRecord:
    server: str
    tool: str
    arguments: dict[str, Any]
    started_at: datetime
    ended_at: datetime | None = None
    status: str = "running"
    error: str | None = None
    result_chars: int = 0


@dataclass
class McpToolResult:
    server: str
    tool: str
    text: str
    structured: Any | None = None
    is_error: bool = False


def _redact_arguments(value: Any, key: str | None = None) -> Any:
    if key and SENSITIVE_KEY_PATTERN.search(key):
        return "[redacted]"
    if isinstance(value, dict):
        return {str(item_key): _redact_arguments(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_redact_arguments(item, key) for item in value]
    if isinstance(value, str):
        return safe_text(strip_sensitive_url_parts(value), limit=2000)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return safe_text(str(value), limit=2000)


class McpHttpClient:
    def __init__(self, config: McpServerConfig, timeout_seconds: int = 20) -> None:
        self.config = config
        self.timeout_seconds = max(2, min(int(timeout_seconds), 60))
        self.session_id: str | None = None
        self.protocol_version = PROTOCOL_VERSION
        self.calls: list[McpCallRecord] = []
        self._request_id = 0
        self._lock = threading.Lock()

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "GroundTruth/1.0.0 (read-only MCP adapter)",
            **self.config.headers,
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
            headers["MCP-Protocol-Version"] = self.protocol_version
        return headers

    def _next_id(self) -> int:
        with self._lock:
            self._request_id += 1
            return self._request_id

    def _post(self, payload: dict[str, Any]) -> Any:
        try:
            response = requests.post(
                self.config.url,
                json=payload,
                headers=self._headers(),
                timeout=self.timeout_seconds,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise McpProtocolError(f"MCP connection failed: {exc.__class__.__name__}.") from exc
        if response.status_code >= 400:
            raise McpProtocolError(f"MCP server returned HTTP {response.status_code}.")
        session_id = response.headers.get("Mcp-Session-Id")
        if session_id:
            self.session_id = safe_text(session_id, limit=200)
        if response.status_code in {202, 204} or not response.content:
            return None
        content_type = response.headers.get("Content-Type", "").lower()
        if "text/event-stream" in content_type:
            return self._parse_sse(response.text, payload.get("id"))
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise McpProtocolError("MCP server returned malformed JSON.") from exc
        return self._unwrap(data, payload.get("id"))

    def _parse_sse(self, text: str, expected_id: Any) -> Any:
        for block in text.replace("\r\n", "\n").split("\n\n"):
            data_lines = [line[5:].strip() for line in block.splitlines() if line.startswith("data:")]
            if not data_lines:
                continue
            data = "\n".join(data_lines)
            if data == "[DONE]":
                continue
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict) and event.get("id") == expected_id:
                return self._unwrap(event, expected_id)
        raise McpProtocolError("MCP server did not return a matching JSON-RPC response.")

    @staticmethod
    def _unwrap(data: Any, expected_id: Any) -> Any:
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("id") == expected_id:
                    return McpHttpClient._unwrap(item, expected_id)
            raise McpProtocolError("MCP server returned no matching JSON-RPC response.")
        if not isinstance(data, dict):
            raise McpProtocolError("MCP server returned an unexpected payload.")
        error = data.get("error")
        if error:
            message = safe_text(str(error.get("message") if isinstance(error, dict) else error), limit=300)
            raise McpProtocolError(f"MCP JSON-RPC error: {message}")
        return data.get("result")

    def initialize(self) -> dict[str, Any]:
        request_id = self._next_id()
        result = self._post(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "GroundTruth", "version": "1.0.0"},
                },
            }
        )
        if not isinstance(result, dict):
            raise McpProtocolError("MCP initialize returned no result.")
        version = result.get("protocolVersion")
        if isinstance(version, str) and version:
            self.protocol_version = safe_text(version, limit=40)
        try:
            self._post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        except McpProtocolError:
            pass
        return result

    def list_tools(self, registry: McpToolRegistry, max_pages: int = 10) -> list[Any]:
        cursor: str | None = None
        added = []
        for _ in range(max_pages):
            params: dict[str, Any] = {}
            if cursor:
                params["cursor"] = cursor
            result = self._post({"jsonrpc": "2.0", "id": self._next_id(), "method": "tools/list", "params": params})
            if not isinstance(result, dict):
                raise McpProtocolError("MCP tools/list returned no result.")
            tools = result.get("tools") or []
            if not isinstance(tools, list):
                raise McpProtocolError("MCP tools/list returned an invalid tools collection.")
            for raw_tool in tools:
                if isinstance(raw_tool, dict):
                    added.append(registry.add_discovered(self.config.name, raw_tool))
            next_cursor = result.get("nextCursor")
            if not isinstance(next_cursor, str) or not next_cursor:
                break
            cursor = next_cursor
        return added

    def call_tool(self, registry: McpToolRegistry, name: str, arguments: dict[str, Any]) -> McpToolResult:
        registry.authorize(self.config.name, name)
        if not isinstance(arguments, dict):
            raise McpProtocolError("MCP tool arguments must be a JSON object.")
        serialized = json.dumps(arguments, ensure_ascii=False)
        if len(serialized) > MAX_ARGUMENT_CHARS:
            raise McpProtocolError("MCP tool arguments exceed the configured input cap.")
        record = McpCallRecord(
            server=self.config.name,
            tool=name,
            arguments=_redact_arguments(arguments),
            started_at=datetime.now(timezone.utc),
        )
        self.calls.append(record)
        try:
            result = self._post(
                {
                    "jsonrpc": "2.0",
                    "id": self._next_id(),
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                }
            )
            if not isinstance(result, dict):
                raise McpProtocolError("MCP tools/call returned no result.")
            is_error = bool(result.get("isError"))
            text_parts: list[str] = []
            for item in result.get("content") or []:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text":
                    text_parts.append(str(item.get("text") or ""))
                elif item.get("type") == "resource":
                    raw_resource = item.get("resource")
                    resource: dict[str, Any] = {}
                    if isinstance(raw_resource, dict):
                        resource = raw_resource
                    text_parts.append(str(resource.get("text") or resource.get("uri") or "[resource omitted]"))
                elif item.get("type") == "image":
                    text_parts.append("[image omitted]")
            text = safe_text("\n".join(text_parts), limit=MAX_RESPONSE_CHARS)
            structured = result.get("structuredContent")
            if structured is not None:
                structured = safe_text(
                    json.dumps(structured, ensure_ascii=False, sort_keys=True), limit=MAX_RESPONSE_CHARS
                )
            record.status = "error" if is_error else "ok"
            record.result_chars = len(text)
            record.ended_at = datetime.now(timezone.utc)
            return McpToolResult(
                server=self.config.name,
                tool=name,
                text=text,
                structured=structured,
                is_error=is_error,
            )
        except Exception as exc:
            record.status = "error"
            record.error = safe_text(f"{exc.__class__.__name__}: {exc}", limit=500)
            record.ended_at = datetime.now(timezone.utc)
            raise
