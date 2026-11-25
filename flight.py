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
BONUS_HULL_LIMIT = 5
PLAYER_START_X = 142
STEP = 1 / 60
INPUT_TIMEOUT = 0.7
CHARGE_TIME = 0.65
MAX_WEAPON_TIER = 3
LEVEL_TRANSITION_FRAMES = round(2.8 / STEP)
RUNNING_STATES = {"playing", "transition"}
CONTROL_NAMES = ("up", "down", "left", "right", "fire", "shield")

Wave = tuple[float, tuple[tuple[str, int], ...]]
SPREAD_PATTERNS = (
    (-155, 0, 155),
    (-230, -115, 0, 115, 230),
    (-300, -200, -100, 0, 100, 200, 300),
)


@dataclass(frozen=True)
class Boss:
    style: str
    name: str
    w: int
    h: int
    hull: int
    interval: float
    spread: tuple[int, ...]


@dataclass(frozen=True)
class Level:
    name: str
    # Spawn time, enemy type and starting altitude.
    waves: tuple[Wave, ...]
    # Keys are the zero-based wave and position within that formation.
    drops: dict[tuple[int, int], str]
    enemy_speed: float
    boss: Boss


LEVELS = (
    Level(
        name="Órbita da Fronteira",
        waves=(
            (0.55, (("scout", 135), ("scout", 270), ("scout", 405))),
            (5.8, (("gunner", 145), ("scout", 270), ("gunner", 395))),
            (11.0, (("scout", 100), ("gunner", 210), ("gunner", 330), ("scout", 440))),
            (16.5, (("gunner", 105), ("scout", 205), ("scout", 335), ("gunner", 435))),
            (22.0, (("boss", 270),)),
        ),
        drops={
            (0, 0): "standard", (0, 1): "spread",
            (1, 0): "plasma", (1, 1): "life", (1, 2): "charge",
            (2, 1): "spread", (2, 2): "plasma",
            (3, 1): "life", (3, 3): "plasma",
        },
        enemy_speed=1.0,
        boss=Boss("command", "Nave de Comando", 142, 132, 32, 0.86, (-145, -72, 0, 72, 145)),
    ),
    Level(
        name="Cinturão de Gelo",
        waves=(
            (0.55, (("scout", 115), ("gunner", 205), ("scout", 320), ("gunner", 420))),
            (5.2, (("scout", 405), ("scout", 315), ("gunner", 230), ("scout", 140))),
            (9.7, (("gunner", 100), ("scout", 265), ("gunner", 410), ("scout", 265))),
            (14.3, (("gunner", 220), ("gunner", 320), ("scout", 95), ("scout", 445))),
            (19.5, (("boss", 270),)),
        ),
        drops={
            (0, 1): "life", (0, 3): "standard", (1, 2): "plasma",
            (2, 1): "spread", (2, 3): "charge", (3, 1): "life",
        },
        enemy_speed=1.12,
        boss=Boss("frost", "Sentinela Glacial", 116, 156, 46, 0.66, (-68, 0, 68)),
    ),
    Level(
        name="Fenda Rubra",
        waves=(
            (0.45, (("gunner", 270), ("scout", 90), ("scout", 450), ("gunner", 270))),
            (4.8, (("gunner", 145), ("gunner", 400), ("scout", 235), ("scout", 310))),
            (9.0, (
                ("scout", 100), ("gunner", 180), ("gunner", 360), ("scout", 440), ("gunner", 270),
            )),
            (13.6, (
                ("gunner", 105), ("scout", 195), ("gunner", 270), ("scout", 345), ("gunner", 435),
            )),
            (19.0, (("boss", 270),)),
        ),
        drops={
            (0, 0): "life", (0, 3): "charge", (1, 1): "spread",
            (2, 2): "life", (2, 4): "standard", (3, 2): "plasma",
        },
        enemy_speed=1.24,
        boss=Boss("rift", "Devastador Rubro", 172, 95, 58, 0.70, (-190, -125, -63, 0, 63, 125, 190)),
    ),
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
    weapon: str = "standard"
    weapon_levels: dict[str, int] = field(
        default_factory=lambda: {"standard": 1, "spread": 0, "plasma": 0, "charge": 1}
    )


@dataclass
class Enemy(Body):
    kind: str
    hull: int
    max_hull: int
    origin_y: float
    fire_after: float
    drop: str | None = None
    volleys: int = 0


@dataclass
class Pickup(Body):
    kind: str


@dataclass
class Shot(Body):
    kind: str
    vx: float
    vy: float = 0.0
    damage: int = 1
    tier: int = 1
    boss_style: str | None = None


@dataclass
class Mission:
    status: str = "ready"
    frame: int = 0
    level: int = 1
    level_start_frame: int = 0
    transition_until: int = 0
    hull: int = MAX_HULL
    max_hull: int = MAX_HULL
    score: int = 0
    wave: int = 0
    player: Player = field(default_factory=lambda: Player(PLAYER_START_X, HEIGHT / 2, 48, 30))
    enemies: list[Enemy] = field(default_factory=list)
    shots: list[Shot] = field(default_factory=list)
    enemy_shots: list[Shot] = field(default_factory=list)
    pickups: list[Pickup] = field(default_factory=list)
    last_pickup: str | None = None
    pickups_collected: int = 0

    @property
    def elapsed(self) -> float:
        return self.frame * STEP

    @property
    def level_elapsed(self) -> float:
        return (self.frame - self.level_start_frame) * STEP

    @property
    def level_definition(self) -> Level:
        return LEVELS[self.level - 1]

    def snapshot(self) -> dict:
        player = self.player
        level = self.level_definition
        return {
            "status": self.status,
            "width": WIDTH,
            "height": HEIGHT,
            "time": self.elapsed,
            "level_time": self.level_elapsed,
            "distance": self.elapsed * 120,
            "hull": self.hull,
            "max_hull": self.max_hull,
            "score": self.score,
            "level": self.level,
            "level_name": level.name,
            "level_total": len(LEVELS),
            "next_level_name": LEVELS[self.level].name if self.status == "transition" else None,
            "transition_remaining": max(0, self.transition_until - self.frame) * STEP,
            "wave": self.wave,
            "wave_total": len(level.waves),
            "last_pickup": self.last_pickup,
            "pickups_collected": self.pickups_collected,
            "player": {
                **player.position(),
                "shield": player.shield,
                "charge": player.charge,
                "energy": player.energy,
                "weapon": player.weapon,
                "weapon_levels": player.weapon_levels.copy(),
                "invulnerable": self.elapsed < player.protected_until,
            },
            "enemies": [
                {
                    **enemy.position(),
                    "kind": enemy.kind,
                    "hull": enemy.hull,
                    "max_hull": enemy.max_hull,
                    "drop": enemy.drop,
                    "boss_style": level.boss.style if enemy.kind == "boss" else None,
                    "boss_name": level.boss.name if enemy.kind == "boss" else None,
                }
                for enemy in self.enemies
            ],
            "shots": [{**shot.position(), "kind": shot.kind, "tier": shot.tier} for shot in self.shots],
            "enemy_shots": [
                {**shot.position(), "kind": shot.kind, "boss_style": shot.boss_style}
                for shot in self.enemy_shots
            ],
            "pickups": [{**pickup.position(), "kind": pickup.kind} for pickup in self.pickups],
        }


class FlightController:
    """Owns the two workers and keeps input, frame updates and snapshots atomic."""

    def __init__(self) -> None:
        self._mission = Mission()
        self._lock = threading.Lock()
        self._wake = threading.Semaphore(0)
        self._wave_requested = threading.Semaphore(0)
        self._wave_created = threading.Semaphore(0)
        self._wave_requests: SimpleQueue[tuple[Level, int, float]] = SimpleQueue()
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
            was_running = self._mission.status in RUNNING_STATES
            self._mission = Mission(status="playing")
            self._clear_input()
            self._next_update = time.monotonic()
            if not was_running:
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
            if self._mission.status == "transition":
                return
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
                if self._mission.status in RUNNING_STATES:
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
        fighters = {"scout": (42, 30, 1), "gunner": (58, 44, 2)}
        while True:
            self._wave_requested.acquire()
            if self._stopping.is_set():
                return
            level, wave_index, level_start = self._wave_requests.get()
            start, formation = level.waves[wave_index]
            stats = {**fighters, "boss": (level.boss.w, level.boss.h, level.boss.hull)}
            enemies = []
            for index, (kind, y) in enumerate(formation):
                w, h, hull = stats[kind]
                x = WIDTH + w / 2 + 38 * index
                fire_after = level_start + start + 1.35 + 0.28 * index
                drop = level.drops.get((wave_index, index))
                enemies.append(Enemy(x, y, w, h, kind, hull, hull, y, fire_after, drop=drop))
            self._formations.put(enemies)
            self._wave_created.release()

    def _advance(self, now: float) -> None:
        mission = self._mission
        mission.frame += 1
        if mission.status == "transition":
            if mission.frame >= mission.transition_until:
                self._start_next_level()
            return

        if self._last_input is not None and now - self._last_input > INPUT_TIMEOUT:
            self._clear_input()
        level = mission.level_definition
        if mission.wave < len(level.waves) and mission.level_elapsed >= level.waves[mission.wave][0]:
            self._wave_requests.put((level, mission.wave, mission.level_start_frame * STEP))
            self._wave_requested.release()
            self._wave_created.acquire()
            mission.enemies.extend(self._formations.get())
            mission.wave += 1

        self._move_player()
        self._move_enemies()
        mission.shots = self._move_shots(mission.shots)
        mission.enemy_shots = self._move_shots(mission.enemy_shots)
        self._move_pickups()
        self._resolve_collisions()

    def _start_next_level(self) -> None:
        mission = self._mission
        mission.level += 1
        mission.level_start_frame = mission.frame
        mission.transition_until = 0
        mission.wave = 0
        mission.status = "playing"
        mission.player.x = PLAYER_START_X
        mission.player.y = HEIGHT / 2
        mission.player.protected_until = mission.elapsed + 1.2

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
                self._fire_player()
                player.fire_after = mission.elapsed + 0.13
            elif not pressed:
                if player.charge >= 1:
                    self._fire_charged()
                player.charge = 0
        self._fire_edges.clear()
        if controls["fire"]:
            player.charge = min(1, player.charge + STEP / CHARGE_TIME)

    def _fire_player(self) -> None:
        mission = self._mission
        player = mission.player
        x, y = player.x + 27, player.y
        tier = max(1, player.weapon_levels[player.weapon])
        bonus = tier - 1
        if player.weapon == "spread":
            for vy in SPREAD_PATTERNS[bonus]:
                mission.shots.append(Shot(x, y, 23 + 2 * bonus, 6, "spread", 750, vy, tier=tier))
        elif player.weapon == "plasma":
            mission.shots.append(Shot(
                x, y, 36 + 8 * bonus, 14 + 4 * bonus, "plasma", 810, damage=2 + bonus, tier=tier,
            ))
        else:
            mission.shots.append(Shot(
                x, y, 24 + 4 * bonus, 6 + 2 * bonus, "normal", 770 + 38 * bonus, damage=tier, tier=tier,
            ))

    def _fire_charged(self) -> None:
        mission = self._mission
        player = mission.player
        tier = player.weapon_levels["charge"]
        bonus = tier - 1
        mission.shots.append(Shot(
            player.x + 32, player.y, 68 + 8 * bonus, 36 + 6 * bonus,
            "charged", 860, damage=8 + 3 * bonus, tier=tier,
        ))

    def _move_enemies(self) -> None:
        mission = self._mission
        level = mission.level_definition
        speed_step = level.enemy_speed * STEP
        for enemy in mission.enemies:
            if enemy.kind == "boss":
                self._move_boss(enemy, level, speed_step)
            elif enemy.kind == "gunner":
                enemy.x -= 120 * speed_step
                enemy.y = enemy.origin_y + 30 * math.sin(enemy.x / 110)
            else:
                enemy.x -= 193 * speed_step
                enemy.y = enemy.origin_y + 34 * math.sin(enemy.x / 64)

            if enemy.x < WIDTH - 18 and mission.elapsed >= enemy.fire_after:
                self._fire_enemy(enemy)
        mission.enemies = [enemy for enemy in mission.enemies if enemy.x > -enemy.w / 2]

    def _move_boss(self, enemy: Enemy, level: Level, speed_step: float) -> None:
        age = self._mission.level_elapsed - level.waves[-1][0]
        if level.boss.style == "frost":
            enemy.x = max(796, enemy.x - 108 * speed_step)
            enemy.y = enemy.origin_y + 108 * math.cos(age)
        elif level.boss.style == "rift":
            enemy.x = max(735 + 62 * math.cos(age * 1.9), enemy.x - 190 * speed_step)
            enemy.y = enemy.origin_y + 92 * math.sin(age * 1.8) + 44 * math.sin(age * 3.2)
        else:
            enemy.x = max(788, enemy.x - 130 * speed_step)
            enemy.y = enemy.origin_y + 132 * math.sin(age * 1.3)

    def _fire_enemy(self, enemy: Enemy) -> None:
        mission = self._mission
        start_x = enemy.x - enemy.w / 2
        if enemy.kind == "boss":
            self._fire_boss(enemy, start_x)
        else:
            # Aimed gunners and slower, straight scout shots produce distinct patterns.
            vy = 0.0
            if enemy.kind == "gunner":
                vy = max(-170, min(170, (mission.player.y - enemy.y) * 0.53))
            mission.enemy_shots.append(Shot(start_x, enemy.y, 15, 10, "enemy", -285, vy))
            enemy.fire_after = mission.elapsed + (1.8 if enemy.kind == "gunner" else 3.5)

    def _fire_boss(self, enemy: Enemy, start_x: float) -> None:
        mission = self._mission
        level = mission.level_definition
        boss = level.boss
        delta_y = mission.player.y - enemy.y
        spread = boss.spread
        speed = -335 * level.enemy_speed
        offset = 0.0
        mount_spacing = 0.0
        w, h = 19, 13
        if boss.style == "frost":
            offset = max(-150, min(150, delta_y * 0.85))
            mount_spacing = enemy.h * 0.14
            w, h = 24, 15
        elif boss.style == "rift" and enemy.volleys % 2:
            offset = max(-145, min(145, delta_y * 0.75))
            spread = (-55, 0, 55)
            speed -= 75
            w, h = 35, 11

        center = (len(spread) - 1) / 2
        for index, vy in enumerate(spread):
            y = enemy.y + (index - center) * mount_spacing
            mission.enemy_shots.append(
                Shot(start_x, y, w, h, "enemy", speed, offset + vy, boss_style=boss.style)
            )
        enemy.volleys += 1
        enemy.fire_after = mission.elapsed + boss.interval

    @staticmethod
    def _move_shots(shots: list[Shot]) -> list[Shot]:
        visible = []
        for shot in shots:
            shot.x += shot.vx * STEP
            shot.y += shot.vy * STEP
            if -shot.w < shot.x < WIDTH + shot.w and -shot.h < shot.y < HEIGHT + shot.h:
                visible.append(shot)
        return visible

    def _move_pickups(self) -> None:
        mission = self._mission
        remaining = []
        for pickup in mission.pickups:
            pickup.x -= 126 * STEP
            can_collect = pickup.kind != "life" or mission.hull < BONUS_HULL_LIMIT
            if can_collect and pickup.overlaps(mission.player):
                if pickup.kind == "life":
                    mission.hull += 1
                    mission.max_hull = max(mission.max_hull, mission.hull)
                else:
                    levels = mission.player.weapon_levels
                    levels[pickup.kind] = min(MAX_WEAPON_TIER, levels[pickup.kind] + 1)
                    if pickup.kind != "charge":
                        mission.player.weapon = pickup.kind
                mission.last_pickup = pickup.kind
                mission.pickups_collected += 1
            elif pickup.x + pickup.w / 2 > 0:
                remaining.append(pickup)
        mission.pickups = remaining

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
                if target.drop:
                    mission.pickups.append(Pickup(target.x, target.y, 26, 26, target.drop))
        mission.shots = missed_shots
        mission.enemies = [enemy for enemy in mission.enemies if enemy.hull > 0]
        if boss_destroyed:
            self._finish_level()
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

    def _finish_level(self) -> None:
        mission = self._mission
        mission.enemies.clear()
        mission.shots.clear()
        mission.enemy_shots.clear()
        mission.pickups.clear()
        mission.player.shield = False
        self._clear_input()
        if mission.level == len(LEVELS):
            mission.status = "won"
        else:
            mission.status = "transition"
            mission.transition_until = mission.frame + LEVEL_TRANSITION_FRAMES
