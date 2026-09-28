# Copyright 2026 Victor Santiago Montano Diaz
# Licensed under the Apache License, Version 2.0.

"""Closed transition catalogs carried inside authenticated helper authorization."""

from __future__ import annotations

import re

from computer_use.browser.managed_authorization import (
    canonical_json,
    closure_identity,
    fields,
    profile_pair,
    require,
    sha256,
)

AUTHORIZATION_FIELDS = (
    "schema pre_signing_claim_sha256 helper_closure_id architecture "
    "cua_version source_commit tooling_commit input_closure final_closure consumer_inputs "
    "signing_run_id signing_attempt signing_job_id output_artifact "
    "publisher_policy_sha256 legal_policy_sha256 mapping_sha256 adoption_edges"
)


def authorization_fields(value: dict) -> dict:
    require(isinstance(value, dict) and type(value.get("schema")) is int
            and value["schema"] in (1, 2), "unsupported closure authorization")
    return fields(value, AUTHORIZATION_FIELDS + (" signed_predecessors" if value["schema"] == 2 else ""))


def closure_key(architecture: str, closure: dict) -> str:
    profile_pair(architecture)
    closure_identity(closure)
    return sha256(canonical_json({"architecture": architecture, "input_closure": closure}))


def transition_edges(authorization: dict) -> list[dict]:
    """Validate catalog content, not its authenticity; the caller proves the latter."""
    authorization_fields(authorization)
    architecture = authorization["architecture"]
    profile_pair(architecture)
    original = closure_identity(authorization["input_closure"])
    final = closure_identity(authorization["final_closure"])
    require(original != final, "signed closure must differ from its unsigned input")
    common = {key: authorization[key] for key in ("architecture", "cua_version", "source_commit")}
    edges = [{**common, "direction": "unsigned-to-signed", "input_closure": original, "final_closure": final}]
    if authorization["schema"] == 2:
        catalog = fields(authorization["signed_predecessors"], "schema architecture entries")
        require(type(catalog["schema"]) is int and catalog["schema"] == 1
                and catalog["architecture"] == architecture
                and isinstance(catalog["entries"], list) and 0 < len(catalog["entries"]) <= 32,
                "invalid signed predecessor catalog")
        require(authorization["helper_closure_id"] == closure_key(architecture, original),
                "signing claim must remain keyed by exact input closure")
        seen_inputs = {closure_key(architecture, original)}
        seen_payloads = {(original["relay_sha256"], original["archive_sha256"])}
        seen_archives = {final["archive_sha256"]}
        ordering = []
        for entry in catalog["entries"]:
            fields(entry, "cua_version source_commit input_closure final_closure")
            require(isinstance(entry["cua_version"], str)
                    and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", entry["cua_version"]) is not None
                    and isinstance(entry["source_commit"], str)
                    and re.fullmatch(r"[0-9a-f]{40}", entry["source_commit"]) is not None
                    and entry["source_commit"] != "0" * 40, "invalid signed predecessor source")
            before = closure_identity(entry["input_closure"])
            after = closure_identity(entry["final_closure"])
            identity = closure_key(architecture, before)
            payload = (before["relay_sha256"], before["archive_sha256"])
            require(before != after and identity not in seen_inputs
                    and payload not in seen_payloads
                    and after["archive_sha256"] not in seen_archives,
                    "signed fixtures must have distinct reviewed inputs and archives")
            seen_inputs.add(identity)
            seen_payloads.add(payload)
            seen_archives.add(after["archive_sha256"])
            ordering.append(after["archive_sha256"])
            edges.append({**common, "direction": "signed-to-signed",
                          "input_closure": after, "final_closure": final,
                          "predecessor_version": entry["cua_version"],
                          "predecessor_source_commit": entry["source_commit"]})
        require(ordering == sorted(ordering), "signed predecessor catalog must be sorted")
    require(authorization["adoption_edges"] == edges, "invalid adoption transformation edge")
    return edges


def allows_state_transition(authorization: dict, previous: dict) -> bool:
    transition_edges(authorization)
    if authorization["schema"] != 2 or previous["architecture"] != authorization["architecture"]:
        return False
    # A fresh attestation may add a reviewed reverse edge without modifying or
    # re-signing the already verified helper bytes.
    if (previous["input_closure"] == authorization["input_closure"]
            and previous["final_closure"] == authorization["final_closure"]):
        return True
    return any(entry["input_closure"] == previous["input_closure"]
               and entry["final_closure"] == previous["final_closure"]
               for entry in authorization["signed_predecessors"]["entries"])
