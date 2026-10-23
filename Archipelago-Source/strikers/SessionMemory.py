"""Validate a stable save before renewing the game's short-lived client lease."""

import struct

from .Memory import MANAGER_ADDRESS, MANAGER_SIZE, u32, valid_pointer
from .Session import CONNECT, READY, WAITING, bind_save, inspect_save
from .UnlockPatch import SESSION

SCENES = 0x80373E60
LEASE_FRAMES = 300


def publish(read, write, status, *, ready=False):
    # Clear the lease first on denial; ready is committed only after ownership.
    if not ready:
        write(SESSION, bytes(4))
    if read(SESSION + 4, 4) != struct.pack(">I", status):
        write(SESSION + 4, struct.pack(">I", status))
    if ready:
        write(SESSION, struct.pack(">I", LEASE_FRAMES))


def validate_save(read, write, key, *, adopt=False):
    if not key:
        return CONNECT, None
    epoch = bytes(read(SESSION + 12, 4))
    manager = int.from_bytes(read(MANAGER_ADDRESS, 4), "big")
    if not valid_pointer(manager, MANAGER_SIZE):
        return WAITING, None
    before = bytes(read(manager, MANAGER_SIZE))
    scenes = int.from_bytes(read(SCENES, 4), "big")
    at_menu = False
    if valid_pointer(scenes, 0x108):
        stack = bytes(read(scenes, 0x108))
        depth = u32(stack, 4)
        at_menu = 1 <= depth <= 32 and u32(stack, 8 + 4 * (depth - 1)) in (2, 3)
    if before != bytes(read(manager, MANAGER_SIZE)):
        return WAITING, None
    decision = inspect_save(before, key, at_menu=at_menu, adopt=adopt)
    if decision.bind and not bind_save(read, write, manager, before, key):
        return WAITING, None
    if epoch != bytes(read(SESSION + 12, 4)) or manager != int.from_bytes(
        read(MANAGER_ADDRESS, 4), "big"
    ):
        return WAITING, None
    return decision.status, (manager, epoch)


def unchanged_save(read, key, token):
    if token is None:
        return False
    manager, epoch = token
    return (
        epoch == bytes(read(SESSION + 12, 4))
        and manager == int.from_bytes(read(MANAGER_ADDRESS, 4), "big")
        and inspect_save(bytes(read(manager, MANAGER_SIZE)), key).status == READY
    )
