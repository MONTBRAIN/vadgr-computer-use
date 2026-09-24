# Release profile construction

`scripts/build_profile_wheels.py` constructs eight managed wheels and one
standalone wheel directly from the source tree. Each managed wheel has a unique
wheel build tag. Linux and WSL therefore have separate immutable asset names.
The producer never strips or relabels an existing wheel.

`scripts/check_profile_wheels.py --catalog OUTPUT/cua-profile-catalog.json`
validates the complete retained output without importing package code. It checks
canonical manifests, native headers, exact recursive inventories, package markers,
wheel RECORD entries and identical native Windows/WSL helper input bytes.
Catalog verification is a data check. Consumers must also verify its attestation
and reviewed producer identity. The attestation bundle and publication record
remain outside the catalog hash domain.

The builder requires both native helper directories. Each contains the relay,
one broker ZIP and its member manifest from `build_windows_broker.py`. It also
requires a producer descriptor with `producer` and `profiles` mappings. Each
profile evidence record has `build_sha256`, `test_sha256`, `sbom_sha256`, numeric
`native_job_ids`, and immutable `artifacts` records with `id` and `sha256`.
The descriptor binds the exact source and tooling commits and the first hosted
workflow attempt on master. No artifact or release ID is guessed.

The producer creates one adoption directory per architecture under its isolated
build output. These generated directories do not belong in Git:

```text
adoption/
  x86_64/
    adoption-policy.json
    trusted-root.json
    gh.exe
    LICENSE
  aarch64/
    adoption-policy.json
    trusted-root.json
    gh.exe
    LICENSE
```

Each generated policy binds the actual source/version and helper closure to the
reviewed root, verifier, signing classes and signer/source allowlists. The package
contains separate digest pins for each policy, root and verifier. Source and
helper hashes are derived after building, so no committed policy must name the
commit that contains itself. Derivation does not authorize a new signer or class.

The protected-input review must supply these files before the producer can run:

- `requirements/windows-broker-build.txt`: the complete, hashed native build
  dependency lock. Both architectures use this committed lock with binary-only
  installation and dependency resolution disabled. `toolchain.json` also binds
  each native Python distribution archive by URL and SHA-256.
- `verifier-inputs.json`: exact archive, executable and license identities for
  native Windows GitHub CLI 2.95.0, plus the fixed offline trusted-root snapshot.
  Provisioning downloads only these producer inputs, verifies their sizes and
  hashes, checks native architecture, and freezes the required files. Neither
  the application nor the adoption path downloads anything. The binaries are
  build artifacts, not large committed source files.
- `adoption-rules.json`: exact reviewed Vadgr source/signer allowlists, expiry and
  per-architecture member rules, described below. No broadening from a candidate
  output or runtime environment is allowed.
- `size-budgets.json`: reviewed maximum wheel bytes for each of the eight profile
  names and `standalone`, as a canonical JSON object with positive integer values.

The remaining protected input is `adoption-rules.json`. It is deliberately absent
until its actual signing and legal decisions are available. Preflight names this
file precisely. The trusted producer cannot substitute a smoke-test identity or
invent a legal approval. Its canonical JSON schema is:

- `schema`: integer 1.
- `expires_at`: reviewed UTC Unix expiry, strictly in the future.
- `source_sha_allowlist` and `signer_sha_allowlist`: nonempty lists of exact,
  nonzero, 40-character Vadgr commits. These identify approved source and trusted
  signing workflow code, not the CUA source being built.
- `files`: exactly `x86_64` and `aarch64`. Each maps every broker member and
  `vadgr-cua-host.exe` to its fixed rule. A missing or extra path fails. Each
  rule contains `trust_class`, `signer_policy_sha256`, `legal_approval_sha256`,
  `signer`, `certificate_sha256`, `chain_root_sha256`, `digest_algorithm`, and
  `timestamp_algorithm`. The classes are `publisher-sign`, `vendor-preserve`
  or `data`. Data uses null signature fields. Native classes need real reviewed
  policy/legal hashes, certificate/root hashes, subject, `sha256` and
  `rfc3161-sha256`. The producer derives `input_sha256` from the built bytes.

The trusted workflow runs only from master, on its first dispatched attempt.
It verifies numeric repository/owner identities and uses the same source and
tooling commit. The fresh validator re-reads the GitHub run, successful native
jobs, retained artifact IDs/digests and evidence hashes. It compares packaged
source with its checkout, independently regenerates both policies from the fixed
review inputs, and checks all nine wheels before attesting the catalog. Native
build and live qualification remain separate results.

## Package size ceilings

The committed ceilings are 8 MiB for each native Linux/macOS managed wheel,
80 MiB for each Windows/WSL managed wheel, and 256 MiB for standalone. The wheel
format deliberately uses deterministic stored ZIP entries. The standalone
verifiers alone are 41,483,064 and 38,109,496 bytes, measured from the pinned
release archives on 2026-09-24. Two helper closures, common source, manifests
and notices must fit the remaining standalone allowance. A managed profile has
one helper closure and no offline verifier. Native Linux/macOS have neither.
These are maximum construction budgets, not claims of measured candidate size.
Every producer logs actual compressed wheel bytes and unpacked component bytes.
A larger artifact fails and needs a reviewed explanation and budget change.

The native SBOM inventories every broker member, each nested standard-library
ZIP member, the relay, the bootloader, and their exact SHA-256 values. Every
collected DLL/PYD must match a member of the pinned Python distribution.
OpenSSL, libffi, Microsoft VC runtime and static Python dependencies have
separate component identities. Pinned upstream notices travel inside the
broker archive. The relay source inventory records actual linked Go packages,
source hashes and their notices. Build tools are not mislabeled as shipped
components. The SPDX creation time is the actual build time. Legal conclusions
remain `NOASSERTION` until their separate exact-target review, particularly
Microsoft redistribution rights; this inventory is not an approval.

## Unsigned development qualification

`development-profile.yml` builds the matching native helper on feature pushes
and pull requests, without signing, attestation or publication permissions.
`scripts/build_development_profile.py` creates a wheel with a `0development`
build tag, a mandatory `development: true` package marker and a separate
`development-receipt.json`. This artifact supports unsigned standalone selection
and browser tests before the implementation PR. It covers only its declared
Windows/WSL architecture. Its receipt says `publishable: false` and
`adoption: disabled`; it contains no adoption policy or verifier. The release
catalog checker rejects this receipt, and the publication workflow requires the
trusted nine-wheel catalog. Development artifacts never satisfy signed or
offline-adoption cells. Run the same builder locally only from the exact clean
committed source with native helper inputs from that commit.
