from __future__ import annotations

import pytest

from groundtruth.mcp import McpServerConfig, McpToolRegistry


@pytest.fixture()
def registry() -> McpToolRegistry:
    registry = McpToolRegistry(["fake:get_workspace"])
    registry.register_server(
        McpServerConfig(
            name="fake",
            url="https://mcp.example.test/mcp",
        )
    )
    return registry


def test_read_only_tool_is_approved(registry: McpToolRegistry) -> None:
    tool = registry.add_discovered(
        "fake",
        {
            "name": "get_workspace",
            "description": "Read one workspace",
            "inputSchema": {"type": "object"},
            "annotations": {"readOnlyHint": True},
        },
    )
    assert tool.read_only is True
    assert tool.enabled is True
    assert registry.authorize("fake", "get_workspace") is tool
    assert [item.name for item in registry.approved_tools()] == ["get_workspace"]


def test_read_tool_is_blocked_without_allowlist() -> None:
    registry = McpToolRegistry([])
    tool = registry.add_discovered("fake", {"name": "list_workspaces", "description": "List workspaces"})
    assert tool.read_only is True
    assert tool.enabled is False
    assert tool.policy_reason == "not allowlisted"
    with pytest.raises(PermissionError):
        registry.authorize("fake", "list_workspaces")


def test_write_and_shell_tools_are_blocked_even_if_allowlisted() -> None:
    registry = McpToolRegistry(["fake:delete_workspace", "fake:run_command", "fake:get_workspace"])
    delete = registry.add_discovered("fake", {"name": "delete_workspace", "description": "Delete a workspace"})
    command = registry.add_discovered("fake", {"name": "run_command", "description": "Run a shell command"})
    assert delete.read_only is False
    assert delete.enabled is False
    assert command.read_only is False
    assert command.enabled is False
    with pytest.raises(PermissionError):
        registry.authorize("fake", "delete_workspace")
    with pytest.raises(PermissionError):
        registry.authorize("fake", "run_command")


def test_destructive_annotation_overrides_read_prefix(registry: McpToolRegistry) -> None:
    tool = registry.add_discovered(
        "fake",
        {
            "name": "list_and_delete",
            "description": "Looks read-only by name",
            "annotations": {"destructiveHint": True},
        },
    )
    assert tool.read_only is False
    assert tool.enabled is False


def test_tool_lookup_requires_unique_bare_name() -> None:
    registry = McpToolRegistry(["one:get", "two:get"])
    registry.add_discovered("one", {"name": "get", "description": "read"})
    registry.add_discovered("two", {"name": "get", "description": "read"})
    assert registry.find("one:get") is not None
    assert registry.find("get") is None
    with pytest.raises(PermissionError):
        registry.authorize("missing", "get")
