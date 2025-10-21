import http.server, socketserver, time, threading

last_tick = {"t": time.time()}

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args, **kwargs): pass
    def do_GET(self):
        if self.path != "/healthz":
            self.send_response(404); self.end_headers(); return
        self.send_response(200)
        self.send_header("Content-Type","text/plain")
        self.end_headers()
        self.wfile.write(b"ok\n")

def start_healthz(port=8787):
    httpd = socketserver.TCPServer(("", port), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd

if __name__ == "__main__":
    start_healthz()
    print("[healthz] serving on :8787")
    while True:
        time.sleep(60)
