from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from groundtruth.config import Settings
from groundtruth.mcp.client import McpCallRecord, McpHttpClient, McpProtocolError, McpToolResult
from groundtruth.mcp.tool_registry import McpServerConfig, McpTool, McpToolRegistry
from groundtruth.utils.redaction import safe_text


@dataclass
class McpServerStatus:
    name: str
    configured: bool
    connected: bool
    tools: int = 0
    approved_tools: int = 0
    error: str | None = None


class McpManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.registry = McpToolRegistry(settings.mcp_allowlist)
        self.configs: list[McpServerConfig] = []
        self.config_errors: list[str] = []
        self.statuses: list[McpServerStatus] = []
        self.clients: dict[str, McpHttpClient] = {}
        self._load_servers()

    def _load_servers(self) -> None:
        raw_servers = self.settings.mcp_servers
        if not isinstance(raw_servers, list):
            self.config_errors.append("MCP server configuration must be a JSON array.")
            return
        for raw in raw_servers:
            if not isinstance(raw, dict):
                self.config_errors.append("Ignored an MCP server entry that was not an object.")
                continue
            try:
                config = McpServerConfig.from_dict(raw)
            except ValueError as exc:
                self.config_errors.append(str(exc))
                continue
            self.configs.append(config)
            self.registry.register_server(config)
            self.statuses.append(McpServerStatus(name=config.name, configured=True, connected=False))

    @property
    def enabled(self) -> bool:
        return bool(self.configs)

    def discover(self) -> list[McpTool]:
        self.statuses = []
        for config in self.configs:
            status = McpServerStatus(name=config.name, configured=True, connected=False)
            client = McpHttpClient(config, timeout_seconds=self.settings.request_timeout_seconds)
            try:
                client.initialize()
                client.list_tools(self.registry, max_pages=max(1, min(self.settings.max_pages, 10)))
                self.clients[config.name] = client
                status.connected = True
            except (McpProtocolError, ValueError, OSError) as exc:
                status.error = safe_text(f"{exc.__class__.__name__}: {exc}", limit=400)
            status.tools = len([item for item in self.registry.all_tools() if item.server == config.name])
            status.approved_tools = len([item for item in self.registry.approved_tools() if item.server == config.name])
            self.statuses.append(status)
        return self.registry.approved_tools()

    def call(self, qualified_name: str, arguments: dict[str, Any]) -> McpToolResult:
        tool = self.registry.find(qualified_name)
        if tool is None:
            raise PermissionError("MCP tool was not discovered from the live tool list.")
        if not tool.enabled:
            raise PermissionError(f"MCP tool is blocked by policy: {tool.policy_reason}.")
        self.registry.authorize(tool.server, tool.name)
        client = self.clients.get(tool.server)
        if client is None:
            raise McpProtocolError("MCP server is not connected. Run discovery first.")
        return client.call_tool(self.registry, tool.name, arguments)

    def calls(self) -> list[McpCallRecord]:
        return [record for client in self.clients.values() for record in client.calls]

    def summary(self) -> dict[str, Any]:
        return {
            "configured_servers": len(self.configs),
            "connected_servers": len([status for status in self.statuses if status.connected]),
            "discovered_tools": len(self.registry.all_tools()),
            "approved_tools": len(self.registry.approved_tools()),
            "allowlist": sorted(self.registry.allowlist),
            "servers": [
                {
                    "name": status.name,
                    "configured": status.configured,
                    "connected": status.connected,
                    "tools": status.tools,
                    "approved_tools": status.approved_tools,
                    "error": status.error,
                }
                for status in self.statuses
            ],
            "config_errors": self.config_errors,
        }
