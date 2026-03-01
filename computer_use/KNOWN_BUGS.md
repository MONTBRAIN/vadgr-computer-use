# Known Bugs

## Fixed

### 1. screenshot_region clobbers global scale factors
- **Found**: 2026-03-01
- **Impact**: After any `screenshot_region()` call, all subsequent `click()` calls landed at completely wrong positions (e.g., clicking at real pixel 480 instead of scaled 1349)
- **Root cause**: `screenshot_region()` passed its small region image through `_downscale()`, which reset `_scale_x`/`_scale_y` to 1.0 (since region < MAX_WIDTH). All action tools use `_to_real()` which depends on those globals.
- **Fix**: `screenshot_region()` no longer calls `_downscale()` — returns raw region bytes directly
- **Tests**: `TestScreenshotRegionScalePreservation` (5 tests) in `test_mcp_server.py`

### 2. get_screen_size returned real pixels instead of display pixels
- **Found**: 2026-03-01
- **Impact**: Reported 3840x2400 but all tools expected 1366x853 display coordinates. LLM used wrong coordinate space.
- **Root cause**: `get_screen_size()` called `engine.get_screen_size()` which returns real screen dims, but all tools work in downscaled display space.
- **Fix**: Returns display dims computed from `_MAX_WIDTH` (or cached `_display_w`/`_display_h` after first screenshot)
- **Tests**: 3 tests in `TestInfoTools` in `test_mcp_server.py`

## Open

### 3. Text selection is unreliable
- **Found**: 2026-02
- **Symptom**: Selecting text in applications (e.g., click-drag to highlight) is imprecise. The start/end coordinates don't always land at the right character positions.
- **Status**: Not yet investigated deeply

### 4. Vision struggles with small/dense UI elements
- **Found**: 2026-03-01
- **Symptom**: LLM cannot reliably identify individual stickers, small icons, or dense grid items from screenshots. Zooming in via `screenshot_region` helps but adds roundtrips and the region coordinates themselves can be imprecise.
- **Status**: Inherent vision model limitation. Could potentially be improved with better region capture or element-level accessibility data for sticker grids.
