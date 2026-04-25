"""Tests for the Linux platform backend."""

import os
from unittest.mock import MagicMock, patch, mock_open

import pytest

from computer_use.core.errors import ScreenCaptureError

from computer_use.platform.linux import jeepney_import, evdev_import, ecodes

_has_jeepney = jeepney_import is not None
_has_evdev = evdev_import is not None


# -- Display session detection --


class TestIsWayland:
    def test_wayland_display_set(self):
        from computer_use.platform.linux import _is_wayland

        with patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}):
            assert _is_wayland() is True

    def test_xdg_session_type_wayland(self):
        from computer_use.platform.linux import _is_wayland

        env = {"XDG_SESSION_TYPE": "wayland"}
        with patch.dict(os.environ, env, clear=True):
            assert _is_wayland() is True

    def test_x11_session(self):
        from computer_use.platform.linux import _is_wayland

        env = {"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"}
        with patch.dict(os.environ, env, clear=True):
            assert _is_wayland() is False

    def test_no_display_vars(self):
        from computer_use.platform.linux import _is_wayland

        with patch.dict(os.environ, {}, clear=True):
            assert _is_wayland() is False


# -- Screenshot capture factory --


class TestCreateScreenCapture:
    @patch("computer_use.platform.linux._is_wayland", return_value=False)
    def test_x11_returns_mss_capture(self, _mock):
        from computer_use.platform.linux import _create_screen_capture, MssScreenCapture

        mock_mss = MagicMock(spec=MssScreenCapture)
        with patch("computer_use.platform.linux.MssScreenCapture", return_value=mock_mss):
            capture = _create_screen_capture()
        assert capture is mock_mss

    @patch("computer_use.platform.linux._is_wayland", return_value=True)
    @patch("shutil.which", side_effect=lambda cmd: "/usr/bin/grim" if cmd == "grim" else None)
    def test_wayland_prefers_grim_when_it_works(self, _which, _wayland):
        from computer_use.platform.linux import _create_screen_capture, GrimScreenCapture

        with patch.object(GrimScreenCapture, "capture_full"):
            capture = _create_screen_capture()
            assert isinstance(capture, GrimScreenCapture)

    @patch("computer_use.platform.linux._is_wayland", return_value=True)
    @patch("shutil.which", side_effect=lambda cmd: "/usr/bin/gnome-screenshot" if cmd == "gnome-screenshot" else None)
    def test_wayland_falls_back_to_gnome_screenshot(self, _which, _wayland):
        from computer_use.platform.linux import _create_screen_capture, GnomeScreenCapture

        with patch.object(GnomeScreenCapture, "capture_full"):
            capture = _create_screen_capture()
            assert isinstance(capture, GnomeScreenCapture)

    @patch("computer_use.platform.linux._is_wayland", return_value=True)
    @patch("shutil.which", return_value="/usr/bin/grim")
    def test_wayland_skips_broken_tool(self, _which, _wayland):
        """If grim is installed but fails, fall back to gnome-screenshot."""
        from computer_use.platform.linux import (
            _create_screen_capture, GrimScreenCapture, GnomeScreenCapture,
        )

        def which_both(cmd):
            return f"/usr/bin/{cmd}" if cmd in ("grim", "gnome-screenshot") else None

        with (
            patch("shutil.which", side_effect=which_both),
            patch.object(GrimScreenCapture, "capture_full", side_effect=ScreenCaptureError("nope")),
            patch.object(GnomeScreenCapture, "capture_full"),
        ):
            capture = _create_screen_capture()
            assert isinstance(capture, GnomeScreenCapture)

    @patch("computer_use.platform.linux._is_wayland", return_value=True)
    @patch("shutil.which", return_value=None)
    def test_wayland_no_tools_raises(self, _which, _wayland):
        from computer_use.platform.linux import _create_screen_capture

        with pytest.raises(ScreenCaptureError, match="No working Wayland screenshot tool"):
            _create_screen_capture()


# -- Grim capture (wlroots Wayland) --


class TestGrimScreenCapture:
    def _make_capture(self):
        from computer_use.platform.linux import GrimScreenCapture
        return GrimScreenCapture()

    @patch("subprocess.run")
    def test_capture_full_reads_png(self, mock_run):
        fake_png = b"\x89PNG\r\n\x1a\nfake"
        mock_run.return_value = MagicMock(returncode=0, stdout=fake_png, stderr=b"")

        with patch("builtins.open", mock_open(read_data=fake_png)):
            with patch("computer_use.platform.linux.GrimScreenCapture._read_image_size", return_value=(1920, 1080)):
                capture = self._make_capture()
                state = capture.capture_full()

        assert state.width == 1920
        assert state.height == 1080
        assert state.image_bytes == fake_png

    @patch("subprocess.run")
    def test_capture_full_handles_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr=b"grim failed")

        capture = self._make_capture()
        with pytest.raises(ScreenCaptureError, match="grim failed"):
            capture.capture_full()


# -- Gnome screenshot capture --


class TestGnomeScreenCapture:
    def _make_capture(self):
        from computer_use.platform.linux import GnomeScreenCapture
        return GnomeScreenCapture()

    @patch("subprocess.run")
    def test_capture_full_reads_png(self, mock_run):
        fake_png = b"\x89PNG\r\n\x1a\nfake"
        mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")

        with patch("builtins.open", mock_open(read_data=fake_png)):
            with patch("computer_use.platform.linux.GnomeScreenCapture._read_image_size", return_value=(2560, 1440)):
                capture = self._make_capture()
                state = capture.capture_full()

        assert state.width == 2560
        assert state.height == 1440
        assert state.image_bytes == fake_png

    @patch("subprocess.run")
    def test_capture_full_handles_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr=b"cannot capture")

        capture = self._make_capture()
        with pytest.raises(ScreenCaptureError, match="gnome-screenshot failed"):
            capture.capture_full()


# -- Mss capture (X11) --


class TestMssScreenCapture:
    @patch("computer_use.platform.linux.mss_import")
    def test_capture_full(self, mock_mss_mod):
        from computer_use.platform.linux import MssScreenCapture

        fake_screenshot = MagicMock()
        fake_screenshot.width = 1920
        fake_screenshot.height = 1080
        fake_screenshot.size = (1920, 1080)
        fake_screenshot.bgra = b"\x00" * (1920 * 1080 * 4)

        mock_instance = MagicMock()
        mock_instance.monitors = [{}, {"left": 0, "top": 0, "width": 1920, "height": 1080}]
        mock_instance.grab.return_value = fake_screenshot
        mock_mss_mod.mss.return_value = mock_instance

        capture = MssScreenCapture()
        state = capture.capture_full()

        assert state.width == 1920
        assert state.height == 1080
        assert len(state.image_bytes) > 0


# -- Backend integration --


class TestLinuxBackend:
    @patch("computer_use.platform.linux._is_wayland", return_value=False)
    @patch("shutil.which", return_value="/usr/bin/xdotool")
    def test_is_available_with_xdotool_on_x11(self, _which, _wayland):
        from computer_use.platform.linux import LinuxBackend
        assert LinuxBackend().is_available() is True

    @patch("computer_use.platform.linux._is_wayland", return_value=True)
    @patch("computer_use.platform.linux._is_mutter_available", return_value=True)
    @patch("computer_use.platform.linux._wayland_screenshot_tool_available", return_value=True)
    def test_is_available_with_mutter_on_wayland(self, _tool, _mutter, _wayland):
        from computer_use.platform.linux import LinuxBackend
        assert LinuxBackend().is_available() is True

    @patch("computer_use.platform.linux._is_wayland", return_value=False)
    @patch("shutil.which", return_value=None)
    def test_not_available_without_xdotool_on_x11(self, _which, _wayland):
        from computer_use.platform.linux import LinuxBackend
        assert LinuxBackend().is_available() is False

    @patch("computer_use.platform.linux._create_screen_capture")
    def test_get_screen_capture_delegates_to_factory(self, mock_factory):
        from computer_use.platform.linux import LinuxBackend

        mock_capture = MagicMock()
        mock_factory.return_value = mock_capture

        backend = LinuxBackend()
        result = backend.get_screen_capture()
        assert result is mock_capture
        mock_factory.assert_called_once()


# -- Scale factor detection --


class TestScaleFactor:
    def test_reads_gdk_scale(self):
        from computer_use.platform.linux import _get_scale_factor

        with patch.dict(os.environ, {"GDK_SCALE": "2"}):
            assert _get_scale_factor() == 2.0

    def test_defaults_to_one(self):
        with patch.dict(os.environ, {}, clear=True):
            from computer_use.platform.linux import _get_scale_factor
            assert _get_scale_factor() == 1.0

    def test_handles_bad_value(self):
        from computer_use.platform.linux import _get_scale_factor

        with patch.dict(os.environ, {"GDK_SCALE": "not_a_number"}):
            assert _get_scale_factor() == 1.0


# -- Mutter RemoteDesktop executor --


class _SessionCallRecorder:
    """Records calls made via MutterRemoteDesktopExecutor._call.

    Each entry is (method_name, signature, body). Returns canned reply bodies
    keyed by method name; falls back to () for methods without a meaningful reply.
    """

    def __init__(self):
        self.calls: list[tuple[str, str, tuple]] = []
        self._replies = {
            "CreateSession": ("/org/gnome/Mutter/RemoteDesktop/Session/u1",),
            "Get": (("s", "test-session-id"),),
            # ScreenCast.CreateSession (matched by addr -> CreateSession; same key as RD)
            # We disambiguate inside the test by inspecting calls.
            "RecordMonitor": ("/org/gnome/Mutter/ScreenCast/Stream/u1",),
        }
        self._create_session_count = 0

    def __call__(self, addr, method, signature="", body=()):
        self.calls.append((method, signature, body))
        if method == "CreateSession":
            self._create_session_count += 1
            if self._create_session_count == 1:
                return ("/org/gnome/Mutter/RemoteDesktop/Session/u1",)
            return ("/org/gnome/Mutter/ScreenCast/Session/u1",)
        return self._replies.get(method, ())


def _make_mutter_executor():
    """Build a MutterRemoteDesktopExecutor without touching any real DBus
    connection or input device. The recorder captures every _call() invocation
    both during construction and afterwards."""
    from computer_use.platform.linux import MutterRemoteDesktopExecutor

    recorder = _SessionCallRecorder()
    fake_conn = MagicMock()
    with patch("computer_use.platform.linux._build_xkb_char_map", return_value=None), \
         patch("computer_use.platform.linux._open_dbus_connection", return_value=fake_conn), \
         patch.object(MutterRemoteDesktopExecutor, "_call", new=recorder):
        ex = MutterRemoteDesktopExecutor()

    def _call_proxy(addr, method, signature="", body=()):
        return recorder(addr, method, signature, body)
    ex._call = _call_proxy
    return ex, recorder


class TestGetSystemKeyboardLayout:
    def test_reads_us_layout(self):
        from computer_use.platform.linux import _get_system_keyboard_layout

        content = 'XKBMODEL="pc105"\nXKBLAYOUT="us"\nXKBVARIANT=""\n'
        with patch("builtins.open", mock_open(read_data=content)):
            assert _get_system_keyboard_layout() == "us"

    def test_reads_french_layout(self):
        from computer_use.platform.linux import _get_system_keyboard_layout

        content = 'XKBLAYOUT="fr"\n'
        with patch("builtins.open", mock_open(read_data=content)):
            assert _get_system_keyboard_layout() == "fr"

    def test_multi_layout_takes_first(self):
        from computer_use.platform.linux import _get_system_keyboard_layout

        content = 'XKBLAYOUT="us,fr"\n'
        with patch("builtins.open", mock_open(read_data=content)):
            assert _get_system_keyboard_layout() == "us"

    def test_defaults_to_us_on_missing_file(self):
        from computer_use.platform.linux import _get_system_keyboard_layout

        with patch("builtins.open", side_effect=FileNotFoundError):
            assert _get_system_keyboard_layout() == "us"


class TestBuildXkbCharMap:
    def test_returns_map_on_this_system(self):
        from computer_use.platform.linux import _build_xkb_char_map

        char_map = _build_xkb_char_map(layout="us")
        if char_map is None:
            pytest.skip("libxkbcommon not available")
        # Basic letters
        assert char_map["a"].keycode == 30 and not char_map["a"].shift
        assert char_map["z"].keycode == 44 and not char_map["z"].shift
        # Digits
        assert char_map["1"].keycode == 2 and not char_map["1"].shift
        # Shifted symbols
        assert char_map["_"].keycode == 12 and char_map["_"].shift
        assert char_map["("].keycode == 10 and char_map["("].shift

    def test_french_layout_has_altgr(self):
        from computer_use.platform.linux import _build_xkb_char_map

        fr_map = _build_xkb_char_map(layout="fr")
        if fr_map is None:
            pytest.skip("libxkbcommon not available")
        # Euro sign is AltGr+E on French AZERTY
        assert "€" in fr_map
        assert fr_map["€"].altgr

    def test_french_layout_differs(self):
        from computer_use.platform.linux import _build_xkb_char_map

        us_map = _build_xkb_char_map(layout="us")
        fr_map = _build_xkb_char_map(layout="fr")
        if us_map is None or fr_map is None:
            pytest.skip("libxkbcommon not available")
        # On AZERTY, 'a' and 'q' swap physical positions
        assert us_map["a"].keycode != fr_map["a"].keycode
        assert us_map["q"].keycode != fr_map["q"].keycode

    def test_returns_none_without_xkb(self):
        from computer_use.platform import linux

        original = linux._xkb
        try:
            linux._xkb = None
            result = linux._build_xkb_char_map(layout="us")
            assert result is None
        finally:
            linux._xkb = original


@pytest.mark.skipif(not _has_jeepney, reason="jeepney not installed")
class TestMutterRemoteDesktopExecutor:

    @staticmethod
    def _calls_for(recorder, method):
        return [c for c in recorder.calls if c[0] == method]

    def test_setup_creates_two_sessions_and_records_monitor(self):
        ex, rec = _make_mutter_executor()
        names = [c[0] for c in rec.calls]
        assert names.count("CreateSession") == 2  # RemoteDesktop + ScreenCast
        assert "RecordMonitor" in names
        assert "Start" in names
        assert ex._session_path == "/org/gnome/Mutter/RemoteDesktop/Session/u1"
        assert ex._stream_path == "/org/gnome/Mutter/ScreenCast/Stream/u1"

    def test_raw_move_uses_sdd_signature(self):
        ex, rec = _make_mutter_executor()
        rec.calls.clear()
        ex._raw_move(500, 400)
        moves = self._calls_for(rec, "NotifyPointerMotionAbsolute")
        assert len(moves) == 1
        _, sig, body = moves[0]
        assert sig == "sdd"
        assert body == (ex._stream_path, 500.0, 400.0)
        assert ex._tracker.get_pos() == (500, 400)

    def test_click_emits_press_and_release(self):
        ex, rec = _make_mutter_executor()
        rec.calls.clear()
        ex.click(300, 200)
        btns = self._calls_for(rec, "NotifyPointerButton")
        assert len(btns) == 2
        for _, sig, body in btns:
            assert sig == "ib"
        assert btns[0][2][1] is True
        assert btns[1][2][1] is False

    def test_right_click_uses_btn_right_code(self):
        ex, rec = _make_mutter_executor()
        rec.calls.clear()
        ex.click(300, 200, button="right")
        codes = {body[0] for _, _, body in self._calls_for(rec, "NotifyPointerButton")}
        # BTN_RIGHT = 273 in evdev
        assert 273 in codes

    def test_double_click_emits_four_button_events(self):
        ex, rec = _make_mutter_executor()
        rec.calls.clear()
        ex.double_click(300, 200)
        assert len(self._calls_for(rec, "NotifyPointerButton")) == 4

    def test_key_press_emits_paired_keycode_events(self):
        ex, rec = _make_mutter_executor()
        rec.calls.clear()
        ex.key_press(["ctrl", "c"])
        kc = self._calls_for(rec, "NotifyKeyboardKeycode")
        assert len(kc) == 4
        for _, sig, body in kc:
            assert sig == "ub"
        pressed = sum(1 for _, _, body in kc if body[1] is True)
        released = sum(1 for _, _, body in kc if body[1] is False)
        assert pressed == 2 and released == 2

    def test_type_text_two_chars(self):
        ex, rec = _make_mutter_executor()
        rec.calls.clear()
        ex.type_text("ab")
        assert len(self._calls_for(rec, "NotifyKeyboardKeycode")) == 4

    def test_type_text_newline_sends_enter(self):
        ex, rec = _make_mutter_executor()
        rec.calls.clear()
        ex.type_text("a\nb")
        assert len(self._calls_for(rec, "NotifyKeyboardKeycode")) == 6

    def test_type_text_uppercase_uses_shift(self):
        ex, rec = _make_mutter_executor()
        rec.calls.clear()
        ex.type_text("Hi")
        assert len(self._calls_for(rec, "NotifyKeyboardKeycode")) == 6

    def test_type_text_clipboard_fallback_for_unmappable(self):
        ex, rec = _make_mutter_executor()
        with patch("computer_use.platform.linux._clipboard_paste") as mock_paste:
            ex.type_text("\u4e16")
            mock_paste.assert_called_once()
            assert "\u4e16" in mock_paste.call_args[0][0]

    def test_scroll_down_three_steps(self):
        ex, rec = _make_mutter_executor()
        rec.calls.clear()
        ex.scroll(400, 300, -3)
        assert len(self._calls_for(rec, "NotifyPointerAxisDiscrete")) == 3
        axis = self._calls_for(rec, "NotifyPointerAxis")
        assert len(axis) == 4  # 3 step + 1 finish

    def test_scroll_up_uses_negative_pixel_delta(self):
        ex, rec = _make_mutter_executor()
        rec.calls.clear()
        ex.scroll(400, 300, 2)
        discrete = self._calls_for(rec, "NotifyPointerAxisDiscrete")
        assert len(discrete) == 2
        for _, _, body in discrete:
            assert body[1] == -1
        axis = self._calls_for(rec, "NotifyPointerAxis")
        for _, _, body in axis[:-1]:
            assert body[1] < 0

    def test_drag_emits_press_and_release(self):
        ex, rec = _make_mutter_executor()
        rec.calls.clear()
        ex.drag(100, 100, 500, 500, duration=0.1)
        btns = self._calls_for(rec, "NotifyPointerButton")
        assert len(btns) == 2
        assert btns[0][2][1] is True
        assert btns[1][2][1] is False

    def test_close_stops_and_clears_session(self):
        ex, rec = _make_mutter_executor()
        rec.calls.clear()
        ex.close()
        assert any(c[0] == "Stop" for c in rec.calls)
        assert ex._session_path is None
        assert ex._stream_path is None


class TestIsMutterAvailable:
    @patch("computer_use.platform.linux.jeepney_import", None)
    def test_not_available_without_jeepney(self):
        from computer_use.platform.linux import _is_mutter_available
        assert _is_mutter_available() is False

    @patch("computer_use.platform.linux._open_dbus_connection")
    def test_not_available_when_bus_open_fails(self, mock_open):
        from computer_use.platform.linux import _is_mutter_available
        mock_open.side_effect = Exception("cannot open bus")
        assert _is_mutter_available() is False

    @patch("computer_use.platform.linux._open_dbus_connection")
    def test_not_available_when_mutter_returns_error(self, mock_open):
        from computer_use.platform.linux import _is_mutter_available
        import jeepney
        conn = MagicMock()
        reply = MagicMock()
        reply.header.message_type = jeepney.MessageType.error
        conn.send_and_get_reply.return_value = reply
        mock_open.return_value = conn
        assert _is_mutter_available() is False

    @patch("computer_use.platform.linux._open_dbus_connection")
    def test_available_when_mutter_returns_method_return(self, mock_open):
        from computer_use.platform.linux import _is_mutter_available
        import jeepney
        conn = MagicMock()
        reply = MagicMock()
        reply.header.message_type = jeepney.MessageType.method_return
        conn.send_and_get_reply.return_value = reply
        mock_open.return_value = conn
        assert _is_mutter_available() is True


# -- Evdev action executor --


def _mock_evdev():
    """Create mock evdev module and devices for testing."""

    # Mock mouse with ABS support (like VBox tablet)
    mouse = MagicMock()
    mouse.name = "VirtualBox USB Tablet"
    mouse.path = "/dev/input/event5"
    abs_x_info = MagicMock(max=32767)
    abs_y_info = MagicMock(max=32767)
    mouse.capabilities.return_value = {
        ecodes.EV_ABS: [
            (ecodes.ABS_X, abs_x_info),
            (ecodes.ABS_Y, abs_y_info),
        ],
        ecodes.EV_KEY: [ecodes.BTN_LEFT, ecodes.BTN_RIGHT, ecodes.BTN_MIDDLE],
        ecodes.EV_REL: [ecodes.REL_WHEEL],
    }

    # Mock keyboard
    kbd = MagicMock()
    kbd.name = "AT Translated Set 2 keyboard"
    kbd.path = "/dev/input/event2"
    kbd.capabilities.return_value = {
        ecodes.EV_KEY: list(range(ecodes.KEY_A, ecodes.KEY_Z + 1)),
    }

    return mouse, kbd


@pytest.mark.skipif(not _has_evdev, reason="evdev not installed")
class TestEvdevActionExecutor:
    def _make_executor(self):
        from computer_use.platform.linux import EvdevActionExecutor
        mouse, kbd = _mock_evdev()
        return EvdevActionExecutor(mouse, kbd, screen_w=1920, screen_h=1080)

    def test_move_mouse_abs(self):
        ex = self._make_executor()
        # Test raw move directly (smooth_move generates multiple intermediate calls)
        ex._raw_move(960, 540)

        # Filter for EV_ABS events only
        calls = ex._mouse.write.call_args_list
        abs_x_call = [c for c in calls if c[0][0] == ecodes.EV_ABS and c[0][1] == ecodes.ABS_X]
        abs_y_call = [c for c in calls if c[0][0] == ecodes.EV_ABS and c[0][1] == ecodes.ABS_Y]
        assert len(abs_x_call) == 1
        assert len(abs_y_call) == 1
        # Center of 1920 screen on 0-32767 range should be ~16383
        assert abs(abs_x_call[0][0][2] - 16383) < 2

    def test_raw_move_updates_tracker(self):
        ex = self._make_executor()
        ex._raw_move(960, 540)
        assert ex._tracker.get_pos() == (960, 540)

    def test_click_sends_button_events(self):
        ex = self._make_executor()
        ex.click(100, 100)

        calls = ex._mouse.write.call_args_list
        btn_calls = [c for c in calls if c[0][0] == ecodes.EV_KEY]
        # Should have press (1) and release (0)
        assert any(c[0][2] == 1 for c in btn_calls)  # press
        assert any(c[0][2] == 0 for c in btn_calls)  # release

    def test_right_click(self):
        ex = self._make_executor()
        ex.click(100, 100, button="right")

        calls = ex._mouse.write.call_args_list
        btn_calls = [c for c in calls if c[0][0] == ecodes.EV_KEY and c[0][1] == ecodes.BTN_RIGHT]
        assert len(btn_calls) == 2  # press + release

    def test_double_click(self):
        ex = self._make_executor()
        ex.double_click(100, 100)

        calls = ex._mouse.write.call_args_list
        btn_presses = [c for c in calls if c[0][0] == ecodes.EV_KEY and c[0][2] == 1]
        assert len(btn_presses) == 2  # two clicks

    def test_scroll(self):
        ex = self._make_executor()
        ex.scroll(100, 100, -3)

        calls = ex._mouse.write.call_args_list
        wheel_calls = [c for c in calls if c[0][0] == ecodes.EV_REL and c[0][1] == ecodes.REL_WHEEL]
        assert len(wheel_calls) == 3
        assert all(c[0][2] == -1 for c in wheel_calls)

    def test_key_press(self):
        ex = self._make_executor()
        ex.key_press(["ctrl", "c"])

        calls = ex._kbd.write.call_args_list
        key_calls = [c for c in calls if c[0][0] == ecodes.EV_KEY]
        # Ctrl down, C down, C up, Ctrl up
        assert len(key_calls) == 4

    def test_type_text_short_uses_keys(self):
        """Short text (<=3 chars) should type char-by-char, not clipboard."""
        ex = self._make_executor()
        ex.type_text("hi")

        calls = ex._kbd.write.call_args_list
        key_calls = [c for c in calls if c[0][0] == ecodes.EV_KEY]
        assert len(key_calls) >= 4  # h down/up, i down/up

    @patch("subprocess.run")
    def test_type_text_long_types_each_char(self, mock_run):
        """Long text should type each character individually, not clipboard paste."""
        mock_run.return_value = MagicMock(returncode=0)

        ex = self._make_executor()
        ex.type_text("hello")

        # Should NOT use clipboard
        mock_run.assert_not_called()
        # Each char gets key down + key up + syn events
        calls = ex._kbd.write.call_args_list
        key_calls = [c for c in calls if c[0][0] == ecodes.EV_KEY]
        assert len(key_calls) >= 10  # 5 chars * 2 (press + release)

    def test_type_text_newline_sends_enter(self):
        ex = self._make_executor()
        ex.type_text("a\nb")

        calls = ex._kbd.write.call_args_list
        key_calls = [c for c in calls if c[0][0] == ecodes.EV_KEY]
        # a(down,up) + enter(down,up) + b(down,up) = 6 key events
        assert len(key_calls) >= 6
        pressed_keycodes = [c[0][1] for c in key_calls if c[0][2] == 1]
        assert ecodes.KEY_ENTER in pressed_keycodes

    def test_type_text_uppercase_uses_shift(self):
        ex = self._make_executor()
        ex.type_text("Hi")

        calls = ex._kbd.write.call_args_list
        key_calls = [c for c in calls if c[0][0] == ecodes.EV_KEY]
        # H needs shift: shift(down) + h(down) + h(up) + shift(up) + i(down) + i(up) = 6
        assert len(key_calls) >= 6
        pressed_keycodes = [c[0][1] for c in key_calls if c[0][2] == 1]
        assert ecodes.KEY_LEFTSHIFT in pressed_keycodes

    def test_type_text_space_works(self):
        ex = self._make_executor()
        ex.type_text("a b")

        calls = ex._kbd.write.call_args_list
        key_calls = [c for c in calls if c[0][0] == ecodes.EV_KEY]
        # a(down,up) + space(down,up) + b(down,up) = 6 key events
        assert len(key_calls) >= 6
        pressed_keycodes = [c[0][1] for c in key_calls if c[0][2] == 1]
        assert ecodes.KEY_SPACE in pressed_keycodes


# -- Action executor factory --


class TestCreateActionExecutor:
    @patch("computer_use.platform.linux._is_wayland", return_value=False)
    def test_x11_returns_xdotool(self, _mock):
        from computer_use.platform.linux import _create_action_executor, LinuxActionExecutor
        ex = _create_action_executor()
        assert isinstance(ex, LinuxActionExecutor)

    @pytest.mark.skipif(not _has_jeepney, reason="jeepney not installed")
    @patch("computer_use.platform.linux._is_wayland", return_value=True)
    @patch("computer_use.platform.linux._is_mutter_available", return_value=True)
    def test_wayland_gnome_returns_mutter(self, _mutter, _wayland):
        from computer_use.platform.linux import _create_action_executor, MutterRemoteDesktopExecutor
        with patch("computer_use.platform.linux.MutterRemoteDesktopExecutor._setup_session"):
            ex = _create_action_executor()
            assert isinstance(ex, MutterRemoteDesktopExecutor)

    @pytest.mark.skipif(not _has_evdev, reason="evdev not installed")
    @patch("computer_use.platform.linux._is_wayland", return_value=True)
    @patch("computer_use.platform.linux._is_mutter_available", return_value=False)
    @patch("computer_use.platform.linux._find_evdev_mouse")
    @patch("computer_use.platform.linux._find_evdev_keyboard")
    def test_wayland_no_mutter_returns_evdev(self, mock_kbd, mock_mouse, _mutter, _wayland):
        from computer_use.platform.linux import _create_action_executor, EvdevActionExecutor

        mouse, kbd = _mock_evdev()
        mock_mouse.return_value = mouse
        mock_kbd.return_value = kbd

        ex = _create_action_executor()
        assert isinstance(ex, EvdevActionExecutor)

    @patch("computer_use.platform.linux._is_wayland", return_value=True)
    @patch("computer_use.platform.linux._is_mutter_available", return_value=False)
    @patch("computer_use.platform.linux._find_evdev_mouse", return_value=None)
    @patch("computer_use.platform.linux._find_evdev_keyboard", return_value=None)
    def test_wayland_no_mutter_no_evdev_raises(self, _kbd, _mouse, _mutter, _wayland):
        from computer_use.core.errors import PlatformNotSupportedError
        from computer_use.platform.linux import _create_action_executor
        with pytest.raises(PlatformNotSupportedError, match="Wayland input"):
            _create_action_executor()


# -- Backend is_available --


class TestLinuxBackendAvailability:
    @patch("computer_use.platform.linux._is_wayland", return_value=True)
    @patch("computer_use.platform.linux._is_mutter_available", return_value=True)
    @patch("computer_use.platform.linux._wayland_screenshot_tool_available", return_value=True)
    def test_available_on_wayland_with_mutter_and_tool(self, _tool, _mutter, _wayland):
        from computer_use.platform.linux import LinuxBackend
        report = LinuxBackend().availability_report()
        assert report.available is True
        assert report.missing == ()

    @patch("computer_use.platform.linux._is_wayland", return_value=True)
    @patch("computer_use.platform.linux._is_mutter_available", return_value=False)
    @patch("computer_use.platform.linux._wayland_screenshot_tool_available", return_value=True)
    def test_available_on_wayland_with_evdev_only(self, _tool, _mutter, _wayland):
        from computer_use.platform import linux
        with patch.object(linux, "evdev_import", MagicMock()):
            report = linux.LinuxBackend().availability_report()
        assert report.available is True

    @patch("computer_use.platform.linux._is_wayland", return_value=True)
    @patch("computer_use.platform.linux._is_mutter_available", return_value=False)
    @patch("computer_use.platform.linux._wayland_screenshot_tool_available", return_value=True)
    def test_unavailable_when_no_input_method(self, _tool, _mutter, _wayland):
        from computer_use.platform import linux
        with patch.object(linux, "evdev_import", None), \
             patch.object(linux, "jeepney_import", MagicMock()):
            report = linux.LinuxBackend().availability_report()
        assert report.available is False
        assert "input-injection" in report.missing
        assert "Mutter" in report.remediation or "evdev" in report.remediation

    @patch("computer_use.platform.linux._is_wayland", return_value=True)
    @patch("computer_use.platform.linux._is_mutter_available", return_value=False)
    @patch("computer_use.platform.linux._wayland_screenshot_tool_available", return_value=True)
    def test_unavailable_when_jeepney_missing(self, _tool, _mutter, _wayland):
        from computer_use.platform import linux
        with patch.object(linux, "evdev_import", None), \
             patch.object(linux, "jeepney_import", None):
            report = linux.LinuxBackend().availability_report()
        assert report.available is False
        assert "jeepney" in report.missing
        assert "pip install vadgr-computer-use" in report.remediation

    @patch("computer_use.platform.linux._is_wayland", return_value=True)
    @patch("computer_use.platform.linux._is_mutter_available", return_value=True)
    @patch("computer_use.platform.linux._wayland_screenshot_tool_available", return_value=False)
    def test_unavailable_when_screenshot_tool_missing(self, _tool, _mutter, _wayland):
        from computer_use.platform.linux import LinuxBackend
        report = LinuxBackend().availability_report()
        assert report.available is False
        assert "screenshot-tool" in report.missing
        assert "gnome-screenshot" in report.remediation or "grim" in report.remediation

    @patch("computer_use.platform.linux._is_wayland", return_value=False)
    @patch("shutil.which", return_value=None)
    def test_unavailable_x11_without_xdotool_lists_apt_command(self, _which, _wayland):
        from computer_use.platform.linux import LinuxBackend
        report = LinuxBackend().availability_report()
        assert report.available is False
        assert "xdotool" in report.missing
        assert "apt install xdotool" in report.remediation


# -- Foreground window detection --


class TestForegroundWindowXdotool:
    """Tests for X11 foreground window detection via xdotool."""

    @patch("subprocess.run")
    def test_parses_xdotool_output(self, mock_run):
        from computer_use.platform.linux import _query_foreground_window_xdotool

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="My Window Title\nX=100\nY=200\nWIDTH=800\nHEIGHT=600\n1234\n",
        )
        with patch("builtins.open", mock_open(read_data="firefox\n")):
            result = _query_foreground_window_xdotool()
        assert result is not None
        assert result.app_name == "firefox"
        assert result.title == "My Window Title"
        assert result.x == 100
        assert result.y == 200
        assert result.width == 800
        assert result.height == 600
        assert result.pid == 1234

    @patch("subprocess.run")
    def test_returns_none_on_failure(self, mock_run):
        from computer_use.platform.linux import _query_foreground_window_xdotool

        mock_run.return_value = MagicMock(returncode=1, stdout="")
        assert _query_foreground_window_xdotool() is None

    @patch("subprocess.run", side_effect=Exception("timeout"))
    def test_returns_none_on_exception(self, _run):
        from computer_use.platform.linux import _query_foreground_window_xdotool

        assert _query_foreground_window_xdotool() is None


class TestForegroundWindowWayland:
    """Tests for Wayland foreground window detection via AT-SPI2."""

    def _make_mock_window(self, app_name, title, pid, active, x, y, w, h):
        """Build a mock AT-SPI2 window accessible."""
        window = MagicMock()
        window.get_name.return_value = title
        window.get_process_id.return_value = pid

        rect = MagicMock()
        rect.x, rect.y, rect.width, rect.height = x, y, w, h
        window.get_extents.return_value = rect

        ss = MagicMock()
        ss.contains.side_effect = lambda st: (
            active if st.value_name == "ATSPI_STATE_ACTIVE" else False
        )
        window.get_state_set.return_value = ss
        return window

    def _make_mock_app(self, name, windows):
        app = MagicMock()
        app.get_name.return_value = name
        app.get_child_count.return_value = len(windows)
        app.get_child_at_index.side_effect = lambda i: windows[i]
        return app

    @patch("computer_use.platform.linux._query_foreground_window_wayland")
    def test_dispatch_uses_wayland_on_wayland(self, mock_wayland):
        from computer_use.platform.linux import (
            _query_foreground_window,
        )
        import computer_use.platform.linux as linux_mod

        # Clear the cache
        linux_mod._fg_window_cache = None
        mock_wayland.return_value = MagicMock(app_name="firefox")

        with patch("computer_use.platform.linux._is_wayland", return_value=True):
            result = _query_foreground_window()
        assert result.app_name == "firefox"
        mock_wayland.assert_called_once()

    @patch("computer_use.platform.linux._query_foreground_window_xdotool")
    def test_dispatch_uses_xdotool_on_x11(self, mock_xdotool):
        from computer_use.platform.linux import _query_foreground_window
        import computer_use.platform.linux as linux_mod

        linux_mod._fg_window_cache = None
        mock_xdotool.return_value = MagicMock(app_name="gedit")

        with patch("computer_use.platform.linux._is_wayland", return_value=False):
            result = _query_foreground_window()
        assert result.app_name == "gedit"
        mock_xdotool.assert_called_once()

    @patch("computer_use.platform.linux._query_foreground_window_xdotool")
    @patch("computer_use.platform.linux._query_foreground_window_wayland")
    def test_dispatch_falls_back_to_xdotool_when_wayland_returns_none(
        self, mock_wayland, mock_xdotool,
    ):
        from computer_use.platform.linux import _query_foreground_window
        import computer_use.platform.linux as linux_mod

        linux_mod._fg_window_cache = None
        mock_wayland.return_value = None
        mock_xdotool.return_value = MagicMock(app_name="xterm")

        with patch("computer_use.platform.linux._is_wayland", return_value=True):
            result = _query_foreground_window()
        assert result.app_name == "xterm"

    def test_picks_last_active_window(self):
        """When multiple windows are ACTIVE, the last one in the tree wins."""
        from computer_use.platform.linux import _query_foreground_window_wayland

        win_chrome = self._make_mock_window(
            "chrome", "Google Chrome", 100, True, 0, 0, 1920, 1080,
        )
        win_terminal = self._make_mock_window(
            "gnome-terminal-", "Terminal", 200, True, 0, 0, 800, 600,
        )
        app_chrome = self._make_mock_app("Google Chrome", [win_chrome])
        app_terminal = self._make_mock_app("gnome-terminal-server", [win_terminal])

        desktop = MagicMock()
        desktop.get_child_count.return_value = 2
        desktop.get_child_at_index.side_effect = [app_chrome, app_terminal]

        mock_atspi = MagicMock()
        mock_atspi.init.return_value = None
        mock_atspi.get_desktop.return_value = desktop
        mock_atspi.CoordType.SCREEN = "SCREEN"

        # Mock StateType so .contains() comparison works
        active_state = MagicMock()
        active_state.value_name = "ATSPI_STATE_ACTIVE"
        mock_atspi.StateType.ACTIVE = active_state

        mock_gi = MagicMock()
        mock_gi.repository.Atspi = mock_atspi

        with patch.dict("sys.modules", {"gi": mock_gi, "gi.repository": mock_gi.repository}):
            result = _query_foreground_window_wayland()

        assert result is not None
        # Last active window wins — terminal is last in tree
        assert result.pid == 200

    def test_returns_none_when_no_active_windows(self):
        from computer_use.platform.linux import _query_foreground_window_wayland

        win = self._make_mock_window("app", "Window", 100, False, 0, 0, 800, 600)
        app = self._make_mock_app("SomeApp", [win])

        desktop = MagicMock()
        desktop.get_child_count.return_value = 1
        desktop.get_child_at_index.side_effect = [app]

        mock_atspi = MagicMock()
        mock_atspi.init.return_value = None
        mock_atspi.get_desktop.return_value = desktop
        mock_atspi.CoordType.SCREEN = "SCREEN"

        active_state = MagicMock()
        active_state.value_name = "ATSPI_STATE_ACTIVE"
        mock_atspi.StateType.ACTIVE = active_state

        mock_gi = MagicMock()
        mock_gi.repository.Atspi = mock_atspi

        with patch.dict("sys.modules", {"gi": mock_gi, "gi.repository": mock_gi.repository}):
            result = _query_foreground_window_wayland()

        assert result is None

    def test_returns_none_when_atspi_not_available(self):
        from computer_use.platform.linux import _query_foreground_window_wayland

        with patch.dict("sys.modules", {"gi": None}):
            result = _query_foreground_window_wayland()
        assert result is None

    def test_reads_app_name_from_proc_comm(self):
        from computer_use.platform.linux import _query_foreground_window_wayland

        win = self._make_mock_window("", "My App", 42, True, 10, 20, 500, 400)
        app = self._make_mock_app("MyApp", [win])

        desktop = MagicMock()
        desktop.get_child_count.return_value = 1
        desktop.get_child_at_index.side_effect = [app]

        mock_atspi = MagicMock()
        mock_atspi.init.return_value = None
        mock_atspi.get_desktop.return_value = desktop
        mock_atspi.CoordType.SCREEN = "SCREEN"

        active_state = MagicMock()
        active_state.value_name = "ATSPI_STATE_ACTIVE"
        mock_atspi.StateType.ACTIVE = active_state

        mock_gi = MagicMock()
        mock_gi.repository.Atspi = mock_atspi

        with patch.dict("sys.modules", {"gi": mock_gi, "gi.repository": mock_gi.repository}):
            with patch("builtins.open", mock_open(read_data="firefox\n")):
                result = _query_foreground_window_wayland()

        assert result is not None
        assert result.app_name == "firefox"
        assert result.title == "My App"
        assert result.x == 10
        assert result.width == 500
