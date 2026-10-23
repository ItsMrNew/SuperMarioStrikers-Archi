"""Power-up queue accounting without Dolphin reads, writes, or persistence I/O."""

import hashlib

from .Items import item_table, powerup_item_units


BOOST_STORAGE_CATEGORY = "strikers_powerup_boosts"
BOOST_OWNER_KEY = "active_owner"
# Keep these persisted key names stable. They identify the human player and
# opponent, even when the human is the away team.
BOOST_CHANNELS = ("home", "away")
BOOST_UNITS = {item_table[name]: units for name, units in powerup_item_units.items()}
MAX_COUNTER = 0xFFFFFFFF


def history_fingerprint(items):
    history = "|".join(f"{entry.item}:{entry.location}:{entry.player}" for entry in items)
    return hashlib.sha256(history.encode("utf-8")).hexdigest()


def settle_boosts(previous, applied_counts):
    """Settle the current owner's queue before handing the mailboxes over."""
    state = dict(previous)
    for channel in BOOST_CHANNELS:
        applied = applied_counts[channel]
        last_applied = state.get(f"last_applied_{channel}")
        if last_applied is not None and applied >= last_applied:
            state[f"pending_{channel}"] = max(
                0, state.get(f"pending_{channel}", 0) - (applied - last_applied)
            )
        state[f"last_applied_{channel}"] = applied
    return state


def rebase_restored_mailboxes(previous, applied_counts, request_counts):
    """Do not count acknowledgements from a different saved mailbox state.

    Only the client writes request counters. A request differing from the last
    published total indicates a reset or restored state, even if its applied
    counter is larger (for example, loading a state after restarting Dolphin).
    """
    for channel in BOOST_CHANNELS:
        last = previous.get(f"last_applied_{channel}")
        if last is None:
            continue
        expected = last + previous.get(f"pending_{channel}", 0)
        if expected <= MAX_COUNTER and request_counts[channel] != expected:
            state = dict(previous)
            for name in BOOST_CHANNELS:
                state[f"last_applied_{name}"] = applied_counts[name]
            return state
    return previous


def reconcile_boosts(previous, items, applied_counts=None):
    """Return updated state; consume only acknowledgements for this history.

    The caller must wait for the authoritative initial item history. A new
    history starts from the current game counters, which may include rewards
    delivered before this seed connected. Missing patch counters are left
    uninitialized until they can be read. Counter rollback means a game reset;
    it must not discard pending items or replay already acknowledged items.
    """
    state = dict(previous)
    index = min(max(int(state.get("item_index", 0)), 0), len(items))
    if state.get("history_fingerprint") != history_fingerprint(items[:index]):
        state = {"item_index": 0}
        for channel in BOOST_CHANNELS:
            state[f"pending_{channel}"] = 0
            state[f"last_applied_{channel}"] = None
        index = 0

    for entry in items[index:]:
        for channel, units in zip(BOOST_CHANNELS, BOOST_UNITS.get(entry.item, (0, 0))):
            state[f"pending_{channel}"] += units
    state["item_index"] = len(items)
    state["history_fingerprint"] = history_fingerprint(items)

    if applied_counts is not None:
        state = settle_boosts(state, applied_counts)
    return state
