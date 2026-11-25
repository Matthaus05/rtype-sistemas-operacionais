"""Threaded simulation for the real-time side-scrolling mission."""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from queue import SimpleQueue


WIDTH, HEIGHT = 960, 540
MAX_HULL = 3
STEP = 1 / 60
INPUT_TIMEOUT = 0.7
CHARGE_TIME = 0.65
CONTROL_NAMES = ("up", "down", "left", "right", "fire", "shield")

# Spawn time, followed by the type and altitude of each enemy in formation.
WAVES = (
    (0.55, (("scout", 135), ("scout", 270), ("scout", 405))),
    (5.8, (("gunner", 145), ("scout", 270), ("gunner", 395))),
    (11.0, (("scout", 100), ("gunner", 210), ("gunner", 330), ("scout", 440))),
    (16.5, (("gunner", 105), ("scout", 205), ("scout", 335), ("gunner", 435))),
    (22.0, (("boss", 270),)),
)


@dataclass
class Body:
    x: float
    y: float
    w: int
    h: int

    def overlaps(self, other: Body) -> bool:
        return (
            abs(self.x - other.x) < (self.w + other.w) / 2
            and abs(self.y - other.y) < (self.h + other.h) / 2
        )

    def position(self) -> dict[str, float | int]:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}


@dataclass
class Player(Body):
    energy: float = 1.0
    shield: bool = False
    charge: float = 0.0
    protected_until: float = 0.0
    fire_after: float = 0.0


@dataclass
class Enemy(Body):
    kind: str
    hull: int
    max_hull: int
    origin_y: float
    fire_after: float


@dataclass
class Shot(Body):
    kind: str
    vx: float
    vy: float = 0.0
    damage: int = 1


@dataclass
class Mission:
    status: str = "ready"
    frame: int = 0
    hull: int = MAX_HULL
    score: int = 0
    wave: int = 0
    player: Player = field(default_factory=lambda: Player(142, HEIGHT / 2, 48, 30))
    enemies: list[Enemy] = field(default_factory=list)
    shots: list[Shot] = field(default_factory=list)
    enemy_shots: list[Shot] = field(default_factory=list)

    @property
    def elapsed(self) -> float:
        return self.frame * STEP

    def snapshot(self) -> dict:
        player = self.player
        return {
            "status": self.status,
            "width": WIDTH,
            "height": HEIGHT,
            "time": self.elapsed,
            "distance": self.elapsed * 120,
            "hull": self.hull,
            "max_hull": MAX_HULL,
            "score": self.score,
            "wave": self.wave,
            "player": {
                **player.position(),
                "shield": player.shield,
                "charge": player.charge,
                "energy": player.energy,
                "invulnerable": self.elapsed < player.protected_until,
            },
            "enemies": [
                {
                    **enemy.position(),
                    "kind": enemy.kind,
                    "hull": enemy.hull,
                    "max_hull": enemy.max_hull,
                }
                for enemy in self.enemies
            ],
            "shots": [{**shot.position(), "kind": shot.kind} for shot in self.shots],
            "enemy_shots": [{**shot.position(), "kind": shot.kind} for shot in self.enemy_shots],
        }


class FlightController:
    """Owns the two workers and keeps input, frame updates and snapshots atomic."""

    def __init__(self) -> None:
        self._mission = Mission()
        self._lock = threading.Lock()
        self._wake = threading.Semaphore(0)
        self._wave_requested = threading.Semaphore(0)
        self._wave_created = threading.Semaphore(0)
        self._wave_requests: SimpleQueue[int] = SimpleQueue()
        self._formations: SimpleQueue[list[Enemy]] = SimpleQueue()
        self._stopping = threading.Event()
        self._started = False
        self._next_update = 0.0
        self._last_input: float | None = None
        self._controls = dict.fromkeys(CONTROL_NAMES, False)
        self._fire_edges: deque[bool] = deque()
        self._simulation = threading.Thread(
            target=self._run_simulation, name="flight-simulation", daemon=True
        )
        self._waves = threading.Thread(
            target=self._produce_waves, name="flight-enemy-waves", daemon=True
        )

    def start(self) -> None:
        with self._lock:
            if self._started or self._stopping.is_set():
                raise RuntimeError("Flight workers cannot be started again.")
            self._started = True
            self._waves.start()
            self._simulation.start()

    def start_mission(self) -> dict:
        with self._lock:
            self._require_running()
            was_playing = self._mission.status == "playing"
            self._mission = Mission(status="playing")
            self._clear_input()
            self._next_update = time.monotonic()
            if not was_playing:
                self._wake.release()
            return self._mission.snapshot()

    def set_input(self, controls: dict[str, bool]) -> None:
        if (
            not isinstance(controls, dict)
            or controls.keys() != set(CONTROL_NAMES)
            or any(type(value) is not bool for value in controls.values())
        ):
            raise ValueError("Expected six boolean controls: up, down, left, right, fire, shield.")

        with self._lock:
            self._require_running()
            if self._mission.status != "playing":
                raise RuntimeError("Start a mission before sending input.")
            # Preserve a quick press and release even if both arrive in one frame.
            if controls["fire"] != self._controls["fire"]:
                self._fire_edges.append(controls["fire"])
            self._controls = controls.copy()
            self._last_input = time.monotonic()

    def snapshot(self) -> dict:
        with self._lock:
            return self._mission.snapshot()

    def stop(self) -> None:
        # The simulation holds this lock while awaiting a formation. The producer
        # always supplies it before shutdown can signal either worker to exit.
        with self._lock:
            if not self._stopping.is_set():
                self._stopping.set()
                self._wake.release()
                self._wave_requested.release()
        if self._started:
            self._simulation.join()
            self._waves.join()

    def _require_running(self) -> None:
        if not self._started or self._stopping.is_set():
            raise RuntimeError("Flight workers are not running.")

    def _clear_input(self) -> None:
        self._controls = dict.fromkeys(CONTROL_NAMES, False)
        self._fire_edges.clear()
        self._last_input = None
        self._mission.player.charge = 0

    def _run_simulation(self) -> None:
        while not self._stopping.is_set():
            with self._lock:
                if self._mission.status == "playing":
                    now = time.monotonic()
                    if now >= self._next_update:
                        self._advance(now)
                        self._next_update += STEP
                        if self._next_update < now - 4 * STEP:
                            self._next_update = now + STEP
                    remaining = max(0, self._next_update - time.monotonic())
                else:
                    remaining = None
            self._wake.acquire(timeout=remaining)

    def _produce_waves(self) -> None:
        dimensions = {"scout": (42, 30, 1), "gunner": (58, 44, 2), "boss": (142, 132, 32)}
        while True:
            self._wave_requested.acquire()
            if self._stopping.is_set():
                return
            start, formation = WAVES[self._wave_requests.get()]
            enemies = []
            for index, (kind, y) in enumerate(formation):
                w, h, hull = dimensions[kind]
                x = WIDTH + w / 2 + 38 * index
                fire_after = start + 1.35 + 0.28 * index
                enemies.append(Enemy(x, y, w, h, kind, hull, hull, y, fire_after))
            self._formations.put(enemies)
            self._wave_created.release()

    def _advance(self, now: float) -> None:
        mission = self._mission
        mission.frame += 1
        if self._last_input is not None and now - self._last_input > INPUT_TIMEOUT:
            self._clear_input()
        if mission.wave < len(WAVES) and mission.elapsed >= WAVES[mission.wave][0]:
            self._wave_requests.put(mission.wave)
            self._wave_requested.release()
            self._wave_created.acquire()
            mission.enemies.extend(self._formations.get())
            mission.wave += 1

        self._move_player()
        self._move_enemies()
        mission.shots = self._move_shots(mission.shots)
        mission.enemy_shots = self._move_shots(mission.enemy_shots)
        self._resolve_collisions()

    def _move_player(self) -> None:
        mission = self._mission
        player = mission.player
        controls = self._controls
        dx = int(controls["right"]) - int(controls["left"])
        dy = int(controls["down"]) - int(controls["up"])
        speed = 340 * STEP / (math.sqrt(2) if dx and dy else 1)
        margin_x, margin_y = player.w / 2 + 8, player.h / 2 + 8
        player.x = min(WIDTH - margin_x, max(margin_x, player.x + dx * speed))
        player.y = min(HEIGHT - margin_y, max(margin_y, player.y + dy * speed))
        player.shield = controls["shield"] and player.energy > 0
        if player.shield:
            player.energy = max(0, player.energy - 0.72 * STEP)
        elif not controls["shield"]:
            player.energy = min(1, player.energy + 0.34 * STEP)

        for pressed in self._fire_edges:
            if pressed and mission.elapsed >= player.fire_after:
                mission.shots.append(Shot(player.x + 27, player.y, 24, 6, "normal", 770))
                player.fire_after = mission.elapsed + 0.13
            elif not pressed:
                if player.charge >= 1:
                    mission.shots.append(
                        Shot(player.x + 32, player.y, 68, 36, "charged", 860, damage=8)
                    )
                player.charge = 0
        self._fire_edges.clear()
        if controls["fire"]:
            player.charge = min(1, player.charge + STEP / CHARGE_TIME)

    def _move_enemies(self) -> None:
        mission = self._mission
        for enemy in mission.enemies:
            if enemy.kind == "boss":
                enemy.x = max(788, enemy.x - 130 * STEP)
                enemy.y = enemy.origin_y + 132 * math.sin((mission.elapsed - WAVES[-1][0]) * 1.3)
            elif enemy.kind == "gunner":
                enemy.x -= 120 * STEP
                enemy.y = enemy.origin_y + 30 * math.sin(enemy.x / 110)
            else:
                enemy.x -= 193 * STEP
                enemy.y = enemy.origin_y + 34 * math.sin(enemy.x / 64)

            if enemy.x < WIDTH - 18 and mission.elapsed >= enemy.fire_after:
                self._fire_enemy(enemy)
        mission.enemies = [enemy for enemy in mission.enemies if enemy.x > -enemy.w / 2]

    def _fire_enemy(self, enemy: Enemy) -> None:
        mission = self._mission
        start_x = enemy.x - enemy.w / 2
        if enemy.kind == "boss":
            for spread in (-145, -72, 0, 72, 145):
                mission.enemy_shots.append(Shot(start_x, enemy.y, 19, 13, "enemy", -335, spread))
            enemy.fire_after = mission.elapsed + 0.86
        else:
            # Aimed gunners and slower, straight scout shots produce distinct patterns.
            vy = 0.0
            if enemy.kind == "gunner":
                vy = max(-170, min(170, (mission.player.y - enemy.y) * 0.53))
            mission.enemy_shots.append(Shot(start_x, enemy.y, 15, 10, "enemy", -285, vy))
            enemy.fire_after = mission.elapsed + (1.8 if enemy.kind == "gunner" else 3.5)

    @staticmethod
    def _move_shots(shots: list[Shot]) -> list[Shot]:
        visible = []
        for shot in shots:
            shot.x += shot.vx * STEP
            shot.y += shot.vy * STEP
            if -shot.w < shot.x < WIDTH + shot.w and -shot.h < shot.y < HEIGHT + shot.h:
                visible.append(shot)
        return visible

    def _resolve_collisions(self) -> None:
        mission = self._mission
        player = mission.player
        missed_shots = []
        boss_destroyed = False
        for shot in mission.shots:
            # A shot that overlaps two targets reaches the leftmost one first.
            target = min(
                (enemy for enemy in mission.enemies if enemy.hull > 0 and shot.overlaps(enemy)),
                key=lambda enemy: enemy.x,
                default=None,
            )
            if target is None:
                missed_shots.append(shot)
                continue
            target.hull -= shot.damage
            if target.hull <= 0:
                mission.score += {"scout": 100, "gunner": 200, "boss": 1200}[target.kind]
                boss_destroyed |= target.kind == "boss"
        mission.shots = missed_shots
        mission.enemies = [enemy for enemy in mission.enemies if enemy.hull > 0]
        if boss_destroyed:
            mission.status = "won"
            mission.enemy_shots.clear()
            mission.enemies.clear()
            return

        contacts = [enemy for enemy in mission.enemies if player.overlaps(enemy)]
        projectiles = [shot for shot in mission.enemy_shots if player.overlaps(shot)]
        if not (contacts or projectiles):
            return
        mission.enemies = [
            enemy for enemy in mission.enemies if enemy.kind == "boss" or not player.overlaps(enemy)
        ]
        mission.enemy_shots = [shot for shot in mission.enemy_shots if not player.overlaps(shot)]
        if not player.shield and mission.elapsed >= player.protected_until:
            mission.hull -= 1
            player.protected_until = mission.elapsed + 1.05
            if mission.hull == 0:
                mission.status = "lost"
