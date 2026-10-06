# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Canonical, nonlocalized AT-SPI role names for numeric wire values.

GetRoleName is optional. Keep the standard enum available without requiring
PyGObject or libatspi inside the installed Python environment. Values follow
GNOME at-spi2-core atspi-constants.h and atspi_role_get_name, checked against
commit 675ad4f16a7a4e0c22873ec96118fce084fc6326. Existing toolkit-provided names
take precedence; this table is only the missing-method fallback.
"""

ROLE_NAMES = (
    "invalid", "accelerator label", "alert", "animation", "arrow",  # 0
    "calendar", "canvas", "check box", "check menu item", "color chooser",  # 5
    "column header", "combo box", "date editor", "desktop icon", "desktop frame",  # 10
    "dial", "dialog", "directory pane", "drawing area", "file chooser",  # 15
    "filler", "focus traversable", "font chooser", "frame", "glass pane",  # 20
    "html container", "icon", "image", "internal frame", "label",  # 25
    "layered pane", "list", "list item", "menu", "menu bar",  # 30
    "menu item", "option pane", "page tab", "page tab list", "panel",  # 35
    "password text", "popup menu", "progress bar", "button", "radio button",  # 40
    "radio menu item", "root pane", "row header", "scroll bar", "scroll pane",  # 45
    "separator", "slider", "spin button", "split pane", "status bar",  # 50
    "table", "table cell", "table column header", "table row header", "tearoff menu item",  # 55
    "terminal", "text", "toggle button", "tool bar", "tool tip",  # 60
    "tree", "tree table", "unknown", "viewport", "window",  # 65
    "extended", "header", "footer", "paragraph", "ruler",  # 70
    "application", "autocomplete", "editbar", "embedded", "entry",  # 75
    "chart", "caption", "document frame", "heading", "page",  # 80
    "section", "redundant object", "form", "link", "input method window",  # 85
    "table row", "tree item", "document spreadsheet", "document presentation", "document text",  # 90
    "document web", "document email", "comment", "list box", "grouping",  # 95
    "image map", "notification", "info bar", "level bar", "title bar",  # 100
    "block quote", "audio", "video", "definition", "article",  # 105
    "landmark", "log", "marquee", "math", "rating",  # 110
    "timer", "static", "math fraction", "math root", "subscript",  # 115
    "superscript", "description list", "description term", "description value", "footnote",  # 120
    "content deletion", "content insertion", "mark", "suggestion", "push button menu",  # 125
    "switch",  # 130
)


def canonical_role_name(value: int) -> str:
    """Unknown future enum values stay visible without inventing a role."""
    if 0 <= value < len(ROLE_NAMES):
        return ROLE_NAMES[value]
    return "unknown"
