"""Install optional roster/cup gates into the supported G4QE01 AP base DOL.

An additional DOL text section sits above BSS and both boot stacks. The two
OSInit arena-low assignments are clamped above it BEFORE the OS clears/allocates
the arena. This reserves 0x3900 bytes beyond the original 0x8038A700 arena low.
No save flags, trophy bits, fixture records or CPU cup rosters are overwritten.
"""

import argparse
import hashlib
import json
from pathlib import Path
import struct

from tools.patch_difficulty import file_offset
from tools.patch_session import SESSION, SESSION_SIZE, emit_session, write_texts
from tools.ppc import Assembler, BEQ, BNE, BGT, BGE, BLR, d, mr, shift_right, x

BASE_SHA256 = "1e9cfbfee7db2a2fd3e7751050b755bc092b249d3c94e9ed46cc2a8c5f5e338b"
BASE = 0x8038B000
SIZE = 0x3000
DATA = BASE + 0x1700
MAGIC = b"RST6"
CONFIG = DATA + 4  # flags, captain icon mask, sidekick icon mask, cup mask
MANIFEST = 0x2800
QUALIFIED = 0x8017C4DC
PHASE = 0x800C0D04
PROCEED = 0x800DA6E0
CONTINUE = 0x800DC5DC
SUPER_TEAM = 0x80176A48
GRID_UPDATE = ((0x800C1E68, 1, 4), (0x800C2D80, 2, 8))
SUPER_GRID_CALLS = (0x800C1E10, 0x800C1E98, 0x800C21B0)
DRAW = 0x800983E4
LOCK_TEXT = "Find this cup's unlock item."


def build(original):
    if hashlib.sha256(original).hexdigest() != BASE_SHA256:
        raise ValueError("Expected the supported G4QE01 AP base executable (BASE_SHA256)")
    a = Assembler(BASE)
    changes = {}

    def hook(address, label):
        # Hook targets are emitted at their labelled addresses below.
        changes[address] = label

    def enabled(bit, fallback):
        a.load(32, 12, CONFIG)
        a.emit(d(28, 12, 0, bit))
        a.branch(fallback, condition=BEQ)

    def original_entry(address):
        a.emit(struct.unpack_from(">I", original, file_offset(original, address))[0])
        a.branch(address + 4)

    def mask_bit(mask_offset, index_reg, result=0):
        a.load(32, 12, CONFIG + mask_offset)
        a.emit(shift_right(result, 12, index_reg), d(28, result, result, 1))

    def require_session():
        a.load(32, 12, SESSION)
        a.emit(d(11, 0, 12, 0))
        a.branch("session_deny", condition=BEQ)

    # OSInit only. Other OSSetArenaLo users retain their original behaviour.
    a.label("arena")
    a.address(12, BASE + SIZE)
    a.emit(x(31, 0, 3, 12, 32))  # cmplw r3,r12
    a.branch("arena_set", condition=BGE)
    a.emit(mr(3, 12))
    a.label("arena_set")
    a.branch(0x80254CE4)
    for address in (0x80253A44, 0x80253A80):
        hook(address, ("arena", True))

    # IsUserQualified: randomized mode bypasses ALL natural/config unlocks.
    a.label("qualified")
    enabled(4, "qualified_native")
    a.emit(d(11, 0, 4, 11))
    a.branch("super_menu", condition=BEQ)
    a.emit(d(14, 0, 4, -1), d(10, 0, 0, 7))
    a.branch("no", condition=BGT)
    mask_bit(12, 0, 3)
    a.emit(BLR)
    a.label("super_menu")
    a.load(32, 12, CONFIG + 12)
    a.emit(d(28, 12, 0, 0xF0))
    a.branch("no", condition=BEQ)
    a.label("yes")
    a.emit(d(14, 3, 0, 1), BLR)
    a.label("no")
    a.emit(d(14, 3, 0, 0), BLR)
    a.label("qualified_native")
    a.branch(0x8017AAD4)  # Existing starting_cup_unlocks trampoline.
    hook(QUALIFIED, ("qualified", False))

    # Replace both inline DisplayCupCanProceed copies. Keep their original
    # native paths intact when randomization is off (including Mushroom).
    for label, address, end, result in (
        ("display", 0x800DAFC8, 0x800DB04C, 27),
        ("confirm", 0x800DBBB4, 0x800DBC34, 29),
    ):
        a.label(label)
        if label == "display":
            a.emit(mr(28, 3))  # displaced instruction at address+4
        enabled(4, label + "_native")
        a.emit(d(32, 0, 31, 0x24))
        mask_bit(12, 0, result)
        a.branch(end)
        a.label(label + "_native")
        a.emit(d(34, 0, 31, 0x1C))
        a.branch(address + (8 if label == "display" else 4))
        hook(address, (label, False))

    a.label("proceed")
    require_session()
    enabled(4, "proceed_native")
    a.emit(d(32, 0, 3, 0x24))
    mask_bit(12, 0)
    a.branch("deny", condition=BEQ)
    a.label("proceed_native")
    original_entry(PROCEED)
    hook(PROCEED, ("proceed", False))

    # Native locked descriptions exist only for Flower/Star/Bowser and describe
    # natural qualification. Supply a valid item message for all eight AP locks.
    a.label("locked_text")
    enabled(4, "locked_text_native")
    a.address(12, DATA + 0x40)
    # Inline TLTextInstance::SetString, retaining the existing black trophy.
    a.emit(
        d(36, 12, 26, 0xF4),
        d(14, 0, 0, 0),
        d(36, 0, 26, 0xEC),
        d(32, 0, 26, 0x90),
        0x54000776,  # rlwinm r0,r0,0,29,27: clear localized-string flag
        d(36, 0, 26, 0x90),
    )
    a.branch(0x800DB7AC)
    a.label("locked_text_native")
    original_entry(0x800DB74C)
    hook(0x800DB74C, ("locked_text", False))

    # Rebuilding a captain grid must not permanently cache an AP-locked Super
    # Team as inactive. The update wrapper and confirmation gate enforce AP
    # ownership; these UI-only calls retain native opponent exclusions instead.
    a.label("super_grid")
    enabled(1, "super_grid_native")
    a.emit(d(14, 3, 0, 1), BLR)
    a.label("super_grid_native")
    a.branch(SUPER_TEAM)
    for address in SUPER_GRID_CALLS:
        hook(address, ("super_grid", True))

    # Captain and sidekick confirm share one component phase transition.
    # Guard both grids; native captain exclusivity remains in the original body.
    a.label("phase")
    require_session()
    a.emit(d(32, 0, 3, 0), d(11, 0, 0, 1))
    a.branch("phase_captain", condition=BEQ)
    a.emit(d(11, 0, 0, 2))
    a.branch("phase_native", condition=BNE)
    enabled(2, "phase_native")
    a.emit(d(14, 10, 0, 0xA4), d(14, 11, 0, 8))
    a.branch("phase_map")
    a.label("phase_captain")
    enabled(1, "phase_native")
    a.emit(d(14, 10, 0, 0x9C), d(14, 11, 0, 4))
    a.label("phase_map")
    a.emit(
        d(32, 12, 3, 4),
        d(32, 0, 3, 8),
        d(7, 0, 0, 4),
        x(31, 12, 12, 0, 266),
        x(31, 12, 12, 10, 23),
        d(32, 12, 12, 8),
        d(34, 0, 12, 0x385),
        d(7, 0, 0, 28),
        x(31, 12, 12, 0, 266),
        d(32, 0, 12, 4),
    )
    a.address(12, CONFIG)
    a.emit(x(31, 12, 12, 11, 23), shift_right(0, 12, 0), d(28, 0, 0, 1))
    a.branch("deny", condition=BEQ)
    a.label("phase_native")
    original_entry(PHASE)
    hook(PHASE, ("phase", False))

    a.label("deny")
    a.address(3, 0x802AB4E8)  # existing sfx_deny string
    a.emit(d(14, 4, 0, 0))
    a.branch(0x8009F940)  # tail call preserves the caller's LR/stack

    a.label("super_team")
    enabled(1, "super_team_native")
    a.emit(d(14, 0, 0, 8))
    mask_bit(4, 0, 3)
    a.emit(BLR)
    a.label("super_team_native")
    original_entry(SUPER_TEAM)
    hook(SUPER_TEAM, ("super_team", False))

    # Resume guards use saved team IDs, which differ from the selection icons.
    a.label("continue")
    require_session()
    a.emit(d(32, 10, 13, -0x5248), d(32, 10, 10, 0x4960))
    enabled(1, "continue_side")
    a.emit(d(32, 0, 10, 0), d(10, 0, 0, 8))
    a.branch("resume_deny", condition=BGT)
    a.address(12, DATA + 0x20)
    a.emit(x(31, 0, 12, 0, 87))  # lbzx icon from team ID
    mask_bit(4, 0)
    a.branch("resume_deny", condition=BEQ)
    a.label("continue_side")
    enabled(2, "continue_native")
    a.emit(d(32, 0, 10, 0), d(11, 0, 0, 8))
    a.branch("continue_native", condition=BEQ)
    a.emit(d(32, 0, 10, 4), d(10, 0, 0, 3))
    a.branch("resume_deny", condition=BGT)
    a.address(12, DATA + 0x30)
    a.emit(x(31, 0, 12, 0, 87))
    mask_bit(8, 0)
    a.branch("resume_deny", condition=BEQ)
    a.label("continue_native")
    original_entry(CONTINUE)
    hook(CONTINUE, ("continue", False))

    # Temporarily mask active entries during native random selection and drawing.
    # Restore only AP-disabled entries afterwards, preserving native updates and
    # the opposite captain's exclusion. New rewards can re-enable on the next frame.
    for address, bit, offset in GRID_UPDATE:
        label = f"grid_{bit}"
        a.label(label)
        enabled(bit, label + "_native")
        a.emit(
            d(37, 1, 1, -0x50),
            0x7C0802A6,
            d(36, 0, 1, 0x54),
            d(36, 30, 1, 0x48),
            d(36, 31, 1, 0x4C),
            mr(30, 3),
            d(32, 31, 3, 8),
            d(14, 9, 0, 0),
            d(14, 10, 31, 4),
        )
        a.load(32, 12, CONFIG + offset)
        a.emit(d(36, 12, 1, 0x20))
        a.label(label + "_mask")
        a.emit(d(34, 0, 31, 0x384), x(31, 0, 9, 0, 0))  # cmpw index,count
        a.branch(label + "_call", condition=BGE)
        a.emit(
            d(32, 0, 10, 0),
            shift_right(11, 12, 0),
            d(28, 11, 11, 1),
            d(34, 0, 10, 8),
            d(14, 8, 1, 0x10),
            x(31, 0, 8, 9, 215),
            x(31, 0, 0, 11, 28),
            d(38, 0, 10, 8),
            d(14, 10, 10, 28),
            d(14, 9, 9, 1),
        )
        a.branch(label + "_mask")
        a.label(label + "_call")
        a.emit(mr(3, 30))
        a.branch(label + "_native", link=True)
        a.emit(mr(3, 31))
        a.branch(DRAW, link=True)
        a.emit(d(32, 12, 1, 0x20))
        a.emit(d(14, 9, 0, 0), d(14, 10, 31, 4))
        a.label(label + "_restore")
        a.emit(d(34, 0, 31, 0x384), x(31, 0, 9, 0, 0))
        a.branch(label + "_return", condition=BGE)
        a.emit(d(32, 0, 10, 0), shift_right(11, 12, 0), d(28, 11, 11, 1))
        a.branch(label + "_next", condition=BNE)
        a.emit(d(14, 8, 1, 0x10), x(31, 0, 8, 9, 87), d(38, 0, 10, 8))
        a.label(label + "_next")
        a.emit(d(14, 10, 10, 28), d(14, 9, 9, 1))
        a.branch(label + "_restore")
        a.label(label + "_return")
        a.emit(
            d(32, 0, 1, 0x54),
            d(32, 30, 1, 0x48),
            d(32, 31, 1, 0x4C),
            0x7C0803A6,
            d(14, 1, 1, 0x50),
            BLR,
        )
        a.label(label + "_native")
        original_entry(address)
        hook(address, (label, False))

    emit_session(a, hook, original_entry)
    section = bytearray(SIZE)
    write_texts(section, BASE)
    code = a.finish()
    assert len(code) < DATA - BASE
    section[: len(code)] = code
    section[DATA - BASE : DATA - BASE + 4] = MAGIC
    section[DATA - BASE + 0x20 : DATA - BASE + 0x29] = bytes((4, 1, 5, 0, 3, 6, 2, 7, 8))
    section[DATA - BASE + 0x30 : DATA - BASE + 0x34] = bytes((0, 3, 1, 2))
    locked_text = (LOCK_TEXT + "\0").encode("utf-16-be")
    assert len(locked_text) < MANIFEST - (DATA - BASE + 0x40)
    section[DATA - BASE + 0x40 : DATA - BASE + 0x40 + len(locked_text)] = locked_text
    signatures = {}
    manifest = {}
    result = bytearray(original)
    for address, value in changes.items():
        if isinstance(value, tuple):
            label, link = value
            value = struct.pack(
                ">I", 0x48000000 | (a.labels[label] - address) & 0x3FFFFFC | int(link)
            )
        pos = file_offset(original, address)
        manifest[str(address)] = original[pos : pos + len(value)].hex()
        result[pos : pos + len(value)] = value
        signatures[address] = value
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    assert len(encoded) < SIZE - MANIFEST - 4
    struct.pack_into(">I", section, MANIFEST, len(encoded))
    section[MANIFEST + 4 : MANIFEST + 4 + len(encoded)] = encoded
    for header, value in ((8, len(result)), (0x50, BASE), (0x98, SIZE)):
        assert struct.unpack_from(">I", result, header)[0] == 0
        struct.pack_into(">I", result, header, value)
    result.extend(section)
    return bytes(result), signatures, a.labels


def remove_unlocks(data):
    if hashlib.sha256(data).hexdigest() == BASE_SHA256:
        return data
    # The supported compact-section binary stores its manifest at 0x1800.
    # Restore its embedded instructions and verify the entire recovered base.
    if (
        hashlib.sha256(data).hexdigest()
        == "73db018a8e9260eecca236e05a072eb1174093a25790b846dc04f7244eeed1b2"
    ):
        offset = struct.unpack_from(">I", data, 8)[0]
        length = struct.unpack_from(">I", data, offset + 0x1800)[0]
        manifest = json.loads(data[offset + 0x1804 : offset + 0x1804 + length])
        original = bytearray(data[:offset])
        for address, value in manifest.items():
            pos = file_offset(original, int(address))
            original[pos : pos + len(bytes.fromhex(value))] = bytes.fromhex(value)
        for header in (8, 0x50, 0x98):
            struct.pack_into(">I", original, header, 0)
        if hashlib.sha256(original).hexdigest() != BASE_SHA256:
            raise ValueError("Invalid compact-section patch base")
        return bytes(original)
    if struct.unpack_from(">I", data, 0x50)[0] != BASE:
        raise ValueError("Unsupported executable; missing unlock section")
    offset = struct.unpack_from(">I", data, 8)[0]
    section = data[offset:]
    if len(section) != SIZE or section[DATA - BASE : DATA - BASE + 4] != MAGIC:
        raise ValueError("Invalid unlock section")
    length = struct.unpack_from(">I", section, MANIFEST)[0]
    if length > SIZE - MANIFEST - 4:
        raise ValueError("Invalid unlock manifest")
    manifest = json.loads(section[MANIFEST + 4 : MANIFEST + 4 + length])
    original = bytearray(data[:offset])
    for address, value in manifest.items():
        pos = file_offset(original, int(address))
        old = bytes.fromhex(value)
        original[pos : pos + len(old)] = old
    for header in (8, 0x50, 0x98):
        struct.pack_into(">I", original, header, 0)
    expected, _, _ = build(original)
    if expected != data:
        raise ValueError("Modified unlock patch; refusing to overwrite")
    return bytes(original)


def patch_unlocks(data):
    return build(remove_unlocks(data))[0]


def signature_source(data):
    """Client manifest generated from the exact reproducible patch."""
    expected, hooks, _ = build(remove_unlocks(data))
    lines = [
        '"""Generated native signatures; use tools.patch_unlocks --signatures to regenerate."""',
        "",
    ]
    for name, value in (
        ("BASE", BASE),
        ("SIZE", SIZE),
        ("CONFIG", CONFIG),
        ("MAGIC_ADDRESS", DATA),
        ("SESSION", SESSION),
        ("SESSION_SIZE", SESSION_SIZE),
    ):
        lines.append(f"{name} = {value:#x}")
    lines.append(f'STATIC_SHA256 = "{hashlib.sha256(expected[-SIZE:]).hexdigest()}"')
    lines.append("HOOKS = {")
    lines.extend(
        f'    {address:#x}: bytes.fromhex("{code.hex()}"),' for address, code in hooks.items()
    )
    lines.append("}\n")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--signatures", type=Path, help="Regenerate the client UnlockPatch.py manifest"
    )
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("Input and output must be separate paths")
    data = patch_unlocks(args.input.read_bytes())
    args.output.write_bytes(data)
    if args.signatures:
        args.signatures.write_text(signature_source(data), encoding="utf-8")
    print(hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    main()
