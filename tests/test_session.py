import struct
import unittest

from worlds.strikers.Data import CUPS, MILESTONES
from worlds.strikers.Memory import MANAGER_SIZE, USER_INFO, TROPHIES, MANAGER_ADDRESS
from worlds.strikers.Session import (
    CONNECT,
    READY,
    WRONG_SAVE,
    LEGACY_SAVE,
    WAITING,
    TAG_OFFSETS,
    inspect_save,
    bind_save,
    save_tag,
    read_tag,
)
from worlds.strikers.SessionMemory import validate_save, publish, unchanged_save, SCENES
from tools.patch_session import SESSION, TEXTS
from tests import test_unlocks as native_tests

unicorn, ppc = native_tests.unicorn, getattr(native_tests, "ppc", None)


class SaveSessionTests(unittest.TestCase):
    def setUp(self):
        self.ram = bytearray(0x1800000)
        self.manager = 0x81000000
        self.scenes = 0x81010000
        self.write(MANAGER_ADDRESS, struct.pack(">I", self.manager))
        self.write(SCENES, struct.pack(">I", self.scenes))
        self.write(self.scenes + 4, struct.pack(">2I", 1, 3))

    def read(self, address, size):
        return self.ram[address - 0x80000000 : address - 0x80000000 + size]

    def write(self, address, data):
        self.ram[address - 0x80000000 : address - 0x80000000 + len(data)] = data

    def test_fresh_save_binds_and_rejects_other_seed_team_or_slot(self):
        key = '["seed",0,1]'
        before = self.read(self.manager, MANAGER_SIZE)
        status, token = validate_save(self.read, self.write, key)
        self.assertEqual(status, READY)
        after = self.read(self.manager, MANAGER_SIZE)
        self.assertEqual(read_tag(after), save_tag(key))
        self.assertEqual(
            set(i for i, (x, y) in enumerate(zip(before, after)) if x != y), set(TAG_OFFSETS)
        )
        self.assertTrue(unchanged_save(self.read, key, token))
        for other in ('["new",0,1]', '["seed",1,1]', '["seed",0,2]'):
            self.assertEqual(validate_save(self.read, self.write, other, adopt=True)[0], WRONG_SAVE)
        self.assertEqual(self.read(self.manager, MANAGER_SIZE), after)

    def test_legacy_progress_requires_explicit_adoption_at_menu(self):
        for offset in (
            TROPHIES,
            *(USER_INFO + value[0] for value in MILESTONES.values()),
            *(cup.offset + 0xE for cup in CUPS),
        ):
            with self.subTest(offset=offset):
                data = bytearray(MANAGER_SIZE)
                data[offset] = 1
                self.assertEqual(inspect_save(data, "key", at_menu=True).status, LEGACY_SAVE)
                self.assertTrue(inspect_save(data, "key", at_menu=True, adopt=True).bind)
                self.assertEqual(inspect_save(data, "key", adopt=True).status, WAITING)

    def test_no_binding_during_active_match_or_unstable_snapshot(self):
        before = self.read(self.manager, MANAGER_SIZE)
        self.write(self.manager + 0x4C38, b"\1")
        self.assertFalse(bind_save(self.read, self.write, self.manager, before, "key"))
        self.assertEqual(validate_save(self.read, self.write, "key", adopt=True)[0], WAITING)
        self.assertEqual(read_tag(self.read(self.manager, MANAGER_SIZE)), bytes(8))

    def test_load_epoch_revokes_token_and_publish_order_is_safe(self):
        status, token = validate_save(self.read, self.write, "key")
        self.assertEqual(status, READY)
        self.write(SESSION + 12, struct.pack(">I", 1))
        self.assertFalse(unchanged_save(self.read, "key", token))
        writes = []

        def write(address, data):
            writes.append(address)
            self.write(address, data)

        publish(self.read, write, READY, ready=True)
        self.assertEqual(writes[-1], SESSION)
        writes.clear()
        publish(self.read, write, WRONG_SAVE)
        self.assertEqual(writes[0], SESSION)
        self.assertEqual(self.read(SESSION, 4), bytes(4))
        self.assertEqual(validate_save(self.read, self.write, None)[0], CONNECT)


@unittest.skipUnless(unicorn, "Unicorn required")
class NativeSessionTests(unittest.TestCase):
    setUp = native_tests.NativeUnlockTests.setUp
    word = native_tests.NativeUnlockTests.word
    config = native_tests.NativeUnlockTests.config
    run_code = native_tests.NativeUnlockTests.run_code

    def test_lease_ticks_expires_and_load_immediately_closes(self):
        for start in (0x80170B78,):
            self.word(SESSION, 2)
            self.word(SESSION + 4, READY)
            self.run_code(start, ends=(start + 4,))
            self.assertEqual(bytes(self.emu.mem_read(SESSION, 8)), struct.pack(">2I", 1, READY))
            self.run_code(start, ends=(start + 4,))
            self.assertEqual(bytes(self.emu.mem_read(SESSION, 8)), bytes(8))
        self.config()
        self.word(SESSION + 12, 17)
        self.run_code(0x8017BDCC, ends=(0x8017BDD0,))
        self.assertEqual(bytes(self.emu.mem_read(SESSION, 8)), bytes(8))
        self.assertEqual(bytes(self.emu.mem_read(SESSION + 12, 4)), struct.pack(">I", 18))

    def test_no_client_blocks_start_and_ready_allows_it(self):
        for entry in (0x80095A18, 0x800C0D04, 0x800DA6E0, 0x800DC5DC):
            self.word(SESSION, 0)
            _, reached = self.run_code(entry, ends=(entry + 4, self.labels["session_deny"]))
            self.assertEqual(reached, [self.labels["session_deny"]])
        self.config(flags=0)
        _, reached = self.run_code(0x80095A18, ends=(0x80095A1C,))
        self.assertEqual(reached, [0x80095A1C])

    def test_popup_uses_correct_text_preserves_caller_and_native_ownership(self):
        popup = self.manager + 0x6000

        def native(emu, address, size, user):
            if address in (0x80095D3C, 0x800AC7F4):
                emu.reg_write(ppc.UC_PPC_REG_3, popup)
                emu.reg_write(ppc.UC_PPC_REG_PC, emu.reg_read(ppc.UC_PPC_REG_LR))

        handle = self.emu.hook_add(unicorn.UC_HOOK_CODE, native)
        try:
            for status in (CONNECT, WRONG_SAVE, LEGACY_SAVE, WAITING):
                self.word(SESSION + 4, status)
                self.run_code(self.labels["session_deny"])
                expected = (TEXTS[status] + "\0").encode("utf-16-be")
                self.assertEqual(bytes(self.emu.mem_read(popup + 0x1C, len(expected))), expected)
                text = self.manager + 0x8000
                self.run_code(0x8009B834, r3=text, r4=1234, r31=popup, ends=(0x8009B838,))
                self.assertEqual(
                    bytes(self.emu.mem_read(text + 0xF4, 4)), struct.pack(">I", popup + 0x1C)
                )
                self.assertEqual(bytes(self.emu.mem_read(SESSION + 20, 4)), bytes(4))
        finally:
            self.emu.hook_del(handle)

    def test_cup_refresh_runs_only_after_revision_changes(self):
        scene = self.manager + 0x5000
        self.word(SESSION + 8, 2)
        calls = []

        def display(emu, address, size, user):
            if address == 0x800DAE8C:
                calls.append(emu.reg_read(ppc.UC_PPC_REG_3))
                emu.reg_write(ppc.UC_PPC_REG_PC, emu.reg_read(ppc.UC_PPC_REG_LR))

        handle = self.emu.hook_add(unicorn.UC_HOOK_CODE, display)
        try:
            for _ in range(2):
                self.run_code(0x800DBA44, r31=scene, ends=(0x800DBA48,))
            self.assertEqual(calls, [scene])
        finally:
            self.emu.hook_del(handle)
