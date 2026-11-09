"""Loopback PostgreSQL STARTTLS mock for isolated Docker contract tests only."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import ssl
import threading
import uuid

SENTINEL = 'SYNTHETIC_VERIFIED_TLS_STARTUP'
SERVERS = {}
TLS = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
TLS.load_cert_chain('/fixtures/agent1-cert.pem.fixture', '/fixtures/agent1-key.pem.fixture')


class Database:
    def __init__(self, refuse):
        self.refuse = refuse
        self.observations = {'requests': 0, 'startups': 0}
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen()
        self.listener.settimeout(0.2)
        self.closed = False
        threading.Thread(target=self.accept, daemon=True).start()

    def accept(self):
        while not self.closed:
            try:
                connection, _ = self.listener.accept()
            except (OSError, TimeoutError):
                continue
            threading.Thread(target=self.handle, args=(connection,), daemon=True).start()

    def handle(self, connection):
        try:
            with connection:
                connection.settimeout(3)
                request = b''
                while len(request) < 8:
                    part = connection.recv(8 - len(request))
                    if not part:
                        return
                    request += part
                self.observations['requests'] += 1
                if request != bytes.fromhex('0000000804d2162f'):
                    return
                connection.sendall(b'N' if self.refuse else b'S')
                if self.refuse:
                    startup = connection.recv(4096)
                    if startup[:1] == b'\x16':
                        connection.sendall(bytes.fromhex('15030300020228'))
                        return
                    channel = connection
                else:
                    channel = TLS.wrap_socket(connection, server_side=True)
                    startup = channel.recv(4096)
                if startup:
                    self.observations['startups'] += 1
                    payload = ('SFATAL\0CZX001\0M' + SENTINEL + '\0\0').encode()
                    channel.sendall(b'E' + (len(payload) + 4).to_bytes(4, 'big') + payload)
                if channel is not connection:
                    channel.close()
        except (OSError, ssl.SSLError):
            pass

    def close(self):
        self.closed = True
        self.listener.close()


class Control(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def respond(self, value):
        payload = json.dumps(value).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Connection', 'close')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        self.respond({'ready': True})

    def do_POST(self):
        if self.path.startswith('/close/'):
            database = SERVERS.pop(self.path.split('/')[-1])
            database.close()
            self.respond(database.observations)
            return
        database = Database(self.path == '/refuse')
        key = uuid.uuid4().hex
        SERVERS[key] = database
        self.respond({'id': key, 'port': database.listener.getsockname()[1]})


if __name__ == '__main__':
    ThreadingHTTPServer(('127.0.0.1', 15431), Control).serve_forever()
