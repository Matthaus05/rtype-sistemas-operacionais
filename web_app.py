"""Serve a browser interface for the threaded Starfighter game."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from flight import FlightController
from game import GameController


WEB_PAGE = Path(__file__).parent / "web" / "index.html"


def create_handler(game: GameController, flight: FlightController) -> type[BaseHTTPRequestHandler]:
    class GameRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == "/":
                try:
                    page = WEB_PAGE.read_bytes()
                except OSError as error:
                    self._send_json(500, {"error": f"Cannot load browser interface: {error}"})
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(page)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(page)
            elif path == "/api/state":
                self._send_json(200, game.snapshot())
            elif path == "/api/flight":
                self._send_json(200, flight.snapshot())
            else:
                self._send_json(404, {"error": "Not found."})

        def do_POST(self) -> None:
            path = urlsplit(self.path).path
            if path == "/api/flight/start":
                try:
                    result = flight.start_mission()
                except RuntimeError as error:
                    self._send_json(409, {"error": str(error)})
                    return
                self._send_json(200, result)
                return

            if path not in {"/api/command", "/api/flight/input"}:
                self._send_json(404, {"error": "Not found."})
                return

            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._send_json(400, {"error": "Invalid Content-Length."})
                return
            if content_length <= 0 or content_length > 4096:
                self._send_json(400, {"error": "Request body must be between 1 and 4096 bytes."})
                return

            try:
                payload = json.loads(self.rfile.read(content_length))
            except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
                self._send_json(400, {"error": "Request body must contain valid JSON."})
                return

            if path == "/api/flight/input":
                try:
                    flight.set_input(payload)
                except ValueError as error:
                    self._send_json(400, {"error": str(error)})
                    return
                except RuntimeError as error:
                    self._send_json(409, {"error": str(error)})
                    return
                self.send_response(204)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return

            if not isinstance(payload, dict) or not isinstance(payload.get("command"), str):
                self._send_json(400, {"error": "A string command is required."})
                return

            try:
                result = game.submit(payload["command"])
            except ValueError as error:
                self._send_json(400, {"error": str(error)})
                return
            except RuntimeError as error:
                self._send_json(409, {"error": str(error)})
                return
            self._send_json(200, result)

        def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
            path = urlsplit(self.path).path
            if (path, code) not in {("/api/flight", 200), ("/api/flight/input", 204)}:
                super().log_request(code, size)

        def _send_json(self, status: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return GameRequestHandler


def create_server(
    game: GameController,
    host: str = "127.0.0.1",
    port: int = 8000,
    *,
    flight: FlightController | None = None,
) -> ThreadingHTTPServer:
    owns_flight = flight is None
    controller = FlightController() if flight is None else flight

    class GameServer(ThreadingHTTPServer):
        def server_close(self) -> None:
            try:
                super().server_close()
            finally:
                if owns_flight:
                    controller.stop()

    server = GameServer((host, port), create_handler(game, controller))
    if owns_flight:
        controller.start()
    return server


def serve() -> None:
    game = GameController()
    server = create_server(game)
    game.start()
    print("Starfighter is running at http://127.0.0.1:8000")
    print("Press Ctrl+C to stop the server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Starfighter.")
    finally:
        server.server_close()
        game.stop()


if __name__ == "__main__":
    serve()
