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
        from agent.deck import Deck
        d = Deck([], fresh_registry)
        assert d.size() == 0
        assert d.tools == []
        assert d.schemas() == []

    def test_deduplication(self, fresh_registry):
        _register_tools(fresh_registry)
        from agent.deck import Deck
        d = Deck(['fs_read_file', 'fs_read_file', 'fs_write_file'], fresh_registry)
        assert d.tools == ['fs_read_file', 'fs_write_file']
        assert d.size() == 2

    def test_has(self, fresh_registry):
        _register_tools(fresh_registry)
        from agent.deck import Deck
        d = Deck(['fs_read_file'], fresh_registry)
        assert d.has('fs_read_file')
        assert not d.has('nonexistent')

    def test_schemas_returns_registry_schemas(self, fresh_registry):
        _register_tools(fresh_registry)
        from agent.deck import Deck
        d = Deck(['fs_read_file', 'fs_write_file'], fresh_registry)
        schemas = d.schemas()
        names = {s['name'] for s in schemas}
        assert names == {'fs_read_file', 'fs_write_file'}

    def test_missing_tool_excluded_from_schema(self, fresh_registry):
        _register_tools(fresh_registry)
        from agent.deck import Deck
        d = Deck(['fs_read_file', 'nonexistent_tool'], fresh_registry)
        schemas = d.schemas()
        assert len(schemas) == 1
        assert schemas[0]['name'] == 'fs_read_file'

    def test_size(self, fresh_registry):
        _register_tools(fresh_registry)
        from agent.deck import Deck
        d = Deck(['fs_read_file', 'fs_write_file', 'fs_search_files'], fresh_registry)
        assert d.size() == 3

    def test_repr(self, fresh_registry):
        _register_tools(fresh_registry)
        from agent.deck import Deck
        d = Deck(['fs_read_file'], fresh_registry)
        assert 'Deck' in repr(d)
        assert 'fs_read_file' in repr(d)


class TestProtocolConversion:
    """get_schemas_for_protocol converts between Anthropic and OpenAI formats."""

    def test_anthropic_format(self, fresh_registry):
        _register_tools(fresh_registry)
        from agent.deck import Deck
        d = Deck(['fs_read_file'], fresh_registry)
        schemas = d.get_schemas_for_protocol('anthropic')
        assert len(schemas) == 1
        assert schemas[0]['name'] == 'fs_read_file'
        assert 'input_schema' in schemas[0]

    def test_openai_format(self, fresh_registry):
        _register_tools(fresh_registry)
        from agent.deck import Deck
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
        from agent.deck import Deck
        d = Deck([], fresh_registry)
        assert d.get_schemas_for_protocol('openai') == []
        assert d.get_schemas_for_protocol('anthropic') == []

    def test_unknown_protocol_falls_back_to_anthropic(self, fresh_registry):
        _register_tools(fresh_registry)
        from agent.deck import Deck
        d = Deck(['fs_read_file'], fresh_registry)
        schemas = d.get_schemas_for_protocol('unknown_protocol')
        assert len(schemas) == 1
        assert schemas[0]['name'] == 'fs_read_file'


class TestBuildDeck:
    """build_deck with redundancy slots."""

    def test_build_empty_skill_tools(self, fresh_registry):
        _register_tools(fresh_registry)
        from agent.deck import build_deck
        d = build_deck([], fresh_registry, redundancy=3)
        assert d.size() == 3
        assert all(fresh_registry.has_tool(t) for t in d.tools)

    def test_build_with_skill_tools_no_duplicates(self, fresh_registry):
        _register_tools(fresh_registry)
        _register_net_tools(fresh_registry)
        from agent.deck import build_deck
        d = build_deck(['fs_read_file', 'net_web_search'], fresh_registry, redundancy=3)
        assert 'fs_read_file' in d.tools
        assert 'net_web_search' in d.tools
        assert d.size() >= 2 + 1

    def test_build_does_not_duplicate(self, fresh_registry):
        _register_tools(fresh_registry)
        from agent.deck import build_deck
        # fs_read_file is in BASELINE_POOL, should not be duplicated
        d = build_deck(['fs_read_file'], fresh_registry, redundancy=3)
        assert d.tools.count('fs_read_file') == 1

    def test_build_redundancy_zero(self, fresh_registry):
        _register_tools(fresh_registry)
        from agent.deck import build_deck
        d = build_deck([], fresh_registry, redundancy=0)
        assert d.size() == 0

    def test_build_baseline_order_preserved(self, fresh_registry):
        _register_tools(fresh_registry)
        from agent.deck import build_deck
        d = build_deck([], fresh_registry, redundancy=5)
        from agent.deck import BASELINE_POOL
        assert d.tools == BASELINE_POOL[:5]


class TestDeckManager:
    """DeckManager — dual-mode procurement, add/drop/reset, logging."""

    def test_default_mode_is_full(self, fresh_registry):
        _register_tools(fresh_registry)
        from agent.deck import DeckManager
        dm = DeckManager(["fs_read_file", "sys_terminal"], fresh_registry)
        assert dm.mode == "full"

    def test_full_mode_returns_config_tools(self, fresh_registry):
        _register_tools(fresh_registry)
        from agent.deck import DeckManager
        dm = DeckManager(["fs_read_file", "sys_terminal"], fresh_registry)
        deck = dm.procure([], lambda tools: tools)
        assert set(deck.tools) == {"fs_read_file", "sys_terminal"}

    def test_focus_mode_with_skill_tools(self, fresh_registry):
        _register_tools(fresh_registry)
        _register_net_tools(fresh_registry)
        from agent.deck import DeckManager
        dm = DeckManager(["fs_read_file", "sys_terminal", "net_web_search"], fresh_registry)
        dm.set_mode("focus")
        deck = dm.procure(["net_web_search"], lambda tools: tools)
        assert "net_web_search" in deck.tools
        # Should have redundancy tools too
        assert len(deck.tools) >= 1 + 1

    def test_focus_mode_fallback_when_no_skills(self, fresh_registry):
        _register_tools(fresh_registry)
        from agent.deck import DeckManager
        dm = DeckManager(["fs_read_file", "sys_terminal"], fresh_registry)
        dm.set_mode("focus")
        deck = dm.procure([], lambda tools: tools)
        assert "fs_read_file" in deck.tools
        assert "fs_search_files" in deck.tools
        assert "sys_terminal" in deck.tools

    def test_add_tool_to_full_mode(self, fresh_registry):
        _register_tools(fresh_registry)
        from agent.deck import DeckManager
        dm = DeckManager(["fs_read_file"], fresh_registry)
        result = dm.add_tool("sys_terminal")
        assert "添加" in result
        deck = dm.procure([], lambda tools: tools)
        assert "sys_terminal" in deck.tools

    def test_add_tool_to_focus_mode(self, fresh_registry):
        _register_tools(fresh_registry)
        from agent.deck import DeckManager
        dm = DeckManager(["fs_read_file"], fresh_registry)
        dm.set_mode("focus")
        result = dm.add_tool("sys_terminal")
        assert "添加" in result
        deck = dm.procure([], lambda tools: tools)
        assert "sys_terminal" in deck.tools

    def test_drop_tool(self, fresh_registry):
        _register_tools(fresh_registry)
        from agent.deck import DeckManager
        dm = DeckManager(["fs_read_file", "sys_terminal"], fresh_registry)
        dm.drop_tool("sys_terminal")
        deck = dm.procure([], lambda tools: tools)
        assert "sys_terminal" not in deck.tools
        assert "fs_read_file" in deck.tools

    def test_reset_clears_focus_tools(self, fresh_registry):
        _register_tools(fresh_registry)
        from agent.deck import DeckManager
        dm = DeckManager(["fs_read_file"], fresh_registry)
        dm.set_mode("focus")
        dm.add_tool("sys_terminal")
        dm.reset()
        # After reset, focus_tools should be empty, so fallback kicks in
        deck = dm.procure([], lambda tools: tools)
        assert "fs_read_file" in deck.tools  # fallback includes it

    def test_set_mode_invalid(self, fresh_registry):
        from agent.deck import DeckManager
        dm = DeckManager([], fresh_registry)
        result = dm.set_mode("invalid")
        assert "未知" in result

    def test_log_records_combos(self, fresh_registry, tmp_path):
        _register_tools(fresh_registry)
        from agent.deck import DeckManager
        log_file = tmp_path / "deck_log.json"
        dm = DeckManager(["fs_read_file"], fresh_registry, log_path=log_file)
        dm.procure([], lambda tools: tools)
        log = dm.get_log()
        assert len(log["combos"]) >= 1
        for key, val in log["combos"].items():
            assert val["count"] >= 1
            assert "last_used" in val

    def test_mode_switch_log(self, fresh_registry, tmp_path):
        _register_tools(fresh_registry)
        from agent.deck import DeckManager
        log_file = tmp_path / "deck_log.json"
        dm = DeckManager([], fresh_registry, log_path=log_file)
        dm.set_mode("focus")
        log = dm.get_log()
        assert log["mode_switches"] >= 1
        assert log["focus_sessions"] >= 1
