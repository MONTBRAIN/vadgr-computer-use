"""Tests for the muscle memory spatial cache."""

import time
import tempfile
import os

import pytest

from computer_use.core.spatial_cache import (
    MuscleMemoryCache,
    CacheEntry,
    adapted_fitts_duration,
    muscle_memory_windmouse_params,
    POWER_LAW_FLOOR,
    DECAY_HALF_LIFE,
    DECAY_MIN_CONFIDENCE,
    SPATIAL_RADIUS,
    EMA_ALPHA,
    MAX_ENTRIES,
)


@pytest.fixture
def cache():
    c = MuscleMemoryCache(":memory:")
    yield c
    c.close()


class TestCacheCRUD:
    def test_record_hit_creates_entry(self, cache):
        entry = cache.record_hit("notepad.exe", "File menu", 50, 12, 80, 24)
        assert entry.hit_count == 1
        assert entry.app_name == "notepad.exe"
        assert entry.element_hint == "file menu"  # lowercased

    def test_lookup_exact_match(self, cache):
        cache.record_hit("app.exe", "Save", 100, 200, 60, 20)
        found = cache.lookup("app.exe", "Save")
        assert found is not None
        assert found.hit_count == 1

    def test_hit_count_increments(self, cache):
        cache.record_hit("app.exe", "btn", 10, 20)
        cache.record_hit("app.exe", "btn", 10, 20)
        cache.record_hit("app.exe", "btn", 10, 20)
        found = cache.lookup("app.exe", "btn")
        assert found.hit_count == 3

    def test_ema_position_smoothing(self, cache):
        cache.record_hit("app.exe", "btn", 100, 200, 40, 24)
        cache.record_hit("app.exe", "btn", 110, 210, 40, 24)
        entry = cache.lookup("app.exe", "btn")
        # EMA: 100 + 0.3*(110-100) = 103
        assert abs(entry.x - 103.0) < 0.1
        assert abs(entry.y - 203.0) < 0.1

    def test_case_insensitive_lookup(self, cache):
        cache.record_hit("App.EXE", "File Menu", 50, 12)
        found = cache.lookup("app.exe", "file menu")
        assert found is not None

    def test_miss_returns_none(self, cache):
        assert cache.lookup("nope.exe", "nothing") is None

    def test_record_miss_reduces_confidence(self, cache):
        cache.record_hit("app.exe", "btn", 10, 20)
        cache.record_miss("app.exe", "btn")
        entry = cache.lookup("app.exe", "btn")
        assert entry.confidence == pytest.approx(0.7, abs=0.01)

    def test_multiple_misses_reduce_to_zero(self, cache):
        cache.record_hit("app.exe", "btn", 10, 20)
        for _ in range(5):
            cache.record_miss("app.exe", "btn")
        entry = cache._hot.get(cache._key("app.exe", "btn"))
        assert entry.confidence == pytest.approx(0.0, abs=0.01)

    def test_record_miss_unknown_is_noop(self, cache):
        cache.record_miss("nope.exe", "nothing")  # should not raise


class TestSpatialProximity:
    def test_finds_nearby_target(self, cache):
        cache.record_hit("app.exe", "button A", 100, 200, 40, 24)
        # Look up with coordinates near (100, 200)
        found = cache.lookup("app.exe", "unknown hint", target_x=110, target_y=205)
        assert found is not None
        assert found.element_hint == "button a"

    def test_rejects_far_target(self, cache):
        cache.record_hit("app.exe", "button A", 100, 200, 40, 24)
        # Look up far away
        found = cache.lookup("app.exe", "unknown", target_x=500, target_y=500)
        assert found is None

    def test_different_app_not_matched(self, cache):
        cache.record_hit("app1.exe", "btn", 100, 200, 40, 24)
        found = cache.lookup("app2.exe", "unknown", target_x=100, target_y=200)
        assert found is None


class TestDecayScoring:
    def test_fresh_entry_full_confidence(self, cache):
        cache.record_hit("app.exe", "btn", 10, 20)
        entry = cache.lookup("app.exe", "btn")
        assert entry is not None

    def test_half_life_decay(self, cache):
        cache.record_hit("app.exe", "btn", 10, 20)
        entry = cache._hot[cache._key("app.exe", "btn")]
        # Simulate entry from DECAY_HALF_LIFE seconds ago
        entry.last_hit_ts = time.time() - DECAY_HALF_LIFE
        decayed = cache._apply_decay(entry)
        assert abs(decayed - 0.5) < 0.05  # ~50% after one half-life

    def test_very_old_entry_returns_none(self, cache):
        cache.record_hit("app.exe", "btn", 10, 20)
        entry = cache._hot[cache._key("app.exe", "btn")]
        # 10 half-lives ago -> confidence ~0.001
        entry.last_hit_ts = time.time() - DECAY_HALF_LIFE * 10
        result = cache.lookup("app.exe", "btn")
        assert result is None


class TestPowerLawAdaptation:
    def test_first_hit_returns_base(self):
        assert adapted_fitts_duration(1.0, 0) == 1.0
        assert adapted_fitts_duration(1.0, 1) == 1.0

    def test_monotonically_decreasing(self):
        durations = [adapted_fitts_duration(1.0, n) for n in range(1, 20)]
        for i in range(1, len(durations)):
            assert durations[i] <= durations[i - 1]

    def test_floor_respected(self):
        # Even at very high hit counts, never below floor
        result = adapted_fitts_duration(1.0, 10000)
        assert result >= POWER_LAW_FLOOR * 1.0

    def test_windmouse_empty_for_low_hits(self):
        assert muscle_memory_windmouse_params(0) == {}
        assert muscle_memory_windmouse_params(1) == {}

    def test_windmouse_params_change_with_hits(self):
        params = muscle_memory_windmouse_params(10)
        assert "gravity" in params
        assert "wind" in params
        assert "max_vel" in params
        assert params["gravity"] > 9.0  # higher than default
        assert params["wind"] < 3.0  # lower than default

    def test_windmouse_params_saturate(self):
        p32 = muscle_memory_windmouse_params(32)
        p1000 = muscle_memory_windmouse_params(1000)
        # Should be very close once saturated
        assert abs(p32["gravity"] - p1000["gravity"]) < 2.0


class TestSequenceTracking:
    def test_record_and_predict(self, cache):
        # Simulate: File menu -> Save (3 times), File menu -> Print (1 time)
        for _ in range(3):
            cache.record_hit("app.exe", "Save", 200, 100, prev_hint="File menu")
        cache.record_hit("app.exe", "Print", 200, 150, prev_hint="File menu")

        predicted = cache.predict_next("app.exe", "File menu")
        assert predicted is not None
        assert predicted.element_hint == "save"

    def test_unknown_returns_none(self, cache):
        assert cache.predict_next("app.exe", "nonexistent") is None


class TestEmptyHintAndCoordGuard:
    def test_empty_hint_skips_tier1_goes_to_rtree(self, cache):
        """When element_hint is empty, skip exact match, use R-Tree proximity."""
        cache.record_hit("app.exe", "button A", 100, 200, 40, 24)
        # Lookup with empty hint but nearby coords should find via R-Tree
        found = cache.lookup("app.exe", "", target_x=110, target_y=205)
        assert found is not None
        assert found.element_hint == "button a"

    def test_empty_hint_no_coords_returns_none(self, cache):
        """Empty hint with no coords should return None (no Tier 1, no Tier 2)."""
        cache.record_hit("app.exe", "button A", 100, 200, 40, 24)
        found = cache.lookup("app.exe", "")
        assert found is None

    def test_coords_at_zero_zero_still_work(self, cache):
        """target_x=0, target_y=0 should still trigger R-Tree lookup."""
        cache.record_hit("app.exe", "origin btn", 5, 5, 40, 24)
        found = cache.lookup("app.exe", "unknown", target_x=0, target_y=0)
        assert found is not None
        assert found.element_hint == "origin btn"

    def test_none_coords_skip_rtree(self, cache):
        """When target_x/target_y are None, R-Tree is skipped."""
        cache.record_hit("app.exe", "btn", 100, 200, 40, 24)
        found = cache.lookup("app.exe", "nonexistent")
        assert found is None

    def test_coord_based_entry_records_and_lookups(self, cache):
        """Synthetic coord-based hints like '@100,200' work normally."""
        cache.record_hit("app.exe", "@100,200", 100, 200, 40, 24)
        found = cache.lookup("app.exe", "@100,200")
        assert found is not None
        assert found.hit_count == 1


class TestPersistenceAndEviction:
    def test_stats_reports_counts(self, cache):
        cache.record_hit("app.exe", "a", 10, 20)
        cache.record_hit("app.exe", "b", 30, 40)
        s = cache.stats()
        assert s["total_entries"] == 2
        assert s["hot_entries"] == 2

    def test_close_and_reopen(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.db")
            cache = MuscleMemoryCache(path)
            cache.record_hit("app.exe", "btn", 10, 20)
            cache.record_hit("app.exe", "btn", 10, 20)
            cache.close()

            cache2 = MuscleMemoryCache(path)
            entry = cache2.lookup("app.exe", "btn")
            assert entry is not None
            assert entry.hit_count == 2
            cache2.close()

    def test_eviction_at_capacity(self, cache):
        # Insert MAX_ENTRIES + 10 entries
        for i in range(MAX_ENTRIES + 10):
            cache.record_hit("app.exe", f"btn_{i}", i, i)
        count = cache._conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        assert count <= MAX_ENTRIES
