import hashlib
import json
import math
import os
import queue
import shutil
import struct
import threading
import time
import uuid
import wave
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


MAX_BODY = 10 * 1024 * 1024
DATA_DIR = Path(os.environ.get("DATA_DIR", "./captures"))
SAMPLE_RATE = 8_000
SAMPLES_PER_BYTE = 16
jobs = queue.Queue()


def canonical_request(metadata, body):
    lines = [
        f"{metadata['method']} {metadata['target']} {metadata['http_version']}",
        *(f"{name}: {value}" for name, value in metadata["headers"]),
        "",
        "",
    ]
    return "\r\n".join(lines).encode() + body


def sonify(data, destination):
    with wave.open(str(destination), "wb") as output:
        output.setparams((1, 2, SAMPLE_RATE, 0, "NONE", "not compressed"))
        for value in data:
            frequency = 220 + value * 6
            samples = (
                int(10_000 * math.sin(2 * math.pi * frequency * i / SAMPLE_RATE))
                for i in range(SAMPLES_PER_BYTE)
            )
            output.writeframesraw(struct.pack(f"<{SAMPLES_PER_BYTE}h", *samples))


def audio_worker():
    while True:
        capture_dir, metadata, body = jobs.get()
        try:
            sonify(canonical_request(metadata, body), capture_dir / "request.wav")
        except Exception as error:
            (capture_dir / "audio-error.txt").write_text(str(error), encoding="utf-8")
        finally:
            jobs.task_done()


class TooLarge(Exception):
    pass


class Collector(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def read_body(self):
        transfer_encoding = self.headers.get("Transfer-Encoding", "").lower()
        if transfer_encoding:
            if transfer_encoding != "chunked":
                self.send_error(501, "Unsupported Transfer-Encoding")
                return None
            return self.read_chunked_body()

        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self.send_error(400, "Invalid Content-Length")
            return None
        if length < 0:
            self.send_error(400, "Invalid Content-Length")
            return None
        if length > MAX_BODY:
            self.send_error(413, "Request body exceeds 10 MiB")
            return None
        body = self.rfile.read(length)
        if len(body) != length:
            self.send_error(400, "Incomplete request body")
            return None
        return body

    def read_chunked_body(self):
        body = bytearray()
        try:
            while True:
                line = self.rfile.readline(8192)
                if not line.endswith(b"\r\n"):
                    raise ValueError
                size = int(line.split(b";", 1)[0], 16)
                if size == 0:
                    while self.rfile.readline(8192) != b"\r\n":
                        pass
                    return bytes(body)
                if len(body) + size > MAX_BODY:
                    raise TooLarge
                chunk = self.rfile.read(size)
                if len(chunk) != size or self.rfile.read(2) != b"\r\n":
                    raise ValueError
                body.extend(chunk)
        except TooLarge:
            self.close_connection = True
            self.send_error(413, "Request body exceeds 10 MiB")
        except (ValueError, OverflowError):
            self.close_connection = True
            self.send_error(400, "Malformed chunked body")
        return None

    def handle_capture(self):
        body = self.read_body()
        if body is None:
            return

        capture_id = f"{time.time_ns()}-{uuid.uuid4().hex}"
        final_dir = DATA_DIR / capture_id
        temp_dir = DATA_DIR / f".{capture_id}"
        metadata = {
            "id": capture_id,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "source": {"address": self.client_address[0], "port": self.client_address[1]},
            "method": self.command,
            "target": self.path,
            "http_version": self.request_version,
            "headers": list(self.headers.raw_items()),
            "body_size": len(body),
            "body_sha256": hashlib.sha256(body).hexdigest(),
        }

        temp_dir.mkdir()
        try:
            (temp_dir / "metadata.json").write_text(
                json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
            )
            (temp_dir / "body.bin").write_bytes(body)
            temp_dir.rename(final_dir)
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            self.send_error(507, "Capture could not be stored")
            return

        jobs.put((final_dir, metadata, body))
        response = json.dumps({"id": capture_id}).encode()
        self.send_response(202)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def __getattr__(self, name):
        if name.startswith("do_"):
            return self.handle_capture
        raise AttributeError(name)

    def log_message(self, format, *args):
        print(f"{self.address_string()} - {format % args}", flush=True)


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=audio_worker, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), Collector)
    server.serve_forever()


if __name__ == "__main__":
    main()
