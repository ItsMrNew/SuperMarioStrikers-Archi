"""Volatile native cup-access setting. Never modifies save data or trophy bits."""

from .UnlockPatch import HOOKS

CUP_ACCESS_MAGIC_ADDRESS = 0x8017AB30
CUP_ACCESS_SETTING_ADDRESS = 0x8017AB34
CUP_ACCESS_MAGIC = bytes.fromhex("43555033")
CUP_ACCESS_SIGNATURES = {
    0x8017C4DC: bytes.fromhex("4bffe5f8"),
    0x8017AAD0: bytes.fromhex("48000068"),
    0x8017AAD4: bytes.fromhex(
        "3d808018 818cab34 2c04000b 4182001c 3804fffe 28000002 41810018 71800001"
        "40820018 4800000c 71800002 4082000c 9421fff0 480019d8 38600001 4e800020"
    ),
    CUP_ACCESS_MAGIC_ADDRESS: CUP_ACCESS_MAGIC,
}


def apply_cup_access(read_bytes, write_bytes, setting):
    supported = all(
        read_bytes(address, len(expected)) in (expected, HOOKS.get(address, expected))
        for address, expected in CUP_ACCESS_SIGNATURES.items()
    )
    if not supported:
        return setting == 0
    value = int(setting).to_bytes(4, "big")
    if read_bytes(CUP_ACCESS_SETTING_ADDRESS, 4) != value:
        write_bytes(CUP_ACCESS_SETTING_ADDRESS, value)
    return True
