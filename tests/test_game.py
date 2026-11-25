import unittest

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


if __name__ == "__main__":
    unittest.main()
