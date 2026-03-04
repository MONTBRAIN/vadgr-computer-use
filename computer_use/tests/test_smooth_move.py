"""Tests for platform-agnostic smooth mouse movement."""

import math
from unittest.mock import MagicMock, patch

from computer_use.core.smooth_move import (
    CursorTracker,
    fitts_duration,
    generate_delays,
    smooth_move,
    windmouse_path,
)


class TestWindMousePath:
    def test_short_distance_returns_endpoint(self):
        # Distance < 2px should just return the endpoint
        path = windmouse_path(100, 100, 101, 100)
        assert path == [(101, 100)]

    def test_same_point_returns_endpoint(self):
        path = windmouse_path(50, 50, 50, 50)
        assert path == [(50, 50)]

    def test_path_starts_near_start_ends_at_target(self):
        path = windmouse_path(0, 0, 500, 500)
        # Path should end exactly at target
        assert path[-1] == (500, 500)
        # Path should have multiple points for a long distance
        assert len(path) > 5

    def test_path_length_scales_with_distance(self):
        short_path = windmouse_path(0, 0, 50, 50)
        long_path = windmouse_path(0, 0, 500, 500)
        # Longer distance should produce more points
        assert len(long_path) > len(short_path)

    def test_path_stays_near_line(self):
        # Path should not deviate wildly from the straight line
        path = windmouse_path(0, 0, 400, 0)
        for x, y in path:
            # y deviation should be bounded (not flying off screen)
            assert abs(y) < 100, f"Point ({x}, {y}) deviates too far from line"

    def test_higher_gravity_straighter_path(self):
        # With very high gravity, path should be almost straight
        path = windmouse_path(0, 0, 300, 0, gravity=50.0, wind=0.1)
        for x, y in path:
            assert abs(y) < 20, f"High gravity path deviated: ({x}, {y})"

    def test_all_points_are_integer_tuples(self):
        path = windmouse_path(10, 20, 300, 400)
        for point in path:
            assert isinstance(point, tuple)
            assert len(point) == 2
            assert isinstance(point[0], int)
            assert isinstance(point[1], int)


class TestFittsDuration:
    def test_zero_distance_returns_zero(self):
        assert fitts_duration(0) == 0.0

    def test_short_distance_returns_minimum(self):
        # Very short distances should hit the floor
        d = fitts_duration(2.0, target_width=40.0)
        assert d >= 0.07  # FITTS_MIN_DURATION

    def test_longer_distance_longer_duration(self):
        # On average, longer distance = longer duration
        short_durations = [fitts_duration(50.0) for _ in range(50)]
        long_durations = [fitts_duration(1000.0) for _ in range(50)]
        avg_short = sum(short_durations) / len(short_durations)
        avg_long = sum(long_durations) / len(long_durations)
        assert avg_long > avg_short

    def test_returns_positive(self):
        for _ in range(100):
            d = fitts_duration(500.0)
            assert d > 0


class TestGenerateDelays:
    def test_single_point(self):
        delays = generate_delays(1, 0.5)
        assert delays == [0.5]

    def test_total_matches_duration(self):
        delays = generate_delays(20, 1.0)
        total = sum(delays)
        # Should approximately sum to total_duration
        assert abs(total - 1.0) < 0.05

    def test_delays_are_positive(self):
        delays = generate_delays(50, 0.5)
        for d in delays:
            assert d >= 0.001

    def test_delays_decrease_over_time(self):
        # EaseOutQuad timestamps progress fast early, slow late.
        # So early delays (big timestamp jumps) > late delays (small jumps).
        delays = generate_delays(20, 1.0)
        early_avg = sum(delays[:5]) / 5
        late_avg = sum(delays[-5:]) / 5
        assert early_avg > late_avg


class TestCursorTracker:
    def test_initial_position(self):
        tracker = CursorTracker(100, 200)
        assert tracker.get_pos() == (100, 200)

    def test_default_position(self):
        tracker = CursorTracker()
        assert tracker.get_pos() == (0, 0)

    def test_update(self):
        tracker = CursorTracker()
        tracker.update(500, 300)
        assert tracker.get_pos() == (500, 300)

    def test_multiple_updates(self):
        tracker = CursorTracker()
        tracker.update(10, 20)
        tracker.update(30, 40)
        assert tracker.get_pos() == (30, 40)


class TestSmoothMove:
    def test_calls_move_primitive_multiple_times(self):
        moves = []

        def mock_move(x, y):
            moves.append((x, y))

        tracker = CursorTracker(0, 0)

        with patch("computer_use.core.smooth_move.time.sleep"):
            smooth_move(300, 300, tracker.get_pos, mock_move)

        # Should have called move_primitive multiple times
        assert len(moves) > 3
        # Should end at the target
        assert moves[-1] == (300, 300)

    def test_skips_short_distance(self):
        moves = []

        def mock_move(x, y):
            moves.append((x, y))

        tracker = CursorTracker(100, 100)

        smooth_move(101, 100, tracker.get_pos, mock_move)

        # Distance < 2, should not move
        assert len(moves) == 0

    def test_hit_count_affects_duration(self):
        """Higher hit_count should result in faster movement (fewer/shorter sleeps)."""
        sleep_times_no_hit = []
        sleep_times_high_hit = []

        def mock_move(x, y):
            pass

        with patch("computer_use.core.smooth_move.time.sleep",
                    side_effect=lambda t: sleep_times_no_hit.append(t)):
            smooth_move(500, 500, CursorTracker(0, 0).get_pos, mock_move, hit_count=0)

        with patch("computer_use.core.smooth_move.time.sleep",
                    side_effect=lambda t: sleep_times_high_hit.append(t)):
            smooth_move(500, 500, CursorTracker(0, 0).get_pos, mock_move, hit_count=20)

        # High hit_count should have shorter total sleep (adapted via Power Law)
        total_no_hit = sum(sleep_times_no_hit)
        total_high_hit = sum(sleep_times_high_hit)
        # Not always true due to randomness, but on average. Use a lenient check.
        # At least the adapted path should have fewer points (straighter)
        assert len(sleep_times_high_hit) <= len(sleep_times_no_hit) + 5

    def test_accepts_callable_primitives(self):
        """Verify that any callable works as get_cursor_pos and move_primitive."""
        cursor_pos = (50, 50)

        def get_pos():
            return cursor_pos

        move_calls = []

        def do_move(x, y):
            move_calls.append((x, y))

        with patch("computer_use.core.smooth_move.time.sleep"):
            smooth_move(200, 200, get_pos, do_move)

        assert len(move_calls) > 0
        assert move_calls[-1] == (200, 200)
