import ipaddress
import re
import urllib.request
import urllib.parse
from urllib.parse import urlparse
from worker_bee.registry import registry


# ── SSRF / protocol guard ──────────────────────────────────────────────

_ALLOWED_SCHEMES = {"http", "https"}

# Block internal/reserved hostnames and IPs that could leak local services.
_BLOCKED_HOSTS = frozenset({
    "localhost", "127.0.0.1", "0.0.0.0", "::1", "0000:0000:0000:0000:0000:0000:0000:0001",
    "169.254.169.254",            # AWS / cloud metadata
    "metadata.google.internal",   # GCP metadata
    "metadata",                   # generic metadata alias
})

# IP ranges that should never be reached from the web tools.
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("::1/128"),
]


def _is_blocked_host(hostname: str) -> bool:
    """Return True if hostname is internal/reserved."""
    h = hostname.lower().rstrip(".")
    if h in _BLOCKED_HOSTS:
        return True
    if h.startswith("127.") or h.startswith("10.") or h.startswith("192.168."):
        return True
    # Check IP ranges
    try:
        addr = ipaddress.ip_address(h)
        for net in _BLOCKED_NETWORKS:
            if addr in net:
                return True
    except ValueError:
        pass
    return False


def _guard_url(raw_url: str) -> None:
    """Raise ValueError if URL is disallowed (file://, internal IP, etc.)."""
    try:
        parsed = urlparse(raw_url)
    except Exception as exc:
        raise ValueError(f"Invalid URL: {exc}")

    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise ValueError(
            f"Disallowed URL scheme '{scheme}'. Only http:// and https:// are permitted."
        )

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise ValueError("URL must include a hostname.")
    if _is_blocked_host(hostname):
        raise ValueError(f"Disallowed host: {hostname}")


def net_web_search(query: str, num_results: int = 5) -> str:
    """Search the web using Bing HTML endpoint (no API key needed)."""
    try:
        url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        results = []
        blocks = re.findall(
            r'<li[^>]*class=["\'][^"\']*b_algo[^"\']*["\'][^>]*>(.*?)</li>',
            html,
            re.DOTALL,
        )
        for block in blocks:
            title_m = re.search(r"<h2[^>]*>(.*?)</h2>", block, re.DOTALL)
            title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip() if title_m else ""
            href_m = re.search(r'href=["\']([^"\']+)["\']', block)
            href = href_m.group(1) if href_m else ""
            if title and href.startswith("http") and "bing.com" not in href:
                results.append(f"- {title}\n  {href}")
                if len(results) >= num_results:
                    break
        return "\n".join(results) or "No results found."
    except Exception as e:
        return f"Search error: {e}"


def net_web_extract(url: str) -> str:
    """Fetch and extract text from a URL."""
    try:
        _guard_url(url)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:4000] + ("\n... (truncated)" if len(text) > 4000 else "")
    except Exception as e:
        return f"Fetch error: {e}"


registry.register(
    name="net_web_search",
    description="Search the web using Bing. No API key required. Returns titles and URLs.",
    parameters={
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "num_results": {"type": "integer", "description": "Number of results", "default": 5}
        },
        "required": ["query"]
    },
    handler=net_web_search,
    tags=["network", "search"],
    category="network"
)

registry.register(
    name="net_web_extract",
    description="Fetch a URL and extract plain text. Strips scripts/styles/HTML tags. Only http(s) external URLs allowed.",
    parameters={
        "properties": {
            "url": {"type": "string", "description": "Full http(s) URL to fetch"}
        },
        "required": ["url"]
    },
    handler=net_web_extract,
    tags=["network", "fetch"],
    category="network"
)
