# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""Concrete Linux capture/input backends + their provider registrations.

Screenshot via the XDG portal, input via pure-python uinput and X11 XTEST, plus
the provider wrappers that register these (and the existing linux.py backends)
with the resolver. Importing ``linux_providers`` registers the providers.
"""
