#!/usr/bin/env python3
import sys
sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
from dynamic_credentials import add_surrogate_to_request, read_response_body
import urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer

UPSTREAM = "https://opencode.ai/zen/go"
CRED = "custom.opencode-go"
HOSTS = ["opencode.ai"]

# usage 账本落盘位置：放仓库内持久目录，VM 重启不丢（/tmp 会被清空）
USAGE_LOG = "/home/hatch/workspace/daedalus-runner/logs/llm_usage.log"

TAVILY_UPSTREAM = "https://api.tavily.com"
TAVILY_CRED = "custom.tavily"
TAVILY_HOSTS = ["api.tavily.com"]

class Handler(BaseHTTPRequestHandler):
    def _forward(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else None
        path = self.path

        # Tavily 搜索走单独的上游和凭证
        if path.startswith("/tavily/"):
            upstream = TAVILY_UPSTREAM
            cred = TAVILY_CRED
            hosts = TAVILY_HOSTS
            url = upstream + path[7:]  # 去掉 /tavily 前缀
            extra_headers = {}
        else:
            upstream = UPSTREAM
            cred = CRED
            hosts = HOSTS
            if path.startswith("/v1/"):
                path = path[3:]
            url = upstream + "/v1" + path
            extra_headers = {
                "User-Agent": "daedalus-proxy/0.1",
                "x-opencode-session": "daedalus-worker-v1",
            }

        req = urllib.request.Request(url, data=body, method=self.command)
        ct = self.headers.get("Content-Type")
        if ct:
            req.add_header("Content-Type", ct)
        add_surrogate_to_request(req, cred, allowed_hosts=hosts)
        for k, v in extra_headers.items():
            req.add_header(k, v)
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
        """从 API 响应里扒 usage，记到账本。
        兼容两种响应形态：
        - 普通 JSON（chat.completions 非流式）
        - SSE 流式（daemon 实际走这个：逐个 data chunk 里找带 usage 的尾包）
        """
        try:
            import json as _json, time as _time, os as _os
            if isinstance(data, (bytes, bytearray)):
                text = bytes(data).decode("utf-8", "replace")
            else:
                text = data
            usage = {}
            model = "unknown"
            try:
                obj = _json.loads(text)
                usage = obj.get("usage") or {}
                model = obj.get("model", "unknown")
            except Exception:
                for line in text.split("\n"):
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if not payload or payload == "[DONE]":
                        continue
                    try:
                        chunk = _json.loads(payload)
                    except Exception:
                        continue
                    if chunk.get("model"):
                        model = chunk["model"]
                    if chunk.get("usage"):
                        usage = chunk["usage"]
            pt = usage.get("prompt_tokens", 0) or 0
            ct = usage.get("completion_tokens", 0) or 0
            if pt or ct:
                _os.makedirs(_os.path.dirname(USAGE_LOG), exist_ok=True)
                line = "%d %s prompt=%d completion=%d total=%d\n" % (
                    int(_time.time()), model, pt, ct, pt + ct)
                with open(USAGE_LOG, "a") as f:
                    f.write(line)
        except Exception:
            pass

    def log_message(self, *a):
        pass

if __name__ == "__main__":
    srv = HTTPServer(("127.0.0.1", 8899), Handler)
    print("proxy on 127.0.0.1:8899", flush=True)
    srv.serve_forever()
