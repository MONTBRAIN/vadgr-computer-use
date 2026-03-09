# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Platform-agnostic smooth mouse movement using WindMouse + Fitts's Law.

Pure math -- no platform imports. Callers inject their own move primitive
and cursor position getter so this works on any OS.

Extracted from bridge/daemon.py to share across all platforms.
"""

import logging
import math
import os
import random
import time
from collections.abc import Callable

from computer_use.core.spatial_cache import (
    adapted_fitts_duration,
    muscle_memory_windmouse_params,
)

logger = logging.getLogger("computer_use.smooth_move")
_DEBUG = os.environ.get("AGENT_FORGE_DEBUG", "") == "1"

# WindMouse path shape
WIND_GRAVITY = 9.0       # pull toward target (higher = straighter path)
WIND_STRENGTH = 3.0      # random curvature (higher = more wobbly)
WIND_MAX_VEL = 20.0      # max step size in pixels per tick
WIND_HOMING_DIST = 12.0  # distance (px) where homing phase kicks in
WIND_VEL_SCALE = 6.0     # velocity scales as dist / this (lower = faster)

# Fitts's Law timing (seconds)
FITTS_A = 0.05           # base reaction time
FITTS_A_JITTER = 0.01    # gaussian noise on a
FITTS_B = 0.11           # log-distance coefficient
FITTS_B_JITTER = 0.015   # gaussian noise on b
FITTS_MIN_DURATION = 0.07  # floor duration

# Click pauses (seconds)
PRE_CLICK_BASE = 0.03
PRE_CLICK_RAND = 0.05

# Drag trajectory (gentler than free movement)
DRAG_GRAVITY = 7.0
DRAG_WIND = 2.0
DRAG_MAX_VEL = 12.0
PRE_DRAG_BASE = 0.03
PRE_DRAG_RAND = 0.04

_SQRT3 = math.sqrt(3)
_SQRT5 = math.sqrt(5)


def windmouse_path(
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    gravity: float = WIND_GRAVITY,
    wind: float = WIND_STRENGTH,
    max_vel: float = WIND_MAX_VEL,
    homing_dist: float = WIND_HOMING_DIST,
) -> list[tuple[int, int]]:
    """Generate a human-like mouse path using the WindMouse algorithm.

    Models the cursor as a particle with two forces:
    - Gravity: constant pull toward target (ballistic aim)
    - Wind: random perturbation that evolves smoothly (natural curvature)

    Returns list of (x, y) integer pixel coordinates.
    """
    dist = math.hypot(end_x - start_x, end_y - start_y)
    if dist < 2:
        return [(end_x, end_y)]

    # Scale parameters to distance so short moves aren't over-animated
    w = min(wind, dist / 50.0)
    m = min(max_vel, dist / WIND_VEL_SCALE)
    m = max(m, 3.0)

    points = []
    sx, sy = float(start_x), float(start_y)
    cx, cy = start_x, start_y
    vx = vy = wx = wy = 0.0
    cur_max = m

    while True:
        d = math.hypot(end_x - sx, end_y - sy)
        if d < 1:
            break

        w_mag = min(w, d)

        if d >= homing_dist:
            # Ballistic phase: active wind perturbation
            wx = wx / _SQRT3 + (random.random() * 2 - 1) * w_mag / _SQRT5
            wy = wy / _SQRT3 + (random.random() * 2 - 1) * w_mag / _SQRT5
        else:
            # Homing phase: wind decays, speed drops
            wx /= _SQRT3
            wy /= _SQRT3
            if cur_max < 3:
                cur_max = random.random() * 3 + 3
            else:
                cur_max /= _SQRT5

        vx += wx + gravity * (end_x - sx) / d
        vy += wy + gravity * (end_y - sy) / d

        v_mag = math.hypot(vx, vy)
        if v_mag > cur_max:
            v_clip = cur_max / 2 + random.random() * cur_max / 2
            vx = (vx / v_mag) * v_clip
            vy = (vy / v_mag) * v_clip

        sx += vx
        sy += vy
        mx, my = int(round(sx)), int(round(sy))

        if mx != cx or my != cy:
            points.append((mx, my))
            cx, cy = mx, my

    # Ensure we land exactly on target
    if not points or points[-1] != (end_x, end_y):
        points.append((end_x, end_y))

    return points


def fitts_duration(distance: float, target_width: float = 40.0) -> float:
    """Movement duration in seconds based on Fitts's Law with human jitter."""
    if distance < 1:
        return 0.0
    a = FITTS_A + random.gauss(0, FITTS_A_JITTER)
    b = FITTS_B + random.gauss(0, FITTS_B_JITTER)
    return max(FITTS_MIN_DURATION, a + b * math.log2(distance / target_width + 1))


def ease_out_quad(t: float) -> float:
    """Easing function: fast start, decelerating to stop. t in [0, 1]."""
    return t * (2 - t)


def generate_delays(num_points: int, total_duration: float) -> list[float]:
    """Generate per-step sleep durations using easeOutQuad timing.

    Early steps are short (fast movement), later steps are longer (deceleration).
    """
    if num_points <= 1:
        return [total_duration]

    timestamps = []
    for i in range(num_points):
        t = i / (num_points - 1)
        timestamps.append(ease_out_quad(t) * total_duration)

    delays = []
    for i in range(1, len(timestamps)):
        delays.append(max(0.001, timestamps[i] - timestamps[i - 1]))
    return delays


class CursorTracker:
    """Software-based cursor position tracker.

    For platforms without GetCursorPos (e.g. Wayland), tracks the last
    known position set by our own move calls.
    """

    def __init__(self, x: int = 0, y: int = 0):
        self._x = x
        self._y = y

    def get_pos(self) -> tuple[int, int]:
        return self._x, self._y

    def update(self, x: int, y: int) -> None:
        self._x = x
        self._y = y


def smooth_move(
    end_x: int,
    end_y: int,
    get_cursor_pos: Callable[[], tuple[int, int]],
    move_primitive: Callable[[int, int], None],
    hit_count: int = 0,
    target_width: float = 40.0,
) -> None:
    """Move mouse to (end_x, end_y) with human-like WindMouse motion.

    Platform-agnostic: callers inject get_cursor_pos and move_primitive.
    When hit_count > 1, adapts path and timing via muscle memory.
    """
    start_x, start_y = get_cursor_pos()
    distance = math.hypot(end_x - start_x, end_y - start_y)

    if distance < 2:
        return

    # Adapt WindMouse params based on muscle memory
    path_kwargs = {}
    if hit_count > 1:
        path_kwargs = muscle_memory_windmouse_params(hit_count)
    path = windmouse_path(start_x, start_y, end_x, end_y, **path_kwargs)

    base_duration = fitts_duration(distance, target_width)
    duration = base_duration
    if hit_count > 1:
        duration = adapted_fitts_duration(duration, hit_count)

    if _DEBUG:
        logger.debug(
            "hit_count=%d dist=%.0f base=%.3fs final=%.3fs points=%d kwargs=%s",
            hit_count, distance, base_duration, duration, len(path), path_kwargs,
        )
    delays = generate_delays(len(path), duration)

    for i, (px, py) in enumerate(path):
        move_primitive(px, py)
        if i < len(delays):
            time.sleep(delays[i])


def smooth_drag(
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    get_cursor_pos: Callable[[], tuple[int, int]],
    move_primitive: Callable[[int, int], None],
    press_button: Callable[[], None],
    release_button: Callable[[], None],
    duration: float = 0.5,
    hit_count: int = 0,
) -> None:
    """Drag from start to end with human-like movement.

    Callers inject primitives for move, button press, and button release.
    """
    # Move to start position with smooth movement
    smooth_move(start_x, start_y, get_cursor_pos, move_primitive, hit_count=hit_count)
    time.sleep(PRE_DRAG_BASE + random.random() * PRE_DRAG_RAND)

    # Press at start
    press_button()

    # Drag path uses gentler parameters
    path = windmouse_path(
        start_x, start_y, end_x, end_y,
        gravity=DRAG_GRAVITY, wind=DRAG_WIND, max_vel=DRAG_MAX_VEL,
    )
    delays = generate_delays(len(path), duration)

    for i, (px, py) in enumerate(path):
        move_primitive(px, py)
        if i < len(delays):
            time.sleep(delays[i])

    # Release
    release_button()
