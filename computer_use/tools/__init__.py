# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""First-party tool implementations grouped by tier.

The agent loop reaches for the cheapest tier first. Tier 0 covers system
primitives (filesystem, shell, HTTP, clock, etc.) that do not require
vision or window introspection.
"""
