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
        self._commands: queue.Queue[
            tuple[str, queue.SimpleQueue[dict[str, Any] | None]]
        ] = queue.Queue()
        self._action_ready = threading.Semaphore(0)
        self._wave_requested = threading.Semaphore(0)
        self._wave_created = threading.Semaphore(0)
        self._simulation_done = threading.Event()
        self._started = False
        self._closed = False
        self._simulation = threading.Thread(
            target=self._run_simulation, name="simulation", daemon=True
        )
        self._wave_producer = threading.Thread(
            target=self._produce_waves, name="enemy-waves", daemon=True
        )

    def start(self) -> None:
        with self._lock:
            if self._started:
                raise RuntimeError("The game has already started.")
            if self._closed:
                raise RuntimeError("The game has already stopped.")
            self._wave_producer.start()
            self._simulation.start()
            self._started = True

    def submit(self, command: str) -> dict[str, Any]:
        command = command.strip().lower()
        if command not in COMMANDS:
            raise ValueError(f"Unknown command: {command}")
        reply: queue.SimpleQueue[dict[str, Any] | None] = queue.SimpleQueue()
        with self._lock:
            if not self._started or self._closed or self._state.ended:
                raise RuntimeError("The game is not accepting commands.")
            self._commands.put((command, reply))
            self._action_ready.release()

        result = reply.get()
        if result is None:
            raise RuntimeError("The game is not accepting commands.")
        return result

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return asdict(self._state)

    def stop(self) -> None:
        with self._lock:
            if not self._closed:
                self._closed = True
                self._action_ready.release()
            started = self._started
        if started:
            self._simulation.join()
            self._wave_producer.join()

    def _produce_waves(self) -> None:
        while True:
            self._wave_requested.acquire()
            if self._simulation_done.is_set():
                return
            with self._lock:
                self._state.waves += 1
                self._state.enemies += 1
            self._wave_created.release()

    def _run_simulation(self) -> None:
        reply = None
        try:
            while True:
                self._action_ready.acquire()
                with self._lock:
                    if self._closed:
                        return
                    command, reply = self._commands.get_nowait()
                result = self._apply_command(command)
                reply.put(result)
                reply = None
                if result["ended"]:
                    return
        finally:
            with self._lock:
                self._closed = True
            if reply is not None:
                reply.put(None)
            while True:
                try:
                    _, pending_reply = self._commands.get_nowait()
                except queue.Empty:
                    break
                pending_reply.put(None)
            # A turn already in progress can need the wave producer until this point.
            self._simulation_done.set()
            self._wave_requested.release()

    def _apply_command(self, command: str) -> dict[str, Any]:
        with self._lock:
            if command == "quit":
                self._state.ended = True
                return {"message": "Mission abandoned.", **asdict(self._state)}
            next_turn = self._state.turn + 1

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

            return {"message": " ".join(messages), **asdict(state)}


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
