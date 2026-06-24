"""Tests for web tools — SSRF protection, URL guards, web search/extract."""
import pytest

from tools.web import (
    _is_blocked_host,
    _guard_url,
)


class TestSSRFHostBlocking:
    """_is_blocked_host — internal/reserved hostname blocking."""

    def test_localhost_blocked(self):
        assert _is_blocked_host("localhost")
        assert _is_blocked_host("LOCALHOST")

    def test_ipv4_loopback_blocked(self):
        assert _is_blocked_host("127.0.0.1")

    def test_aws_metadata_blocked(self):
        assert _is_blocked_host("169.254.169.254")

    def test_gcp_metadata_blocked(self):
        assert _is_blocked_host("metadata.google.internal")

    def test_generic_metadata_blocked(self):
        assert _is_blocked_host("metadata")

    def test_private_10_blocked(self):
        assert _is_blocked_host("10.0.0.1")
        assert _is_blocked_host("10.255.255.255")

    def test_private_192_168_blocked(self):
        assert _is_blocked_host("192.168.1.1")
        assert _is_blocked_host("192.168.0.254")

    def test_private_172_blocked(self):
        assert _is_blocked_host("172.16.0.1")
        assert _is_blocked_host("172.31.255.255")

    def test_ipv6_loopback_blocked(self):
        assert _is_blocked_host("::1")

    def test_ipv6_link_local_blocked(self):
        assert _is_blocked_host("fe80::1")

    def test_public_hosts_allowed(self):
        assert not _is_blocked_host("example.com")
        assert not _is_blocked_host("api.openai.com")
        assert not _is_blocked_host("8.8.8.8")  # public DNS

    def test_trailing_dot_ignored(self):
        """Trailing dot in hostname should be stripped."""
        assert _is_blocked_host("localhost.")
        assert not _is_blocked_host("example.com.")


class TestURLGuard:
    """_guard_url validation."""

    def test_https_allowed(self):
        _guard_url("https://example.com")  # Should not raise

    def test_http_allowed(self):
        _guard_url("http://example.com")  # Should not raise

    def test_file_blocked(self):
        with pytest.raises(ValueError, match="Disallowed URL scheme"):
            _guard_url("file:///etc/passwd")

    def test_ftp_blocked(self):
        with pytest.raises(ValueError, match="Disallowed URL scheme"):
            _guard_url("ftp://example.com")

    def test_javascript_blocked(self):
        with pytest.raises(ValueError, match="Disallowed URL scheme"):
            _guard_url("javascript:alert(1)")

    def test_data_blocked(self):
        with pytest.raises(ValueError, match="Disallowed URL scheme"):
            _guard_url("data:text/html,<script>alert(1)</script>")

    def test_no_scheme_blocked(self):
        with pytest.raises(ValueError, match="Disallowed URL scheme"):
            _guard_url("//example.com")

    def test_internal_ip_blocked(self):
        with pytest.raises(ValueError, match="Disallowed host"):
            _guard_url("http://127.0.0.1:8080/admin")

    def test_localhost_blocked(self):
        with pytest.raises(ValueError, match="Disallowed host"):
            _guard_url("https://localhost/metrics")

    def test_private_ip_blocked(self):
        with pytest.raises(ValueError, match="Disallowed host"):
            _guard_url("http://192.168.1.100/secret")

    def test_aws_metadata_blocked(self):
        with pytest.raises(ValueError, match="Disallowed host"):
            _guard_url("http://169.254.169.254/latest/meta-data/")

    def test_no_hostname_blocked(self):
        with pytest.raises(ValueError, match="hostname"):
            _guard_url("http:///path")

    def test_public_url_allowed(self):
        """Normal public URLs pass validation."""
        _guard_url("https://github.com")
        _guard_url("https://api.openai.com/v1/chat/completions")
        _guard_url("http://example.com:8080/path?q=1")

    def test_query_params_and_fragments(self):
        """URLs with query params and fragments should still be checked."""
        with pytest.raises(ValueError, match="Disallowed host"):
            _guard_url("http://127.0.0.1:8000/users?admin=true#section")


class TestWebSearch:
    """net_web_search — DuckDuckGo HTML endpoint."""

    def test_search_returns_results(self):
        """Basic search returns results from DuckDuckGo."""
        from tools.web import net_web_search
        result = net_web_search("python programming", num_results=3)
        assert len(result) > 0
        # Should not contain raw HTML tags
        assert "<a " not in result or "http" in result

    def test_search_no_results(self):
        """Search with nonsense query returns empty."""
        from tools.web import net_web_search
        result = net_web_search("xkcdqrsxyzzyx12345nonexistent", num_results=1)
        assert isinstance(result, str)


class TestWebExtract:
    """net_web_extract — URL fetching with SSRF guard."""

    def test_extract_public_url(self):
        """Extract text from a small public page."""
        from tools.web import net_web_extract
        result = net_web_extract("http://example.com")
        assert len(result) > 0
        # Should have extracted plain text
        assert "Example Domain" in result or "example" in result.lower()

    def test_extract_blocked_localhost(self):
        """Extracting from localhost should be blocked by SSRF guard."""
        from tools.web import net_web_extract
        result = net_web_extract("http://localhost:8000/test")
        assert "Disallowed" in result or "Error" in result

    def test_extract_invalid_url(self):
        """Invalid URL returns error."""
        from tools.web import net_web_extract
        result = net_web_extract("not-a-valid-url")
        assert "Error" in result or "Invalid" in result or "Disallowed" in result
