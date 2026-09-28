# Exact signed helper transitions

The signed helper transformation and the later choice of predecessor are separate
operations. A signing claim consumes one exact unsigned closure once. A subsequent
authenticated catalog can permit replacement or rollback between two already
verified signed closures without signing either closure again.

## Two distinct reviewed inputs

The trusted `profile-review-inputs` and `profile-wheels` workflows accept only the
named `input_set` values `primary` and `upgrade-fixture`. Primary uses the existing
`source-input.json` and `adoption-rules.json`. The upgrade fixture uses:

```text
packaging/profiles/fixtures/upgrade/source-input.json
packaging/profiles/fixtures/upgrade/adoption-rules.json
```

Both files must be reviewed, committed trusted inputs. They are not generated from
a dispatch parameter. The source record has the same closed schema as primary and
must name a different exact source commit. The member rules must cover the actual
second native build, not copy another build's input hashes. Missing files fail
closed. Native source execution stays separate from trusted validation and OIDC.

The second producer's independently observed closure must also change its relay
or broker archive bytes. A changed input manifest alone, new candidate ID, new
artifact ID, new signing job or a second timestamp does not create a new eligible
input. The two closures must have distinct signed archives as well. Never modify
an already reviewed binary to manufacture a fixture or replay an existing signing
claim. Retain both producer receipts, all three input hashes, per-member rules,
native reports, final artifacts, authorization bundles and consumer receipts.

## Authorization schema 2

The immutable signing claim and final manifest retain schema 1. The claim's
`adoption_inputs` remains exactly `[input_closure]`. Its identity remains:

```text
helper_closure_id = SHA256(canonical({architecture, input_closure}))
signing_claim_ref = refs/tags/cua-signing-claims/<helper_closure_id>
```

Here `canonical` means sorted-key, compact UTF-8 JSON with one final LF. It never
includes a candidate ID. The protected producer retains its durable one-use claim
and reconciles uncertain attempts instead of retrying them.

A schema-2 `helper-closure-authorization.json` retains every schema-1 field and
adds exactly one field, `signed_predecessors`:

```text
{
  schema: 1,
  architecture: "x86_64" | "aarch64",
  entries: [
    {
      cua_version: exact predecessor version,
      source_commit: exact predecessor source commit,
      input_closure: {relay_sha256, archive_sha256, manifest_sha256},
      final_closure: {relay_sha256, archive_sha256, manifest_sha256}
    }
  ]
}
```

The catalog contains 1 to 32 entries sorted by final archive hash. Inputs and
final archives cannot repeat or identify the current candidate. Every digest is
an exact nonzero SHA-256. The protected producer verifies each entry against its
retained prior claim, final manifest, independent signature reports and attested
authorization before including it. A caller-supplied JSON catalog is not authority.

`adoption_edges` starts with the existing exact unsigned-to-signed edge. It then
contains one signed-to-signed edge per catalog entry in the same order:

```text
{
  direction: "signed-to-signed",
  architecture: current architecture,
  cua_version: current candidate version,
  source_commit: current candidate source commit,
  input_closure: predecessor final_closure,
  final_closure: current signed final_closure,
  predecessor_version: predecessor cua_version,
  predecessor_source_commit: predecessor source_commit
}
```

Unknown fields, missing or extra edges, duplicate inputs, metadata-only input
changes and unrelated predecessor identities fail. Schema-1 authorization remains
valid only for its original unsigned-to-signed edge.

## Cycle-free production and rollback

1. Build and independently review distinct unsigned input sets A and B.
2. Consume one closure-keyed signing claim per input set and architecture.
3. Freeze each signed archive, final manifest and transformation mapping. Do not
   embed final signed predecessor hashes inside either archive or final manifest.
4. Verify both retained signed subjects. Issue schema-2 authorization for B with
   A as an exact predecessor. Issue authorization for A with B as the exact reverse
   predecessor when rollback is explicitly reviewed.
5. Regenerate both profile receipts against each new authorization digest. Attest
   each authorization from the trusted producer. This spends no signing claim.
6. Bind the selected authorization digest into the independently authenticated
   installed runtime envelope and parent launch record. Signatures, final helper
   archives and manifests are not rebuilt or modified.

The final manifest's existing `predecessor_catalog_sha256` continues to describe
the embedded released unsigned predecessor catalog. It does not describe the new
signed transition catalog. The latter belongs to the later authorization hash
domain, so forward and reverse authorization cannot form a manifest hash cycle.

The broker receives the authorization path and digest only after parent-channel
or standalone offline attestation verification. It validates the complete catalog,
then proves a signed predecessor using `broker-final-manifest.json`, its exact
digest, source, architecture, archive identity and every installed file. An
unsigned `bundle-manifest.json` cannot stand in for a signed predecessor manifest.
Existing process ownership, creation identity, lock ownership and no-replay
checks remain mandatory before termination.

Standalone state is stored once per Windows architecture under its protected
`current` state directory, not once per unsigned input. Both native and WSL
standalone clients therefore see prior signed adoption after a package update.
Publication compares the exact previously observed state while holding its lock.
Changed state needs a catalog entry matching both the old input and old signed
closure. An absent retained generation requires repair, never unsigned fallback.
Reissuing authorization for the same verified signed bytes may refresh the
catalog without changing the adopted payload.

## Rebaseline and qualification

The historical frozen source `14cb515ba54ca9346ea931ba46d4c3253164c8b4` does not
contain this runtime repair. Keep its observations as historical evidence only.
After the repaired runtime commit is pushed and reviewed, update exact source
pins transactionally and produce new native review packets. Re-review changed
members and signing rules before producing either signed fixture. Do not insert
this module into an old wheel or reuse old signatures for changed bytes.

P07 and the approved P05 rollback cells still need two real signed fixtures on
each required native architecture and execution profile. Unit tests with synthetic
signature records are not those cells. Re-run affected Windows and WSL adoption,
handoff, restart, repair, rollback and no-fallback cells against the exact new
installed bytes. Requalify any other changed package surface according to its
new artifact identity. No existing result is silently promoted to the new source.
