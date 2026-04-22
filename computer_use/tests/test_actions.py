"""Tests for the ActionExecutor ABC contract.

The ABC only declares the primitive methods that platform backends must
implement. There is no router / Action dataclass anymore; MCP tool calls
go directly to primitives like click() / type_text().
"""

from computer_use.core.actions import ActionExecutor


class MockExecutor(ActionExecutor):
    """Concrete executor that records calls for testing."""

    def __init__(self):
        self.calls = []

    def move_mouse(self, x, y):
        self.calls.append(("move_mouse", x, y))

    def click(self, x, y, button="left"):
        self.calls.append(("click", x, y, button))

    def double_click(self, x, y):
        self.calls.append(("double_click", x, y))

    def type_text(self, text):
        self.calls.append(("type_text", text))

    def key_press(self, keys):
        self.calls.append(("key_press", keys))

    def scroll(self, x, y, amount):
        self.calls.append(("scroll", x, y, amount))

    def drag(self, start_x, start_y, end_x, end_y, duration=0.5):
        self.calls.append(("drag", start_x, start_y, end_x, end_y, duration))


class TestActionExecutorContract:
    def test_can_instantiate_concrete_subclass(self):
        ex = MockExecutor()
        assert isinstance(ex, ActionExecutor)

    def test_primitive_methods_are_callable(self):
        ex = MockExecutor()
        ex.click(10, 20)
        ex.type_text("hi")
        ex.key_press(["ctrl", "c"])
        ex.scroll(50, 60, -3)
        ex.drag(1, 2, 3, 4, 0.5)
        assert len(ex.calls) == 5
