import time
import unittest

from flight import FlightController


def controls(**pressed: bool) -> dict[str, bool]:
    released = dict.fromkeys(("up", "down", "left", "right", "fire", "shield"), False)
    return {**released, **pressed}


class FlightControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.flight = FlightController()
        self.flight.start()
        self.addCleanup(self.flight.stop)

    def wait_for(self, predicate, *, held=None, timeout=3):
        deadline = time.monotonic() + timeout
        next_input = 0.0
        while True:
            now = time.monotonic()
            state = self.flight.snapshot()
            if predicate(state):
                return state
            if now >= deadline:
                self.fail(f"Flight condition did not occur within {timeout}s: {state}")
            if held is not None and now >= next_input:
                self.flight.set_input(held)
                next_input = now + 0.15
            time.sleep(0.005)

    def test_simulation_scrolls_without_input_and_produces_the_first_wave(self) -> None:
        ready = self.flight.snapshot()
        self.assertEqual(ready["status"], "ready")
        self.assertEqual(ready["wave"], 0)
        self.assertEqual((ready["width"], ready["height"]), (960, 540))

        start = self.flight.start_mission()
        state = self.wait_for(lambda s: s["wave"] == 1 and s["enemies"])

        self.assertEqual(state["status"], "playing")
        self.assertGreater(state["distance"], start["distance"])
        self.assertGreater(state["time"], start["time"])

    def test_player_moves_in_both_axes(self) -> None:
        start = self.flight.start_mission()["player"]
        state = self.wait_for(
            lambda s: s["player"]["x"] > start["x"] and s["player"]["y"] < start["y"],
            held=controls(right=True, up=True),
        )
        self.assertEqual(state["hull"], state["max_hull"])

    def test_fire_press_shoots_and_charged_release_shoots_again(self) -> None:
        self.flight.start_mission()
        fire = controls(fire=True)
        self.wait_for(lambda s: any(shot["kind"] == "normal" for shot in s["shots"]), held=fire)
        self.wait_for(lambda s: s["player"]["charge"] >= 1, held=fire)

        self.flight.set_input(controls())
        state = self.wait_for(lambda s: any(shot["kind"] == "charged" for shot in s["shots"]))

        self.assertEqual(state["player"]["charge"], 0)

    def test_expired_input_releases_the_shield(self) -> None:
        self.flight.start_mission()
        self.flight.set_input(controls(shield=True))
        shield_on = self.wait_for(lambda s: s["player"]["shield"])
        self.assertLess(shield_on["player"]["energy"], 1)
        shield_off = self.wait_for(lambda s: not s["player"]["shield"])
        self.assertGreater(shield_off["player"]["energy"], 0)

    def test_restarting_resets_progress_and_drops_held_input(self) -> None:
        start = self.flight.start_mission()
        self.wait_for(
            lambda s: s["player"]["x"] > start["player"]["x"], held=controls(right=True)
        )
        restarted = self.flight.start_mission()
        state = self.wait_for(lambda s: s["time"] >= 0.1)

        self.assertEqual(restarted["time"], 0)
        self.assertEqual(restarted["distance"], 0)
        self.assertEqual(restarted["score"], 0)
        self.assertEqual(restarted["hull"], restarted["max_hull"])
        self.assertEqual(state["player"]["x"], start["player"]["x"])

    def test_input_requires_a_running_mission_and_full_boolean_controls(self) -> None:
        with self.assertRaises(RuntimeError):
            self.flight.set_input(controls())
        self.flight.start_mission()
        for invalid in ({"up": True}, controls(up=1), controls(warp=True)):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.flight.set_input(invalid)

        self.flight.stop()
        with self.assertRaises(RuntimeError):
            self.flight.set_input(controls())


if __name__ == "__main__":
    unittest.main()
