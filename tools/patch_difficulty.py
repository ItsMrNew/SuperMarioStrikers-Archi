"""Remove the forced Superstar override from the supplied G4QE01 AP executable.

The original mod's ApplyDifficultySettings and its inlined match initialization
copy overwrite the selected skill and saved cup setting with 3 for modes 1
through 8. Make both conditional skips unconditional. Native difficulty selection, human
team detection, training behavior and every AP hook remain intact.
"""

import argparse
import hashlib
from pathlib import Path
import struct

ORIGINAL_SHA256 = "ac654a0554d97aae5acacf24bce47d1741813fbd0cf23d13e0be19e3084ba424"
PATCHES = (
    (0x8017AAD0, bytes.fromhex("40820068"), bytes.fromhex("48000068")),
    (0x8017B760, bytes.fromhex("40820064"), bytes.fromhex("48000064")),
)


def file_offset(data, address):
    offsets = struct.unpack_from(">18I", data, 0)
    addresses = struct.unpack_from(">18I", data, 0x48)
    sizes = struct.unpack_from(">18I", data, 0x90)
    for offset, start, size in zip(offsets, addresses, sizes):
        if start <= address and address + 4 <= start + size:
            return offset + address - start
    raise ValueError(f"Address {address:#x} is outside the DOL sections")


def unlock_difficulty(data):
    original = bytearray(data)
    for address, old, new in PATCHES:
        offset = file_offset(data, address)
        if original[offset : offset + 4] not in (old, new):
            raise ValueError("Unexpected difficulty instruction; refusing to patch")
        original[offset : offset + 4] = old
    if hashlib.sha256(original).hexdigest() != ORIGINAL_SHA256:
        raise ValueError("Unsupported executable; expected the original G4QE01 AP patch")
    for address, _, new in PATCHES:
        offset = file_offset(data, address)
        original[offset : offset + 4] = new
    return bytes(original)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path, help="A separate output path; input is preserved")
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("Input and output must be separate paths")
    result = unlock_difficulty(args.input.read_bytes())
    args.output.write_bytes(result)
    print(f"{args.output}: SHA256 {hashlib.sha256(result).hexdigest()}")


if __name__ == "__main__":
    main()
