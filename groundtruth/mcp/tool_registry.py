from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from groundtruth.utils.redaction import safe_text

WRITE_VERBS = re.compile(
    r"(?i)\b(create|update|delete|remove|destroy|write|apply|trigger|approve|"
    r"revoke|rotate|run|execute|invoke|publish|deploy|set|put|post|patch|import|"
    r"attach|detach|start|stop|restart|enable|disable)\b"
)
READ_PREFIXES = (
    "get",
    "list",
    "search",
    "describe",
    "read",
    "find",
    "show",
    "lookup",
    "query",
    "fetch",
    "inspect",
    "retrieve",
)
SHELL_TERMS = re.compile(r"(?i)\b(shell|terminal|exec|command|bash|powershell|cmd)\b")


@dataclass(frozen=True)
class McpServerConfig:
    name: str
    url: str
    transport: str = "streamable_http"
    headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "McpServerConfig":
        name = safe_text(str(value.get("name") or "").strip(), limit=80)
        url = str(value.get("url") or "").strip()
        transport = str(value.get("transport") or "streamable_http").strip()
        parsed = urlparse(url)
        if not name:
            raise ValueError("MCP server config requires a name.")
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"MCP server {name!r} requires an HTTP(S) URL.")
        if transport not in {"streamable_http", "http"}:
            raise ValueError(f"MCP server {name!r} uses unsupported transport {transport!r}.")
        headers = {
            safe_text(str(key), limit=80): safe_text(str(item), limit=2000)
            for key, item in (value.get("headers") or {}).items()
        }
        if not headers.get("Authorization") and value.get("token"):
            headers["Authorization"] = f"Bearer {safe_text(str(value['token']), limit=2000)}"
        return cls(name=name, url=url, transport="streamable_http", headers=headers)


@dataclass(frozen=True)
class McpTool:
    server: str
    name: str
    description: str
    input_schema: dict[str, Any]
    read_only: bool
    enabled: bool
    policy_reason: str

    @property
    def qualified_name(self) -> str:
        return f"{self.server}:{self.name}"


class McpToolRegistry:
    def __init__(self, allowlist: list[str] | None = None) -> None:
        self.allowlist = {item.strip() for item in (allowlist or []) if item.strip()}
        self._tools: dict[tuple[str, str], McpTool] = {}
        self._servers: dict[str, McpServerConfig] = {}

    def register_server(self, config: McpServerConfig) -> None:
        self._servers[config.name] = config

    @property
    def servers(self) -> list[McpServerConfig]:
        return sorted(self._servers.values(), key=lambda item: item.name)

    def add_discovered(self, server: str, raw_tool: dict[str, Any]) -> McpTool:
        name = str(raw_tool.get("name") or "").strip()
        if not name:
            raise ValueError("MCP tool is missing a name.")
        description = safe_text(str(raw_tool.get("description") or ""), limit=1200)
        schema = raw_tool.get("inputSchema") or raw_tool.get("input_schema") or {}
        if not isinstance(schema, dict):
            schema = {}
        raw_annotations = raw_tool.get("annotations")
        annotations: dict[str, Any] = raw_annotations if isinstance(raw_annotations, dict) else {}
        read_only = self._classify_read_only(name, description, annotations)
        allowed = self._is_allowlisted(server, name)
        reason = (
            "approved read-only tool"
            if read_only and allowed
            else ("not allowlisted" if read_only else "classified write/unknown")
        )
        tool = McpTool(
            server=server,
            name=name,
            description=description,
            input_schema=schema,
            read_only=read_only,
            enabled=bool(read_only and allowed),
            policy_reason=reason,
        )
        self._tools[(server, name)] = tool
        return tool

    def _is_allowlisted(self, server: str, name: str) -> bool:
        if f"{server}:{name}" in self.allowlist:
            return True
        matching_bare = [entry for entry in self.allowlist if ":" not in entry and entry == name]
        return bool(matching_bare)

    @staticmethod
    def _classify_read_only(name: str, description: str, annotations: dict[str, Any]) -> bool:
        if annotations.get("readOnlyHint") is True:
            return True
        if annotations.get("destructiveHint") is True or annotations.get("readOnlyHint") is False:
            return False
        haystack = f"{name} {description}"
        if SHELL_TERMS.search(haystack):
            return False
        if WRITE_VERBS.search(haystack):
            return False
        lowered = name.lower()
        return lowered.startswith(READ_PREFIXES) or lowered in {"info", "status", "version"}

    def tool(self, server: str, name: str) -> McpTool | None:
        return self._tools.get((server, name))

    def find(self, qualified_name: str) -> McpTool | None:
        if ":" in qualified_name:
            server, name = qualified_name.split(":", 1)
            return self.tool(server, name)
        matches = [item for item in self._tools.values() if item.name == qualified_name]
        return matches[0] if len(matches) == 1 else None

    def all_tools(self) -> list[McpTool]:
        return sorted(self._tools.values(), key=lambda item: (item.server, item.name))

    def approved_tools(self) -> list[McpTool]:
        return [item for item in self.all_tools() if item.enabled]

    def authorize(self, server: str, name: str) -> McpTool:
        tool = self.tool(server, name)
        if tool is None:
            raise PermissionError("MCP tool was not discovered from the live tool list.")
        if not tool.read_only:
            raise PermissionError("MCP tool is classified as write/execute and is blocked.")
        if not self._is_allowlisted(server, name):
            raise PermissionError("MCP tool is not on the human-configured allowlist.")
        return tool
