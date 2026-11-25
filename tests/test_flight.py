import time
import unittest

from flight import STEP, Enemy, FlightController, Pickup, Shot


def controls(**pressed: bool) -> dict[str, bool]:
    released = dict.fromkeys(("up", "down", "left", "right", "fire", "shield"), False)
    return {**released, **pressed}


def defeat_boss(flight: FlightController) -> None:
    mission = flight._mission
    mission.wave = 5
    mission.enemies.append(Enemy(750, 270, 142, 132, "boss", 1, 1, 270, 0))
    mission.shots.append(Shot(750, 270, 24, 6, "normal", 770))
    flight._resolve_collisions()


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
        self.assertEqual(ready["level"], 1)
        self.assertEqual(ready["level_name"], "Órbita da Fronteira")
        self.assertEqual(ready["level_total"], 3)
        self.assertEqual(ready["wave_total"], 5)

        start = self.flight.start_mission()
        state = self.wait_for(lambda s: s["wave"] == 1 and s["enemies"])

        self.assertEqual(state["status"], "playing")
        self.assertGreater(state["distance"], start["distance"])
        self.assertGreater(state["time"], start["time"])
        self.assertIn("spread", [enemy["drop"] for enemy in state["enemies"]])

    def test_next_phase_produces_its_own_first_wave_and_discards_transition_input(self) -> None:
        start = self.flight.start_mission()
        with self.flight._lock:
            defeat_boss(self.flight)
        self.flight.set_input(controls(right=True, fire=True))
        with self.flight._lock:
            self.assertFalse(self.flight._controls["right"])
            self.assertFalse(self.flight._fire_edges)
            self.flight._mission.frame += round(2.8 / STEP)
            self.flight._advance(time.monotonic())

        state = self.wait_for(lambda s: s["level"] == 2 and s["wave"] == 1)
        self.assertEqual(state["level_name"], "Cinturão de Gelo")
        self.assertEqual(state["status"], "playing")
        self.assertLess(state["level_time"], state["time"])
        self.assertEqual(state["player"]["x"], start["player"]["x"])
        self.assertEqual(state["shots"], [])
        self.assertEqual(
            [enemy["kind"] for enemy in state["enemies"]],
            ["scout", "gunner", "scout", "gunner"],
        )
        self.assertEqual(state["enemies"][1]["drop"], "life")

    def test_each_final_wave_spawns_its_own_boss(self) -> None:
        sizes = set()
        hull_values = set()
        attack_patterns = set()
        bosses = (
            ("Nave de Comando", "command"),
            ("Sentinela Glacial", "frost"),
            ("Devastador Rubro", "rift"),
        )
        for phase, (name, style) in enumerate(bosses, start=1):
            with self.subTest(phase=phase):
                self.flight.start_mission()
                with self.flight._lock:
                    mission = self.flight._mission
                    mission.level = phase
                    waves = mission.level_definition.waves
                    mission.wave = len(waves) - 1
                    mission.frame = round(waves[-1][0] / STEP) + 1

                state = self.wait_for(lambda s: any(e["kind"] == "boss" for e in s["enemies"]))
                boss = next(enemy for enemy in state["enemies"] if enemy["kind"] == "boss")
                self.assertEqual(state["level"], phase)
                self.assertEqual(boss["boss_name"], name)
                self.assertEqual(boss["boss_style"], style)
                sizes.add((boss["w"], boss["h"]))
                hull_values.add(boss["max_hull"])

                with self.flight._lock:
                    active_boss = next(enemy for enemy in mission.enemies if enemy.kind == "boss")
                    self.flight._fire_enemy(active_boss)
                    attack_patterns.add(tuple((shot.vx, shot.vy) for shot in mission.enemy_shots))

        self.assertEqual(len(sizes), 3)
        self.assertEqual(len(hull_values), 3)
        self.assertEqual(len(attack_patterns), 3)

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
        with self.flight._lock:
            mission = self.flight._mission
            player = mission.player
            mission.pickups.extend([
                Pickup(player.x, player.y, 24, 24, "plasma"),
                Pickup(player.x, player.y, 24, 24, "plasma"),
                Pickup(player.x, player.y, 24, 24, "charge"),
                Pickup(player.x, player.y, 24, 24, "life"),
            ])
            self.flight._move_pickups()
            mission.pickups.append(Pickup(player.x + 180, player.y, 24, 24, "spread"))
            mission.level = 3
        restarted = self.flight.start_mission()
        state = self.wait_for(lambda s: s["time"] >= 0.1)

        self.assertEqual(restarted["time"], 0)
        self.assertEqual(restarted["level"], 1)
        self.assertEqual(restarted["level_time"], 0)
        self.assertEqual(restarted["wave"], 0)
        self.assertEqual(restarted["distance"], 0)
        self.assertEqual(restarted["score"], 0)
        self.assertEqual(restarted["hull"], restarted["max_hull"])
        self.assertEqual(restarted["max_hull"], 3)
        self.assertEqual(restarted["player"]["weapon"], "standard")
        self.assertEqual(
            restarted["player"]["weapon_levels"],
            {"standard": 1, "spread": 0, "plasma": 0, "charge": 1},
        )
        self.assertEqual(restarted["pickups"], [])
        self.assertEqual(restarted["pickups_collected"], 0)
        self.assertIsNone(restarted["last_pickup"])
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


class FlightUpgradeTests(unittest.TestCase):
    def setUp(self) -> None:
        # Advance individual simulation steps without timing the worker threads.
        self.flight = FlightController()
        self.mission = self.flight._mission
        self.mission.status = "playing"

    def add_pickup(self, kind: str) -> None:
        player = self.mission.player
        self.mission.pickups.append(Pickup(player.x, player.y, 24, 24, kind))

    def collect(self, kind: str) -> None:
        self.add_pickup(kind)
        self.flight._move_pickups()

    def test_enemy_drop_is_created_once_and_can_be_collected(self) -> None:
        player = self.mission.player
        x, y = player.x + 20, player.y
        self.mission.enemies.append(Enemy(x, y, 42, 30, "scout", 1, 1, y, 0, drop="spread"))
        self.mission.shots.extend([Shot(x, y, 24, 6, "normal", 770) for _ in range(2)])

        self.flight._resolve_collisions()
        state = self.flight.snapshot()
        self.assertEqual(state["score"], 100)
        self.assertEqual(state["enemies"], [])
        self.assertEqual(len(state["pickups"]), 1)
        self.assertEqual(state["pickups"][0]["kind"], "spread")
        self.assertEqual((state["pickups"][0]["x"], state["pickups"][0]["y"]), (x, y))

        self.flight._move_pickups()
        state = self.flight.snapshot()
        self.assertEqual(state["pickups"], [])
        self.assertEqual(state["player"]["weapon"], "spread")
        self.assertEqual(state["last_pickup"], "spread")
        self.assertEqual(state["pickups_collected"], 1)

    def test_spread_fires_three_projectiles_in_different_directions(self) -> None:
        self.add_pickup("spread")
        self.flight._move_pickups()
        self.flight._fire_edges.append(True)
        self.flight._move_player()

        self.assertEqual([shot.kind for shot in self.mission.shots], ["spread"] * 3)
        upper, center, lower = sorted(shot.vy for shot in self.mission.shots)
        self.assertLess(upper, 0)
        self.assertEqual(center, 0)
        self.assertGreater(lower, 0)

    def test_plasma_replaces_spread_and_destroys_a_two_hull_enemy_in_one_hit(self) -> None:
        self.add_pickup("spread")
        self.add_pickup("plasma")
        self.flight._move_pickups()
        self.flight._fire_edges.append(True)
        self.flight._move_player()

        state = self.flight.snapshot()
        self.assertEqual(state["player"]["weapon"], "plasma")
        self.assertEqual(state["last_pickup"], "plasma")
        self.assertEqual(state["pickups_collected"], 2)
        self.assertEqual([shot["kind"] for shot in state["shots"]], ["plasma"])
        shot = self.mission.shots[0]
        self.mission.enemies.append(Enemy(shot.x, shot.y, 58, 44, "gunner", 2, 2, shot.y, 0))
        self.flight._resolve_collisions()

        state = self.flight.snapshot()
        self.assertEqual(state["enemies"], [])
        self.assertEqual(state["score"], 200)

    def test_standard_levels_increase_damage_and_preserve_other_weapon_levels(self) -> None:
        self.flight._fire_player()
        first_shot = self.mission.shots.pop()
        self.assertEqual((first_shot.kind, first_shot.tier, first_shot.damage), ("normal", 1, 1))

        for _ in range(2):
            self.collect("plasma")
        self.assertEqual(self.flight.snapshot()["player"]["weapon"], "plasma")

        for tier in (2, 3, 3):
            self.collect("standard")
            self.flight._fire_player()
            shot = self.mission.shots.pop()
            player = self.flight.snapshot()["player"]

            self.assertEqual(player["weapon"], "standard")
            self.assertEqual(player["weapon_levels"]["standard"], tier)
            self.assertEqual(player["weapon_levels"]["plasma"], 2)
            self.assertEqual((shot.kind, shot.tier, shot.damage), ("normal", tier, tier))

    def test_each_spread_level_fires_more_shots(self) -> None:
        for tier, count in ((1, 3), (2, 5), (3, 7), (3, 7)):
            self.collect("spread")
            self.flight._fire_player()
            snapshot = self.flight.snapshot()
            self.assertEqual(snapshot["player"]["weapon_levels"]["spread"], tier)
            self.assertEqual(
                [(shot["kind"], shot["tier"]) for shot in snapshot["shots"]],
                [("spread", tier)] * count,
            )
            self.assertEqual(len({shot.vy for shot in self.mission.shots}), count)
            self.mission.shots.clear()

    def test_plasma_levels_increase_damage_and_projectile_size(self) -> None:
        previous_size = (0, 0)
        for tier in (1, 2, 3):
            self.collect("plasma")
            self.flight._fire_player()
            shot = self.mission.shots.pop()
            player = self.flight.snapshot()["player"]

            self.assertEqual(player["weapon"], "plasma")
            self.assertEqual(player["weapon_levels"]["plasma"], tier)
            self.assertEqual((shot.kind, shot.tier, shot.damage), ("plasma", tier, tier + 1))
            self.assertGreater(shot.w, previous_size[0])
            self.assertGreater(shot.h, previous_size[1])
            previous_size = (shot.w, shot.h)

    def test_charge_levels_increase_damage_without_switching_weapons(self) -> None:
        self.collect("spread")
        for tier, damage in ((1, 8), (2, 11), (3, 14), (3, 14)):
            self.mission.player.charge = 1
            self.flight._fire_edges.append(False)
            self.flight._move_player()
            shot = self.mission.shots.pop()
            player = self.flight.snapshot()["player"]

            self.assertEqual(player["weapon"], "spread")
            self.assertEqual(player["weapon_levels"]["charge"], tier)
            self.assertEqual((shot.kind, shot.tier, shot.damage), ("charged", tier, damage))
            self.collect("charge")

    def test_life_recovers_missing_hull_then_expands_capacity_up_to_five(self) -> None:
        self.mission.hull = 2
        for expected_hull in (3, 4, 5):
            self.add_pickup("life")
            self.flight._move_pickups()
            state = self.flight.snapshot()
            self.assertEqual((state["hull"], state["max_hull"]), (expected_hull, expected_hull))

        self.add_pickup("life")
        self.flight._move_pickups()
        state = self.flight.snapshot()
        self.assertEqual((state["hull"], state["max_hull"]), (5, 5))
        self.assertEqual(state["last_pickup"], "life")
        self.assertEqual(state["pickups_collected"], 3)
        self.assertEqual(len(state["pickups"]), 1)


class FlightCampaignTests(unittest.TestCase):
    def setUp(self) -> None:
        # Advance transitions deterministically without sleeping between frames.
        self.flight = FlightController()
        self.mission = self.flight._mission
        self.mission.status = "playing"

    def finish_transition(self) -> dict:
        for _ in range(round(2.8 / STEP) + 1):
            if self.mission.status != "transition":
                break
            self.flight._advance(time.monotonic())
        return self.flight.snapshot()

    def test_transition_clears_the_field_and_preserves_player_progress(self) -> None:
        self.mission.hull = 3
        self.mission.max_hull = 4
        self.mission.score = 200
        self.mission.player.weapon = "plasma"
        self.mission.player.weapon_levels.update(plasma=2, charge=3)
        self.mission.enemies.append(Enemy(600, 90, 42, 30, "scout", 1, 1, 90, 0))
        self.mission.shots.append(Shot(560, 300, 24, 6, "normal", 770))
        self.mission.enemy_shots.append(Shot(550, 300, 15, 10, "enemy", -280))
        self.mission.pickups.append(Pickup(640, 250, 24, 24, "life"))

        defeat_boss(self.flight)
        transition = self.flight.snapshot()

        self.assertEqual(transition["status"], "transition")
        self.assertEqual(transition["level"], 1)
        self.assertEqual(transition["next_level_name"], "Cinturão de Gelo")
        self.assertAlmostEqual(transition["transition_remaining"], 2.8)
        for collection in ("enemies", "shots", "enemy_shots", "pickups"):
            self.assertEqual(transition[collection], [])

        for _ in range(round(1.4 / STEP)):
            self.flight._advance(time.monotonic())
        midpoint = self.flight.snapshot()
        self.assertEqual(midpoint["status"], "transition")
        self.assertEqual(midpoint["level"], 1)
        self.assertAlmostEqual(midpoint["transition_remaining"], 1.4)

        advanced = self.finish_transition()
        self.assertEqual(advanced["status"], "playing")
        self.assertEqual(advanced["level"], 2)
        self.assertEqual(advanced["wave"], 0)
        self.assertEqual(advanced["level_time"], 0)
        self.assertIsNone(advanced["next_level_name"])
        self.assertEqual(advanced["transition_remaining"], 0)
        self.assertEqual((advanced["hull"], advanced["max_hull"]), (3, 4))
        self.assertGreater(advanced["score"], 200)
        self.assertEqual(advanced["score"], transition["score"])
        self.assertEqual(advanced["player"]["weapon"], "plasma")
        self.assertEqual(
            advanced["player"]["weapon_levels"],
            {"standard": 1, "spread": 0, "plasma": 2, "charge": 3},
        )

    def test_campaign_can_only_be_won_after_defeating_the_third_boss(self) -> None:
        for next_name in ("Cinturão de Gelo", "Fenda Rubra"):
            defeat_boss(self.flight)
            self.assertEqual(self.flight.snapshot()["status"], "transition")
            self.assertEqual(self.finish_transition()["level_name"], next_name)

        defeat_boss(self.flight)
        finished = self.flight.snapshot()
        self.assertEqual(finished["level"], 3)
        self.assertEqual(finished["status"], "won")
        self.assertIsNone(finished["next_level_name"])
        self.assertEqual(finished["transition_remaining"], 0)

    def test_losing_the_last_hull_point_in_the_third_phase_ends_the_campaign(self) -> None:
        self.mission.level = 3
        self.mission.hull = 1
        player = self.mission.player
        self.mission.enemy_shots.append(Shot(player.x, player.y, 15, 10, "enemy", -280))

        self.flight._resolve_collisions()

        state = self.flight.snapshot()
        self.assertEqual(state["level"], 3)
        self.assertEqual(state["hull"], 0)
        self.assertEqual(state["status"], "lost")

    def test_glacial_salvos_aim_up_or_down_as_the_player_moves(self) -> None:
        self.mission.level = 2
        boss = Enemy(810, 270, 116, 156, "boss", 46, 46, 270, 0)

        for y, direction in ((100, -1), (440, 1)):
            with self.subTest(y=y):
                self.mission.player.y = y
                self.flight._fire_enemy(boss)
                self.assertEqual(len(self.mission.enemy_shots), 3)
                self.assertTrue(all(shot.vy * direction > 0 for shot in self.mission.enemy_shots))
                self.mission.enemy_shots.clear()

    def test_rift_boss_alternates_wide_salvos_and_faster_aimed_volleys(self) -> None:
        self.mission.level = 3
        self.mission.player.y = 440
        boss = Enemy(810, 270, 172, 95, "boss", 58, 58, 270, 0)

        self.flight._fire_enemy(boss)
        wide = self.mission.enemy_shots.copy()
        self.mission.enemy_shots.clear()
        self.flight._fire_enemy(boss)
        aimed = self.mission.enemy_shots

        self.assertEqual((len(wide), len(aimed)), (7, 3))
        self.assertTrue(any(shot.vy < 0 for shot in wide))
        self.assertTrue(all(shot.vy > 0 and shot.vx < wide[0].vx for shot in aimed))


if __name__ == "__main__":
    unittest.main()
