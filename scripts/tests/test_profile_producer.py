"""Producer tests use isolated helper bytes and never assert a live signing result."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packaging/profiles"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import adoption_inputs as adoption
import build_profile_wheels as build
import check_profile_wheels as check
import producer
from build_development_profile import build_development
from test_profile_wheels import package_inputs as _package_inputs

profile_inputs = _package_inputs


def rules_for(members):
    rows = {}
    for name, data in members.items():
        row = dict.fromkeys(adoption.SIGNATURE_FIELDS)
        row["trust_class"] = "data"
        if build.native_identity(data):
            row = {key: "1" * 64 for key in adoption.SIGNATURE_FIELDS}
            row.update(
                trust_class="publisher-sign",
                signer="test signer",
                digest_algorithm="sha256",
                timestamp_algorithm="rfc3161-sha256",
            )
        rows[name] = row
    return rows


@pytest.fixture
def adoption_setup(profile_inputs):
    source, helpers, _, descriptor, output = profile_inputs
    base = source / "packaging/profiles"
    base.mkdir(parents=True)
    rules = {
        "schema": 1,
        "expires_at": 4102444800,
        "source_sha_allowlist": ["c" * 40],
        "signer_sha_allowlist": ["d" * 40],
        "files": {},
    }
    inputs = source / "inputs"
    inputs.mkdir()
    pins = {"root": {}, "architectures": {}}
    for architecture, helper in helpers.items():
        target = inputs / ("native-" + architecture)
        target.mkdir()
        for path in helper.iterdir():
            (target / path.name).write_bytes(path.read_bytes())
        members = build.zip_members((helper / "broker.zip").read_bytes())
        members["vadgr-cua-host.exe"] = (helper / "vadgr-cua-host.exe").read_bytes()
        rules["files"][architecture] = rules_for(members)
        directory = output / architecture
        (directory / "adoption-policy.json").unlink()
        pins["root"]["sha256"] = build.digest((directory / "trusted-root.json").read_bytes())
        pins["architectures"][architecture] = {
            "executable_sha256": build.digest((directory / "gh.exe").read_bytes())
        }
        pins["license_sha256"] = build.digest((directory / "LICENSE").read_bytes())
    (base / "adoption-rules.json").write_bytes(build.canonical(rules))
    (base / "verifier-inputs.json").write_bytes(build.canonical(pins))
    return source, inputs, output, descriptor, rules


def test_generates_source_bound_policy_without_future_commit_self_reference(adoption_setup):
    source, inputs, output, descriptor, rules = adoption_setup
    adoption.generate_policies(source, inputs, output, descriptor)
    for architecture in adoption.ARCHITECTURES:
        policy = build.read_json((output / architecture / "adoption-policy.json").read_bytes())
        assert policy["source_commit"] == descriptor["producer"]["source_commit"]
        assert "source_commit" not in rules
        assert "input_closure" not in rules
        assert policy["source_sha_allowlist"] == ["c" * 40]
        assert policy["relay_path"] == "vadgr-cua-host.exe"
        assert all("input_sha256" in row for row in policy["files"].values())
    with pytest.raises(FileExistsError):
        adoption.generate_policies(source, inputs, output, descriptor)


@pytest.mark.parametrize("mutation", ["extra-member", "root", "verifier", "license", "wrong-ref"])
def test_generation_refuses_drift_before_any_policy_is_frozen(adoption_setup, mutation):
    source, inputs, output, descriptor, rules = adoption_setup
    if mutation == "extra-member":
        rules["files"]["x86_64"]["extra"] = dict.fromkeys(adoption.SIGNATURE_FIELDS)
        rules["files"]["x86_64"]["extra"]["trust_class"] = "data"
        (source / "packaging/profiles/adoption-rules.json").write_bytes(build.canonical(rules))
    elif mutation == "wrong-ref":
        descriptor["producer"]["ref"] = "refs/heads/feature"
    else:
        name = {"root": "trusted-root.json", "verifier": "gh.exe", "license": "LICENSE"}[mutation]
        (output / "x86_64" / name).write_bytes(b"changed")
    with pytest.raises(ValueError):
        adoption.generate_policies(source, inputs, output, descriptor)
    assert not list(output.rglob("adoption-policy.json"))


@pytest.mark.parametrize(
    "field,value",
    [("source_sha_allowlist", []), ("signer_sha_allowlist", ["*"]), ("expires_at", 1)],
)
def test_reviewed_authority_cannot_be_invented_or_expired(adoption_setup, field, value):
    rules = adoption_setup[-1]
    rules[field] = value
    with pytest.raises(ValueError):
        adoption.validate_rules(rules)


def test_development_wheel_is_explicit_and_cannot_be_a_release_catalog(profile_inputs):
    source, helpers, output, descriptor, _ = profile_inputs
    receipt = build_development(
        source, helpers["x86_64"], "x86_64", descriptor["producer"]["source_commit"], output
    )
    assert receipt["publishable"] is False
    assert receipt["adoption"] == "disabled"
    assert "0development" in receipt["wheel"]["filename"]
    files = build.zip_members((output / receipt["wheel"]["filename"]).read_bytes())
    trust = check.package_trust(files)
    assert trust["development"] is True and "adoption" not in trust
    wheel_metadata = files["vadgr_computer_use-0.7.9.dist-info/WHEEL"].decode()
    assert "Build: 0developmentx8664\n" in wheel_metadata
    assert set(trust["manifest_sha256"]) == {"windows-x86_64", "wsl-x86_64"}
    with pytest.raises(ValueError):
        check.check_catalog(output / "development-receipt.json")


def test_preflight_requires_reviewed_rules_instead_of_committed_future_policy(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(producer, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="adoption-rules.json") as error:
        producer.preflight()
    assert "adoption-policy.json" not in str(error.value)


def test_committed_size_budgets_and_verifier_identity_are_bounded():
    base = Path(__file__).resolve().parents[2] / "packaging/profiles"
    budgets = build.read_json((base / "size-budgets.json").read_bytes())
    assert set(budgets) == {*build.PROFILES, "standalone"}
    assert all(0 < n <= 256 * 1024 * 1024 for n in budgets.values())
    pins = build.read_json((base / "verifier-inputs.json").read_bytes())
    assert pins["version"] == "2.95.0"
    assert set(pins["architectures"]) == {"x86_64", "aarch64"}
    assert (
        pins["architectures"]["x86_64"]["executable_sha256"]
        != pins["architectures"]["aarch64"]["executable_sha256"]
    )


def test_native_workflows_isolate_the_pinned_python_from_owner_packages():
    root = Path(__file__).resolve().parents[2]
    for name in ("development-profile.yml", "profile-wheels.yml"):
        source = (root / ".github/workflows" / name).read_text(encoding="utf-8")
        assert "python.exe -I -m pip install" in source
        assert "python.exe -I scripts/build_windows_broker.py" in source
