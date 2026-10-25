"""A stand-in for the Ollama server, speaking just enough of its HTTP API for our client."""

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeOllama:
    def __init__(self, models=("qwen3.5:4b",), broken_windows=0):
        self.models = list(models)
        self.requests: list[dict] = []
        self.broken_windows = broken_windows  # first N labelling calls return garbage
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, status, body):
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                if self.path == "/api/tags":
                    self._send(200, {"models": [{"model": m, "name": m} for m in fake.models]})
                else:
                    self._send(404, {"error": "not found"})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.requests.append(body)
                if body["model"] not in fake.models:
                    return self._send(404, {"error": f"model '{body['model']}' not found"})
                self._send(200, {"model": body["model"], "message": {"role": "assistant", "content": fake.reply(body)}, "done": True})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def reply(self, body) -> str:
        prompt = body["messages"][-1]["content"]
        if not body.get("format"):
            return "A lecture about gradients. It covers descent and learning rates."
        if self.broken_windows > 0:
            self.broken_windows -= 1
            return '{"segments": [{"id": 1, "lab'
        segments, sections = [], []
        for seg_id, text in re.findall(r"^\[(\d+)\] \S+ (.*)$", prompt, re.M):
            text = text.lower()
            label, importance = "core", 8
            if "again" in text:
                label, importance = "repeat", 2
            elif "subscribe" in text:
                label, importance = "promo", 0
            segments.append({"id": int(seg_id), "label": label, "importance": importance, "topic": text.split(",")[0][:30]})
        if segments:
            sections.append({"segment_id": segments[0]["id"], "title": f"Part starting at {segments[0]['id']}"})
        return json.dumps({"segments": segments, "sections": sections})

    def __enter__(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
