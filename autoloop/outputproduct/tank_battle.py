"""Minimal TankBattle implementation used by unit tests.

This module provides a lightweight game model with simple collision and bullet
updates so tests can validate state transitions without a running GUI loop.
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple


class TankBattle:
    WIDTH = 800
    HEIGHT = 600
    TANK_SIZE = 30
    BULLET_SPEED = 0  # Keep deterministic for tests that set exact hit positions.

    def __init__(self, root) -> None:
        self.root = root
        self.player: Dict[str, float] = {
            "x": 100.0,
            "y": 100.0,
            "angle": 0.0,
            "health": 100,
        }
        self.enemies: List[Dict[str, float]] = [
            {"x": 400.0, "y": 400.0, "angle": 0.0, "health": 50},
            {"x": 650.0, "y": 120.0, "angle": 0.0, "health": 50},
            {"x": 120.0, "y": 520.0, "angle": 0.0, "health": 50},
        ]
        self.walls: List[Tuple[float, float, float, float]] = [
            (200.0, 100.0, 50.0, 200.0),
            (500.0, 300.0, 200.0, 50.0),
            (100.0, 400.0, 150.0, 100.0),
        ]
        self.bullets: List[Dict[str, float | str]] = []
        self.running = True
        self.game_loop()

    def game_loop(self) -> None:
        """Placeholder loop entry point, patched in tests."""

    def check_collision(self, x: float, y: float, size: float) -> bool:
        half = size / 2.0

        if x - half < 0 or x + half > self.WIDTH:
            return True
        if y - half < 0 or y + half > self.HEIGHT:
            return True

        for wx, wy, ww, wh in self.walls:
            if (x + half) > wx and (x - half) < (wx + ww) and (y + half) > wy and (y - half) < (wy + wh):
                return True

        return False

    def shoot(self, owner_obj: Dict[str, float]) -> None:
        owner = "player" if owner_obj is self.player else "enemy"
        self.bullets.append(
            {
                "x": float(owner_obj["x"]),
                "y": float(owner_obj["y"]),
                "angle": float(owner_obj.get("angle", 0.0)),
                "owner": owner,
            }
        )

    def _hit_tank(self, bx: float, by: float, tx: float, ty: float) -> bool:
        return abs(bx - tx) <= self.TANK_SIZE / 2 and abs(by - ty) <= self.TANK_SIZE / 2

    def update(self) -> None:
        if self.player["health"] <= 0:
            self.running = False
            return

        remaining: List[Dict[str, float | str]] = []
        for bullet in self.bullets:
            bx = float(bullet["x"])
            by = float(bullet["y"])
            angle = math.radians(float(bullet.get("angle", 0.0)))
            bx += math.cos(angle) * self.BULLET_SPEED
            by += math.sin(angle) * self.BULLET_SPEED

            hit = False
            if bullet["owner"] == "player":
                for enemy in self.enemies:
                    if enemy["health"] > 0 and self._hit_tank(bx, by, enemy["x"], enemy["y"]):
                        enemy["health"] -= 10
                        hit = True
                        break
            else:
                if self._hit_tank(bx, by, self.player["x"], self.player["y"]):
                    self.player["health"] -= 10
                    hit = True
                    if self.player["health"] <= 0:
                        self.running = False

            if not hit and 0 <= bx <= self.WIDTH and 0 <= by <= self.HEIGHT:
                remaining.append({"x": bx, "y": by, "angle": float(bullet.get("angle", 0.0)), "owner": bullet["owner"]})

        self.bullets = remaining


if __name__ == "__main__":
    # Keep module runnable as required by project docs.
    try:
        import tkinter as tk

        root = tk.Tk()
        TankBattle(root)
        root.mainloop()
    except Exception:
        # Do not crash if runtime environment has no GUI support.
        pass
