import time
import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

logger = logging.getLogger("MJPEGStreamer")


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Servidor HTTP multihilo para atender streaming a múltiples clientes concurrentes."""
    daemon_threads = True


class StreamServerState:
    def __init__(self):
        self.lock = threading.Lock()
        self.latest_frame = None
        self.fps = 0
        self.last_update = time.time()

    def update_frame(self, frame_bytes: bytes, fps: int = 0):
        with self.lock:
            self.latest_frame = frame_bytes
            self.fps = fps
            self.last_update = time.time()

    def get_frame(self):
        with self.lock:
            return self.latest_frame, self.fps, self.last_update


_state = StreamServerState()


class MJPEGHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Desactivar logs ruidosos de peticiones HTTP por cada frame
        return

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        if self.path == '/video_feed':
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.end_headers()

            try:
                last_sent_time = 0
                while True:
                    frame, fps, last_update = _state.get_frame()
                    if frame is not None and last_update > last_sent_time:
                        last_sent_time = last_update
                        self.wfile.write(b'--frame\r\n')
                        self.wfile.write(b'Content-Type: image/jpeg\r\n')
                        self.wfile.write(f'Content-Length: {len(frame)}\r\n\r\n'.encode('utf-8'))
                        self.wfile.write(frame)
                        self.wfile.write(b'\r\n')
                    time.sleep(0.03)  # ~30 FPS máximo de streaming web
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as e:
                logger.debug(f"Cliente desconectado de streaming: {e}")

        elif self.path == '/status':
            frame, fps, last_update = _state.get_frame()
            is_active = (time.time() - last_update) < 3.0 if frame else False
            payload = json.dumps({
                "status": "online" if is_active else "waiting",
                "fps": fps,
                "has_frame": frame is not None
            }).encode('utf-8')

            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        else:
            self.send_response(404)
            self.end_headers()


def start_stream_server(host: str = "0.0.0.0", port: int = 8088):
    """Inicia el servidor HTTP de streaming MJPEG en un hilo en segundo plano."""
    try:
        server = ThreadedHTTPServer((host, port), MJPEGHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info(f"✓ Servidor de Streaming MJPEG activo en http://{host}:{port}/video_feed")
        return server
    except Exception as e:
        logger.error(f"No se pudo iniciar el servidor de streaming en {host}:{port} ({e})")
        return None


def update_stream_frame(frame_bytes: bytes, fps: int = 0):
    """Actualiza el frame JPEG que se transmite al navegador web."""
    _state.update_frame(frame_bytes, fps)
