"""Tests for InfraToolSet — linux-only, no platform filtering."""
from agent.infra_toolsets import InfraToolSet


class TestPlatformDetection:
    """Platform is always linux."""

    def test_always_linux(self):
        infra = InfraToolSet()
        assert infra.detect_platform() == "linux"

    def test_platform_property(self):
        infra = InfraToolSet()
        assert infra.platform == "linux"


class TestToolAvailability:
    """All tools available on linux."""

    def test_get_available_tools_empty(self):
        """Linux returns empty list (meaning no filter)."""
        infra = InfraToolSet()
        assert infra.get_available_tools() == []

    def test_is_tool_available_always_true(self):
        infra = InfraToolSet()
        assert infra.is_tool_available("send_message")
        assert infra.is_tool_available("fs_read_file")
        assert infra.is_tool_available("anything")


class TestToolFiltering:
    """filter_tools passes everything through on linux."""

    def test_linux_no_filter(self):
        infra = InfraToolSet()
        tools = ["fs_read_file", "sys_terminal", "net_web_search", "send_message"]
        filtered = infra.filter_tools(tools)
        assert filtered == tools

    def test_filter_empty_list(self):
        infra = InfraToolSet()
        assert infra.filter_tools([]) == []

    def test_filter_preserves_order(self):
        infra = InfraToolSet()
        tools = ["z", "a", "m"]
        assert infra.filter_tools(tools) == tools


class TestDescribe:
    """describe output."""

    def test_describe_contains_linux(self):
        infra = InfraToolSet()
        desc = infra.describe()
        assert "linux" in desc
        assert "unlimited" in desc


class TestInvalidate:
    """invalidate is a no-op but doesn't crash."""

    def test_invalidate_noop(self):
        infra = InfraToolSet()
        infra.invalidate()
        assert infra.detect_platform() == "linux"
