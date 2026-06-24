"""Tests for Deck — tool boundary, protocol conversion, build_deck."""


def _register_tools(reg):
    """Register minimal tools needed for Deck tests."""
    for name in ["fs_read_file", "fs_write_file", "fs_search_files", "sys_terminal", "send_message", "cronjob"]:
        if not reg.has_tool(name):
            reg.register(
                name=name,
                description=f"Mock {name}",
                parameters={"type": "object", "properties": {}, "required": []},
                handler=lambda *a, **_kw: "ok",
                tags=["test"],
                category="test",
            )


def _register_net_tools(reg):
    """Register network tools."""
    for name in ["net_web_search", "net_web_extract"]:
        if not reg.has_tool(name):
            reg.register(
                name=name,
                description=f"Mock {name}",
                parameters={"type": "object", "properties": {}, "required": []},
                handler=lambda *a, **_kw: "ok",
                tags=["test"],
                category="test",
            )


class TestDeck:
    """Deck basic operations."""

    def test_empty_deck(self, fresh_registry):
        from worker_bee.deck import Deck
        d = Deck([], fresh_registry)
        assert d.size() == 0
        assert d.tools == []
        assert d.schemas() == []

    def test_deduplication(self, fresh_registry):
        _register_tools(fresh_registry)
        from worker_bee.deck import Deck
        d = Deck(['fs_read_file', 'fs_read_file', 'fs_write_file'], fresh_registry)
        assert d.tools == ['fs_read_file', 'fs_write_file']
        assert d.size() == 2

    def test_has(self, fresh_registry):
        _register_tools(fresh_registry)
        from worker_bee.deck import Deck
        d = Deck(['fs_read_file'], fresh_registry)
        assert d.has('fs_read_file')
        assert not d.has('nonexistent')

    def test_schemas_returns_registry_schemas(self, fresh_registry):
        _register_tools(fresh_registry)
        from worker_bee.deck import Deck
        d = Deck(['fs_read_file', 'fs_write_file'], fresh_registry)
        schemas = d.schemas()
        names = {s['name'] for s in schemas}
        assert names == {'fs_read_file', 'fs_write_file'}

    def test_missing_tool_excluded_from_schema(self, fresh_registry):
        _register_tools(fresh_registry)
        from worker_bee.deck import Deck
        d = Deck(['fs_read_file', 'nonexistent_tool'], fresh_registry)
        schemas = d.schemas()
        assert len(schemas) == 1
        assert schemas[0]['name'] == 'fs_read_file'

    def test_size(self, fresh_registry):
        _register_tools(fresh_registry)
        from worker_bee.deck import Deck
        d = Deck(['fs_read_file', 'fs_write_file', 'fs_search_files'], fresh_registry)
        assert d.size() == 3

    def test_repr(self, fresh_registry):
        _register_tools(fresh_registry)
        from worker_bee.deck import Deck
        d = Deck(['fs_read_file'], fresh_registry)
        assert 'Deck' in repr(d)
        assert 'fs_read_file' in repr(d)


class TestProtocolConversion:
    """get_schemas_for_protocol converts between Anthropic and OpenAI formats."""

    def test_anthropic_format(self, fresh_registry):
        _register_tools(fresh_registry)
        from worker_bee.deck import Deck
        d = Deck(['fs_read_file'], fresh_registry)
        schemas = d.get_schemas_for_protocol('anthropic')
        assert len(schemas) == 1
        assert schemas[0]['name'] == 'fs_read_file'
        assert 'input_schema' in schemas[0]

    def test_openai_format(self, fresh_registry):
        _register_tools(fresh_registry)
        from worker_bee.deck import Deck
        d = Deck(['fs_read_file', 'fs_write_file'], fresh_registry)
        schemas = d.get_schemas_for_protocol('openai')
        assert len(schemas) == 2
        for s in schemas:
            assert s['type'] == 'function'
            assert 'function' in s
            assert 'name' in s['function']
            assert 'description' in s['function']
            assert 'parameters' in s['function']

    def test_openai_empty_deck(self, fresh_registry):
        from worker_bee.deck import Deck
        d = Deck([], fresh_registry)
        assert d.get_schemas_for_protocol('openai') == []
        assert d.get_schemas_for_protocol('anthropic') == []

    def test_unknown_protocol_falls_back_to_anthropic(self, fresh_registry):
        _register_tools(fresh_registry)
        from worker_bee.deck import Deck
        d = Deck(['fs_read_file'], fresh_registry)
        schemas = d.get_schemas_for_protocol('unknown_protocol')
        assert len(schemas) == 1
        assert schemas[0]['name'] == 'fs_read_file'


class TestBuildDeck:
    """build_deck with redundancy slots."""

    def test_build_empty_skill_tools(self, fresh_registry):
        _register_tools(fresh_registry)
        from worker_bee.deck import build_deck
        d = build_deck([], fresh_registry, redundancy=3)
        assert d.size() == 3
        assert all(fresh_registry.has_tool(t) for t in d.tools)

    def test_build_with_skill_tools_no_duplicates(self, fresh_registry):
        _register_tools(fresh_registry)
        _register_net_tools(fresh_registry)
        from worker_bee.deck import build_deck
        d = build_deck(['fs_read_file', 'net_web_search'], fresh_registry, redundancy=3)
        assert 'fs_read_file' in d.tools
        assert 'net_web_search' in d.tools
        assert d.size() >= 2 + 1

    def test_build_does_not_duplicate(self, fresh_registry):
        _register_tools(fresh_registry)
        from worker_bee.deck import build_deck
        # fs_read_file is in BASELINE_POOL, should not be duplicated
        d = build_deck(['fs_read_file'], fresh_registry, redundancy=3)
        assert d.tools.count('fs_read_file') == 1

    def test_build_redundancy_zero(self, fresh_registry):
        _register_tools(fresh_registry)
        from worker_bee.deck import build_deck
        d = build_deck([], fresh_registry, redundancy=0)
        assert d.size() == 0

    def test_build_baseline_order_preserved(self, fresh_registry):
        _register_tools(fresh_registry)
        from worker_bee.deck import build_deck
        d = build_deck([], fresh_registry, redundancy=5)
        from worker_bee.deck import BASELINE_POOL
        assert d.tools == BASELINE_POOL[:5]
