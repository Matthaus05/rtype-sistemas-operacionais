import threading
import unittest
from concurrent.futures import Future
from typing import Any
from unittest.mock import patch

from game import GameController


class GameControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.game = GameController()
        self.game.start()

    def tearDown(self) -> None:
        self.game.stop()

    def test_fire_destroys_enemy_and_awards_points(self) -> None:
        result = self.game.submit("fire")

        self.assertEqual(result["turn"], 1)
        self.assertEqual(result["enemies"], 0)
        self.assertEqual(result["score"], 100)

    def test_shield_prevents_damage_during_enemy_strike(self) -> None:
        for command in ("wait", "wait", "wait", "shield"):
            result = self.game.submit(command)

        self.assertEqual(result["turn"], 4)
        self.assertEqual(result["hull"], 3)
        self.assertIn("shield absorbed", result["message"])

    def test_surviving_all_mission_turns_wins(self) -> None:
        for _ in range(18):
            result = self.game.submit("fire")

        self.assertTrue(result["ended"])
        self.assertTrue(result["victory"])

    def test_unknown_command_does_not_advance_the_game(self) -> None:
        with self.assertRaises(ValueError):
            self.game.submit("warp")

        self.assertEqual(self.game.snapshot()["turn"], 0)

    def test_stopped_game_rejects_commands_without_blocking(self) -> None:
        self.game.stop()

        with self.assertRaisesRegex(RuntimeError, "not accepting commands"):
            self._submit_in_background("wait").result(timeout=2)

    def test_quit_releases_a_command_already_in_the_queue(self) -> None:
        quit_started = threading.Event()
        finish_quit = threading.Event()
        wait_queued = threading.Event()
        apply_command = self.game._apply_command
        enqueue = self.game._commands.put

        def delayed_quit(command: str) -> dict[str, Any]:
            quit_started.set()
            finish_quit.wait()
            return apply_command(command)

        def signal_enqueue(item: Any) -> None:
            enqueue(item)
            wait_queued.set()

        with patch.object(self.game, "_apply_command", side_effect=delayed_quit):
            quit_result = self._submit_in_background("quit")
            try:
                self.assertTrue(quit_started.wait(timeout=2))
                with patch.object(self.game._commands, "put", side_effect=signal_enqueue):
                    wait_result = self._submit_in_background("wait")
                    self.assertTrue(wait_queued.wait(timeout=2))
            finally:
                finish_quit.set()
            self.assertTrue(quit_result.result(timeout=2)["ended"])
            with self.assertRaisesRegex(RuntimeError, "not accepting commands"):
                wait_result.result(timeout=2)

    def _submit_in_background(self, command: str) -> Future[dict[str, Any]]:
        response: Future[dict[str, Any]] = Future()

        def submit() -> None:
            try:
                response.set_result(self.game.submit(command))
            except Exception as error:
                response.set_exception(error)

        threading.Thread(target=submit, daemon=True).start()
        return response


if __name__ == "__main__":
    unittest.main()
