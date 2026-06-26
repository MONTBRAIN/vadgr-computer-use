// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// Shared content-script error type. Lives in its own module so op handlers and
// the actionability gate both depend on it without a circular import.

export class OpFailed extends Error {}
