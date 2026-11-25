import json
import threading
import time
import unittest
import urllib.error
import urllib.request

from flight import FlightController
from game import GameController
from web_app import create_server


class BrowserInterfaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.game = GameController()
        self.game.start()
        self.addCleanup(self.game.stop)
        self.flight = FlightController()
        self.flight.start()
        self.addCleanup(self.flight.stop)
        self.server = create_server(self.game, port=0, flight=self.flight)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=1)

    def test_homepage_serves_the_playable_interface(self) -> None:
        with urllib.request.urlopen(self.base_url) as response:
            page = response.read().decode("utf-8")

        self.assertEqual(response.status, 200)
        self.assertIn("Starfighter", page)
        self.assertIn("<canvas", page)
        self.assertIn("/api/flight/input", page)

    def test_flight_endpoints_start_a_mission_and_move_the_ship(self) -> None:
        with urllib.request.urlopen(f"{self.base_url}/api/flight", timeout=2) as response:
            self.assertEqual(json.load(response)["status"], "ready")

        request = urllib.request.Request(f"{self.base_url}/api/flight/start", method="POST")
        with urllib.request.urlopen(request, timeout=2) as response:
            started = json.load(response)
        self.assertEqual(started["status"], "playing")

        controls = dict.fromkeys(("up", "down", "left", "right", "fire", "shield"), False)
        controls["right"] = True
        request = self.flight_input(controls)
        with urllib.request.urlopen(request, timeout=2) as response:
            self.assertEqual(response.status, 204)
            self.assertEqual(response.read(), b"")

        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            with urllib.request.urlopen(f"{self.base_url}/api/flight", timeout=2) as response:
                if json.load(response)["player"]["x"] > started["player"]["x"]:
                    return
            time.sleep(0.01)
        self.fail("The ship did not move after sending right input")

    def test_flight_input_rejects_an_incomplete_payload(self) -> None:
        self.flight.start_mission()
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(self.flight_input({"fire": True}), timeout=2)

        self.assertEqual(error.exception.code, 400)
        error.exception.close()

    def flight_input(self, controls: dict[str, bool]) -> urllib.request.Request:
        return urllib.request.Request(
            f"{self.base_url}/api/flight/input",
            data=json.dumps(controls).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

    def test_state_endpoint_returns_initial_game_state(self) -> None:
        with urllib.request.urlopen(f"{self.base_url}/api/state") as response:
            state = json.load(response)

        self.assertEqual(state["turn"], 0)
        self.assertEqual(state["hull"], 3)

    def test_command_endpoint_advances_the_game(self) -> None:
        request = urllib.request.Request(
            f"{self.base_url}/api/command",
            data=json.dumps({"command": "fire"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            result = json.load(response)

        self.assertEqual(result["turn"], 1)
        self.assertEqual(result["score"], 100)

    def test_invalid_command_returns_bad_request(self) -> None:
        request = urllib.request.Request(
            f"{self.base_url}/api/command",
            data=json.dumps({"command": "warp"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request)

        self.assertEqual(error.exception.code, 400)
        self.assertEqual(self.game.snapshot()["turn"], 0)


if __name__ == "__main__":
    unittest.main()
