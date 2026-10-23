import asyncio
import itertools
import struct
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from worlds.strikers import StrikersWorld
from worlds import network_data_package

network_data_package["games"][StrikersWorld.game] = StrikersWorld.get_data_package_data()
from worlds.strikers.Data import CUPS, GOAL_LOCATION, MILESTONES
from worlds.strikers.Locations import location_groups, location_table
from worlds.strikers.Memory import (
    FriendlyTracker,
    LiveMatch,
    Match,
    MANAGER_SIZE,
    STATS_SIZE,
    STATS_ADDRESS,
    USER_INFO,
    TROPHIES,
    PATCH_SIGNATURES,
    saved_locations,
    read_friendly,
)
from test.general import setup_multiworld
from Fill import distribute_items_restrictive

# Stub only the external emulator boundary; world/client/framework code is real.
sys.modules.setdefault("dolphin_memory_engine", types.ModuleType("dolphin_memory_engine"))
from worlds.strikers.Client import StrikersContext, check_bowser_deathlink
from worlds.strikers import Client as strikers_client
from worlds.strikers.Items import item_table


def blank():
    data = bytearray(MANAGER_SIZE)
    for cup in CUPS:
        struct.pack_into(">i", data, cup.offset, -1)
        if cup.knockout:
            struct.pack_into(">i", data, cup.knockout, -1)
    return data


def fixture(
    data, offset, teams=(3, 2), sidekicks=(0, 1), stadium=0, pads=(0, -1, -1, -1), scores=(3, 1)
):
    struct.pack_into(">5i6h", data, offset, *teams, *sidekicks, stadium, *pads, *scores)


class SaveChecks(unittest.TestCase):
    def test_empty_save_has_no_checks(self):
        self.assertEqual(saved_locations(blank()), set())

    def test_every_cup_matches_including_bowser_and_super_bowser(self):
        for cup in CUPS:
            with self.subTest(cup=cup.name):
                data = blank()
                struct.pack_into(">i", data, cup.offset, 3)
                for number in range(cup.rounds):
                    fixture(data, cup.offset + 0x20 + number * (cup.teams // 2) * 0x20)
                if cup.knockout:
                    struct.pack_into(">i", data, cup.knockout, 3)
                    fixture(data, cup.knockout + 0x20)
                    fixture(data, cup.knockout + 0x60)
                found = saved_locations(data)
                for number in range(1, cup.match_count + 1):
                    self.assertIn(f"{cup.name} - Match {number}", found)
                self.assertNotIn(GOAL_LOCATION, found)

    def test_loss_completes_match_but_not_win_challenges(self):
        data = blank()
        cup = CUPS[0]
        struct.pack_into(">i", data, cup.offset, 3)
        fixture(data, cup.offset + 0x20, scores=(0, 4))
        found = saved_locations(data)
        self.assertEqual(found, {"Mushroom Cup - Match 1"})

    def test_away_player_win_and_combo(self):
        data = blank()
        cup = CUPS[0]
        struct.pack_into(">i", data, cup.offset, 7)
        fixture(
            data,
            cup.offset + 0x20,
            teams=(3, 7),
            sidekicks=(0, 3),
            stadium=4,
            pads=(-1, 1, -1, -1),
            scores=(2, 3),
        )
        found = saved_locations(data)
        self.assertIn("First Win - Yoshi", found)
        self.assertIn("Win with Yoshi + Birdo", found)
        self.assertIn("Win with Yoshi at Crater Field", found)
        self.assertNotIn("First Win - Mario", found)

    def test_unplayed_cpu_multiplayer_invalid_and_tied_games_do_not_count(self):
        cases = [
            dict(scores=(0, 0)),
            dict(pads=(-1, -1, -1, -1)),
            dict(pads=(0, 1, -1, -1)),
            dict(teams=(99, 2)),
            dict(stadium=99),
            dict(sidekicks=(99, 0)),
            dict(scores=(-5, 3)),
            dict(scores=(2, 2)),
        ]
        for case in cases:
            with self.subTest(case=case):
                data = blank()
                struct.pack_into(">i", data, CUPS[0].offset, 3)
                fixture(data, CUPS[0].offset + 0x20, **case)
                self.assertEqual(saved_locations(data), set())

    def test_all_eight_trophies_required_for_goal(self):
        for mask in range(256):
            data = blank()
            data[TROPHIES] = mask
            self.assertEqual(GOAL_LOCATION in saved_locations(data), mask == 255)
        data = blank()
        data[TROPHIES + 1] = 31
        self.assertNotIn(GOAL_LOCATION, saved_locations(data))

    def test_super_star_last_match_is_not_victory(self):
        data = blank()
        cup = CUPS[6]
        struct.pack_into(">i", data, cup.offset, 3)
        fixture(data, cup.offset + 0x20 + 13 * 4 * 0x20)
        self.assertIn("Super Star Cup - Match 14", saved_locations(data))
        self.assertNotIn(GOAL_LOCATION, saved_locations(data))

    def test_trophy_grants_all_placements_and_five_bonuses(self):
        for cup in CUPS:
            data = blank()
            data[TROPHIES] = 1 << cup.trophy_bit
            found = saved_locations(data)
            for label in ("Top 3", "Top 2", "Champion"):
                self.assertIn(f"{cup.name} - {label}", found)
            for number in range(1, 6):
                self.assertIn(f"{cup.name} - Cup Win Bonus {number}", found)

    def test_history_placement_is_cumulative_not_exact(self):
        for cup in CUPS:
            for rank, count in ((0, 3), (1, 2), (2, 1), (3, 0), (-2, 0)):
                data = blank()
                spoil = USER_INFO + 0x50 + cup.trophy_bit * 0x218
                data[spoil + 0x208] = 1
                struct.pack_into(">b", data, spoil + 0x28, rank)
                struct.pack_into(">i", data, spoil + 0x2C, 3)
                self.assertEqual(len(saved_locations(data)), count)

    def test_bowser_semifinal_and_final_losses_have_appropriate_placement(self):
        for cup in (CUPS[3], CUPS[7]):
            data = blank()
            struct.pack_into(">i", data, cup.knockout, 3)
            fixture(data, cup.knockout + 0x20, scores=(1, 3))
            found = saved_locations(data)
            self.assertIn(f"{cup.name} - Top 3", found)
            self.assertNotIn(f"{cup.name} - Top 2", found)
            fixture(data, cup.knockout + 0x60, scores=(1, 3))
            found = saved_locations(data)
            self.assertIn(f"{cup.name} - Top 2", found)
            self.assertNotIn(f"{cup.name} - Champion", found)

    def test_original_bowser_final_survives_robot_challenge_replacement(self):
        data = blank()
        fixture(data, USER_INFO + 0x111C, teams=(7, 2), sidekicks=(3, 1), stadium=5)
        found = saved_locations(data)
        self.assertIn("Bowser Cup - Match 9", found)
        self.assertIn("Bowser Cup - Top 2", found)
        self.assertIn("Win with Yoshi + Birdo", found)
        self.assertNotIn("Bowser Cup - Champion", found)

    def test_super_team_does_not_generate_impossible_sidekick_combos(self):
        match = Match((8, 3), (-2, 0), 5, (0, -1, -1, -1), (3, 1))
        self.assertTrue(match.completed_by(8))
        names = match.win_locations(0)
        self.assertIn("First Win - Super Team", names)
        self.assertFalse(any(" + " in name for name in names))

    def test_all_milestone_boundaries(self):
        for name, (offset, thresholds) in MILESTONES.items():
            for index, threshold in enumerate(thresholds):
                for value, count in ((threshold - 1, index), (threshold, index + 1)):
                    data = blank()
                    struct.pack_into(">H", data, USER_INFO + offset, value)
                    self.assertEqual(len(saved_locations(data)), count, (name, value))


class GrudgeChecks(unittest.TestCase):
    def live(self, ended=False, wins=(0, 0), identity=(1,), pads=(0, -1, -1, -1)):
        return LiveMatch(identity, Match((4, 3), (0, 1), 1, pads, (0, 0)), ended, wins)

    def test_no_check_for_lead_then_award_win_once(self):
        tracker = FriendlyTracker()
        self.assertFalse(tracker.observe(self.live()))
        found = tracker.observe(self.live(True, (1, 0)))
        self.assertIn("Win with Peach + Toad", found)
        self.assertIn("Win with Peach at The Palace", found)
        self.assertFalse(tracker.observe(self.live(True, (1, 0))))

    def test_loss_forfeit_and_ambiguous_counters_do_not_award_win(self):
        for wins in ((0, 1), (0, 0), (1, 1), (2, 0)):
            tracker = FriendlyTracker()
            tracker.observe(self.live())
            self.assertFalse(tracker.observe(self.live(True, wins)))

    def test_reconnect_at_results_and_different_match_do_not_invent_win(self):
        tracker = FriendlyTracker()
        self.assertFalse(tracker.observe(self.live(True, (1, 0))))
        tracker.observe(self.live())
        self.assertFalse(tracker.observe(self.live(True, (1, 0), identity=(2,))))

    def test_rematch_and_torn_sample(self):
        tracker = FriendlyTracker()
        tracker.observe(self.live(wins=(1, 1)))
        tracker.observe(None)
        self.assertFalse(tracker.observe(self.live(True, (2, 1))))
        tracker.observe(self.live(wins=(2, 1), identity=(2,)))
        self.assertTrue(tracker.observe(self.live(True, (3, 1), identity=(2,))))

    def test_memory_reader_validates_mode_pointers_training_and_human_sides(self):
        data = blank()
        data[0x4C38] = 1
        struct.pack_into(">I", data, 0x10, 0x81001000)
        stats = bytearray(STATS_SIZE)
        struct.pack_into(">I", stats, 0, 0x81001000)
        info = bytearray(32)
        fixture(info, 0)
        memory = {STATS_ADDRESS: struct.pack(">I", 0x81000000), 0x81000000: stats, 0x81001000: info}

        def read(address, size):
            return bytes(memory[address][:size])

        self.assertIsNotNone(read_friendly(read, 0x80800000, data))
        data[0x4C38] = 0
        self.assertIsNone(read_friendly(read, 0x80800000, data))
        stats[0x4C2] = 1
        self.assertIsNotNone(read_friendly(read, 0x80800000, data))
        data[0x4C38] = 1
        data[0x4959] = 1
        self.assertIsNone(read_friendly(read, 0x80800000, data))
        data[0x4959] = 0
        fixture(info, 0, pads=(0, 1, -1, -1))
        self.assertIsNone(read_friendly(read, 0x80800000, data))
        fixture(info, 0, pads=(1, 1, -1, -1))
        self.assertIsNotNone(read_friendly(read, 0x80800000, data))
        struct.pack_into(">i", data, 0x4954, 10)
        self.assertIsNone(read_friendly(read, 0x80800000, data))


class GenerationChecks(unittest.TestCase):
    def test_legacy_location_ids_are_unchanged(self):
        expected = []
        legacy = [cup for cup in CUPS if not cup.knockout]
        for cup in legacy:
            expected.extend(f"{cup.name} - Match {i}" for i in range(1, cup.match_count + 1))
        expected.append("Super Team Unlocked")
        for cup in legacy:
            expected.extend(f"{cup.name} - Cup Win Bonus {i}" for i in range(1, 6))
        self.assertEqual(len(expected), 76)
        for index, name in enumerate(expected, 1):
            self.assertEqual(location_table[name], 0x535800 + index)
        self.assertEqual(len(location_table), len(set(location_table.values())))

    def test_option_combinations_balance_pool_and_locations(self):
        toggles = (
            "placement_checks",
            "milestone_checks",
            "captain_win_checks",
            "stadium_win_checks",
            "character_unlock_checks",
        )
        for values in itertools.product((0, 1), repeat=len(toggles)):
            for combo in (0, 1, 2):
                options = dict(zip(toggles, values), combo_checks=combo)
                mw = setup_multiworld(StrikersWorld, options=options, seed=22)
                self.assertEqual(len(mw.itempool), len(mw.get_unfilled_locations()))
                self.assertEqual(mw.get_location(GOAL_LOCATION, 1).item.name, "Victory")
                names = {
                    name
                    for group in location_groups(mw.worlds[1].fill_slot_data()).values()
                    for name in group
                }
                self.assertEqual(names, {loc.name for loc in mw.get_locations()})

    def test_real_archipelago_fill_and_goal(self):
        for options in ({}, {"combo_checks": 2}, {"enable_traps": 1, "trap_weight": 100}):
            mw = setup_multiworld(StrikersWorld, options=options, seed=22)
            distribute_items_restrictive(mw)
            self.assertFalse(mw.get_unfilled_locations())
            state = mw.state.copy()
            self.assertFalse(mw.completion_condition[1](state))
            state.collect(mw.get_location(GOAL_LOCATION, 1).item, True)
            self.assertTrue(mw.completion_condition[1](state))

    def test_two_player_multiworld_fill(self):
        mw = setup_multiworld(
            [StrikersWorld, StrikersWorld], options=[{}, {"combo_checks": 2}], seed=22
        )
        distribute_items_restrictive(mw)
        self.assertFalse(mw.get_unfilled_locations())
        self.assertTrue(any(loc.item.player != loc.player for loc in mw.get_locations()))

    def test_bundled_executable_signatures_match(self):
        dol = (
            Path(__file__).resolve().parents[1] / "Riivolution/Riivolution/StrikersAP/main.dol"
        ).read_bytes()
        for address, expected in PATCH_SIGNATURES.items():
            found = None
            for index in range(18):
                offset, start, size = (
                    struct.unpack_from(">I", dol, base + index * 4)[0] for base in (0, 0x48, 0x90)
                )
                if start <= address < start + size:
                    found = dol[offset + address - start : offset + address - start + len(expected)]
            self.assertEqual(found, expected)


class ClientChecks(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.storage = {}
        self.patches = [
            patch("Utils.persistent_load", return_value=self.storage),
            patch(
                "Utils.persistent_store",
                side_effect=lambda category, key, value: self.storage.setdefault(
                    category, {}
                ).__setitem__(key, value),
            ),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.ctx = StrikersContext(None, None)
        self.ctx.team = 0
        self.ctx.slot = 1
        self.ctx.server_seed_name = "seed-a"
        self.ctx.check_locations = AsyncMock(return_value=set())
        self.ctx.send_msgs = AsyncMock()
        self.ctx.update_death_link = AsyncMock()
        self.connect()

    def connect(self, **options):
        self.ctx.on_package("Connected", {"slot_data": {"protocol_version": 2, **options}})

    async def asyncTearDown(self):
        await asyncio.sleep(0)

    async def test_ownership_survives_network_outage_but_not_slot_change(self):
        from worlds.strikers.Client import known_items
        from NetUtils import NetworkItem

        item = NetworkItem(0x535430, 1, 1, 1)
        self.ctx.items_received = [item]
        self.ctx.item_history_received = True
        self.ctx.offline_items = (item,)
        self.ctx.reset_server_state()
        self.assertEqual(known_items(self.ctx), (item,))
        self.ctx.slot, self.ctx.team, self.ctx.server_seed_name = 2, 0, "new-seed"
        self.connect()
        self.assertEqual(known_items(self.ctx), ())
        self.assertEqual(self.ctx.offline_items, ())

    async def test_disabled_locations_are_not_sent(self):
        self.connect(combo_checks=0, captain_win_checks=0)
        await self.ctx.record_checks(
            {"Win with Peach + Toad", "First Win - Peach", "First Win at The Palace"}
        )
        self.ctx.check_locations.assert_awaited_once_with(
            {location_table["First Win at The Palace"]}
        )

    async def test_observed_checks_persist_and_are_seed_scoped(self):
        await self.ctx.record_checks({"First Win - Peach"})
        first_key = self.ctx.progress_key
        self.assertEqual(
            self.storage["strikers_checks_v2"][first_key], [location_table["First Win - Peach"]]
        )
        self.ctx.server_seed_name = "seed-b"
        self.connect()
        self.assertFalse(self.ctx.observed_checks)
        self.ctx.server_seed_name = "seed-a"
        self.connect()
        self.assertIn(location_table["First Win - Peach"], self.ctx.observed_checks)

    async def test_goal_waits_for_connection_and_is_sent_once(self):
        await self.ctx.record_checks({GOAL_LOCATION})
        self.ctx.send_msgs.assert_not_awaited()
        self.ctx.server = SimpleNamespace(socket=SimpleNamespace(open=True, closed=False))
        await self.ctx.record_checks(set())
        await self.ctx.record_checks(set())
        self.ctx.send_msgs.assert_awaited_once()
        self.assertTrue(self.ctx.finished_game)

    async def test_repeated_poll_does_not_resend_checks(self):
        await self.ctx.record_checks({"First Win - Peach"})
        await self.ctx.record_checks({"First Win - Peach"})
        self.ctx.check_locations.assert_awaited_once()

    def boost_memory(self):
        memory = {
            strikers_client.AP_POWERUP_BOOST_MAGIC_ADDR: strikers_client.AP_POWERUP_BOOST_MAGIC
        }
        boundary = "worlds.strikers.Client.dolphin_memory_engine."
        mocks = [
            patch(
                boundary + "read_bytes",
                side_effect=lambda address, size: memory.get(address, 0).to_bytes(size, "big"),
                create=True,
            ),
            patch(
                boundary + "read_byte",
                side_effect=lambda address: memory.get(address, 0),
                create=True,
            ),
            patch(
                boundary + "write_bytes",
                side_effect=lambda address, data: memory.__setitem__(
                    address, int.from_bytes(data, "big")
                ),
                create=True,
            ),
        ]
        for mock in mocks:
            mock.start()
            self.addCleanup(mock.stop)
        self.ctx.items_received = [
            SimpleNamespace(item=item_table["Double Power-Up Boost"], location=1, player=1),
            SimpleNamespace(item=item_table["Power-Up Boost Trap"], location=2, player=1),
        ]
        self.ctx.on_package("ReceivedItems", {"index": 0, "items": []})
        return memory

    async def test_double_boost_trap_queue_acknowledgements_and_repeat_poll(self):
        memory = self.boost_memory()
        await strikers_client.apply_received_items(self.ctx)
        self.assertEqual(memory[strikers_client.AP_POWERUP_BOOST_REQUEST_ADDR], 2)
        self.assertEqual(memory[strikers_client.AP_OPPONENT_POWERUP_REQUEST_ADDR], 2)
        memory[strikers_client.AP_POWERUP_BOOST_APPLIED_ADDR] = 1
        memory[strikers_client.AP_OPPONENT_POWERUP_APPLIED_ADDR] = 2
        await strikers_client.apply_received_items(self.ctx)
        saved = self.storage["strikers_powerup_boosts"][self.ctx.progress_key]
        self.assertEqual((saved["pending_home"], saved["pending_away"]), (1, 0))
        await strikers_client.apply_received_items(self.ctx)
        self.assertEqual(memory[strikers_client.AP_POWERUP_BOOST_REQUEST_ADDR], 2)
        self.assertEqual(memory[strikers_client.AP_OPPONENT_POWERUP_REQUEST_ADDR], 2)

    async def test_delayed_item_history_on_reconnect_preserves_pending_boosts(self):
        memory = self.boost_memory()
        await strikers_client.apply_received_items(self.ctx)
        memory[strikers_client.AP_POWERUP_BOOST_APPLIED_ADDR] = 1
        memory[strikers_client.AP_OPPONENT_POWERUP_APPLIED_ADDR] = 2
        await strikers_client.apply_received_items(self.ctx)
        saved = dict(self.storage["strikers_powerup_boosts"][self.ctx.progress_key])
        history = self.ctx.items_received
        # Connected may arrive several polls before the authoritative history.
        self.ctx.items_received = []
        self.connect()
        await strikers_client.apply_received_items(self.ctx)
        self.assertEqual(self.storage["strikers_powerup_boosts"][self.ctx.progress_key], saved)
        self.ctx.items_received = history
        self.ctx.on_package("ReceivedItems", {"index": 0, "items": []})
        await strikers_client.apply_received_items(self.ctx)
        self.assertEqual(memory[strikers_client.AP_POWERUP_BOOST_REQUEST_ADDR], 2)
        self.assertEqual(memory[strikers_client.AP_OPPONENT_POWERUP_REQUEST_ADDR], 2)

    async def test_new_seed_does_not_consume_boosts_against_old_game_counters(self):
        memory = self.boost_memory()
        memory[strikers_client.AP_POWERUP_BOOST_APPLIED_ADDR] = 8
        memory[strikers_client.AP_OPPONENT_POWERUP_APPLIED_ADDR] = 12
        await strikers_client.apply_received_items(self.ctx)
        self.assertEqual(memory[strikers_client.AP_POWERUP_BOOST_REQUEST_ADDR], 10)
        self.assertEqual(memory[strikers_client.AP_OPPONENT_POWERUP_REQUEST_ADDR], 14)

    async def test_unchanged_reward_poll_does_not_rewrite_storage(self):
        self.boost_memory()
        await strikers_client.apply_received_items(self.ctx)
        with patch("Utils.persistent_store") as save:
            await strikers_client.apply_received_items(self.ctx)
        save.assert_not_called()

    async def test_seed_a_b_a_settles_previous_owner_and_rebases_returning_queue(self):
        memory = self.boost_memory()
        await strikers_client.apply_received_items(self.ctx)
        key_a = self.ctx.progress_key
        # One A reward is consumed between the last poll and changing slots.
        memory[strikers_client.AP_POWERUP_BOOST_APPLIED_ADDR] = 1
        self.ctx.server_seed_name = "seed-b"
        self.connect()
        self.ctx.item_history_received = True
        await strikers_client.apply_received_items(self.ctx)
        memory[strikers_client.AP_POWERUP_BOOST_APPLIED_ADDR] = 3
        memory[strikers_client.AP_OPPONENT_POWERUP_APPLIED_ADDR] = 2
        await strikers_client.apply_received_items(self.ctx)
        self.ctx.server_seed_name = "seed-a"
        self.connect()
        self.ctx.item_history_received = True
        await strikers_client.apply_received_items(self.ctx)
        saved = self.storage["strikers_powerup_boosts"][key_a]
        self.assertEqual((saved["pending_home"], saved["pending_away"]), (1, 2))
        self.assertEqual(memory[strikers_client.AP_POWERUP_BOOST_REQUEST_ADDR], 4)
        self.assertEqual(memory[strikers_client.AP_OPPONENT_POWERUP_REQUEST_ADDR], 4)

    async def test_closed_socket_deathlink_is_not_acknowledged(self):
        memory = self.boost_memory()
        self.ctx.death_link_enabled = True
        self.ctx.server = SimpleNamespace(socket=SimpleNamespace(open=False, closed=True))
        self.ctx.player_names[1] = "Test Player"
        memory[strikers_client.AP_MAILBOX_MAGIC_ADDR] = strikers_client.AP_MAILBOX_MAGIC
        memory[strikers_client.AP_MAILBOX_MODE_ADDR] = 1
        memory[strikers_client.AP_MAILBOX_SEQUENCE_ADDR] = 1
        memory[strikers_client.AP_MAILBOX_COMPLETED_ROUND_ADDR] = 0x80000001
        with self.assertRaises(ConnectionError):
            await strikers_client.check_deathlink_cup_losses(self.ctx)
        self.assertIsNone(self.ctx.deathlink_last_mailbox_sequence)
        self.assertEqual(memory[strikers_client.AP_MAILBOX_COMPLETED_ROUND_ADDR], 0x80000001)

    async def test_load_old_state_after_dolphin_restart_preserves_pending_queue(self):
        memory = self.boost_memory()
        await strikers_client.apply_received_items(self.ctx)
        memory[strikers_client.AP_POWERUP_BOOST_APPLIED_ADDR] = 1
        await strikers_client.apply_received_items(self.ctx)
        # Restart Dolphin, then load a state from a session with larger counters.
        for address in (
            strikers_client.AP_POWERUP_BOOST_APPLIED_ADDR,
            strikers_client.AP_POWERUP_BOOST_REQUEST_ADDR,
            strikers_client.AP_OPPONENT_POWERUP_APPLIED_ADDR,
            strikers_client.AP_OPPONENT_POWERUP_REQUEST_ADDR,
        ):
            memory[address] = 0
        await strikers_client.apply_received_items(self.ctx)
        memory[strikers_client.AP_POWERUP_BOOST_APPLIED_ADDR] = 7
        memory[strikers_client.AP_POWERUP_BOOST_REQUEST_ADDR] = 15
        memory[strikers_client.AP_OPPONENT_POWERUP_APPLIED_ADDR] = 9
        memory[strikers_client.AP_OPPONENT_POWERUP_REQUEST_ADDR] = 20
        await strikers_client.apply_received_items(self.ctx)
        saved = self.storage["strikers_powerup_boosts"][self.ctx.progress_key]
        self.assertEqual((saved["pending_home"], saved["pending_away"]), (1, 2))
        self.assertEqual(memory[strikers_client.AP_POWERUP_BOOST_REQUEST_ADDR], 8)
        self.assertEqual(memory[strikers_client.AP_OPPONENT_POWERUP_REQUEST_ADDR], 11)
        memory[strikers_client.AP_POWERUP_BOOST_APPLIED_ADDR] = 8
        await strikers_client.apply_received_items(self.ctx)
        self.assertEqual(
            self.storage["strikers_powerup_boosts"][self.ctx.progress_key]["pending_home"], 0
        )

    async def test_failed_reward_persistence_does_not_publish_unrecorded_items(self):
        memory = self.boost_memory()
        with patch("Utils.persistent_store", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                await strikers_client.apply_received_items(self.ctx)
        self.assertEqual(memory.get(strikers_client.AP_POWERUP_BOOST_REQUEST_ADDR, 0), 0)
        self.assertEqual(memory.get(strikers_client.AP_OPPONENT_POWERUP_REQUEST_ADDR, 0), 0)
        await strikers_client.apply_received_items(self.ctx)
        self.assertEqual(memory[strikers_client.AP_POWERUP_BOOST_REQUEST_ADDR], 2)
        self.assertEqual(memory[strikers_client.AP_OPPONENT_POWERUP_REQUEST_ADDR], 2)

    async def test_replaying_same_cup_round_sends_a_new_deathlink(self):
        memory = self.boost_memory()
        self.ctx.death_link_enabled = True
        self.ctx.send_death = AsyncMock()
        memory[strikers_client.AP_MAILBOX_MAGIC_ADDR] = strikers_client.AP_MAILBOX_MAGIC
        memory[strikers_client.AP_MAILBOX_MODE_ADDR] = 1
        for sequence in (1, 2):
            memory[strikers_client.AP_MAILBOX_SEQUENCE_ADDR] = sequence
            memory[strikers_client.AP_MAILBOX_COMPLETED_ROUND_ADDR] = 0x80000001
            await strikers_client.check_deathlink_cup_losses(self.ctx)
            await strikers_client.check_deathlink_cup_losses(self.ctx)
        self.assertEqual(self.ctx.send_death.await_count, 2)

    async def test_failed_cup_deathlink_can_retry(self):
        memory = self.boost_memory()
        self.ctx.death_link_enabled = True
        self.ctx.send_death = AsyncMock(side_effect=[OSError("network unavailable"), None])
        memory[strikers_client.AP_MAILBOX_MAGIC_ADDR] = strikers_client.AP_MAILBOX_MAGIC
        memory[strikers_client.AP_MAILBOX_MODE_ADDR] = 1
        memory[strikers_client.AP_MAILBOX_SEQUENCE_ADDR] = 1
        memory[strikers_client.AP_MAILBOX_COMPLETED_ROUND_ADDR] = 0x80000001
        with self.assertRaises(OSError):
            await strikers_client.check_deathlink_cup_losses(self.ctx)
        await strikers_client.check_deathlink_cup_losses(self.ctx)
        self.assertEqual(self.ctx.send_death.await_count, 2)
        self.assertEqual(memory[strikers_client.AP_MAILBOX_COMPLETED_ROUND_ADDR], 1)

    async def test_invalid_cup_mailbox_counts_are_rejected(self):
        memory = self.boost_memory()
        memory[strikers_client.AP_MAILBOX_MAGIC_ADDR] = strikers_client.AP_MAILBOX_MAGIC
        memory[strikers_client.AP_MAILBOX_MODE_ADDR] = 1
        memory[strikers_client.AP_MAILBOX_SEQUENCE_ADDR] = 1
        for count in (0, 4, 0x7FFFFFFF):
            with self.subTest(count=count):
                memory[strikers_client.AP_MAILBOX_COMPLETED_ROUND_ADDR] = count | 0x80000000
                self.assertIsNone(strikers_client.read_cup_mailbox())

    async def test_boost_mailbox_overflow_retains_pending_rewards(self):
        memory = self.boost_memory()
        memory[strikers_client.AP_POWERUP_BOOST_APPLIED_ADDR] = 0xFFFFFFFF
        memory[strikers_client.AP_POWERUP_BOOST_REQUEST_ADDR] = 0xFFFFFFFF
        await strikers_client.apply_received_items(self.ctx)
        saved = self.storage["strikers_powerup_boosts"][self.ctx.progress_key]
        self.assertEqual(saved["pending_home"], 2)
        self.assertEqual(memory[strikers_client.AP_POWERUP_BOOST_REQUEST_ADDR], 0xFFFFFFFF)

    async def test_old_seed_disables_sync(self):
        self.ctx.on_package("Connected", {"slot_data": {"protocol_version": 1}})
        self.assertFalse(self.ctx.protocol_supported)

    async def test_offline_result_is_durable_and_queued_for_reconnect(self):
        self.ctx.slot = None
        await self.ctx.record_checks({"First Win - Peach"})
        self.ctx.check_locations.assert_not_awaited()
        self.assertIn(location_table["First Win - Peach"], self.ctx.locations_checked)
        self.assertIn(
            location_table["First Win - Peach"],
            self.storage["strikers_checks_v2"][self.ctx.progress_key],
        )

    async def test_failed_persistence_is_retried_without_losing_result(self):
        with patch("Utils.persistent_store", side_effect=OSError("test write failure")):
            with self.assertRaises(OSError):
                await self.ctx.record_checks({"First Win - Peach"})
        self.assertTrue(self.ctx.progress_dirty)
        await self.ctx.flush_checks()
        self.assertFalse(self.ctx.progress_dirty)
        self.assertIn(
            location_table["First Win - Peach"],
            self.storage["strikers_checks_v2"][self.ctx.progress_key],
        )

    async def test_bowser_deathlink_loss_once_and_no_win_death(self):
        self.ctx.death_link_enabled = True
        self.ctx.send_death = AsyncMock()
        for mode in (4, 8):
            data = blank()
            struct.pack_into(">i", data, 0x4954, mode)
            struct.pack_into(">I", data, 0x10 + mode * 4, 0x81001000)
            stats = bytearray(STATS_SIZE)
            stats[0x4C2] = 1
            struct.pack_into(">I", stats, 0, 0x81001000)
            info = bytearray(32)
            fixture(info, 0, scores=(1, 3))
            memory = {
                STATS_ADDRESS: struct.pack(">I", 0x81000000),
                0x81000000: stats,
                0x81001000: info,
            }
            with patch(
                "worlds.strikers.Client.dolphin_memory_engine.read_bytes",
                side_effect=lambda address, size: bytes(memory[address][:size]),
                create=True,
            ):
                await check_bowser_deathlink(self.ctx, 0x80800000, data)
                await check_bowser_deathlink(self.ctx, 0x80800000, data)
                stats[0x4C2] = 0
                await check_bowser_deathlink(self.ctx, 0x80800000, data)
                stats[0x4C2] = 1
                fixture(info, 0, scores=(3, 1))
                await check_bowser_deathlink(self.ctx, 0x80800000, data)
                stats[0x4C2] = 0
                await check_bowser_deathlink(self.ctx, 0x80800000, data)
                stats[0x4C2] = 1
                fixture(info, 0, scores=(0, 4))
                self.ctx.send_death.side_effect = [OSError("network unavailable"), None]
                await check_bowser_deathlink(self.ctx, 0x80800000, data)
                self.assertEqual(self.ctx.pending_bowser_deaths, 1)
                await check_bowser_deathlink(self.ctx, 0x80800000, data)
                self.ctx.send_death.side_effect = None
                # A replayed forfeit may have the same fixture, score and Veteran
                # counter. Observing the next match start makes it a new result.
                stats[0x4C2] = 0
                await check_bowser_deathlink(self.ctx, 0x80800000, data)
                stats[0x4C2] = 1
                await check_bowser_deathlink(self.ctx, 0x80800000, data)
                await check_bowser_deathlink(self.ctx, 0x80800000, data)
        self.assertEqual(self.ctx.send_death.await_count, 8)

    async def test_bowser_forfeit_normalization_sends_one_death(self):
        self.ctx.death_link_enabled = True
        self.ctx.send_death = AsyncMock()
        for mode in (4, 8):
            data = blank()
            struct.pack_into(">i", data, 0x4954, mode)
            struct.pack_into(">I", data, 0x10 + mode * 4, 0x81001000)
            stats = bytearray(STATS_SIZE)
            stats[0x4C2] = 1
            struct.pack_into(">I", stats, 0, 0x81001000)
            info = bytearray(32)
            fixture(info, 0, scores=(-5, 0))
            memory = {
                STATS_ADDRESS: struct.pack(">I", 0x81000000),
                0x81000000: stats,
                0x81001000: info,
            }
            with patch(
                "worlds.strikers.Client.dolphin_memory_engine.read_bytes",
                side_effect=lambda address, size: bytes(memory[address][:size]),
                create=True,
            ):
                await check_bowser_deathlink(self.ctx, 0x80800000, data)
                fixture(info, 0, scores=(0, 3))
                struct.pack_into(">H", data, USER_INFO + 0x1112, 1)
                await check_bowser_deathlink(self.ctx, 0x80800000, data)
                # Native autosave refreshes mSaveID seconds after the forfeit.
                struct.pack_into(">I", data, USER_INFO, 123456)
                await check_bowser_deathlink(self.ctx, 0x80800000, data)
        self.assertEqual(self.ctx.send_death.await_count, 2)

    async def test_bowser_acknowledgement_survives_restart_and_is_seed_scoped(self):
        key = (0x80800000, 4, 0x81001000)
        self.ctx.remember_bowser_result(key)
        restored = StrikersContext(None, None)
        restored.team, restored.slot, restored.server_seed_name = 0, 1, "seed-a"
        restored.update_death_link = AsyncMock()
        restored.check_locations = AsyncMock()
        restored.on_package("Connected", {"slot_data": {"protocol_version": 2}})
        self.assertEqual(restored.last_bowser_result, key)
        restored.server_seed_name = "seed-b"
        restored.on_package("Connected", {"slot_data": {"protocol_version": 2}})
        self.assertIsNone(restored.last_bowser_result)
        restored.server_seed_name = "seed-a"
        restored.on_package("Connected", {"slot_data": {"protocol_version": 2}})
        self.assertEqual(restored.last_bowser_result, key)
        restored.remember_bowser_result(None)
        self.assertIsNone(
            self.storage["strikers_bowser_deathlink_v1"][restored.progress_key]["result"]
        )

    async def test_bowser_acknowledgement_retries_storage_without_forgetting_send(self):
        key = (0x80800000, 8, 0x81001000)
        with patch("Utils.persistent_store", side_effect=OSError("storage unavailable")):
            with self.assertRaises(OSError):
                self.ctx.remember_bowser_result(key)
        self.assertEqual(self.ctx.last_bowser_result, key)
        self.assertTrue(self.ctx.bowser_result_dirty)
        self.ctx.remember_bowser_result(key)
        self.assertFalse(self.ctx.bowser_result_dirty)
        self.assertEqual(
            self.storage["strikers_bowser_deathlink_v1"][self.ctx.progress_key]["result"], list(key)
        )
        with patch("Utils.persistent_store") as save:
            self.ctx.remember_bowser_result(key)
        save.assert_not_called()
