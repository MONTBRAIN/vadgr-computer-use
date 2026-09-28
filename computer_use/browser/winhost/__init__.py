# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License").
# http://www.apache.org/licenses/LICENSE-2.0

"""Source marker for the Windows relay shim.

The reviewed release-profile producer builds ``main.go`` for the exact native
architecture and inserts that binary into the corresponding retained artifact.
Generic source builds deliberately contain no prebuilt relay.
"""
