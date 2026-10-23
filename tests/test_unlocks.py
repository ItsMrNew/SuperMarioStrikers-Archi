import hashlib
import itertools
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest

from BaseClasses import CollectionState
from Fill import distribute_items_restrictive
from test.general import setup_multiworld
from worlds.strikers import StrikersWorld
from worlds.strikers.Data import CAPTAINS, CUPS, SIDEKICKS
from worlds.strikers.Items import CAPTAIN_ITEMS, CUP_ITEMS, SIDEKICK_ITEMS, item_table
from worlds.strikers.Unlocks import starting, progression_items
from worlds.strikers.UnlockMemory import apply_unlocks, unlock_masks, CAPTAIN_ICONS, SIDEKICK_ICONS
from worlds.strikers.UnlockPatch import STATIC_SHA256, HOOKS
from tools.patch_difficulty import file_offset
from tools.patch_session import SESSION
from tools.patch_unlocks import (
    BASE,
    SIZE,
    CONFIG,
    QUALIFIED,
    PHASE,
    PROCEED,
    CONTINUE,
    SUPER_TEAM,
    GRID_UPDATE,
    SUPER_GRID_CALLS,
    DRAW,
    LOCK_TEXT,
    build,
    patch_unlocks,
    remove_unlocks,
)

try:
    import unicorn
    from unicorn import ppc_const as ppc
except ImportError:
    unicorn = None

DOL = Path(__file__).resolve().parents[1] / "Riivolution/Riivolution/StrikersAP/main.dol"


class UnlockTests(unittest.TestCase):
    def test_option_combinations_fill_and_beat_game(self):
        for flags, goal in itertools.product(itertools.product((False, True), repeat=3), range(4)):
            options = dict(
                zip(("randomize_captains", "randomize_sidekicks", "randomize_cups"), flags)
            )
            options["goal"] = goal
            mw = setup_multiworld(StrikersWorld, options=options, seed=710 + goal)
            required = progression_items(mw.worlds[1].fill_slot_data())
            self.assertTrue(required <= {item.name for item in mw.itempool})
            self.assertTrue(all(item.advancement for item in mw.itempool if item.name in required))
            distribute_items_restrictive(mw)
            self.assertTrue(mw.can_beat_game(), (flags, goal))
            self.assertFalse(mw.get_unfilled_locations())

    def test_reachability_tracks_actual_roster_cups_and_goal(self):
        mw = setup_multiworld(
            StrikersWorld,
            options=dict(
                randomize_captains=True,
                randomize_sidekicks=True,
                randomize_cups=True,
                combo_checks="all",
            ),
        )
        state = CollectionState(mw)
        for name in ("Mushroom Cup - Match 1", "First Win - Mario", "Win with Mario + Toad"):
            self.assertTrue(mw.get_location(name, 1).can_reach(state), name)
        for name in (
            "Flower Cup - Match 1",
            "First Win - Peach",
            "Win with Peach + Birdo",
            "All Eight Battle Trophies",
            "First Win at Konga Coliseum",
        ):
            self.assertFalse(mw.get_location(name, 1).can_reach(state), name)
        for item in (
            CUP_ITEMS["Flower Cup"],
            CAPTAIN_ITEMS["Peach"],
            SIDEKICK_ITEMS["Birdo"],
            "Konga Unlock",
        ):
            state.collect(mw.worlds[1].create_item(item), True)
        for name in (
            "Flower Cup - Match 1",
            "First Win - Peach",
            "Win with Peach + Birdo",
            "First Win at Konga Coliseum",
        ):
            self.assertTrue(mw.get_location(name, 1).can_reach(state), name)
        self.assertFalse(mw.get_location("All Eight Battle Trophies", 1).can_reach(state))
        for item in CUP_ITEMS.values():
            state.collect(mw.worlds[1].create_item(item), True)
        self.assertTrue(mw.get_location("All Eight Battle Trophies", 1).can_reach(state))

    def test_invalid_starters_and_tiny_pools_fail_clearly(self):
        for options in (
            dict(randomize_captains=True, starting_captains=["Mario"]),
            dict(randomize_sidekicks=True, starting_sidekicks=[]),
            dict(randomize_cups=True, starting_cups=[]),
            dict(
                randomize_captains=True,
                randomize_sidekicks=True,
                randomize_cups=True,
                goal="match_wins",
                included_cups=[],
                milestone_checks=False,
                stadium_win_checks=False,
                combo_checks="off",
            ),
        ):
            with self.assertRaises(ValueError):
                setup_multiworld(StrikersWorld, options=options)

    def test_starting_groups_no_duplicate_items_and_stable_ids(self):
        for group in range(4):
            mw = setup_multiworld(
                StrikersWorld, options=dict(randomize_cups=True, starting_cup_unlocks=group)
            )
            slot = mw.worlds[1].fill_slot_data()
            for cup in CUPS:
                self.assertEqual(
                    CUP_ITEMS[cup.name] in {item.name for item in mw.itempool},
                    cup.name not in starting(slot, "cups"),
                )
        self.assertEqual(item_table["Super Team Unlock"], 0x535405)
        self.assertNotEqual(item_table["Yoshi Unlock"], item_table[CAPTAIN_ITEMS["Yoshi"]])
        self.assertEqual(len(item_table), len(set(item_table.values())))

    def test_native_masks_item_delivery_reconnect_seed_change_and_signatures(self):
        data = DOL.read_bytes()
        _, hooks, _ = build(remove_unlocks(data))
        self.assertEqual(hooks, HOOKS)
        memory = {BASE: data[-SIZE:], **hooks}
        writes = []

        def read(address, size):
            if BASE <= address < BASE + SIZE:
                return memory[BASE][address - BASE : address - BASE + size]
            return memory[address]

        def write(address, value):
            writes.append((address, value))
            region = bytearray(memory[BASE])
            region[address - BASE : address - BASE + len(value)] = value
            memory[BASE] = bytes(region)

        self.assertEqual(hashlib.sha256(memory[BASE]).hexdigest(), STATIC_SHA256)
        options = dict(randomize_captains=True, randomize_sidekicks=True, randomize_cups=True)
        received = [
            SimpleNamespace(item=item_table[name])
            for name in (
                CAPTAIN_ITEMS["Peach"],
                SIDEKICK_ITEMS["Birdo"],
                CUP_ITEMS["Super Bowser Cup"],
            )
        ]
        for items in ((), received, received, ()):
            self.assertTrue(apply_unlocks(read, write, options, items))
            self.assertEqual(read(CONFIG, 16), unlock_masks(options, items))
        self.assertEqual(sum(address == CONFIG for address, _ in writes), 3)
        self.assertTrue(apply_unlocks(read, write, {}, ()))
        self.assertEqual(struct.unpack(">I", read(CONFIG, 4))[0], 0)
        memory[QUALIFIED] = bytes(4)
        self.assertFalse(apply_unlocks(read, write, options, received))
        self.assertFalse(apply_unlocks(lambda a, n: bytes(n), write, options, received))
        self.assertTrue(apply_unlocks(lambda a, n: bytes(n), write, {}, ()))

    def test_patch_reversible_reproducible_and_rejects_corruption(self):
        data = DOL.read_bytes()
        base = remove_unlocks(data)
        self.assertEqual(patch_unlocks(base), data)
        self.assertEqual(patch_unlocks(data), data)
        for position in (-1, file_offset(data, QUALIFIED), file_offset(data, BASE), 0x50):
            bad = bytearray(data)
            bad[position] ^= 1
            with self.assertRaises(ValueError):
                patch_unlocks(bad)


@unittest.skipUnless(unicorn, "Unicorn executes the native PowerPC gates")
class NativeUnlockTests(unittest.TestCase):
    def setUp(self):
        data = DOL.read_bytes()
        self.emu = unicorn.Uc(unicorn.UC_ARCH_PPC, unicorn.UC_MODE_32 | unicorn.UC_MODE_BIG_ENDIAN)
        self.emu.mem_map(0x80000000, 0x1800000)
        for offset, address, size in zip(
            struct.unpack_from(">18I", data),
            struct.unpack_from(">18I", data, 0x48),
            struct.unpack_from(">18I", data, 0x90),
        ):
            if size:
                self.emu.mem_write(address, data[offset : offset + size])
        self.manager, self.stack, self.stop = 0x81000000, 0x81700000, 0x80001000
        self.r13 = 0x80379660
        self.emu.mem_write(self.r13 - 0x5248, struct.pack(">I", self.manager))
        _, _, self.labels = build(remove_unlocks(data))

    def word(self, address, value):
        self.emu.mem_write(address, struct.pack(">I", value))

    def run_code(self, start, *, r3=0, r4=0, r26=0, r31=456, ends=()):
        for index in range(1, 32):
            self.emu.reg_write(getattr(ppc, f"UC_PPC_REG_{index}"), 0)
        for reg, value in (
            (1, self.stack),
            (3, r3),
            (4, r4),
            (13, self.r13),
            (26, r26),
            (30, 123),
            (31, r31),
        ):
            self.emu.reg_write(getattr(ppc, f"UC_PPC_REG_{reg}"), value)
        self.emu.reg_write(ppc.UC_PPC_REG_LR, self.stop)
        reached = []

        def stop(emu, address, size, user):
            if address in ends:
                reached.append(address)
                emu.emu_stop()

        handle = self.emu.hook_add(unicorn.UC_HOOK_CODE, stop)
        try:
            self.emu.emu_start(start, self.stop, count=3000)
        finally:
            self.emu.hook_del(handle)
        self.assertIn(self.emu.reg_read(ppc.UC_PPC_REG_PC), (*ends, self.stop))
        self.assertEqual(self.emu.reg_read(ppc.UC_PPC_REG_30), 123)
        return self.emu.reg_read(ppc.UC_PPC_REG_3), reached

    def config(self, flags=7, captains=0x1FF, sidekicks=15, cups=255):
        self.emu.mem_write(CONFIG, struct.pack(">4I", flags, captains, sidekicks, cups))
        self.word(SESSION, 300)
        self.word(SESSION + 4, 1)

    def test_all_cup_masks_and_super_menu_override_natural_trophies(self):
        self.emu.mem_write(self.manager, b"\xff" * 0x4C80)
        before = bytes(self.emu.mem_read(self.manager, 0x4C80))
        for mask, mode in itertools.product(range(256), range(12)):
            self.config(cups=mask)
            value, _ = self.run_code(QUALIFIED, r3=self.manager, r4=mode)
            expected = (
                bool(mask & 0xF0)
                if mode == 11
                else bool(mask & 1 << (mode - 1))
                if 1 <= mode <= 8
                else False
            )
            self.assertEqual(value, int(expected), (mask, mode))
            self.assertEqual(self.emu.reg_read(ppc.UC_PPC_REG_1), self.stack)
        self.assertEqual(bytes(self.emu.mem_read(self.manager, 0x4C80)), before)

    def test_cup_proceed_denies_locked_regular_and_super_cups(self):
        scene = self.manager + 0x5000
        for mask, cup in itertools.product((0, 1, 0x80, 0x55, 255), range(8)):
            self.config(cups=mask)
            self.word(scene + 0x24, cup)
            _, reached = self.run_code(PROCEED, r3=scene, ends=(PROCEED + 4, self.labels["deny"]))
            self.assertEqual(reached, [PROCEED + 4 if mask & 1 << cup else self.labels["deny"]])

    def test_cup_display_and_confirmation_use_individual_masks(self):
        scene = self.manager + 0x5000
        for mask, cup in itertools.product(range(256), range(8)):
            self.config(cups=mask)
            self.word(scene + 0x24, cup)
            for hook, end, result in ((0x800DAFC8, 0x800DB04C, 27), (0x800DBBB4, 0x800DBC34, 29)):
                self.run_code(hook, r3=0xDEADBEEF, r31=scene, ends=(end,))
                self.assertEqual(
                    self.emu.reg_read(getattr(ppc, f"UC_PPC_REG_{result}")),
                    int(bool(mask & 1 << cup)),
                )
                self.assertEqual(self.emu.reg_read(ppc.UC_PPC_REG_31), scene)
                if result == 27:
                    self.assertEqual(self.emu.reg_read(ppc.UC_PPC_REG_28), 0xDEADBEEF)

    def test_super_team_grid_does_not_cache_ap_lock_after_rebuild(self):
        for entry, mask in itertools.product(SUPER_GRID_CALLS, (0, 0x100)):
            self.config(captains=mask)
            result, reached = self.run_code(entry, ends=(entry + 4,))
            self.assertEqual(reached, [entry + 4])
            self.assertEqual(result, 1)
            self.config(flags=0)
            _, reached = self.run_code(entry, ends=(SUPER_TEAM,))
            self.assertEqual(reached, [SUPER_TEAM])

    def test_locked_cup_text_covers_all_eight_and_preserves_natural_mode(self):
        scene, text = self.manager + 0x5000, self.manager + 0x6000
        for flags, cup in itertools.product((0, 4), range(8)):
            self.config(flags=flags)
            self.word(scene + 0x24, cup)
            self.word(text + 0xF4, 123)
            self.word(text + 0xEC, 456)
            self.word(text + 0x90, 0xFF)
            _, reached = self.run_code(
                0x800DB74C, r26=text, r31=scene, ends=(0x800DB750, 0x800DB7AC)
            )
            self.assertEqual(reached, [0x800DB7AC if flags else 0x800DB750])
            pointer = struct.unpack(">I", self.emu.mem_read(text + 0xF4, 4))[0]
            if flags:
                self.assertEqual(
                    bytes(self.emu.mem_read(pointer, (len(LOCK_TEXT) + 1) * 2)),
                    (LOCK_TEXT + "\0").encode("utf-16-be"),
                )
                self.assertEqual(bytes(self.emu.mem_read(text + 0xEC, 4)), bytes(4))
                self.assertEqual(struct.unpack(">I", self.emu.mem_read(text + 0x90, 4))[0], 0xF7)
            else:
                self.assertEqual(pointer, 123)

    def test_roster_confirmation_both_sides_and_all_masks(self):
        component, parent, grid, menu = (self.manager + i for i in (0, 0x100, 0x500, 0x1000))
        self.word(component + 4, parent)
        self.word(grid + 8, menu)
        for phase, count in ((1, 9), (2, 4)):
            self.word(component, phase)
            for side in range(2):
                self.word(component + 8, side)
                self.word(parent + (0x9C if phase == 1 else 0xA4) + 4 * side, grid)
                for icon, mask in itertools.product(
                    range(count), (0, 1, 2, 4, 8, 0x20, 0x80, 0x100, 0x1FF)
                ):
                    self.word(menu + 4, icon)
                    self.config(captains=mask, sidekicks=mask)
                    _, reached = self.run_code(
                        PHASE, r3=component, ends=(PHASE + 4, self.labels["deny"])
                    )
                    self.assertEqual(
                        reached,
                        [PHASE + 4 if mask & 1 << icon else self.labels["deny"]],
                        (phase, side, icon, mask),
                    )

    def test_resume_locked_rosters_and_super_team_sidekick_exception(self):
        cup = self.manager + 0x78
        self.word(self.manager + 0x4960, cup)
        for captain, sidekick in itertools.product(CAPTAINS, SIDEKICKS):
            self.word(cup, captain)
            self.word(cup + 4, sidekick)
            for has_captain, has_sidekick in itertools.product((False, True), repeat=2):
                self.config(
                    captains=(1 << CAPTAIN_ICONS[captain]) if has_captain else 0,
                    sidekicks=(1 << SIDEKICK_ICONS[sidekick]) if has_sidekick else 0,
                )
                _, reached = self.run_code(
                    CONTINUE, r3=1, ends=(CONTINUE + 4, self.labels["resume_deny"])
                )
                expected = has_captain and (has_sidekick or captain == 8)
                self.assertEqual(
                    reached, [CONTINUE + 4 if expected else self.labels["resume_deny"]]
                )

    def test_super_team_ignores_natural_unlock_when_randomized(self):
        for mask in (0, 255, 256, 511):
            self.config(captains=mask)
            value, _ = self.run_code(SUPER_TEAM, r3=self.manager)
            self.assertEqual(value, int(bool(mask & 256)))

    def test_arena_reservation_keeps_larger_loader_bounds(self):
        for low in (0x80388700, 0x8038A700, BASE + SIZE, BASE + SIZE + 0x1000):
            value, _ = self.run_code(self.labels["arena"], r3=low)
            self.assertEqual(value, max(low, BASE + SIZE))
            self.assertEqual(struct.unpack(">I", self.emu.mem_read(self.r13 - 0x5AA8, 4))[0], value)

    def test_grid_mask_draw_and_restore_preserve_native_exclusions(self):
        grid, menu = self.manager, self.manager + 0x1000
        self.word(grid + 8, menu)
        self.emu.mem_write(DRAW, bytes.fromhex("4e800020"))
        for entry, bit, offset in GRID_UPDATE:
            # Stub expensive UI services, while executing all actual mask,
            # drawing call, restoration, trampoline and ABI instructions.
            self.emu.mem_write(entry + 4, bytes.fromhex("38210020 4e800020"))
            count = 9 if bit == 1 else 4
            self.emu.mem_write(menu + 0x384, bytes([count]))
            for mask in (0, 1, 2, 0x55, 0x1FF):
                self.config(captains=mask, sidekicks=mask)
                original = [int(index != 1) for index in range(count)]
                for index in range(count):
                    self.word(menu + 4 + index * 28, index)
                    self.emu.mem_write(menu + 12 + index * 28, bytes([original[index]]))
                drawn = []

                def capture(emu, address, size, user):
                    if address == DRAW:
                        drawn.extend(
                            emu.mem_read(menu + 12 + index * 28, 1)[0] for index in range(count)
                        )

                handle = self.emu.hook_add(unicorn.UC_HOOK_CODE, capture)
                try:
                    self.run_code(entry, r3=grid, r4=8)
                finally:
                    self.emu.hook_del(handle)
                self.assertEqual(
                    drawn,
                    [value & int(bool(mask & 1 << index)) for index, value in enumerate(original)],
                )
                self.assertEqual(
                    [self.emu.mem_read(menu + 12 + index * 28, 1)[0] for index in range(count)],
                    original,
                )
                self.assertEqual(self.emu.reg_read(ppc.UC_PPC_REG_1), self.stack)
                self.assertEqual(self.emu.reg_read(ppc.UC_PPC_REG_31), 456)
