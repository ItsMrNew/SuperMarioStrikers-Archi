"""Reward persistence and emulator counter boundaries, without a running game."""

import json
from types import SimpleNamespace
import unittest

from worlds.strikers.Items import item_table
from worlds.strikers.Rewards import history_fingerprint, reconcile_boosts


def item(name, location=1):
    return SimpleNamespace(item=item_table[name], location=location, player=1)


class RewardAccountingChecks(unittest.TestCase):
    def test_legacy_saved_state_is_compatible_and_not_mutated(self):
        items = [item("Double Power-Up Boost")]
        previous = {
            "item_index": 1,
            "history_fingerprint": history_fingerprint(items),
            "pending_home": 1,
            "pending_away": 0,
            "last_applied_home": 8,
            "last_applied_away": 6,
        }
        snapshot = json.dumps(previous, sort_keys=True)
        updated = reconcile_boosts(previous, items, {"home": 9, "away": 6})
        self.assertEqual(updated["pending_home"], 0)
        self.assertEqual(json.dumps(previous, sort_keys=True), snapshot)

    def test_missing_patch_keeps_queue_until_counters_are_available(self):
        items = [item("Double Power-Up Boost"), item("Power-Up Boost Trap", 2)]
        state = reconcile_boosts({}, items)
        state = json.loads(json.dumps(state))  # Simulate persistence and restart.
        self.assertIsNone(state["last_applied_home"])
        state = reconcile_boosts(state, items, {"home": 8, "away": 12})
        self.assertEqual((state["pending_home"], state["pending_away"]), (2, 2))
        self.assertEqual((state["last_applied_home"], state["last_applied_away"]), (8, 12))

    def test_dolphin_counter_reset_preserves_only_unconsumed_rewards(self):
        items = [item("Double Power-Up Boost")]
        state = reconcile_boosts({}, items, {"home": 0, "away": 0})
        state = reconcile_boosts(state, items, {"home": 1, "away": 0})
        self.assertEqual(state["pending_home"], 1)
        state = reconcile_boosts(state, items, {"home": 0, "away": 0})
        self.assertEqual(state["pending_home"], 1)
        state = reconcile_boosts(state, items, {"home": 1, "away": 0})
        self.assertEqual(state["pending_home"], 0)

    def test_new_items_append_without_replaying_acknowledged_history(self):
        items = [item("Double Power-Up Boost")]
        state = reconcile_boosts({}, items, {"home": 0, "away": 0})
        state = reconcile_boosts(state, items, {"home": 2, "away": 0})
        items += [item("Power-Up Boost", 2), item("Power-Up Boost Trap", 3)]
        state = reconcile_boosts(state, items, {"home": 2, "away": 0})
        self.assertEqual((state["pending_home"], state["pending_away"]), (1, 2))

    def test_replaced_authoritative_history_uses_a_new_counter_baseline(self):
        items = [item("Double Power-Up Boost")]
        state = reconcile_boosts({}, items, {"home": 0, "away": 0})
        replacement = [item("Power-Up Boost Trap", 42)]
        state = reconcile_boosts(state, replacement, {"home": 20, "away": 30})
        self.assertEqual((state["pending_home"], state["pending_away"]), (0, 2))
        self.assertEqual(state["last_applied_away"], 30)

    def test_unlock_nothing_and_victory_items_are_not_boosts(self):
        items = [
            item(name, index) for index, name in enumerate(("Konga Unlock", "Nothing", "Victory"))
        ]
        state = reconcile_boosts({}, items, {"home": 0, "away": 0})
        self.assertEqual((state["pending_home"], state["pending_away"]), (0, 0))
