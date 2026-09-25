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
The descriptor binds the exact source and tooling commits separately and the
first hosted workflow attempt on master. `source-input.json` pins the reviewed
product commit and version. It accepts no workflow input or environment override.
No artifact or release ID is guessed.

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
contains separate digest pins for each policy, root and verifier. Every member
must first match its independently reviewed input hash. The producer then derives
the source and enclosing closure identities, so no committed policy must name
the commit that contains itself. Derivation does not authorize changed bytes,
a new signer or a new class.

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
  rule contains `input_sha256`, `trust_class`, `signer_policy_sha256`, `legal_approval_sha256`,
  `signer`, `certificate_sha256`, `chain_root_sha256`, `digest_algorithm`, and
  `timestamp_algorithm`. The classes are `publisher-sign`, `vendor-preserve`
  or `data`. Every class requires a nonzero lowercase `input_sha256` copied from
  the exact reviewed inventory. Data uses null signature fields. Native classes
  need real reviewed policy/legal hashes, certificate/root hashes and subject.
  Publisher signing requires `sha256` and `rfc3161-sha256`. Vendor preservation
  records independently verified upstream digest and timestamp algorithms; no
  algorithm is defaulted from publisher policy. The current native verifier
  supports the vendor pair `sha256` / `rfc3161-sha256`. A missing, weaker or
  unsupported vendor pair fails closed and needs a reviewed verifier change.
  The producer compares built member bytes with the reviewed `input_sha256`;
  it never replaces that approval with a hash derived from new output.

The trusted workflow runs only from master, on its first dispatched attempt.
Its separate source checkout uses the exact reviewed commit. Every source checkout
must be clean, match the pinned version, and contain no symlink or submodule.
The native build jobs can execute candidate source but have no signing or
attestation permissions and retain no checkout credential. A fresh validator
runs only master tooling and reads the candidate source and artifacts as data.
It verifies numeric repository/owner identities, binds the workflow run, native
jobs and artifact origins to the tooling commit, and binds packaged source and
helper manifests to the source commit. It independently regenerates both policies
from master review inputs and checks all nine wheels before attesting the catalog.
Native build and live qualification remain separate results.

## Qualification and landing order

`profile-review-inputs.yml` breaks the legal-inventory preparation dependency.
It runs only trusted master tooling on the first dispatch and builds the exact
reviewed source on native x64 and ARM64 runners without signing credentials.
Its artifacts contain only member inventories, the exact unreviewed SPDX record,
verbatim available notices/source receipts and build-input pins. No executable,
archive, wheel, adoption policy, final catalog or attestation is uploaded.
Every receipt says `publishable: false`, `legal_approval: false`,
`signing_approval: false` and `adoption: disabled`. Every member's trust class
remains unassigned. Review data does not establish redistribution rights,
signature validity or permission to transform a third-party binary.

Reviewers use this packet to identify every native member, conclude its legal
duties and approve the exact rules. They must separately verify non-secret
publisher/vendor certificate identities and authorize the exact consumer
source/tooling allowlists and expiry. The packet is not an approval and cannot
replace the final producer preflight. After those reviewed inputs land, the
normal producer still rebuilds and validates the exact member set and every
member hash before it can create held final wheels. A changed path or byte,
including a notice or relay byte, fails before either adoption policy is frozen.
Renew the exact review before changing its approved hash. A later build does
not inherit approval merely because its paths and classifications match.

### Preparing the review draft

Download and independently verify the retained review artifacts first. Record
the trusted workflow/source identities and the receipt hash for each architecture.
The following command reads the extracted text packets and freezes only two new
draft files. Replace each path and receipt hash with the recorded exact value:

```sh
python scripts/prepare_adoption_review.py --x86-64-review REVIEW_X64 --x86-64-receipt-sha256 RECEIPT_X64_SHA256 --aarch64-review REVIEW_ARM64 --aarch64-receipt-sha256 RECEIPT_ARM64_SHA256 --output NEW_REVIEW_DIRECTORY
```

Both packets must match the committed CUA source/version and the same review
run, attempt and tooling commit. Their file inventories must match exactly.
The command refuses a changed receipt, missing/extra file or changed file hash.
`adoption-rules.draft.json` copies every exact member hash and marks non-native
members as data. Native classes and all signature/legal fields remain null;
source/signer allowlists remain empty and expiry remains null. This draft fails
the final producer's validation. `review-binding.json` records the selected
receipt identities and the draft digest. Neither file grants approval.

Complete the redistribution and transformation review for all members, including
code inside non-native archives and retained notices. Independently verify every
vendor signature, chain, digest and timestamp. Keep the Authenticode chain-root
hash distinct from the offline Sigstore root hash. Enter only the reviewed
publisher/vendor identities and exact legal and signature-policy record hashes.
Never convert a successful signature check into a redistribution conclusion.

The producer allowlists identify the separately reviewed Vadgr source and signing
workflow commits, not the CUA source or this tooling commit. Select those exact
identities from the reviewed signing bootstrap before freezing the standalone
wheel. Review a concrete expiry. After these decisions, land the completed
canonical `adoption-rules.json` through its own review. Preparing a draft does
not authorize that landing, signing, merge or publication.

The subsequent protected preview identifies exact retained candidate inputs,
both Windows/WSL consumer bindings, every preserved member and its verification,
and all signing operations. Count publisher-sign members once per architecture;
the matching WSL consumer uses identical signed bytes. Other vehicle operations
and a second signed fixture have separate budgets. Approve the exact one-use
claim only after reviewing that complete preview. Never retry an uncertain
vendor call without reconciliation and a new authorization.

Data admission checks for this prerequisite are:

```sh
python -m pytest scripts/tests/test_adoption_review.py scripts/tests/test_profile_producer.py scripts/tests/test_profile_review_inputs.py scripts/tests/test_profile_source_boundary.py -q
python packaging/profiles/producer.py preflight
```

Until complete approved rules exist, the second command must refuse with the
missing `adoption-rules.json` prerequisite. Test each changed-member case against
both architectures, including native broker, relay and non-native notice bytes;
no rejected case may freeze either policy. These checks exercise build tooling
only. They do not replace native signature checks or signed/adoption live cells.

The trusted producer tooling lands through a separate prerequisite PR before
the runtime implementation PR. It adds no runtime change or version bump.
The reviewed source pin can name that still-open implementation branch's exact
commit. Moving the branch does not move the pin; a product fix requires a new
reviewed input commit and new retained artifacts.

After the tooling and exact adoption rules land, dispatch `profile-wheels.yml`
on master once. Keep all nine wheels and the catalog held. Qualify native
Linux/macOS, Windows and WSL against those retained bytes. The separately approved
signing job transforms the Windows helper closure once per architecture for both
native Windows and WSL. Signed/adoption cells run against its actual held output.
Only the complete required live matrix and final green checks make the runtime
implementation PR eligible for owner-approved merge. Publication follows its own
review and publishes the retained qualified artifacts without rebuilding.

Missing reviewed `adoption-rules.json` prevents producer dispatch. A tooling PR,
an unsigned development pass or a catalog attestation is no signed-helper pass.

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
