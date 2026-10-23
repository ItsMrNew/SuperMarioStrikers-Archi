"""Publish authoritative, volatile unlock masks after verifying the native patch."""

import hashlib
import struct

from .Data import CAPTAINS, CUPS, SIDEKICKS
from .Items import CAPTAIN_ITEMS, CUP_ITEMS, SIDEKICK_ITEMS, item_table
from .Unlocks import randomized, starting
from .UnlockPatch import (
    BASE,
    SIZE,
    CONFIG,
    MAGIC_ADDRESS,
    STATIC_SHA256,
    HOOKS,
    SESSION,
    SESSION_SIZE,
)

CAPTAIN_ICONS = (4, 1, 5, 0, 3, 6, 2, 7, 8)
SIDEKICK_ICONS = (0, 3, 1, 2)


def unlock_masks(options, received):
    ids = {item.item for item in received}
    masks = []
    flags = 0
    for kind, table, entries, bit in (
        (
            "captains",
            CAPTAIN_ITEMS,
            [(name, CAPTAIN_ICONS[index]) for index, name in CAPTAINS.items()],
            1,
        ),
        (
            "sidekicks",
            SIDEKICK_ITEMS,
            [(name, SIDEKICK_ICONS[index]) for index, name in SIDEKICKS.items()],
            2,
        ),
        ("cups", CUP_ITEMS, [(cup.name, cup.trophy_bit) for cup in CUPS], 4),
    ):
        if options.get(f"randomize_{kind}"):
            flags |= bit
        starters = starting(options, kind)
        masks.append(
            sum(
                1 << index
                for name, index in entries
                if name in starters or item_table[table[name]] in ids
            )
        )
    return struct.pack(">4I", flags, *masks)


def valid_patch(read):
    if read(MAGIC_ADDRESS, 4) != b"RST6":
        return False
    data = bytearray(read(BASE, SIZE))
    data[CONFIG - BASE : CONFIG - BASE + 16] = bytes(16)
    data[SESSION - BASE : SESSION - BASE + SESSION_SIZE] = bytes(SESSION_SIZE)
    return hashlib.sha256(data).hexdigest() == STATIC_SHA256 and not any(
        read(address, len(expected)) != expected for address, expected in HOOKS.items()
    )


def apply_unlocks(read, write, options, received):
    if read(MAGIC_ADDRESS, 4) != b"RST6":
        return not randomized(options)
    if not valid_patch(read):
        return False
    desired = unlock_masks(options, received)
    if read(CONFIG, 16) != desired:
        write(CONFIG, desired)
        revision = (int.from_bytes(read(SESSION + 8, 4), "big") + 1) & 0xFFFFFFFF
        write(SESSION + 8, revision.to_bytes(4, "big"))
    return True
