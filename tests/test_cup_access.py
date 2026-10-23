import hashlib
import itertools
from pathlib import Path
import struct
import unittest

from tools.patch_cup_access import (
    BASE_SHA256,
    CAVE,
    HOOK,
    SETTING_ADDRESS,
    patch_cup_access,
    remove_cup_access,
)
from tools.patch_difficulty import file_offset
from tools.patch_unlocks import remove_unlocks
from worlds.strikers.CupAccess import (
    CUP_ACCESS_SETTING_ADDRESS,
    CUP_ACCESS_SIGNATURES,
    apply_cup_access,
)

try:
    import unicorn
    from unicorn import ppc_const as ppc
except ImportError:
    unicorn = None

DOL = Path(__file__).resolve().parents[1] / "Riivolution/Riivolution/StrikersAP/main.dol"


class CupAccessTests(unittest.TestCase):
    def test_patch_reversible_idempotent_and_signatures(self):
        data = remove_unlocks(DOL.read_bytes())
        original = remove_cup_access(data)
        self.assertEqual(hashlib.sha256(original).hexdigest(), BASE_SHA256)
        self.assertEqual(patch_cup_access(original), data)
        self.assertEqual(patch_cup_access(data), data)
        for address, expected in CUP_ACCESS_SIGNATURES.items():
            offset = file_offset(data, address)
            self.assertEqual(data[offset : offset + len(expected)], expected)

    def test_unexpected_binary_or_hook_rejected(self):
        for offset in (
            -1,
            file_offset(DOL.read_bytes(), HOOK),
            file_offset(DOL.read_bytes(), CAVE),
        ):
            data = bytearray(DOL.read_bytes())
            data[offset] ^= 1
            with self.assertRaises(ValueError):
                patch_cup_access(data)

    def test_setting_changes_only_volatile_word_and_can_clear(self):
        memory = dict(CUP_ACCESS_SIGNATURES)
        memory[CUP_ACCESS_SETTING_ADDRESS] = bytes(4)
        writes = []

        def write(address, value):
            writes.append(address)
            memory[address] = value

        for setting in (3, 3, 1, 2, 0):
            self.assertTrue(apply_cup_access(lambda address, size: memory[address], write, setting))
            self.assertEqual(memory[CUP_ACCESS_SETTING_ADDRESS], setting.to_bytes(4, "big"))
        self.assertEqual(writes, [CUP_ACCESS_SETTING_ADDRESS] * 4)
        writes.clear()
        self.assertFalse(apply_cup_access(lambda address, size: bytes(size), write, 3))
        self.assertTrue(apply_cup_access(lambda address, size: bytes(size), write, 0))
        self.assertFalse(writes)

    @unittest.skipUnless(unicorn, "Install Unicorn to execute the native PowerPC access matrix")
    def test_native_access_matrix_preserves_save_and_abi(self):
        data = DOL.read_bytes()
        emu = unicorn.Uc(unicorn.UC_ARCH_PPC, unicorn.UC_MODE_32 | unicorn.UC_MODE_BIG_ENDIAN)
        emu.mem_map(0x80000000, 0x1800000)
        for offset, start, size in zip(
            struct.unpack_from(">18I", data),
            struct.unpack_from(">18I", data, 0x48),
            struct.unpack_from(">18I", data, 0x90),
        ):
            if size:
                emu.mem_write(start, data[offset : offset + size])
        # Stub only the external configuration service. Execute the actual
        # IsUserQualified function, trampoline, stack handling and save reads.
        emu.mem_write(0x801D5988, bytes.fromhex("4e800020"))
        emu.mem_write(0x801D519C, bytes.fromhex("3c608110 4e800020"))
        emu.mem_write(0x81100000, struct.pack(">2I", 1, 1))
        manager, stack, stop = 0x81000000, 0x81700000, 0x80001000
        for setting, trophies, flags, mode, config in itertools.product(
            range(4), range(16), range(4), range(12), range(2)
        ):
            saved = bytearray(0x4C80)
            saved[0x2F20] = trophies
            saved[0x3FE4], saved[0x3FE5] = flags & 1, (flags >> 1) & 1
            emu.mem_write(manager, bytes(saved))
            emu.mem_write(SETTING_ADDRESS, struct.pack(">I", setting))
            emu.mem_write(0x80014820, struct.pack(">2I", 0x38600000 | config, 0x4E800020))
            emu.ctl_remove_cache(0x80014820, 0x80014828)
            for reg, value in (
                (ppc.UC_PPC_REG_1, stack),
                (ppc.UC_PPC_REG_3, manager),
                (ppc.UC_PPC_REG_4, mode),
                (ppc.UC_PPC_REG_30, 123),
                (ppc.UC_PPC_REG_31, 456),
                (ppc.UC_PPC_REG_LR, stop),
            ):
                emu.reg_write(reg, value)
            emu.emu_start(HOOK, stop, count=500)
            expected = {
                2: bool(setting & 1 or flags & 1 or config),
                3: bool(setting & 1 or flags & 2 or config),
                4: bool(setting & 1 or trophies & 7 == 7 or config),
                11: bool(setting & 2 or trophies & 8 or config),
            }.get(mode, False)
            case = (setting, trophies, flags, mode, config)
            self.assertEqual(emu.reg_read(ppc.UC_PPC_REG_PC), stop, case)
            self.assertEqual(emu.reg_read(ppc.UC_PPC_REG_3), int(expected), case)
            self.assertEqual(emu.reg_read(ppc.UC_PPC_REG_1), stack, case)
            self.assertEqual(emu.reg_read(ppc.UC_PPC_REG_30), 123, case)
            self.assertEqual(emu.reg_read(ppc.UC_PPC_REG_31), 456, case)
            self.assertEqual(bytes(emu.mem_read(manager, len(saved))), saved, case)
