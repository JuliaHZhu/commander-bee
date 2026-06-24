"""
Tests for NATS swarm communication tools and listener.

Uses JetStream for message persistence.
Requires a running NATS server with JetStream enabled on localhost:4222.
Run: pytest tests/test_swarm.py -v
"""
import asyncio
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.swarm import swarm_publish, swarm_request, _get_bee_id, _next_sequence


class TestSwarmTools:
    """Tests for tools/swarm.py"""

    def test_get_bee_id_fallback(self):
        """If no config.json, bee_id should fallback to 'unknown-bee'."""
        with patch.object(Path, "read_text", side_effect=FileNotFoundError):
            assert _get_bee_id() == "unknown-bee"

    def test_get_bee_id_from_config(self, tmp_path):
        """Read bee_id from config.json."""
        wb_dir = tmp_path / ".worker-bee"
        wb_dir.mkdir()
        cfg = wb_dir / "config.json"
        cfg.write_text(json.dumps({"bee_id": "bee-test"}))
        with patch("tools.swarm.Path.home", return_value=tmp_path):
            # Reset cache
            import tools.swarm
            tools.swarm._BEE_ID = None
            assert _get_bee_id() == "bee-test"

    def test_sequence_increments(self):
        """Sequence number should increment."""
        s1 = _next_sequence()
        s2 = _next_sequence()
        assert s2 == s1 + 1

    @patch("tools.swarm._run_async")
    def test_swarm_publish_returns_ok(self, mock_run):
        """swarm_publish should return success JSON."""
        mock_run.return_value = None
        result = swarm_publish("swarm.event.test", {"msg": "hello"})
        data = json.loads(result)
        assert data["ok"] is True
        assert data["subject"] == "swarm.event.test"

    @patch("tools.swarm._run_async")
    def test_swarm_request_returns_result(self, mock_run):
        """swarm_request should return response text."""
        mock_run.return_value = '{"result": "ok"}'
        result = swarm_request("swarm.query.test", {"q": "hi"})
        assert result == '{"result": "ok"}'

    @patch("tools.swarm._run_async")
    def test_swarm_request_timeout_handling(self, mock_run):
        """swarm_request should handle timeout gracefully."""
        mock_run.side_effect = asyncio.TimeoutError()
        result = swarm_request("swarm.query.test", {"q": "hi"}, timeout=1)
        data = json.loads(result)
        assert data["ok"] is False
        assert "超时" in data["error"] or "timeout" in data["error"].lower()


class TestSwarmListener:
    """Tests for swarm/listener.py mailbox writing."""

    def test_write_envelope_uses_message_id_as_filename(self, tmp_path):
        """Listener should write file using message_id as filename."""
        import swarm.listener as listener
        listener.MAILBOX_INBOX = tmp_path / "inbox"

        msg_id = str(uuid.uuid4())
        data = json.dumps({
            "message_id": msg_id,
            "subject": "swarm.event.test",
            "data": {"x": 1},
        }).encode()
        listener._write_envelope("swarm.event.test", "", data)

        filepath = listener.MAILBOX_INBOX / f"{msg_id}.json"
        assert filepath.exists()
        envelope = json.loads(filepath.read_text())
        assert envelope["message_id"] == msg_id

    def test_write_envelope_generates_message_id_if_missing(self, tmp_path):
        """If incoming message lacks message_id, listener should generate one."""
        import swarm.listener as listener
        listener.MAILBOX_INBOX = tmp_path / "inbox"

        data = json.dumps({"foo": "bar"}).encode()
        listener._write_envelope("swarm.event.test", "", data)

        files = list(listener.MAILBOX_INBOX.glob("*.json"))
        assert len(files) == 1
        envelope = json.loads(files[0].read_text())
        assert "message_id" in envelope
        assert envelope["subject"] == "swarm.event.test"
        assert "sequence" in envelope


class TestSwarmIntegration:
    """Integration tests — requires NATS server with JetStream running."""

    @pytest.mark.skipif(
        os.environ.get("NATS_URL") is None,
        reason="Requires NATS server with JetStream. Set NATS_URL=nats://localhost:4222 and start nats-server -js to run."
    )
    def test_publish_to_real_nats(self):
        """Send a message to a real NATS JetStream server.

        NOTE: Ensure the swarm-listener has created the 'swarm-messages' Stream,
        or js.publish() will fail with 'no stream matches subject'.
        """
        os.environ["SWARM_NATS_URL"] = os.environ.get("NATS_URL", "nats://localhost:4222")
        result = swarm_publish("swarm.test.integration", {"hello": "world"})
        data = json.loads(result)
        assert data["ok"] is True
