"""Tests for tool registry — thread safety, caching, generation counter."""
import threading
import time




class TestToolRegistry:
    """Core registry functionality."""

    def test_register_and_call(self, fresh_registry):
        """Register a tool and call it."""
        def echo(msg: str) -> str:
            return msg

        fresh_registry.register(
            name="test_echo",
            description="Echo back",
            parameters={"properties": {"msg": {"type": "string"}}, "required": ["msg"]},
            handler=echo,
            tags=["test"],
            category="testing",
        )

        result = fresh_registry.call("test_echo", {"msg": "hello"})
        assert result == "hello"

    def test_call_unknown_tool(self, fresh_registry):
        """Calling an unregistered tool returns error string."""
        result = fresh_registry.call("nonexistent", {})
        assert "Error" in result
        assert "not found" in result

    def test_call_error_is_caught(self, fresh_registry):
        """Handler exception is caught and returned as error string."""
        def fail():
            raise ValueError("boom")

        fresh_registry.register(
            name="failer",
            description="Always fails",
            parameters={"properties": {}},
            handler=fail,
        )

        result = fresh_registry.call("failer", {})
        assert "Error" in result

    def test_output_truncation(self, fresh_registry):
        """Long output is truncated to 8000 chars."""
        def long_output() -> str:
            return "x" * 10000

        fresh_registry.register(
            name="long",
            description="Long output",
            parameters={"properties": {}},
            handler=long_output,
        )

        result = fresh_registry.call("long", {})
        assert len(result) <= 8000

    def test_has_tool(self, fresh_registry):
        """has_tool reflects registration state."""
        fresh_registry.register(
            name="present",
            description="exists",
            parameters={"properties": {}},
            handler=lambda: "ok",
        )
        assert fresh_registry.has_tool("present")
        assert not fresh_registry.has_tool("missing")

    def test_deregister(self, fresh_registry):
        """Deregister removes a tool."""
        fresh_registry.register(
            name="temp",
            description="temporary",
            parameters={"properties": {}},
            handler=lambda: "ok",
        )
        assert fresh_registry.has_tool("temp")

        removed = fresh_registry.deregister("temp")
        assert removed
        assert not fresh_registry.has_tool("temp")

    def test_deregister_nonexistent(self, fresh_registry):
        """Deregistering nonexistent tool returns False."""
        assert not fresh_registry.deregister("nonexistent")


class TestRegistrySchemas:
    """Schema generation and filtering."""

    def test_get_schema(self, fresh_registry):
        """get_schema returns a copy of the tool schema."""
        fresh_registry.register(
            name="a",
            description="Tool A",
            parameters={"properties": {"x": {"type": "int"}}},
            handler=lambda x: str(x),
        )
        s = fresh_registry.get_schema("a")
        assert s["name"] == "a"
        assert s["description"] == "Tool A"
        assert "input_schema" in s

    def test_get_schemas_unfiltered(self, fresh_registry):
        """Unfiltered get_schemas returns all tools."""
        for name in ["a", "b", "c"]:
            fresh_registry.register(
                name=name,
                description=f"Tool {name}",
                parameters={"properties": {}},
                handler=lambda: "ok",
            )
        schemas = fresh_registry.get_schemas()
        assert len(schemas) == 3

    def test_get_schemas_enabled_filter(self, fresh_registry):
        """get_schemas with enabled list returns only those tools."""
        for name in ["a", "b", "c", "d"]:
            fresh_registry.register(
                name=name,
                description=f"Tool {name}",
                parameters={"properties": {}},
                handler=lambda: "ok",
            )
        schemas = fresh_registry.get_schemas(enabled=["a", "c"])
        names = {s["name"] for s in schemas}
        assert names == {"a", "c"}

    def test_get_schemas_tag_filter(self, fresh_registry):
        """get_schemas with tags filter returns matching tools."""
        fresh_registry.register(
            name="read",
            description="Read",
            parameters={"properties": {}},
            handler=lambda: "ok",
            tags=["fs", "read"],
        )
        fresh_registry.register(
            name="write",
            description="Write",
            parameters={"properties": {}},
            handler=lambda: "ok",
            tags=["fs", "write"],
        )
        fresh_registry.register(
            name="search",
            description="Search",
            parameters={"properties": {}},
            handler=lambda: "ok",
            tags=["net"],
        )

        schemas = fresh_registry.get_schemas(tags=["fs"])
        names = {s["name"] for s in schemas}
        assert names == {"read", "write"}

    def test_get_schema_nonexistent(self, fresh_registry):
        """Nonexistent schema returns None."""
        assert fresh_registry.get_schema("nonexistent") is None


class TestRegistryGeneration:
    """Generation counter and cache invalidation."""

    def test_generation_starts_positive(self, fresh_registry):
        """New registry has generation >= 0."""
        assert fresh_registry.generation >= 0

    def test_generation_bumps_on_register(self, fresh_registry):
        """Register bumps generation counter."""
        gen_before = fresh_registry.generation
        fresh_registry.register(
            name="tool",
            description="t",
            parameters={"properties": {}},
            handler=lambda: "ok",
        )
        assert fresh_registry.generation > gen_before

    def test_generation_bumps_on_deregister(self, fresh_registry):
        """Deregister bumps generation counter."""
        fresh_registry.register(
            name="tool",
            description="t",
            parameters={"properties": {}},
            handler=lambda: "ok",
        )
        gen_before = fresh_registry.generation
        fresh_registry.deregister("tool")
        assert fresh_registry.generation > gen_before


class TestRegistryThreadSafety:
    """Concurrent access safety."""

    def test_concurrent_registration(self, fresh_registry):
        """Multiple threads registering tools simultaneously."""
        errors = []

        def register_tool(idx):
            try:
                fresh_registry.register(
                    name=f"thread_{idx}",
                    description=f"Tool from thread {idx}",
                    parameters={"properties": {}},
                    handler=lambda: "ok",
                )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=register_tool, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert all(fresh_registry.has_tool(f"thread_{i}") for i in range(20))

    def test_concurrent_reads_during_write(self, fresh_registry):
        """Reads during concurrent writes don't crash."""
        fresh_registry.register(
            name="base",
            description="base",
            parameters={"properties": {}},
            handler=lambda: "ok",
        )

        errors = []
        def reader():
            try:
                for _ in range(100):
                    fresh_registry.get_schema("base")
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        def writer():
            try:
                for i in range(50):
                    fresh_registry.register(
                        name=f"w{i}",
                        description=f"w{i}",
                        parameters={"properties": {}},
                        handler=lambda: "ok",
                    )
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=reader) for _ in range(5)]
        threads.append(threading.Thread(target=writer))
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


class TestRegistryListing:
    """list_tools and list_by_category."""

    def test_list_by_category(self, fresh_registry):
        """Tools grouped by category."""
        fresh_registry.register(
            name="a", description="A",
            parameters={"properties": {}}, handler=lambda: "ok",
            category="filesystem",
        )
        fresh_registry.register(
            name="b", description="B",
            parameters={"properties": {}}, handler=lambda: "ok",
            category="filesystem",
        )
        fresh_registry.register(
            name="c", description="C",
            parameters={"properties": {}}, handler=lambda: "ok",
            category="network",
        )

        cats = fresh_registry.list_by_category()
        assert "filesystem" in cats
        assert "network" in cats
        assert set(cats["filesystem"]) == {"a", "b"}
        assert cats["network"] == ["c"]

    def test_uncategorized_tool(self, fresh_registry):
        """Tool without category goes to 'uncategorized'."""
        fresh_registry.register(
            name="orphan",
            description="orphan",
            parameters={"properties": {}},
            handler=lambda: "ok",
        )
        cats = fresh_registry.list_by_category()
        assert "uncategorized" in cats
        assert "orphan" in cats["uncategorized"]

    def test_snapshot(self, fresh_registry):
        """snapshot returns schemas without handlers."""
        fresh_registry.register(
            name="tool",
            description="desc",
            parameters={"properties": {"x": {"type": "int"}}},
            handler=lambda x: "ok",
            tags=["test"],
            category="testing",
        )
        snap = fresh_registry.snapshot()
        assert "tool" in snap
        assert "handler" not in snap["tool"]
        assert snap["tool"]["tags"] == {"test"}
        assert snap["tool"]["category"] == "testing"

    def test_get_tool_info(self, fresh_registry):
        """get_tool_info excludes handler."""
        fresh_registry.register(
            name="info",
            description="info tool",
            parameters={"properties": {}},
            handler=lambda: "ok",
            tags=["a", "b"],
        )
        info = fresh_registry.get_tool_info("info")
        assert info is not None
        assert "handler" not in info
        assert set(info["tags"]) == {"a", "b"}
