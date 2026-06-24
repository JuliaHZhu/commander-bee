"""
swarm file server — HTTP 文件传输服务。

用于跨机器传输大文件（不通过 NATS）。
工作流程：
  1. 发送方启动 HTTP 服务暴露文件
  2. 通过 NATS 发送 file_url 消息
  3. 接收方读取 mailbox → HTTP 下载到本地

启动：
    python swarm/file_server.py [port] [shared_dir]
    # 默认 port=8080，shared_dir=~/.worker-bee/shared
"""
import http.server
import json
import os
import sys
import urllib.parse
from pathlib import Path

DEFAULT_PORT = 8080
DEFAULT_DIR = Path.home() / ".worker-bee" / "shared"


class FileHandler(http.server.SimpleHTTPRequestHandler):
    """Simple HTTP handler for file listing/download."""

    def log_message(self, format, *args):
        # Suppress default logging; optionally add structured logging here
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self._list_files()
            return
        # Fallback to static file serving
        super().do_GET()

    def _list_files(self):
        """Return JSON list of available files."""
        shared_dir = self.server.shared_dir
        files = []
        if shared_dir.exists():
            for p in sorted(shared_dir.iterdir()):
                if p.is_file():
                    files.append({
                        "name": p.name,
                        "size": p.stat().st_size,
                        "mtime": p.stat().st_mtime,
                    })
        body = json.dumps({"files": files}, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def translate_path(self, path):
        """Restrict access to shared_dir only."""
        shared_dir = self.server.shared_dir
        # Strip query string and decode
        path = urllib.parse.unquote(path.split("?", 1)[0])
        # Join with shared_dir as root
        result = shared_dir / path.lstrip("/")
        # Security: ensure it's inside shared_dir
        try:
            result.resolve().relative_to(shared_dir.resolve())
        except ValueError:
            return str(shared_dir / "nonexistent")
        return str(result)


class FileServer(http.server.ThreadingHTTPServer):
    def __init__(self, address, handler, shared_dir: Path):
        super().__init__(address, handler)
        self.shared_dir = shared_dir


def run_server(port: int = DEFAULT_PORT, shared_dir: Path = DEFAULT_DIR):
    shared_dir.mkdir(parents=True, exist_ok=True)
    server = FileServer(("0.0.0.0", port), FileHandler, shared_dir)
    print(f"[file-server] Serving {shared_dir} on http://0.0.0.0:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[file-server] Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    shared = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_DIR
    run_server(port, shared)
