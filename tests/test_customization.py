import itertools
import json
import struct
import unittest
from collections import Counter
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from . import test_expansion as fixtures
from .test_expansion import blank, fixture
from worlds.strikers import StrikersWorld, Client
from worlds.strikers.Data import MILESTONES, milestone_thresholds
from worlds.strikers.Items import CHEAT_UNLOCKS
from worlds.strikers.Locations import location_groups, location_table
from worlds.strikers.Memory import STATS_ADDRESS, STATS_SIZE, TROPHIES, USER_INFO, saved_locations
from worlds.strikers.Options import CustomSidekickCombos, IncludedCaptains
from worlds.strikers.Progress import progress_lines
from test.general import setup_multiworld
from Fill import distribute_items_restrictive


class CustomizationTests(unittest.TestCase):
    def test_cup_density_goals_and_minimal_pools_fill(self):
        for goal, matches, bonuses, placements in itertools.product(
            range(4), (False, True), (0, 1, 5), (False, True)
        ):
            options = dict(
                goal=goal,
                required_battle_trophies=1,
                required_cups=["Mushroom Cup"],
                included_cups=["Mushroom Cup"],
                cup_match_checks=matches,
                cup_win_bonus_count=bonuses,
                placement_checks=placements,
                milestone_checks=False,
                captain_win_checks=False,
                stadium_win_checks=False,
                combo_checks=0,
            )
            expected = 3 * matches + bonuses + 3 * placements
            if not expected:
                with self.assertRaises(ValueError):
                    setup_multiworld(StrikersWorld, options=options)
                continue
            mw = setup_multiworld(StrikersWorld, options=options, seed=31)
            self.assertEqual(len(mw.itempool), expected)
            self.assertEqual(len(mw.get_locations()), expected + 1)
            distribute_items_restrictive(mw)
            self.assertFalse(mw.get_unfilled_locations())

    def test_scaled_milestone_boundaries_preserve_native_data(self):
        for percent, name in itertools.product((10, 25, 50, 100, 200), MILESTONES):
            options = {"milestone_requirement_percent": percent}
            thresholds = milestone_thresholds(name, options)
            for medal, target in zip(("Bronze", "Silver", "Gold"), thresholds):
                data = blank()
                offset = USER_INFO + MILESTONES[name][0]
                location = f"{medal} {name} Trophy"
                struct.pack_into(">H", data, offset, target - 1)
                self.assertNotIn(location, saved_locations(data, options))
                struct.pack_into(">H", data, offset, target)
                original = bytes(data)
                self.assertIn(location, saved_locations(data, options))
                self.assertEqual(data, original)
        self.assertEqual(
            milestone_thresholds("Veteran", {"milestone_requirement_percent": 10}), (3, 5, 10)
        )

    def test_challenge_filters_and_custom_pairs(self):
        mw = setup_multiworld(
            StrikersWorld,
            options={
                "included_captains": ["Peach", "Yoshi"],
                "included_stadiums": ["The Palace"],
                "combo_checks": "custom",
                "custom_sidekick_combos": ["Win with Yoshi + Birdo", "Win with Mario + Toad"],
                "custom_stadium_combos": [
                    "Win with Peach at The Palace",
                    "Win with Yoshi at Crater Field",
                ],
            },
        )
        slot = mw.worlds[1].fill_slot_data()
        json.dumps(slot)
        groups = location_groups(slot)
        self.assertEqual(groups["Captain Wins"], ["First Win - Peach", "First Win - Yoshi"])
        self.assertEqual(groups["Stadium Wins"], ["First Win at The Palace"])
        self.assertEqual(groups["Captain and Sidekick Wins"], ["Win with Yoshi + Birdo"])
        self.assertEqual(groups["Captain and Stadium Wins"], ["Win with Peach at The Palace"])
        self.assertEqual(len(IncludedCaptains.from_any("all").value), 9)
        with self.assertRaises(ValueError):
            CustomSidekickCombos.from_any(["Win with Yoshi + Toads"])
        distribute_items_restrictive(mw)
        self.assertFalse(mw.get_unfilled_locations())

    def test_filler_controls_exact_counts_and_cheat_selection(self):
        for traps, boost, double in itertools.product((0, 37, 100), (0, 50, 100), (0, 50, 100)):
            mw = setup_multiworld(
                StrikersWorld,
                options={
                    "enable_traps": True,
                    "trap_weight": traps,
                    "powerup_weight": boost,
                    "double_powerup_weight": double,
                    "cheat_unlocks": [],
                },
            )
            counts = Counter(item.name for item in mw.itempool)
            self.assertFalse(set(counts) & CHEAT_UNLOCKS)
            filler = sum(
                counts[n]
                for n in (
                    "Nothing",
                    "Power-Up Boost",
                    "Double Power-Up Boost",
                    "Power-Up Boost Trap",
                )
            )
            expected_traps = (filler * traps + 50) // 100
            expected_boosts = ((filler - expected_traps) * boost + 50) // 100
            self.assertEqual(counts["Power-Up Boost Trap"], expected_traps)
            self.assertEqual(counts["Double Power-Up Boost"], expected_boosts * double // 100)
            self.assertEqual(
                counts["Power-Up Boost"], expected_boosts - expected_boosts * double // 100
            )
            self.assertEqual(counts["Nothing"], filler - expected_traps - expected_boosts)
            self.assertEqual(len(mw.itempool), len(mw.get_unfilled_locations()))
        mw = setup_multiworld(StrikersWorld, options={"cheat_unlocks": ["Giant Cheat"]})
        self.assertEqual({item.name for item in mw.itempool} & CHEAT_UNLOCKS, {"Giant Cheat"})

    def test_progress_targets_missing_cups_and_enabled_checks(self):
        data = blank()
        data[TROPHIES] = 1
        options = dict(
            goal="selected_cups",
            required_cups=["Mushroom Cup", "Flower Cup"],
            included_cups=["Mushroom Cup", "Flower Cup"],
            cup_match_checks=False,
            cup_win_bonus_count=0,
            milestone_checks=False,
            captain_win_checks=False,
            stadium_win_checks=False,
            combo_checks=0,
        )
        lines = "\n".join(
            progress_lines(options, data, 0, {location_table["Mushroom Cup - Champion"]})
        )
        self.assertIn("Cup trophies: 1/2", lines)
        self.assertIn("Required cups remaining: Flower Cup", lines)
        self.assertIn("Checks: 1/6", lines)
        self.assertIn(
            "Match wins: 7/10",
            "\n".join(
                progress_lines(
                    dict(options, goal="match_wins", required_match_wins=10), None, 7, set()
                )
            ),
        )
        self.assertIn("waiting for a stable", "\n".join(progress_lines(options, None, 0, set())))
        self.assertIn(
            "Next Veteran: 0/13 (Bronze, AP target)",
            "\n".join(progress_lines({"milestone_requirement_percent": 50}, data, 0, set())),
        )


class OutboxTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.ClientChecks.asyncSetUp
    asyncTearDown = fixtures.ClientChecks.asyncTearDown
    connect = fixtures.ClientChecks.connect

    def bowser_memory(self):
        data = blank()
        struct.pack_into(">i", data, 0x4954, 4)
        struct.pack_into(">I", data, 0x20, 0x81001000)
        stats = bytearray(STATS_SIZE)
        struct.pack_into(">I", stats, 0, 0x81001000)
        stats[0x4C2] = 1
        info = bytearray(32)
        fixture(info, 0, scores=(0, 3))
        memory = {STATS_ADDRESS: struct.pack(">I", 0x81000000), 0x81000000: stats, 0x81001000: info}
        mock = patch(
            "worlds.strikers.Client.dolphin_memory_engine.read_bytes",
            side_effect=lambda a, n: bytes(memory[a][:n]),
            create=True,
        )
        mock.start()
        self.addCleanup(mock.stop)
        return data, stats

    async def test_offline_loss_leaves_results_restart_and_delivers_once(self):
        self.connect(death_link=True)
        data, stats = self.bowser_memory()
        self.ctx.slot = None
        await Client.check_bowser_deathlink(self.ctx, 0x80800000, data)
        await Client.check_bowser_deathlink(self.ctx, 0x80800000, data)
        self.assertEqual(self.ctx.pending_bowser_deaths, 1)
        # Leave results/start another game while still offline; pending survives.
        stats[0x4C2] = 0
        await Client.check_bowser_deathlink(self.ctx, 0x80800000, data)
        self.assertIsNone(self.ctx.last_bowser_result)
        restored = Client.StrikersContext(None, None)
        restored.team, restored.slot, restored.server_seed_name = 0, 1, "seed-a"
        restored.update_death_link = AsyncMock()
        restored.check_locations = AsyncMock()
        restored.send_death = AsyncMock()
        restored.on_package("Connected", {"slot_data": {"protocol_version": 4, "death_link": True}})
        self.assertEqual(restored.pending_bowser_deaths, 1)
        await restored.flush_bowser_deaths()
        await restored.flush_bowser_deaths()
        restored.send_death.assert_awaited_once()
        self.assertEqual(
            self.storage["strikers_bowser_deathlink_v1"][restored.progress_key]["pending"], 0
        )

    async def test_failed_storage_does_not_send_or_duplicate_and_socket_retry(self):
        self.connect(death_link=True)
        data, _ = self.bowser_memory()
        self.ctx.send_death = AsyncMock()
        with patch("Utils.persistent_store", side_effect=OSError("disk")):
            with self.assertRaises(OSError):
                await Client.check_bowser_deathlink(self.ctx, 0x80800000, data)
        self.ctx.send_death.assert_not_awaited()
        self.assertEqual(self.ctx.pending_bowser_deaths, 1)
        self.ctx.send_death.side_effect = ConnectionError("offline")
        await Client.check_bowser_deathlink(self.ctx, 0x80800000, data)
        self.assertEqual(self.ctx.pending_bowser_deaths, 1)
        self.ctx.send_death.side_effect = None
        await self.ctx.flush_bowser_deaths()
        self.assertEqual(self.ctx.pending_bowser_deaths, 0)

    async def test_queue_is_seed_scoped_and_legacy_ack_migrates(self):
        key = self.ctx.progress_key
        self.ctx.remember_bowser_result((1, 4, 2), loss=True)
        self.ctx.server_seed_name = "seed-b"
        self.connect(death_link=True)
        self.assertEqual(self.ctx.pending_bowser_deaths, 0)
        self.ctx.server_seed_name = "seed-a"
        self.connect(death_link=True)
        self.assertEqual(self.ctx.pending_bowser_deaths, 1)
        self.storage.pop("strikers_bowser_deathlink_v1")
        self.storage["strikers_bowser_result_v2"] = {key: [1, 4, 2]}
        restored = Client.StrikersContext(None, None)
        restored.team, restored.slot, restored.server_seed_name = 0, 1, "seed-a"
        restored.update_death_link = AsyncMock()
        restored.check_locations = AsyncMock()
        restored.on_package("Connected", {"slot_data": {"protocol_version": 2}})
        self.assertEqual(restored.last_bowser_result, (1, 4, 2))
        self.assertEqual(restored.pending_bowser_deaths, 0)

    async def test_pending_loss_does_not_send_to_an_unsupported_or_disabled_slot(self):
        self.connect(death_link=True)
        self.ctx.remember_bowser_result((1, 4, 2), loss=True)
        self.ctx.send_death = AsyncMock()
        self.connect(protocol_version=999, death_link=True)
        await self.ctx.flush_bowser_deaths()
        self.ctx.send_death.assert_not_awaited()
        self.connect(death_link=False)
        await self.ctx.flush_bowser_deaths()
        self.ctx.send_death.assert_not_awaited()
        self.assertEqual(self.ctx.pending_bowser_deaths, 1)
        self.connect(death_link=True)
        await self.ctx.flush_bowser_deaths()
        self.ctx.send_death.assert_awaited_once()

    async def test_switching_seed_during_send_acknowledges_the_outgoing_queue(self):
        self.connect(death_link=True)
        owner = self.ctx.progress_key
        self.ctx.remember_bowser_result((1, 4, 2), loss=True)

        async def send_and_switch(_):
            self.ctx.server_seed_name = "seed-b"
            self.connect(death_link=True)

        self.ctx.send_death = AsyncMock(side_effect=send_and_switch)
        await self.ctx.flush_bowser_deaths()
        self.assertEqual(self.ctx.pending_bowser_deaths, 0)
        self.assertEqual(self.storage["strikers_bowser_deathlink_v1"][owner]["pending"], 0)
        self.ctx.server_seed_name = "seed-a"
        self.connect(death_link=True)
        await self.ctx.flush_bowser_deaths()
        self.ctx.send_death.assert_awaited_once()

    async def test_client_scaled_and_filtered_checks(self):
        self.connect(
            protocol_version=4,
            goal="all_enabled_checks",
            included_cups=[],
            milestone_max_tier=0,
            milestone_requirement_percent=10,
            captain_win_checks=False,
            stadium_win_checks=False,
            combo_checks=0,
        )
        data = blank()
        for name, (offset, _) in MILESTONES.items():
            struct.pack_into(
                ">H", data, USER_INFO + offset, milestone_thresholds(name, self.ctx.slot_data)[0]
            )
        memory = {Client.MANAGER_ADDRESS: struct.pack(">I", 0x80800000), 0x80800000: data}
        self.ctx.server = SimpleNamespace(socket=SimpleNamespace(open=True, closed=False))
        with (
            patch.object(
                Client.dolphin_memory_engine,
                "read_bytes",
                side_effect=lambda a, n: bytes(memory[a][:n]),
                create=True,
            ),
            patch.object(Client, "read_friendly", return_value=None),
        ):
            await Client.check_expansion_locations(self.ctx)
        self.assertEqual(len(self.ctx.observed_checks), 6)
        self.assertTrue(self.ctx.finished_game)
        self.assertEqual(self.ctx.last_game_data, data)
