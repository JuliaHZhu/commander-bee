"""Integration tests for AIAgent — Deck integration, protocol conversion, dummy runs.

Uses monkeypatch to mock API calls so we don't need a real LLM.
"""
import pytest
from worker_bee.agent import AIAgent
from worker_bee.deck import Deck


@pytest.fixture
def agent():
    """Return an AIAgent with Anthropic protocol and test config."""
    return AIAgent({
        "model": "test",
        "provider": "anthropic",
        "api_key": "test-key",
        "base_url": "https://test.example.com",
        "max_iterations": 5,
        "system_prompt": "test",
        "tools": ["fs_read_file", "sys_terminal"],
    })


class TestAgentProtocolConversion:
    """AIAgent with Deck — ensuring protocol compatibility."""

    def test_deck_anthropic_protocol(self, agent, monkeypatch, fresh_registry):
        """Agent with Anthropic protocol calls Deck.get_schemas_for_protocol('anthropic')."""
        deck = Deck(['fs_read_file'], fresh_registry)

        # Mock the anthropic client
        class MockResponse:
            class Content:
                def __init__(self):
                    self.text = "Hello from mock"
                    self.type = "text"
            content = [Content()]

        monkeypatch.setattr(
            agent.client.messages, "create",
            lambda **kwargs: MockResponse()
        )

        result = agent.run([{"role": "user", "content": "test"}], deck=deck)
        # Should not crash — the critical regression test
        assert isinstance(result, str)
        # Should have received a response
        assert len(result) > 0

    def test_deck_openai_protocol(self, monkeypatch, fresh_registry):
        """Agent with OpenAI protocol calls Deck.get_schemas_for_protocol('openai')."""
        agent_oai = AIAgent({
            "model": "gpt-4o",
            "provider": "openai",
            "api_key": "sk-test",
            "base_url": "https://api.openai.com/v1",
            "max_iterations": 5,
            "system_prompt": "test",
            "tools": ["fs_read_file"],
        })

        deck = Deck(['fs_read_file'], fresh_registry)

        class MockChoice:
            class Message:
                content = "Hello from OpenAI mock"
                tool_calls = None
            message = Message()

        class MockResponse:
            choices = [MockChoice()]

        monkeypatch.setattr(
            agent_oai.client.chat.completions, "create",
            lambda **kwargs: MockResponse()
        )

        result = agent_oai.run([{"role": "user", "content": "test"}], deck=deck)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_deck_with_tool_use(self, agent, monkeypatch, fresh_registry):
        """Agent with Deck handles tool_use loop correctly."""
        deck = Deck(['fs_read_file'], fresh_registry)

        call_count = 0

        class ToolUse:
            type = "tool_use"
            id = "tool_001"
            name = "fs_read_file"
            input = {"path": "test.txt"}

        class TextBlock:
            type = "text"
            text = "Final answer"

        def mock_create(**kwargs):
            nonlocal call_count
            call_count += 1
            class MockResponse:
                @property
                def content(self):
                    if call_count == 1:
                        return [ToolUse()]
                    return [TextBlock()]
            return MockResponse()

        monkeypatch.setattr(agent.client.messages, "create", mock_create)

        # Also need to mock the tool execution
        monkeypatch.setattr(
            fresh_registry, "call",
            lambda name, args: "mocked file content"
        )

        result = agent.run([{"role": "user", "content": "read test.txt"}], deck=deck)
        assert result == "Final answer"
        assert call_count >= 2  # at least one tool use + final response


class TestAgentWithoutDeck:
    """AIAgent runs correctly without a Deck (legacy path)."""

    def test_no_deck_passes_tools_normally(self, agent, monkeypatch):
        """When no deck is provided, uses enabled_tools from config."""
        class MockResponse:
            class Content:
                def __init__(self):
                    self.text = "No deck response"
                    self.type = "text"
            content = [Content()]

        monkeypatch.setattr(
            agent.client.messages, "create",
            lambda **kwargs: MockResponse()
        )

        result = agent.run([{"role": "user", "content": "test"}])
        assert result == "No deck response"


class TestAgentMaxIterations:
    """Agent respects max_iterations and halts gracefully."""

    def test_max_iterations_halt(self, agent, monkeypatch, fresh_registry):
        """Agent returns halt message when max iterations reached."""
        deck = Deck(['fs_read_file'], fresh_registry)

        class ToolUse:
            type = "tool_use"
            id = "tool_001"
            name = "fs_read_file"
            input = {"path": "test.txt"}

        def mock_create(**kwargs):
            class MockResponse:
                @property
                def content(self):
                    return [ToolUse()]
            return MockResponse()

        monkeypatch.setattr(agent.client.messages, "create", mock_create)
        monkeypatch.setattr(
            fresh_registry, "call",
            lambda name, args: "content"
        )

        result = agent.run([{"role": "user", "content": "test"}], deck=deck)
        assert "max iterations" in result or result == "(reached max iterations)"


class TestAgentMessageFormat:
    """Message format conversion is correct."""

    def test_to_api_messages_simple(self, agent):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        api = agent._to_api_messages(messages)
        assert len(api) == 2
        assert api[0]["role"] == "user"
        assert api[0]["content"] == "hello"

    def test_to_api_messages_tool_result_anthropic(self, agent):
        """Tool results are wrapped in tool_result blocks for Anthropic."""
        messages = [
            {"role": "tool", "tool_call_id": "tc1", "content": "result text"},
        ]
        api = agent._to_api_messages(messages)
        assert api[0]["role"] == "user"
        assert isinstance(api[0]["content"], list)
        assert api[0]["content"][0]["type"] == "tool_result"
        assert api[0]["content"][0]["tool_use_id"] == "tc1"

    def test_to_api_messages_tool_calls_anthropic(self, agent):
        """Assistant tool calls are converted to tool_use blocks."""
        messages = [
            {
                "role": "assistant",
                "content": "Let me read that",
                "tool_calls": [
                    {"id": "tc1", "name": "fs_read_file", "input": {"path": "x"}}
                ],
            },
        ]
        api = agent._to_api_messages(messages)
        assert api[0]["role"] == "assistant"
        blocks = api[0]["content"]
        assert any(b.get("type") == "tool_use" for b in blocks)
        assert any(b.get("type") == "text" for b in blocks)


class TestAgentInit:
    """AIAgent initialization."""

    def test_anthropic_protocol(self):
        agent = AIAgent({
            "provider": "anthropic",
            "api_key": "test",
            "model": "claude",
        })
        assert agent._protocol == "anthropic"

    def test_openai_protocol(self):
        agent = AIAgent({
            "provider": "openai",
            "api_key": "sk-test",
            "model": "gpt-4o",
        })
        assert agent._protocol == "openai"

    def test_defaults(self):
        agent = AIAgent({
            "provider": "anthropic",
            "api_key": "test",
        })
        assert agent.model == "kimi-k2.6"
        assert agent.max_iterations == 60
