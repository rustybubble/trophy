"""Local setup-time calibration endpoint without web-framework dependencies."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from calibration import calibrate


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/calibrate":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 64 * 1024:
                raise ValueError("Expected a JSON body no larger than 64 KiB")
            response = calibrate(json.loads(self.rfile.read(length)))
            status = 200
        except (ValueError, KeyError, TypeError) as exc:
            response = {"error": str(exc), "trusted": False}
            status = 422
        payload = json.dumps(response, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == "/healthz":
            payload = b'{"ok":true,"solver":"opencv-planar-v1"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        else:
            self.send_error(404)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8050)
    args = parser.parse_args()
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
