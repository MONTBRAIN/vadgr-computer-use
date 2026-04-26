"""Behavioral tests for the macOS platform backend.

These tests run on every platform: the macos module imports Quartz and
mss lazily, and the tests replace those module-level references with
mocks so no real CGEvent ever fires. The mocks expose the pyobjc API
shape (functions, enum constants, return value structs) so the tests
exercise real code paths.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Stubs and fixtures
# ---------------------------------------------------------------------------


def _make_quartz_stub():
    q = MagicMock(name="Quartz")

    # Distinct values so assertions can pin the exact constant used.
    q.kCGHIDEventTap = 100
    q.kCGEventMouseMoved = 5
    q.kCGEventLeftMouseDown = 1
    q.kCGEventLeftMouseUp = 2
    q.kCGEventRightMouseDown = 3
    q.kCGEventRightMouseUp = 4
    q.kCGEventOtherMouseDown = 25
    q.kCGEventOtherMouseUp = 26
    q.kCGEventLeftMouseDragged = 6
    q.kCGMouseButtonLeft = 0
    q.kCGMouseButtonRight = 1
    q.kCGMouseButtonCenter = 2
    q.kCGMouseEventClickState = 1
    q.kCGScrollEventUnitLine = 0
    q.kCGEventFlagMaskShift = 0x20000
    q.kCGEventFlagMaskControl = 0x40000
    q.kCGEventFlagMaskAlternate = 0x80000
    q.kCGEventFlagMaskCommand = 0x100000

    q.CGEventGetLocation.return_value = SimpleNamespace(x=10.0, y=20.0)
    q.CGEventCreate.return_value = MagicMock(name="cur_event")

    bounds = SimpleNamespace(size=SimpleNamespace(width=1470.0, height=956.0))
    q.CGDisplayBounds.return_value = bounds
    q.CGDisplayPixelsWide.return_value = 1470  # macOS 26 returns points here
    q.CGDisplayPixelsHigh.return_value = 956
    q.CGMainDisplayID.return_value = 1
    # Display mode exposes the true physical pixel size.
    q.CGDisplayCopyDisplayMode.return_value = MagicMock(name="display_mode")
    q.CGDisplayModeGetPixelWidth.return_value = 2940
    q.CGDisplayModeGetPixelHeight.return_value = 1912
    q.CGDisplayModeGetWidth.return_value = 1470
    q.CGDisplayModeGetHeight.return_value = 956

    q.CGPreflightScreenCaptureAccess.return_value = True
    q.CGRequestScreenCaptureAccess.return_value = True

    # CGEventCreateMouseEvent / KeyboardEvent / ScrollWheelEvent each return a
    # distinct mock per call so order assertions are unambiguous.
    q.CGEventCreateMouseEvent.side_effect = lambda *a, **kw: MagicMock(name="mev")
    q.CGEventCreateKeyboardEvent.side_effect = lambda *a, **kw: MagicMock(name="kev")
    q.CGEventCreateScrollWheelEvent.side_effect = lambda *a, **kw: MagicMock(name="sev")
    return q


def _make_hiservices_stub(trusted=True):
    h = MagicMock(name="HIServices")
    h.AXIsProcessTrusted.return_value = trusted
    h.AXIsProcessTrustedWithOptions.return_value = trusted
    h.kAXTrustedCheckOptionPrompt = "AXTrustedCheckOptionPrompt"
    return h


def _make_mss_stub(width=1470, height=956):
    mss_mod = MagicMock(name="mss")
    inst = MagicMock(name="mss_instance")
    inst.__enter__.return_value = inst
    inst.__exit__.return_value = False
    inst.monitors = [
        {"left": 0, "top": 0, "width": width, "height": height},
        {"left": 0, "top": 0, "width": width, "height": height},
    ]
    shot = SimpleNamespace(
        size=(width, height),
        width=width,
        height=height,
        bgra=b"\x00\x00\x00\xff" * (width * height),
    )
    inst.grab.return_value = shot
    mss_mod.mss = MagicMock(return_value=inst)
    return mss_mod, inst, shot


@pytest.fixture
def quartz():
    return _make_quartz_stub()


@pytest.fixture
def hiservices():
    return _make_hiservices_stub()


@pytest.fixture
def mss_pair():
    return _make_mss_stub()


@pytest.fixture
def macos_mod(quartz, hiservices, mss_pair):
    mss_mod, _inst, _shot = mss_pair
    import computer_use.platform.macos as m
    with patch.object(m, "_Quartz", quartz), \
         patch.object(m, "_HIServices", hiservices), \
         patch.object(m, "_mss", mss_mod):
        yield m


# ---------------------------------------------------------------------------
# MacOSScreenCapture
# ---------------------------------------------------------------------------


class TestMacOSScreenCapture:
    def test_capture_full_returns_png_bytes_with_logical_dimensions(
        self, macos_mod, mss_pair
    ):
        _mod, _inst, shot = mss_pair
        cap = macos_mod.MacOSScreenCapture()
        state = cap.capture_full()

        assert state.width == shot.width
        assert state.height == shot.height

        # Decoded PNG has the same logical dimensions, not Retina pixels.
        from PIL import Image
        import io as _io
        img = Image.open(_io.BytesIO(state.image_bytes))
        assert img.size == (shot.width, shot.height)

    def test_capture_full_uses_primary_monitor(self, macos_mod, mss_pair):
        _mod, inst, _shot = mss_pair
        macos_mod.MacOSScreenCapture().capture_full()
        # mss exposes primary as monitors[1] (monitors[0] is the union).
        inst.grab.assert_called_once_with(inst.monitors[1])

    def test_capture_region_passes_region_dict_to_mss(self, macos_mod, mss_pair):
        _mod, inst, _shot = mss_pair
        from computer_use.core.types import Region
        macos_mod.MacOSScreenCapture().capture_region(Region(11, 22, 33, 44))
        inst.grab.assert_called_once()
        passed = inst.grab.call_args[0][0]
        assert passed == {"left": 11, "top": 22, "width": 33, "height": 44}

    def test_capture_region_returns_state_with_requested_size(
        self, macos_mod, mss_pair
    ):
        _mod, inst, _shot = mss_pair
        # Region returns its own shot so the test pins requested dims.
        small = SimpleNamespace(
            size=(33, 44), width=33, height=44,
            bgra=b"\x00\x00\x00\xff" * (33 * 44),
        )
        inst.grab.return_value = small
        from computer_use.core.types import Region
        state = macos_mod.MacOSScreenCapture().capture_region(Region(0, 0, 33, 44))
        assert state.width == 33
        assert state.height == 44

    def test_get_screen_size_returns_logical_points_from_quartz(
        self, macos_mod, quartz
    ):
        size = macos_mod.MacOSScreenCapture().get_screen_size()
        assert size == (1470, 956)
        quartz.CGDisplayBounds.assert_called_with(quartz.CGMainDisplayID())

    def test_get_scale_factor_is_pixels_over_points(self, macos_mod):
        cap = macos_mod.MacOSScreenCapture()
        # 2940 wide pixels / 1470 logical points = 2.0
        assert cap.get_scale_factor() == pytest.approx(2.0)

    def test_get_scale_factor_returns_one_when_quartz_missing(
        self, macos_mod
    ):
        with patch.object(macos_mod, "_Quartz", None):
            cap = macos_mod.MacOSScreenCapture()
            assert cap.get_scale_factor() == 1.0


# ---------------------------------------------------------------------------
# MacOSActionExecutor: helpers
# ---------------------------------------------------------------------------


def _events_posted(quartz):
    """Return the list of event types posted, in order, by reading the
    first arg passed to each CGEventCreate*Event call (the source) is None
    and the second arg is the event type. Mouse events use CGEventCreateMouseEvent;
    keyboard events use CGEventCreateKeyboardEvent.
    """
    posted = []
    for c in quartz.CGEventCreateMouseEvent.call_args_list:
        # signature: (source, type, location, mouseButton)
        posted.append(("mouse", c.args[1], c.args[2], c.args[3]))
    for c in quartz.CGEventCreateKeyboardEvent.call_args_list:
        # signature: (source, virtualKey, keyDown)
        posted.append(("key", c.args[1], c.args[2]))
    return posted


# ---------------------------------------------------------------------------
# MacOSActionExecutor
# ---------------------------------------------------------------------------


class TestMacOSActionExecutorMouse:
    def test_raw_move_posts_mouse_moved_event_at_target(
        self, macos_mod, quartz
    ):
        ex = macos_mod.MacOSActionExecutor()
        ex._raw_move(123, 456)

        # Find a CGEventCreateMouseEvent with kCGEventMouseMoved at (123,456).
        mouse_calls = quartz.CGEventCreateMouseEvent.call_args_list
        moves = [
            c for c in mouse_calls
            if c.args[1] == quartz.kCGEventMouseMoved and c.args[2] == (123, 456)
        ]
        assert len(moves) >= 1
        # CGEventPost was called with the HID tap.
        post_calls = quartz.CGEventPost.call_args_list
        assert any(c.args[0] == quartz.kCGHIDEventTap for c in post_calls)

    def test_raw_move_updates_internal_tracker(self, macos_mod):
        ex = macos_mod.MacOSActionExecutor()
        ex._raw_move(77, 88)
        assert ex._tracker.get_pos() == (77, 88)

    def test_move_mouse_delegates_to_smooth_move(self, macos_mod):
        ex = macos_mod.MacOSActionExecutor()
        with patch.object(macos_mod, "smooth_move") as mock_sm:
            ex.move_mouse(500, 300)
        mock_sm.assert_called_once()
        args = mock_sm.call_args.args
        assert args[0] == 500
        assert args[1] == 300

    def test_left_click_posts_down_then_up_in_order(self, macos_mod, quartz):
        ex = macos_mod.MacOSActionExecutor()
        with patch.object(macos_mod, "smooth_move"):
            ex.click(100, 200)

        types_in_order = [
            c.args[1] for c in quartz.CGEventCreateMouseEvent.call_args_list
        ]
        # Must contain down then up, in that order.
        i_down = types_in_order.index(quartz.kCGEventLeftMouseDown)
        i_up = types_in_order.index(quartz.kCGEventLeftMouseUp)
        assert i_down < i_up

    def test_right_click_uses_right_button_events(self, macos_mod, quartz):
        ex = macos_mod.MacOSActionExecutor()
        with patch.object(macos_mod, "smooth_move"):
            ex.click(10, 20, button="right")
        types_called = [
            c.args[1] for c in quartz.CGEventCreateMouseEvent.call_args_list
        ]
        assert quartz.kCGEventRightMouseDown in types_called
        assert quartz.kCGEventRightMouseUp in types_called

    def test_middle_click_uses_other_button_events(self, macos_mod, quartz):
        ex = macos_mod.MacOSActionExecutor()
        with patch.object(macos_mod, "smooth_move"):
            ex.click(10, 20, button="middle")
        types_called = [
            c.args[1] for c in quartz.CGEventCreateMouseEvent.call_args_list
        ]
        assert quartz.kCGEventOtherMouseDown in types_called
        assert quartz.kCGEventOtherMouseUp in types_called

    def test_double_click_sets_clickstate_two_on_second_pair(
        self, macos_mod, quartz
    ):
        ex = macos_mod.MacOSActionExecutor()
        with patch.object(macos_mod, "smooth_move"):
            ex.double_click(40, 60)

        # Find the click_state values written via CGEventSetIntegerValueField
        # for kCGMouseEventClickState.
        click_state_values = [
            c.args[2]
            for c in quartz.CGEventSetIntegerValueField.call_args_list
            if c.args[1] == quartz.kCGMouseEventClickState
        ]
        # Two clicks: first with state=1 (twice: down+up), second with state=2.
        assert click_state_values.count(1) >= 2
        assert click_state_values.count(2) >= 2

    def test_drag_posts_down_then_dragged_steps_then_up(
        self, macos_mod, quartz
    ):
        ex = macos_mod.MacOSActionExecutor()
        with patch.object(macos_mod, "smooth_move"):
            ex.drag(100, 100, 400, 400, duration=0.05)

        types_called = [
            c.args[1] for c in quartz.CGEventCreateMouseEvent.call_args_list
        ]
        assert quartz.kCGEventLeftMouseDown in types_called
        assert quartz.kCGEventLeftMouseUp in types_called
        # At least one drag step in between, and it must come between down and up.
        i_down = types_called.index(quartz.kCGEventLeftMouseDown)
        i_up = len(types_called) - 1 - list(reversed(types_called)).index(
            quartz.kCGEventLeftMouseUp
        )
        dragged_indices = [
            i for i, t in enumerate(types_called)
            if t == quartz.kCGEventLeftMouseDragged
        ]
        assert dragged_indices, "drag must emit at least one Dragged event"
        assert all(i_down < i < i_up for i in dragged_indices)

    def test_scroll_creates_line_scroll_event_with_amount(
        self, macos_mod, quartz
    ):
        ex = macos_mod.MacOSActionExecutor()
        ex.scroll(0, 0, 3)
        quartz.CGEventCreateScrollWheelEvent.assert_called_once()
        args = quartz.CGEventCreateScrollWheelEvent.call_args.args
        # (source, units, wheelCount, wheel1, ...)
        assert args[1] == quartz.kCGScrollEventUnitLine
        assert args[2] == 1
        assert args[3] == 3

    def test_scroll_negative_amount_passes_negative_value(
        self, macos_mod, quartz
    ):
        ex = macos_mod.MacOSActionExecutor()
        ex.scroll(0, 0, -5)
        args = quartz.CGEventCreateScrollWheelEvent.call_args.args
        assert args[3] == -5


class TestMacOSActionExecutorKeyboard:
    def test_type_text_posts_one_unicode_pair_per_character(
        self, macos_mod, quartz
    ):
        ex = macos_mod.MacOSActionExecutor()
        ex.type_text("hi")
        # Two characters -> at least 4 keyboard events created (down+up each).
        kb_calls = quartz.CGEventCreateKeyboardEvent.call_args_list
        assert len(kb_calls) >= 4
        # Each character should also have a SetUnicodeString call.
        unistr_calls = quartz.CGEventKeyboardSetUnicodeString.call_args_list
        assert len(unistr_calls) >= 4
        chars_typed = [c.args[2] for c in unistr_calls]
        assert "h" in chars_typed
        assert "i" in chars_typed

    def test_type_text_handles_unicode(self, macos_mod, quartz):
        ex = macos_mod.MacOSActionExecutor()
        ex.type_text("é")
        chars_typed = [
            c.args[2]
            for c in quartz.CGEventKeyboardSetUnicodeString.call_args_list
        ]
        assert "é" in chars_typed

    def test_key_press_enter_posts_keycode_36(self, macos_mod, quartz):
        ex = macos_mod.MacOSActionExecutor()
        ex.key_press(["enter"])
        # First arg of CGEventCreateKeyboardEvent is source, second is keycode.
        keycodes_pressed = [
            c.args[1] for c in quartz.CGEventCreateKeyboardEvent.call_args_list
        ]
        assert 36 in keycodes_pressed

    def test_key_press_ctrl_c_sets_control_flag_and_keycode_c(
        self, macos_mod, quartz
    ):
        ex = macos_mod.MacOSActionExecutor()
        ex.key_press(["ctrl", "c"])

        # Keycode for "c" on standard layout = 8.
        keycodes = [
            c.args[1] for c in quartz.CGEventCreateKeyboardEvent.call_args_list
        ]
        assert 8 in keycodes
        # Flags applied at least once must include Control bit.
        flags_used = [
            c.args[1] for c in quartz.CGEventSetFlags.call_args_list
        ]
        assert any(f & quartz.kCGEventFlagMaskControl for f in flags_used)

    def test_key_press_ctrl_shift_t_includes_both_modifier_bits(
        self, macos_mod, quartz
    ):
        """Regression: previous AppleScript path silently dropped second
        non-modifier in chords. CGEvent flags must combine Ctrl|Shift on t."""
        ex = macos_mod.MacOSActionExecutor()
        ex.key_press(["ctrl", "shift", "t"])

        flags_used = [
            c.args[1] for c in quartz.CGEventSetFlags.call_args_list
        ]
        combined = quartz.kCGEventFlagMaskControl | quartz.kCGEventFlagMaskShift
        assert any((f & combined) == combined for f in flags_used)

    def test_key_press_cmd_shift_a_uses_command_flag(self, macos_mod, quartz):
        ex = macos_mod.MacOSActionExecutor()
        ex.key_press(["cmd", "shift", "a"])
        flags_used = [
            c.args[1] for c in quartz.CGEventSetFlags.call_args_list
        ]
        assert any(f & quartz.kCGEventFlagMaskCommand for f in flags_used)
        assert any(f & quartz.kCGEventFlagMaskShift for f in flags_used)

    def test_key_press_empty_list_is_noop(self, macos_mod, quartz):
        ex = macos_mod.MacOSActionExecutor()
        ex.key_press([])
        quartz.CGEventCreateKeyboardEvent.assert_not_called()


# ---------------------------------------------------------------------------
# MacOSBackend
# ---------------------------------------------------------------------------


class TestMacOSBackendAvailability:
    def test_available_when_darwin_with_quartz_and_mss(self, macos_mod):
        with patch("sys.platform", "darwin"):
            report = macos_mod.MacOSBackend().availability_report()
        assert report.available is True

    def test_unavailable_when_quartz_missing(self, macos_mod):
        with patch("sys.platform", "darwin"), \
             patch.object(macos_mod, "_Quartz", None):
            report = macos_mod.MacOSBackend().availability_report()
        assert report.available is False
        assert any("pyobjc" in m.lower() or "quartz" in m.lower()
                   for m in report.missing)
        assert "pip install" in report.remediation

    def test_unavailable_when_mss_missing(self, macos_mod):
        with patch("sys.platform", "darwin"), \
             patch.object(macos_mod, "_mss", None):
            report = macos_mod.MacOSBackend().availability_report()
        assert report.available is False
        assert "mss" in report.missing

    def test_unavailable_off_darwin(self, macos_mod):
        with patch("sys.platform", "linux"):
            report = macos_mod.MacOSBackend().availability_report()
        assert report.available is False


class TestMacOSBackendPermissionPrompts:
    def test_init_calls_ax_prompt_with_prompt_option_true(
        self, macos_mod, hiservices, quartz
    ):
        hiservices.AXIsProcessTrusted.return_value = False
        quartz.CGPreflightScreenCaptureAccess.return_value = True
        with patch("sys.platform", "darwin"), \
             patch.object(macos_mod.time, "sleep"), \
             patch.object(macos_mod.time, "monotonic",
                          side_effect=[0.0, 100.0]):
            macos_mod.MacOSBackend()
        hiservices.AXIsProcessTrustedWithOptions.assert_called_once()
        opts = hiservices.AXIsProcessTrustedWithOptions.call_args.args[0]
        assert any("Prompt" in str(k) for k in opts.keys())
        assert any(v is True for v in opts.values())

    def test_init_calls_request_screen_capture_access(
        self, macos_mod, quartz, hiservices
    ):
        hiservices.AXIsProcessTrusted.return_value = True
        quartz.CGPreflightScreenCaptureAccess.return_value = False
        with patch("sys.platform", "darwin"), \
             patch.object(macos_mod.subprocess, "run"), \
             patch.object(macos_mod.time, "sleep"):
            macos_mod.MacOSBackend()
        quartz.CGRequestScreenCaptureAccess.assert_called_once()

    def test_init_does_not_prompt_off_darwin(
        self, macos_mod, quartz, hiservices
    ):
        with patch("sys.platform", "linux"):
            macos_mod.MacOSBackend()
        quartz.CGRequestScreenCaptureAccess.assert_not_called()
        hiservices.AXIsProcessTrustedWithOptions.assert_not_called()


class TestMacOSBackendCaching:
    def test_screen_capture_cached(self, macos_mod):
        with patch("sys.platform", "darwin"):
            b = macos_mod.MacOSBackend()
        assert b.get_screen_capture() is b.get_screen_capture()

    def test_action_executor_cached(self, macos_mod):
        with patch("sys.platform", "darwin"):
            b = macos_mod.MacOSBackend()
        assert b.get_action_executor() is b.get_action_executor()


class TestMacOSPermissionStatus:
    def test_returns_grant_flags_on_darwin(
        self, macos_mod, quartz, hiservices
    ):
        hiservices.AXIsProcessTrusted.return_value = True
        quartz.CGPreflightScreenCaptureAccess.return_value = False
        with patch("sys.platform", "darwin"):
            status = macos_mod.macos_permission_status()
        assert status["macos_accessibility_granted"] is True
        assert status["macos_screen_recording_granted"] is False
        assert "python_executable" in status

    def test_returns_empty_off_darwin(self, macos_mod):
        with patch("sys.platform", "linux"):
            assert macos_mod.macos_permission_status() == {}

    def test_returns_empty_when_quartz_missing(self, macos_mod):
        with patch("sys.platform", "darwin"), \
             patch.object(macos_mod, "_Quartz", None):
            assert macos_mod.macos_permission_status() == {}


# ---------------------------------------------------------------------------
# Doctor merges macOS permission status
# ---------------------------------------------------------------------------


class TestRequestPermissionsOrchestration:
    """request_permissions must never fire two TCC dialogs at once.

    macOS shows only one TCC dialog per process at a time, so calling
    AXIsProcessTrustedWithOptions and CGRequestScreenCaptureAccess back to
    back drops the second. The orchestration must serialize them.
    """

    def _open_calls(self, mock_run):
        return [
            c for c in mock_run.call_args_list
            if c.args and isinstance(c.args[0], list)
            and len(c.args[0]) >= 2
            and c.args[0][0] == "open"
        ]

    def test_noop_when_both_granted(self, macos_mod, quartz, hiservices):
        hiservices.AXIsProcessTrusted.return_value = True
        quartz.CGPreflightScreenCaptureAccess.return_value = True
        with patch("sys.platform", "darwin"), \
             patch.object(macos_mod.subprocess, "run") as mock_run, \
             patch.object(macos_mod.time, "sleep"):
            macos_mod.request_permissions()
        hiservices.AXIsProcessTrustedWithOptions.assert_not_called()
        quartz.CGRequestScreenCaptureAccess.assert_not_called()
        assert not self._open_calls(mock_run)

    def test_only_ax_missing_fires_ax_prompt_only(
        self, macos_mod, quartz, hiservices
    ):
        hiservices.AXIsProcessTrusted.return_value = False
        quartz.CGPreflightScreenCaptureAccess.return_value = True
        with patch("sys.platform", "darwin"), \
             patch.object(macos_mod.subprocess, "run") as mock_run, \
             patch.object(macos_mod.time, "sleep"), \
             patch.object(macos_mod.time, "monotonic",
                          side_effect=[0.0, 100.0]):
            macos_mod.request_permissions()
        hiservices.AXIsProcessTrustedWithOptions.assert_called_once()
        quartz.CGRequestScreenCaptureAccess.assert_not_called()
        assert not self._open_calls(mock_run)

    def test_only_sr_missing_fires_sr_path_no_ax_prompt(
        self, macos_mod, quartz, hiservices
    ):
        hiservices.AXIsProcessTrusted.return_value = True
        quartz.CGPreflightScreenCaptureAccess.return_value = False
        with patch("sys.platform", "darwin"), \
             patch.object(macos_mod.subprocess, "run") as mock_run, \
             patch.object(macos_mod.time, "sleep"):
            macos_mod.request_permissions()
        hiservices.AXIsProcessTrustedWithOptions.assert_not_called()
        quartz.CGRequestScreenCaptureAccess.assert_called_once()
        opens = self._open_calls(mock_run)
        assert opens
        assert "Privacy_ScreenCapture" in opens[0].args[0][1]

    def test_both_missing_fires_ax_first_then_waits_then_fires_sr(
        self, macos_mod, quartz, hiservices
    ):
        hiservices.AXIsProcessTrusted.return_value = False
        quartz.CGPreflightScreenCaptureAccess.return_value = False
        events: list[str] = []

        def ax_prompt(_opts):
            events.append("ax_prompt")
            return False

        def sr_prompt():
            events.append("sr_prompt")
            return False

        def opener(args, **kw):
            if args and args[0] == "open":
                events.append("settings_open")
            return MagicMock(returncode=0)

        hiservices.AXIsProcessTrustedWithOptions.side_effect = ax_prompt
        quartz.CGRequestScreenCaptureAccess.side_effect = sr_prompt

        with patch("sys.platform", "darwin"), \
             patch.object(macos_mod.subprocess, "run", side_effect=opener), \
             patch.object(macos_mod.time, "sleep"), \
             patch.object(macos_mod.time, "monotonic",
                          side_effect=[0.0, 100.0]):
            macos_mod.request_permissions()

        assert "ax_prompt" in events
        assert "sr_prompt" in events
        # AX prompt strictly before any SR-side action.
        ax_idx = events.index("ax_prompt")
        assert all(
            events.index(e) > ax_idx for e in events
            if e in ("sr_prompt", "settings_open")
        )

    def test_both_missing_short_circuits_when_ax_grant_detected(
        self, macos_mod, quartz, hiservices
    ):
        """If user grants AX quickly, the SR step fires without waiting
        the full timeout."""
        hiservices.AXIsProcessTrusted.side_effect = [
            False,  # initial check before firing AX
            False,  # poll iteration 1
            True,   # poll iteration 2 -> user granted, break
        ]
        quartz.CGPreflightScreenCaptureAccess.return_value = False

        sleeps: list[float] = []
        with patch("sys.platform", "darwin"), \
             patch.object(macos_mod.subprocess, "run") as _mock_run, \
             patch.object(macos_mod.time, "sleep",
                          side_effect=sleeps.append), \
             patch.object(macos_mod.time, "monotonic",
                          side_effect=[0.0, 1.0, 2.0, 3.0]):
            macos_mod.request_permissions()

        # SR prompt called after AX granted.
        quartz.CGRequestScreenCaptureAccess.assert_called_once()
        # We did NOT exhaust 30s of polling.
        assert sum(sleeps) < 5.0


class TestScreenRecordingPreflight:
    def _settings_open_calls(self, mock_run):
        return [
            c for c in mock_run.call_args_list
            if c.args and isinstance(c.args[0], list)
            and len(c.args[0]) >= 2
            and c.args[0][0] == "open"
        ]

    def test_capture_full_raises_when_screen_recording_revoked(
        self, macos_mod, quartz
    ):
        from computer_use.core.errors import ScreenCaptureError
        quartz.CGPreflightScreenCaptureAccess.return_value = False
        with patch.object(macos_mod.subprocess, "run") as mock_run:
            with pytest.raises(ScreenCaptureError, match="Screen Recording"):
                macos_mod.MacOSScreenCapture().capture_full()
        opens = self._settings_open_calls(mock_run)
        assert opens, "expected Settings deep-link to be opened"
        url = opens[0].args[0][1]
        assert "Privacy_ScreenCapture" in url

    def test_capture_region_raises_when_screen_recording_revoked(
        self, macos_mod, quartz
    ):
        from computer_use.core.errors import ScreenCaptureError
        from computer_use.core.types import Region
        quartz.CGPreflightScreenCaptureAccess.return_value = False
        with patch.object(macos_mod.subprocess, "run"):
            with pytest.raises(ScreenCaptureError):
                macos_mod.MacOSScreenCapture().capture_region(
                    Region(0, 0, 10, 10)
                )

    def test_capture_full_succeeds_when_screen_recording_granted(
        self, macos_mod, quartz
    ):
        quartz.CGPreflightScreenCaptureAccess.return_value = True
        with patch.object(macos_mod.subprocess, "run") as mock_run:
            macos_mod.MacOSScreenCapture().capture_full()
        # No "open" deep-link should fire on the happy path.
        opens = self._settings_open_calls(mock_run)
        assert not opens

    def test_settings_open_failure_does_not_swallow_permission_error(
        self, macos_mod, quartz
    ):
        from computer_use.core.errors import ScreenCaptureError
        quartz.CGPreflightScreenCaptureAccess.return_value = False
        with patch.object(
            macos_mod.subprocess, "run", side_effect=OSError("nope")
        ):
            with pytest.raises(ScreenCaptureError):
                macos_mod.MacOSScreenCapture().capture_full()


class TestAccessibilityPreflight:
    def _settings_open_calls(self, mock_run):
        return [
            c for c in mock_run.call_args_list
            if c.args and isinstance(c.args[0], list)
            and len(c.args[0]) >= 2
            and c.args[0][0] == "open"
        ]

    def _executor(self, macos_mod):
        with patch.object(macos_mod, "smooth_move"):
            return macos_mod.MacOSActionExecutor()

    def test_click_raises_when_accessibility_revoked(
        self, macos_mod, hiservices
    ):
        from computer_use.core.errors import ActionError
        hiservices.AXIsProcessTrusted.return_value = False
        ex = self._executor(macos_mod)
        with patch.object(macos_mod.subprocess, "run") as mock_run, \
             patch.object(macos_mod, "smooth_move"):
            with pytest.raises(ActionError, match="Accessibility"):
                ex.click(10, 20)
        opens = self._settings_open_calls(mock_run)
        assert opens, "expected Settings deep-link to be opened"
        assert "Privacy_Accessibility" in opens[0].args[0][1]

    def test_double_click_raises_when_accessibility_revoked(
        self, macos_mod, hiservices
    ):
        from computer_use.core.errors import ActionError
        hiservices.AXIsProcessTrusted.return_value = False
        ex = self._executor(macos_mod)
        with patch.object(macos_mod.subprocess, "run"), \
             patch.object(macos_mod, "smooth_move"):
            with pytest.raises(ActionError):
                ex.double_click(10, 20)

    def test_move_mouse_raises_when_accessibility_revoked(
        self, macos_mod, hiservices
    ):
        from computer_use.core.errors import ActionError
        hiservices.AXIsProcessTrusted.return_value = False
        ex = self._executor(macos_mod)
        with patch.object(macos_mod.subprocess, "run"), \
             patch.object(macos_mod, "smooth_move"):
            with pytest.raises(ActionError):
                ex.move_mouse(10, 20)

    def test_type_text_raises_when_accessibility_revoked(
        self, macos_mod, hiservices
    ):
        from computer_use.core.errors import ActionError
        hiservices.AXIsProcessTrusted.return_value = False
        ex = self._executor(macos_mod)
        with patch.object(macos_mod.subprocess, "run"):
            with pytest.raises(ActionError):
                ex.type_text("hi")

    def test_key_press_raises_when_accessibility_revoked(
        self, macos_mod, hiservices
    ):
        from computer_use.core.errors import ActionError
        hiservices.AXIsProcessTrusted.return_value = False
        ex = self._executor(macos_mod)
        with patch.object(macos_mod.subprocess, "run"):
            with pytest.raises(ActionError):
                ex.key_press(["enter"])

    def test_scroll_raises_when_accessibility_revoked(
        self, macos_mod, hiservices
    ):
        from computer_use.core.errors import ActionError
        hiservices.AXIsProcessTrusted.return_value = False
        ex = self._executor(macos_mod)
        with patch.object(macos_mod.subprocess, "run"):
            with pytest.raises(ActionError):
                ex.scroll(10, 20, 3)

    def test_drag_raises_when_accessibility_revoked(
        self, macos_mod, hiservices
    ):
        from computer_use.core.errors import ActionError
        hiservices.AXIsProcessTrusted.return_value = False
        ex = self._executor(macos_mod)
        with patch.object(macos_mod.subprocess, "run"), \
             patch.object(macos_mod, "smooth_move"):
            with pytest.raises(ActionError):
                ex.drag(0, 0, 10, 10, duration=0.01)

    def test_click_succeeds_when_accessibility_granted(
        self, macos_mod, hiservices
    ):
        hiservices.AXIsProcessTrusted.return_value = True
        ex = self._executor(macos_mod)
        with patch.object(macos_mod.subprocess, "run") as mock_run, \
             patch.object(macos_mod, "smooth_move"):
            ex.click(10, 20)
        opens = self._settings_open_calls(mock_run)
        assert not opens


class TestDoctorMergesMacOSStatus:
    def test_doctor_includes_macos_fields_on_darwin(self, capsys):
        import json
        from computer_use import mcp_server

        supervisor = MagicMock()
        supervisor.status.return_value = {"daemon_running": False, "port": 19542}

        with patch("sys.platform", "darwin"), \
             patch.object(mcp_server, "_get_supervisor",
                          return_value=supervisor), \
             patch("computer_use.platform.macos.macos_permission_status",
                   return_value={
                       "macos_accessibility_granted": False,
                       "macos_screen_recording_granted": True,
                       "python_executable": "/opt/homebrew/bin/python3.12",
                   }):
            mcp_server._cmd_doctor(MagicMock())

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["macos_accessibility_granted"] is False
        assert parsed["macos_screen_recording_granted"] is True
        assert parsed["python_executable"].endswith("python3.12")
        assert parsed["daemon_running"] is False

    def test_doctor_omits_macos_fields_off_darwin(self, capsys):
        import json
        from computer_use import mcp_server

        supervisor = MagicMock()
        supervisor.status.return_value = {"daemon_running": True}
        with patch("sys.platform", "linux"), \
             patch.object(mcp_server, "_get_supervisor",
                          return_value=supervisor):
            mcp_server._cmd_doctor(MagicMock())

        parsed = json.loads(capsys.readouterr().out)
        assert "macos_accessibility_granted" not in parsed
        assert "macos_screen_recording_granted" not in parsed
