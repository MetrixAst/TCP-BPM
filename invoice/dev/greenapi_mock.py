"""Заглушка Green API для локального стенда: ничего не отправляет в WhatsApp,
только пишет каждый запрос в лог и в /data/requests.jsonl.

GET /_requests — последние принятые запросы (для проверок).
"""
import json
import re
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

LOG = Path("/data/requests.jsonl")
ROUTE = re.compile(r"^/waInstance(?P<instance>[^/]+)/(?P<method>[A-Za-z]+)/(?P<token>[^/?]+)")


class Handler(BaseHTTPRequestHandler):
    def _reply(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _record(self, method, body):
        entry = {
            "ts": time.time(),
            "http": self.command,
            "method": method,
            "content_type": self.headers.get("Content-Type", ""),
            "size": len(body),
            "body": body[:2000].decode("utf-8", "replace"),
        }
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"{self.command} {method} {entry['size']}b", flush=True)

    def _handle(self):
        if self.path.startswith("/_requests"):
            lines = LOG.read_text().splitlines()[-50:] if LOG.exists() else []
            return self._reply(200, [json.loads(line) for line in lines])
        m = ROUTE.match(self.path)
        if not m:
            return self._reply(404, {"error": "unknown route"})
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        method = m.group("method")
        self._record(method, body)
        if method == "getStateInstance":
            return self._reply(200, {"stateInstance": "authorized"})
        if method == "lastOutgoingMessages":
            return self._reply(200, [])
        if method == "setSettings":
            return self._reply(200, {"saveSettings": True})
        return self._reply(200, {"idMessage": f"MOCK{uuid.uuid4().hex[:16].upper()}"})

    do_GET = _handle
    do_POST = _handle

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
