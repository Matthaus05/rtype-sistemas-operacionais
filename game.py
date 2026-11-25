"""Terminal space-shooter prototype demonstrating threads and semaphores."""

from __future__ import annotations

import queue
import threading
from dataclasses import asdict, dataclass
from typing import Any


MISSION_TURNS = 18
COMMANDS = {"fire", "shield", "wait", "quit"}


@dataclass
class GameState:
    turn: int = 0
    hull: int = 3
    score: int = 0
    enemies: int = 0
    waves: int = 0
    ended: bool = False
    victory: bool = False


class GameController:
    """Coordinates player commands, the simulation, and enemy-wave production."""

    def __init__(self) -> None:
        self._state = GameState()
        self._lock = threading.Lock()
        self._commands: queue.Queue[str] = queue.Queue()
        self._results: queue.Queue[dict[str, Any]] = queue.Queue()
        self._action_ready = threading.Semaphore(0)
        self._wave_requested = threading.Semaphore(0)
        self._wave_created = threading.Semaphore(0)
        self._stop_requested = threading.Event()
        self._started = False
        self._simulation = threading.Thread(
            target=self._run_simulation, name="simulation", daemon=True
        )
        self._wave_producer = threading.Thread(
            target=self._produce_waves, name="enemy-waves", daemon=True
        )

    def start(self) -> None:
        if self._started:
            raise RuntimeError("The game has already started.")
        self._started = True
        self._wave_producer.start()
        self._simulation.start()

    def submit(self, command: str) -> dict[str, Any]:
        command = command.strip().lower()
        if command not in COMMANDS:
            raise ValueError(f"Unknown command: {command}")
        if not self._started or self._state.ended:
            raise RuntimeError("The game is not accepting commands.")

        self._commands.put(command)
        self._action_ready.release()
        return self._results.get()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return asdict(self._state)

    def stop(self) -> None:
        self._stop_requested.set()
        self._action_ready.release()
        self._wave_requested.release()
        if self._started:
            self._simulation.join(timeout=1)
            self._wave_producer.join(timeout=1)

    def _produce_waves(self) -> None:
        while not self._stop_requested.is_set():
            if not self._wave_requested.acquire(timeout=0.1):
                continue
            if self._stop_requested.is_set():
                break
            with self._lock:
                self._state.waves += 1
                self._state.enemies += 1
            self._wave_created.release()

    def _run_simulation(self) -> None:
        while True:
            self._action_ready.acquire()
            if self._stop_requested.is_set():
                return

            command = self._commands.get()
            if command == "quit":
                with self._lock:
                    self._state.ended = True
                self._results.put({"message": "Mission abandoned.", **self.snapshot()})
                return

            next_turn = self.snapshot()["turn"] + 1
            if (next_turn - 1) % 3 == 0:
                self._wave_requested.release()
                self._wave_created.acquire()

            with self._lock:
                state = self._state
                state.turn = next_turn
                messages: list[str] = []

                if command == "fire":
                    if state.enemies:
                        state.enemies -= 1
                        state.score += 100
                        messages.append("Direct hit! +100 points.")
                    else:
                        messages.append("No target in range.")
                elif command == "shield":
                    messages.append("Shield engaged for this turn.")
                else:
                    messages.append("You hold position.")

                if state.turn % 4 == 0 and state.enemies:
                    state.enemies -= 1
                    if command == "shield":
                        messages.append("The shield absorbed an enemy strike.")
                    else:
                        state.hull -= 1
                        messages.append("Enemy strike! Hull integrity -1.")

                if state.hull <= 0:
                    state.ended = True
                    messages.append("Your ship was destroyed.")
                elif state.turn >= MISSION_TURNS:
                    state.ended = True
                    state.victory = True
                    messages.append("Mission complete! The frontier is safe.")

                result = {"message": " ".join(messages), **asdict(state)}
            self._results.put(result)


def play() -> None:
    controller = GameController()
    controller.start()
    print("STARFIGHTER: FRONTLINE PROTOCOL")
    print("Survive 18 turns. Waves arrive every 3 turns; strikes hit every 4.")
    print("Commands: [f]ire, [s]hield, [w]ait, [q]uit")

    try:
        while not controller.snapshot()["ended"]:
            state = controller.snapshot()
            print(
                f"\nTurn {state['turn']}/{MISSION_TURNS} | Hull: {state['hull']} "
                f"| Enemies: {state['enemies']} | Score: {state['score']}"
            )
            command = input("Your command: ").strip().lower()
            aliases = {"f": "fire", "s": "shield", "w": "wait", "q": "quit"}
            try:
                result = controller.submit(aliases.get(command, command))
            except ValueError:
                print("Choose f, s, w, or q.")
                continue
            print(result["message"])
    except (EOFError, KeyboardInterrupt):
        print("\nMission interrupted.")
    finally:
        controller.stop()

    final = controller.snapshot()
    print(
        f"\nFinal score: {final['score']} | "
        f"Result: {'VICTORY' if final['victory'] else 'MISSION ENDED'}"
    )


if __name__ == "__main__":
    play()
