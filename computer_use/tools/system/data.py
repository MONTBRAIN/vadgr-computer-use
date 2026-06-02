# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Data format parsers + serializers.

JSON and CSV use the stdlib. YAML is optional: ``parse_yaml`` /
``serialize_yaml`` raise a clear RuntimeError if PyYAML isn't installed,
rather than crashing at import time.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Optional

from computer_use.core.ops import OperationGroup

_ops = OperationGroup("data")


def _parse_json(source: str) -> Any:
    return json.loads(source)


def _serialize_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True)


def _parse_csv(source: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(source)))


def _serialize_csv(value: list[dict[str, Any]]) -> str:
    if not value:
        return ""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(value[0].keys()))
    writer.writeheader()
    for row in value:
        writer.writerow(row)
    return buf.getvalue()


def _load_yaml_module():
    try:
        import yaml
    except ImportError as e:
        raise RuntimeError(
            "YAML support requires PyYAML. Install with `pip install pyyaml`."
        ) from e
    return yaml


def _parse_yaml(source: str) -> Any:
    return _load_yaml_module().safe_load(source)


def _serialize_yaml(value: Any) -> str:
    return _load_yaml_module().safe_dump(value, sort_keys=True)


@_ops.operation("parse_json")
def _op_parse_json(source: Optional[str] = None) -> Any:
    if source is None:
        raise ValueError("data.parse_json requires source")
    return _parse_json(source)


@_ops.operation("serialize_json")
def _op_serialize_json(value: Any = None) -> str:
    return _serialize_json(value)


@_ops.operation("parse_csv")
def _op_parse_csv(source: Optional[str] = None) -> list[dict[str, str]]:
    if source is None:
        raise ValueError("data.parse_csv requires source")
    return _parse_csv(source)


@_ops.operation("serialize_csv")
def _op_serialize_csv(value: Any = None) -> str:
    return _serialize_csv(value or [])


@_ops.operation("parse_yaml")
def _op_parse_yaml(source: Optional[str] = None) -> Any:
    if source is None:
        raise ValueError("data.parse_yaml requires source")
    return _parse_yaml(source)


@_ops.operation("serialize_yaml")
def _op_serialize_yaml(value: Any = None) -> str:
    return _serialize_yaml(value)


def data(
    op: str,
    source: Optional[str] = None,
    value: Any = None,
) -> Any:
    """Dispatch a data-format sub-operation.

    Args:
        op: One of ``parse_json``, ``serialize_json``, ``parse_csv``,
            ``serialize_csv``, ``parse_yaml``, ``serialize_yaml``.
        source: Raw text to parse (for parse_* ops).
        value: Python value to serialize (for serialize_* ops).
    """
    return _ops.run(op, source=source, value=value)
