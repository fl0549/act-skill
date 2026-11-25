"""Minimal Chrome DevTools client over adb (stdlib only)."""
import base64, json, os, socket, struct, subprocess, urllib.request
PORT = 9222
def forward(adb="adb"):
    subprocess.run([adb, "forward", f"tcp:{PORT}", "localabstract:chrome_devtools_remote"], capture_output=True)
def tabs():
    return json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list"))
class Tab:
    def __init__(self, ws_url):
        path = ws_url.split(f":{PORT}", 1)[1]
        self.s = socket.create_connection(("127.0.0.1", PORT), timeout=20)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{PORT}\r\nUpgrade: websocket\r\n"
                        f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf: buf += self.s.recv(4096)
        self.buf = buf.split(b"\r\n\r\n", 1)[1]; self.id = 0
    def _send(self, text):
        data = text.encode(); mask = os.urandom(4); n = len(data)
        hdr = b"\x81" + (bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + struct.pack(">H", n) if n < 65536 else bytes([0x80 | 127]) + struct.pack(">Q", n))
        self.s.sendall(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))
    def _read(self, n):
        while len(self.buf) < n: self.buf += self.s.recv(65536)
        out, self.buf = self.buf[:n], self.buf[n:]; return out
    def _recv(self):
        msg = b""
        while True:
            b1, b2 = self._read(2); n = b2 & 0x7F
            if n == 126: n = struct.unpack(">H", self._read(2))[0]
            elif n == 127: n = struct.unpack(">Q", self._read(8))[0]
            msg += self._read(n)
            if b1 & 0x80: return msg.decode()
    def call(self, method, **params):
        self.id += 1; self._send(json.dumps({"id": self.id, "method": method, "params": params}))
        while True:
            r = json.loads(self._recv())
            if r.get("id") == self.id: return r.get("result", r.get("error"))
    def js(self, expr):
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value", r)
