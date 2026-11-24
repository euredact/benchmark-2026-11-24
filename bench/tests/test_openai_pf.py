import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from bench.adapters.openai_pf import OpenAIPrivacyFilterAdapter

TEXT = "Contact Anna Kowalska at anna@example.pl."


def test_spans_are_checked_against_the_text():
    a = OpenAIPrivacyFilterAdapter({"model_path": "x"})
    raw = {"spans": [{"label": "private_person", "start": 8, "end": 21, "text": "Anna Kowalska"},
                     {"label": "private_email", "start": 25, "end": 40, "text": "not the text there"}], "warning": None}
    parsed = a.parse(raw, TEXT, "pl")
    assert [(s.start, s.end, s.type) for s in parsed.spans] == [(8, 21, "private_person")] and parsed.unresolved == 1


@pytest.fixture
def server():
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body = json.dumps({"status": "ok", "device": "cuda", "opf": "0.1.0"}).encode()
            self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

        def do_POST(self):
            text = json.loads(self.rfile.read(int(self.headers["Content-Length"])))["text"]
            i = text.index("anna@")
            body = json.dumps({"spans": [{"label": "private_email", "start": i, "end": i + 15, "text": text[i:i + 15]}],
                               "warning": None}).encode()
            self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_remote_mode_through_the_environment(server, monkeypatch):
    monkeypatch.setenv("OPF_BASE_URL", server)
    a = OpenAIPrivacyFilterAdapter({"model_path": "unused", "model_revision": "rev"})
    a.preflight()
    r = a.detect(TEXT, "pl")
    assert [(s.start, s.end, s.type) for s in r.spans] == [(25, 40, "private_email")] and r.model_version == "rev"
    v = a.versions()
    assert v["mode"] == "remote" and v["server.device"] == "cuda"
