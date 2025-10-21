from __future__ import annotations
import logging, threading, time, json, socket
from http.server import BaseHTTPRequestHandler, HTTPServer

log = logging.getLogger(__name__)

# ---- Global state (idempotent start) ----
_health_srv = None
_metrics_srv = None
_hb_thr = None
_last_hb_ts = 0.0
_start_ts = time.time()
_lock = threading.Lock()

# ---- Heartbeat ----
def _hb_loop(period=60):
    global _last_hb_ts
    while True:
        _last_hb_ts = time.time()
        log.debug("hb:alive ts=%s", _last_hb_ts)
        time.sleep(period)

def start_heartbeat(period: int = 60):
    global _hb_thr
    with _lock:
        if _hb_thr and _hb_thr.is_alive():
            return
        _hb_thr = threading.Thread(target=_hb_loop, kwargs={"period": period}, daemon=True)
        _hb_thr.start()
        log.info("heartbeat: started period=%ss", period)

# ---- Healthz HTTP ----
class _HealthzHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # hiljennä default-logging
        log.debug("healthz: " + fmt, *args)

    def do_GET(self):
        try:
            now = time.time()
            lag = now - (_last_hb_ts or _start_ts)
            payload = {
                "ok": True if lag < 180 else False,
                "ts": int(now),
                "host": socket.gethostname(),
                "lag_seconds": round(lag, 3),
                "msg": "heartbeat" if lag < 180 else "stale",
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200 if payload["ok"] else 503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            log.exception("healthz error: %s", e)
            self.send_response(500); self.end_headers()

def _serve_http(server: HTTPServer, tag: str):
    log.info("%s: serving on %s:%s", tag, *server.server_address)
    try:
        server.serve_forever()
    except Exception as e:
        log.exception("%s stopped: %s", tag, e)

def start_healthz_server(host: str = "0.0.0.0", port: int = 8787):
    global _health_srv
    with _lock:
        if _health_srv:
            return
        _health_srv = HTTPServer((host, port), _HealthzHandler)
        t = threading.Thread(target=_serve_http, args=(_health_srv, "healthz"), daemon=True)
        t.start()
        log.info("healthz: started on %s:%d", host, port)

# ---- Metrics HTTP (kevyt Prometheus-tyylinen tekstitulos) ----
class _MetricsHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        log.debug("metrics: " + fmt, *args)

    def do_GET(self):
        try:
            now = time.time()
            lag = now - (_last_hb_ts or _start_ts)
            lines = []
            lines.append("# HELP bot_uptime_seconds Process uptime in seconds")
            lines.append("# TYPE bot_uptime_seconds gauge")
            lines.append(f"bot_uptime_seconds {int(now - _start_ts)}")
            lines.append("# HELP bot_heartbeat_lag_seconds Seconds since last heartbeat")
            lines.append("# TYPE bot_heartbeat_lag_seconds gauge")
            lines.append(f"bot_heartbeat_lag_seconds {round(lag,3)}")
            body = ("\n".join(lines) + "\n").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            log.exception("metrics error: %s", e)
            self.send_response(500); self.end_headers()

def start_metrics_server(host: str = "0.0.0.0", port: int = 9108):
    global _metrics_srv
    with _lock:
        if _metrics_srv:
            return
        _metrics_srv = HTTPServer((host, port), _MetricsHandler)
        t = threading.Thread(target=_serve_http, args=(_metrics_srv, "metrics"), daemon=True)
        t.start()
        log.info("metrics: started on %s:%d", host, port)
