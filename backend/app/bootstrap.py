"""Start /health before alembic so compose does not mark the container unhealthy."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] == "/health":
            body = b'{"status":"ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(503)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"migrating")

    def log_message(self, format: str, *args: object) -> None:
        return


def _serve_health(host: str, port: int) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), _HealthHandler)
    thread = threading.Thread(target=httpd.serve_forever, name="migrate-health", daemon=True)
    thread.start()
    return httpd


def main() -> None:
    host = "0.0.0.0"
    port = 8000
    print("bootstrap: /health while alembic upgrade head", flush=True)
    httpd = _serve_health(host, port)
    try:
        rc = subprocess.call(["alembic", "upgrade", "head"])
    finally:
        httpd.shutdown()
        httpd.server_close()
    if rc != 0:
        print(f"bootstrap: alembic failed rc={rc}", flush=True)
        sys.exit(rc)
    print("bootstrap: starting uvicorn", flush=True)
    os.execvp(
        "uvicorn",
        ["uvicorn", "app.main:app", "--host", host, "--port", str(port)],
    )


if __name__ == "__main__":
    main()
