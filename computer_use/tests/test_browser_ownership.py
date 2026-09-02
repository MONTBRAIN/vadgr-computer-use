import pytest

from computer_use.browser.ownership import OwnershipConflict, OwnershipRegistry


def registry():
    value = OwnershipRegistry()
    value.observe("p", [{"window_id": 1, "tabs": [{"tab_id": 10}, {"tab_id": 11}]}])
    return value


def test_window_lease_dominates_all_child_tabs():
    leases = registry()
    window = leases.claim_window("p", 1, "a")
    assert leases.require("p", 1, 10, "a") == window
    with pytest.raises(OwnershipConflict) as caught:
        leases.claim_tab("p", 1, 11, "b")
    assert caught.value.code == "target_owned_by_another_client"


def test_tab_claim_does_not_grant_shared_window():
    leases = registry()
    tab = leases.claim_tab("p", 1, 10, "a")
    assert leases.require("p", 1, 10, "a") == tab
    with pytest.raises(OwnershipConflict):
        leases.claim_window("p", 1, "b")
    other = leases.claim_tab("p", 1, 11, "b")
    assert other.owner_id == "b"


def test_release_fences_old_revision_and_keeps_target_unowned():
    leases = registry()
    lease = leases.claim_tab("p", 1, 10, "a")
    leases.release_tab("p", 10, "a")
    assert leases.describe("p", 1, 10, "b")["state"] == "unowned"
    replacement = leases.claim_tab("p", 1, 10, "b")
    assert replacement.revision > lease.revision
    with pytest.raises(OwnershipConflict):
        leases.require("p", 1, 10, "b", revision=lease.revision)


def test_disconnected_owner_becomes_explicitly_reclaimable():
    leases = registry()
    leases.claim_window("p", 1, "a")
    leases.orphan_client("a")
    assert leases.describe("p", 1, 10, "b")["state"] == "orphaned"
    assert leases.claim_window("p", 1, "b").owner_id == "b"


def test_opener_child_inherits_tab_or_popup_window_owner():
    leases = registry()
    leases.claim_tab("p", 1, 10, "a")
    leases.observe(
        "p",
        [
            {
                "window_id": 1,
                "tabs": [
                    {"tab_id": 10},
                    {"tab_id": 12, "opener_tab_id": 10},
                ],
            },
            {"window_id": 2, "tabs": [{"tab_id": 20, "opener_tab_id": 10}]},
        ],
    )
    assert leases.describe("p", 1, 12, "a")["state"] == "mine"
    assert leases.describe("p", 2, 20, "a")["scope"] == "window"


def test_recovered_epoch_marks_only_rediscovered_targets_orphaned():
    leases = OwnershipRegistry(orphan_on_first_observe=True)
    leases.observe("p", [{"window_id": 1, "tabs": [{"tab_id": 10}, {"tab_id": 11}]}])
    assert leases.describe("p", 1, 10, "a")["state"] == "orphaned"
    assert leases.claim_tab("p", 1, 10, "a").owner_id == "a"
    assert leases.describe("p", 1, 10, "a")["state"] == "mine"
    assert leases.describe("p", 1, 11, "a")["state"] == "orphaned"
    leases.observe(
        "p",
        [{"window_id": 1, "tabs": [{"tab_id": 10}, {"tab_id": 11}, {"tab_id": 12}]}],
    )
    assert leases.describe("p", 1, 12, "a")["state"] == "unowned"


def test_observation_prunes_closed_targets_and_their_leases():
    leases = registry()
    leases.claim_tab("p", 1, 10, "a")
    leases.observe("p", [{"window_id": 1, "tabs": [{"tab_id": 11}]}])
    assert leases.describe("p", 1, 10, "a")["state"] == "unowned"
