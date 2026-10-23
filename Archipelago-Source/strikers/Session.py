"""Bind a save to one AP slot without changing its achievements or file format.

G4QE01 serializes all 0x113C UserInfo bytes and checksums them. Six bytes of
VisualSettings alignment padding plus two after mTrophies are unused by native
fields. Visual option backup/restore copies the padding; defaults change fields
only. The marker is persisted by the game's next ordinary save.
"""

import hashlib
from dataclasses import dataclass

from .Data import CUPS, MILESTONES
from .Memory import MANAGER_SIZE, TROPHIES, USER_INFO, saved_locations

TAG_OFFSETS = tuple(USER_INFO + n for n in (0x4E, 0x4F, 0x25, 0x26, 0x27, 0x2D, 0x2E, 0x2F))
CONNECT, READY, WRONG_SAVE, LEGACY_SAVE, WAITING, BAD_PATCH = range(6)
MESSAGES = {
    CONNECT: "Connect the Strikers client to your Archipelago slot.",
    READY: "Save verified. Archipelago is ready.",
    WRONG_SAVE: "This save belongs to another Archipelago slot. Load the matching save or a fresh save.",
    LEGACY_SAVE: "This unbound save already has progress. Use a fresh save; /adoptsave confirm can explicitly migrate it.",
    WAITING: "Return to the title or main menu to bind this save.",
    BAD_PATCH: "Install the supplied Riivolution patch and boot the game again.",
}


def save_tag(key):
    return b"AP" + hashlib.sha256(key.encode("utf-8")).digest()[:6]


def read_tag(data):
    return bytes(data[offset] for offset in TAG_OFFSETS)


def pristine(data):
    if len(data) != MANAGER_SIZE or any(data[TROPHIES : TROPHIES + 2]):
        return False
    if any(
        data[USER_INFO + offset : USER_INFO + offset + 2] != b"\0\0"
        for offset, _ in MILESTONES.values()
    ):
        return False
    if any(data[cup.offset + 0xE] or (cup.knockout and data[cup.knockout + 0xE]) for cup in CUPS):
        return False
    return not saved_locations(data)


@dataclass(frozen=True)
class SaveDecision:
    status: int
    bind: bool = False


def inspect_save(data, key, *, at_menu=False, adopt=False):
    if len(data) != MANAGER_SIZE or not key:
        return SaveDecision(WAITING)
    tag = read_tag(data)
    if tag == save_tag(key):
        return SaveDecision(READY)
    if tag.startswith(b"AP"):
        return SaveDecision(WRONG_SAVE)
    if not at_menu or data[0x4C38]:
        return SaveDecision(WAITING)
    if not pristine(data) and not adopt:
        return SaveDecision(LEGACY_SAVE)
    return SaveDecision(READY, bind=True)


def bind_save(read, write, manager, before, key):
    """Recheck the full snapshot, commit magic last, and verify every written byte."""
    if bytes(read(manager, MANAGER_SIZE)) != bytes(before):
        return False
    tag = save_tag(key)
    for index in (*range(2, 8), 0, 1):
        write(manager + TAG_OFFSETS[index], tag[index : index + 1])
    after = bytes(read(manager, MANAGER_SIZE))
    expected = bytearray(before)
    for offset, value in zip(TAG_OFFSETS, tag):
        expected[offset] = value
    return after == expected
