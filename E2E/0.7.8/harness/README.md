# 0.7.8 E2E harness

This directory contains the released-wheel transition fixtures and safe
lifecycle recorder for the 0.7.8 pass. Each helper validates an isolated test
root before it changes state. Helpers prepare faults and record safe metadata.
They never drive the product goal, stop an unknown process, or read a token.

The implementation adds each helper before its first use. Run every helper from
this committed directory. Do not replace a helper with a temporary host script.
