# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""The Cache fast path: one bulk read of an application's exported tree.

Node-by-node walking costs one D-Bus round trip per node, which is the slow part
of a read. ``org.a11y.atspi.Cache.GetItems`` returns an application's whole
exported tree in a single call, so a warm read is one round trip plus in-process
matching instead of hundreds. This module is the pure part: it parses the
``GetItems`` body into an in-process snapshot the client can answer role, name,
state and structure from without touching the bus. Extents and text are not in
the cache and stay live reads, taken only for the few elements a query returns.

Two facts the snapshot is built around, both observed on a real GNOME box:

- **The cache is populated lazily.** A freshly launched app exports only its top
  nodes until something walks it; the first walk both answers the query and warms
  the cache, so the snapshot's ``child_count`` is compared against the children it
  actually holds and an incomplete node falls back to a live read.
- **The role is an enum, not a name**, and a toolkit's own ``GetRoleName`` does
  not always match the canonical AT-SPI name (GTK4 renders role 43 as "button",
  not "push button"). So role names are resolved by the client against
  ``GetRoleName``, calibrated once per enum, never assumed from a static table:
  the snapshot carries the raw enum and the client maps it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

# A node is an opaque (bus_name, object_path) pair, the same identity used
# everywhere else. GetItems refs are (so) structs, which decode to exactly this.
Node = tuple[str, str]


@dataclass(frozen=True)
class CacheItem:
    """One accessible as the cache exports it: structure, role enum, state, name.

    Extents and text are deliberately absent: ``GetItems`` does not carry them,
    and they are read live for the few elements a query actually returns.
    """

    ref: Node
    parent: Node
    child_count: int
    interfaces: tuple[str, ...]
    name: str
    role_enum: int
    states: tuple[str, ...]


class CacheSnapshot:
    """An application's exported tree, keyed by node, answered without the bus."""

    def __init__(
        self, items: dict[Node, CacheItem], children: dict[Node, list[Node]]
    ) -> None:
        self._items = items
        self._children = children

    def has(self, node: Node) -> bool:
        return node in self._items

    def item(self, node: Node) -> CacheItem | None:
        return self._items.get(node)

    def children(self, node: Node) -> list[Node]:
        """The node's children as the cache holds them (may be incomplete)."""
        return list(self._children.get(node, ()))

    def is_complete(self, node: Node) -> bool:
        """Whether the cache holds every child the node declares it has.

        An incomplete node means the cache was not warm for that branch, so the
        caller reads it live (which also warms it) rather than missing children.
        """
        item = self._items.get(node)
        if item is None:
            return False
        return len(self._children.get(node, ())) >= item.child_count

    def role_enums(self) -> set[int]:
        return {item.role_enum for item in self._items.values()}

    def node_with_role(self, role_enum: int) -> Node | None:
        """A node carrying this role enum, for the client to calibrate its name."""
        for node, item in self._items.items():
            if item.role_enum == role_enum:
                return node
        return None

    def __len__(self) -> int:
        return len(self._items)


def _as_node(ref) -> Node:
    # A GetItems (so) ref decodes to a two-element sequence (bus_name, path).
    return (ref[0], ref[1])


def build_snapshot(
    body, decode_states: Callable[[int, int], tuple[str, ...]]
) -> CacheSnapshot:
    """Parse a ``Cache.GetItems`` reply body into a snapshot.

    ``body`` is the array of item structs
    ``(ref, app, parent, index, child_count, interfaces, name, role, description,
    states)``. States are the two-word AT-SPI bitfield, decoded with the same
    function the live path uses, so a cached state set is identical to a walked
    one. Children are grouped by parent and ordered by the declared index.
    """
    items: dict[Node, CacheItem] = {}
    pending: dict[Node, list[tuple[int, Node]]] = {}
    for it in body:
        ref = _as_node(it[0])
        parent = _as_node(it[2])
        index = int(it[3])
        child_count = int(it[4])
        interfaces = tuple(it[5])
        name = it[6]
        role_enum = int(it[7])
        state_words = it[9]
        low = int(state_words[0]) if len(state_words) > 0 else 0
        high = int(state_words[1]) if len(state_words) > 1 else 0
        items[ref] = CacheItem(
            ref=ref, parent=parent, child_count=child_count,
            interfaces=interfaces, name=name, role_enum=role_enum,
            states=decode_states(low, high),
        )
        pending.setdefault(parent, []).append((index, ref))
    children = {
        parent: [ref for _index, ref in sorted(entries)]
        for parent, entries in pending.items()
    }
    return CacheSnapshot(items, children)
