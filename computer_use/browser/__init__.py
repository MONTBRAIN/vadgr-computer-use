# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Browser tier (Tier 1): MV3 extension + native messaging.

The Python half of the browser tier. It never imports the ``extension/``
side — the two communicate only over the versioned wire protocol defined in
``protocol.py`` (mirrored in ``extension/src/protocol.ts``).
"""
