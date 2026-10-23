"""Add independent cup access to the difficulty-unlocked G4QE01 AP executable.

Reuse only the forced-difficulty block skipped by patch_difficulty. IsUserQualified
checks a volatile setting before its original body. No save/trophy data is written.
The setting defaults to zero at boot and is maintained by the connected client.
"""

import argparse
import hashlib
from pathlib import Path
import struct

from tools.patch_difficulty import file_offset

BASE_SHA256 = "41e2c64bc51ad24e64fccb3e7e790928f0701c44e992021b10822717310167f8"
HOOK = 0x8017C4DC
CAVE = 0x8017AAD4
MAGIC_ADDRESS = 0x8017AB30
SETTING_ADDRESS = 0x8017AB34
MAGIC = 0x43555033  # CUP3
ORIGINAL_CAVE = bytes.fromhex(
    "80a34954 2c050005 40800018 2c050001 40800008 4800000c 38800001 48000008"
    "38800000 5480063f 40820024 2c050009 40800018 2c050005 40800008 4800000c"
    "38800001 48000008 38800000 5480063f 41820014 80834960 38000003 38e00003 90040010"
)


def branch(source, target):
    return 0x48000000 | ((target - source) & 0x03FFFFFC)


# r3=this, r4=mode. Only volatile r0/r12/CR0 are changed before the native body.
# Regular mode queries 2..4 use bit 0; the Super menu query 11 uses bit 1.
WORDS = [
    0x3D808018,  # lis r12,0x8018
    0x818CAB34,  # lwz r12,-0x54cc(r12)
    0x2C04000B,  # cmpwi r4,11
    0x4182001C,  # beq super
    0x3804FFFE,  # addi r0,r4,-2
    0x28000002,  # cmplwi r0,2
    0x41810018,  # bgt native
    0x71800001,  # andi. r0,r12,1
    0x40820018,  # bne yes
    0x4800000C,  # b native
    0x71800002,  # super: andi. r0,r12,2
    0x4082000C,  # bne yes
    0x9421FFF0,  # native: original stwu r1,-16(r1)
    branch(CAVE + 13 * 4, HOOK + 4),
    0x38600001,  # yes: li r3,1
    0x4E800020,  # blr
]
CAVE_CODE = struct.pack(">16I", *WORDS)
PATCHED_CAVE = CAVE_CODE + struct.pack(">9I", *([0x60000000] * 7), MAGIC, 0)
PATCHES = (
    (HOOK, bytes.fromhex("9421fff0"), struct.pack(">I", branch(HOOK, CAVE))),
    (CAVE, ORIGINAL_CAVE, PATCHED_CAVE),
)


def remove_cup_access(data):
    original = bytearray(data)
    for address, old, new in PATCHES:
        offset = file_offset(data, address)
        if original[offset : offset + len(old)] not in (old, new):
            raise ValueError("Unexpected cup-access instructions; refusing to patch")
        original[offset : offset + len(old)] = old
    if hashlib.sha256(original).hexdigest() != BASE_SHA256:
        raise ValueError("Unsupported executable; expected the difficulty-unlocked G4QE01 AP base")
    return bytes(original)


def patch_cup_access(data):
    result = bytearray(remove_cup_access(data))
    for address, _, new in PATCHES:
        offset = file_offset(result, address)
        result[offset : offset + len(new)] = new
    return bytes(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("Input and output must be separate paths")
    result = patch_cup_access(args.input.read_bytes())
    args.output.write_bytes(result)
    print(f"{args.output}: SHA256 {hashlib.sha256(result).hexdigest()}")


if __name__ == "__main__":
    main()
