import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from metranscript import privacy, server, settings, store


class ServerCase(unittest.TestCase):
    """A real HTTP server on a free port with meetings and .env redirected to a temp folder."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.patches = [
            mock.patch.object(store, "ROOT", root / "meetings"),
            mock.patch.object(settings, "ROOT", root),
            mock.patch.object(privacy, "ROOT", root),
            mock.patch.object(server, "watcher", None),
        ]
        for p in cls.patches:
            p.start()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        server.HOSTS.add(f"127.0.0.1:{cls.port}")
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        for p in cls.patches:
            p.stop()
        cls.tmp.cleanup()

    def call(self, method, path, body=None, headers=None, raw=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": f"127.0.0.1:{self.port}", "Content-Type": "application/json", **(headers or {})}
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        conn.request(method, path, body=data, headers=h)
        res = conn.getresponse()
        payload = res.read()
        conn.close()
        ctype = res.getheader("Content-Type", "")
        return res.status, (json.loads(payload) if "json" in ctype else payload.decode())
