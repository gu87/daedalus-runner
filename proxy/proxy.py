#!/usr/bin/env python3
import sys
sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
from dynamic_credentials import add_surrogate_to_request, read_response_body
import urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer

UPSTREAM = "https://opencode.ai/zen/go"
CRED = "custom.opencode-go"
HOSTS = ["opencode.ai"]

class Handler(BaseHTTPRequestHandler):
    def _forward(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else None
        path = self.path
        if path.startswith("/v1/"):
            path = path[3:]
        url = UPSTREAM + "/v1" + path
        req = urllib.request.Request(url, data=body, method=self.command)
        ct = self.headers.get("Content-Type")
        if ct:
            req.add_header("Content-Type", ct)
        add_surrogate_to_request(req, CRED, allowed_hosts=HOSTS)
        req.add_header("User-Agent", "daedalus-proxy/0.1")
        req.add_header("x-opencode-session", "daedalus-worker-v1")
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = read_response_body(resp)
                self._log_usage(data)
                self.send_response(resp.status)
                self.send_header("Content-Type", resp.headers.get("Content-Type", "application/json"))
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as e:
            data = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            msg = ("proxy error: %s" % e).encode()
            self.send_response(502)
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)
    do_GET = _forward
    do_POST = _forward
    do_PUT = _forward
    do_DELETE = _forward
    def _log_usage(self, data):
        """从 API 响应里扒 usage，记到 /tmp/llm_usage.log"""
        try:
            import json as _json, time as _time
            obj = _json.loads(data)
            usage = obj.get("usage") or {}
            model = obj.get("model", "unknown")
            pt = usage.get("prompt_tokens", 0)
            ct = usage.get("completion_tokens", 0)
            if pt or ct:
                line = "%d %s prompt=%d completion=%d total=%d\n" % (
                    int(_time.time()), model, pt, ct, pt + ct)
                with open("/tmp/llm_usage.log", "a") as f:
                    f.write(line)
        except Exception:
            pass

    def log_message(self, *a):
        pass

if __name__ == "__main__":
    srv = HTTPServer(("127.0.0.1", 8899), Handler)
    print("proxy on 127.0.0.1:8899", flush=True)
    srv.serve_forever()
