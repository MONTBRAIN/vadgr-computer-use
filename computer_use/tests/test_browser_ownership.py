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


def test_single_tab_reclaim_splits_expired_window_without_claiming_siblings():
    leases = registry()
    old = leases.claim_window("p", 1, "a")
    leases.orphan_client("a")
    claimed = leases.claim_tab("p", 1, 10, "b")
    assert leases.require("p", 1, 10, "b", claimed.revision) == claimed
    assert leases.describe("p", 1, 10, "b")["scope"] == "tab"
    assert leases.describe("p", 1, 11, "b")["state"] == "orphaned"
    assert leases.describe("p", 1, None, "b")["state"] != "mine"
    for client, tab in [("a", 10), ("a", 11), ("b", 11)]:
        with pytest.raises(OwnershipConflict):
            leases.require("p", 1, tab, client, old.revision)
    sibling = leases.claim_tab("p", 1, 11, "c")
    assert leases.require("p", 1, 11, "c", sibling.revision) == sibling
    assert leases.require("p", 1, 10, "b", claimed.revision) == claimed


@pytest.mark.parametrize("popup", [False, True])
def test_released_descendant_does_not_inherit_again_on_observation(popup):
    leases = registry()
    leases.claim_tab("p", 1, 10, "a")
    child = {"tab_id": 12, "opener_tab_id": 10}
    windows = [{"window_id": 1, "tabs": [{"tab_id": 10}, {"tab_id": 11}]}]
    if popup:
        windows.append({"window_id": 2, "tabs": [child]})
    else:
        windows[0]["tabs"].append(child)
    wid = 2 if popup else 1
    leases.observe("p", windows)
    assert leases.describe("p", wid, 12, "a")["state"] == "mine"
    if popup:
        leases.release_window("p", wid, "a")
    else:
        leases.release_tab("p", 12, "a")
    for _ in range(3):
        leases.observe("p", windows)
        assert leases.describe("p", wid, 12, "b")["state"] == "unowned"
    claim = leases.claim_window("p", wid, "b") if popup else leases.claim_tab("p", wid, 12, "b")
    leases.observe("p", windows)
    assert leases.require("p", wid, 12, "b", claim.revision) == claim
    with pytest.raises(OwnershipConflict):
        leases.require("p", wid, 12, "a")
    assert leases.describe("p", 1, 10, "a")["state"] == "mine"
    assert leases.describe("p", 1, 11, "a")["state"] == "unowned"


def test_new_descendant_does_not_reclaim_an_existing_released_popup_window():
    leases = registry()
    leases.claim_tab("p", 1, 10, "a")
    windows = [
        {"window_id": 1, "tabs": [{"tab_id": 10}]},
        {"window_id": 2, "tabs": [{"tab_id": 20, "opener_tab_id": 10}]},
    ]
    leases.observe("p", windows)
    leases.release_window("p", 2, "a")
    windows[1]["tabs"].append({"tab_id": 21, "opener_tab_id": 10})
    leases.observe("p", windows)
    for tid in [20, 21]:
        assert leases.describe("p", 2, tid, "a")["state"] == "unowned"


def test_closed_target_id_is_not_retained_as_a_release_tombstone():
    leases = registry()
    leases.claim_tab("p", 1, 10, "a")
    initial = [{"window_id": 1, "tabs": [{"tab_id": 10}]}]
    with_child = [{"window_id": 1, "tabs": [{"tab_id": 10}, {"tab_id": 12, "opener_tab_id": 10}]}]
    leases.observe("p", with_child)
    leases.release_tab("p", 12, "a")
    leases.observe("p", initial)
    leases.observe("p", with_child)
    assert leases.describe("p", 1, 12, "a")["state"] == "mine"


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("popup", [False, True])
def test_new_descendant_chain_inherits_independent_of_snapshot_order(reverse, popup):
    leases = registry()
    leases.claim_tab("p", 1, 10, "a")
    children = [{"tab_id": 20, "opener_tab_id": 10}, {"tab_id": 30, "opener_tab_id": 20}]
    if reverse:
        children.reverse()
    if popup:
        windows = [{"window_id": child["tab_id"], "tabs": [child]} for child in children]
        windows.append({"window_id": 1, "tabs": [{"tab_id": 10}]})
    else:
        windows = [{"window_id": 1, "tabs": [{"tab_id": 10}, *children]}]
    leases.observe("p", windows)
    for tid in [20, 30]:
        wid = tid if popup else 1
        assert leases.describe("p", wid, tid, "a")["state"] == "mine"


def test_inheritance_stops_at_released_ancestor_missing_opener_and_cycle():
    leases = registry()
    leases.claim_tab("p", 1, 10, "a")
    tabs = [{"tab_id": 10}, {"tab_id": 20, "opener_tab_id": 10}]
    leases.observe("p", [{"window_id": 1, "tabs": tabs}])
    leases.release_tab("p", 20, "a")
    tabs += [
        {"tab_id": 30, "opener_tab_id": 20},
        {"tab_id": 40, "opener_tab_id": 999},
        {"tab_id": 50, "opener_tab_id": 60},
        {"tab_id": 60, "opener_tab_id": 50},
    ]
    leases.observe("p", [{"window_id": 1, "tabs": tabs}])
    for tid in [20, 30, 40, 50, 60]:
        assert leases.describe("p", 1, tid, "a")["state"] == "unowned"
