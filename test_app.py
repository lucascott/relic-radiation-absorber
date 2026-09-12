import http.client
import json
import tempfile
import threading
import unittest
import wave
from pathlib import Path

import app


class CollectorTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        app.DATA_DIR = Path(self.temp.name)
        self.server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Collector)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        if not any(thread.name == "test-audio-worker" for thread in threading.enumerate()):
            threading.Thread(target=app.audio_worker, daemon=True, name="test-audio-worker").start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def test_capture_and_audio(self):
        body = b"\x00secret\xff"
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        connection.request(
            "SCRAPE",
            "/anything?x=1",
            body,
            {"Authorization": "Bearer unredacted", "Cookie": "session=secret"},
        )
        response = connection.getresponse()
        capture_id = json.loads(response.read())["id"]
        connection.close()
        self.assertEqual(response.status, 202)
        app.jobs.join()

        capture = app.DATA_DIR / capture_id
        metadata = json.loads((capture / "metadata.json").read_text())
        self.assertEqual((capture / "body.bin").read_bytes(), body)
        self.assertIn(["Authorization", "Bearer unredacted"], metadata["headers"])
        self.assertIn(["Cookie", "session=secret"], metadata["headers"])
        with wave.open(str(capture / "request.wav"), "rb") as audio:
            self.assertEqual(audio.getnframes(), len(app.canonical_request(metadata, body)) * app.SAMPLES_PER_BYTE)

    def test_rejects_oversized_body(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        connection.request("POST", "/", headers={"Content-Length": str(app.MAX_BODY + 1)})
        response = connection.getresponse()
        response.read()
        connection.close()
        self.assertEqual(response.status, 413)
        self.assertEqual(list(app.DATA_DIR.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
