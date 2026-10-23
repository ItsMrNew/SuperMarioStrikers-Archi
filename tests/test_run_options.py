import itertools
import json
import struct
import unittest
from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from . import test_expansion as fixtures
from .test_expansion import blank
from worlds.strikers import StrikersWorld
from worlds.strikers import Client
from worlds.strikers.Goals import goal_location, goal_reached
from worlds.strikers.Locations import location_groups, location_table
from worlds.strikers.Memory import (
    FriendlyTracker,
    LiveMatch,
    Match,
    MANAGER_ADDRESS,
    TROPHIES,
)
from worlds.strikers.Options import IncludedCups, RequiredCups, StartingCupUnlocks
from test.general import setup_multiworld
from Fill import distribute_items_restrictive
import yaml


class RunOptionTests(unittest.TestCase):
    def test_bundled_yaml_examples_parse_verify_and_fill(self):
        root = Path(__file__).resolve().parents[1]
        for path in [root / "Strikers.yaml", *sorted((root / "examples").glob("*.yaml"))]:
            options = yaml.safe_load(path.read_text())[StrikersWorld.game]
            mw = setup_multiworld(StrikersWorld, options=options, seed=22)
            for name in options:
                getattr(mw.worlds[1].options, name).verify(mw.worlds[1], "Tester1", 0)
            distribute_items_restrictive(mw)
            self.assertFalse(mw.get_unfilled_locations(), path.name)

    def test_shortest_pool_and_all_goals_fill(self):
        for goal, tier, access in itertools.product(range(4), range(3), range(4)):
            mw = setup_multiworld(
                StrikersWorld,
                options={
                    "goal": goal,
                    "required_battle_trophies": 1,
                    "included_cups": ["Mushroom Cup"],
                    "required_cups": ["Mushroom Cup"],
                    "required_match_wins": 1,
                    "milestone_max_tier": tier,
                    "starting_cup_unlocks": access,
                    "placement_checks": False,
                    "milestone_checks": False,
                    "captain_win_checks": False,
                    "stadium_win_checks": False,
                    "combo_checks": 0,
                },
                seed=22,
            )
            slot = mw.worlds[1].fill_slot_data()
            json.dumps(slot)
            self.assertEqual(slot["protocol_version"], 6)
            self.assertEqual(len(mw.itempool), 8)
            self.assertEqual(len(mw.get_locations()), 9)
            distribute_items_restrictive(mw)
            self.assertFalse(mw.get_unfilled_locations())
            self.assertEqual(mw.get_location(goal_location(slot), 1).item.name, "Victory")

    def test_invalid_goal_configurations_fail_early(self):
        cases = [
            {"included_cups": ["Mushroom Cup"]},
            {"goal": 1, "required_cups": []},
            {"goal": 1, "included_cups": ["Mushroom Cup"]},
            {
                "goal": 3,
                "included_cups": [],
                "placement_checks": False,
                "milestone_checks": False,
                "captain_win_checks": False,
                "stadium_win_checks": False,
                "combo_checks": 0,
            },
        ]
        for options in cases:
            with self.subTest(options=options), self.assertRaises(ValueError):
                setup_multiworld(StrikersWorld, options=options)
        with self.assertRaises(ValueError):
            IncludedCups.from_any(["Bowzers Cup"])

    def test_lists_all_defaults_and_independent_access(self):
        self.assertEqual(len(IncludedCups.from_any("all").value), 8)
        self.assertEqual(
            RequiredCups.from_any("Mushroom Cup, Flower Cup").value, {"Mushroom Cup", "Flower Cup"}
        )
        self.assertEqual(StartingCupUnlocks.from_any("natural").value, 0)
        mw = setup_multiworld(StrikersWorld)
        default = mw.worlds[1].fill_slot_data()
        self.assertEqual(len(mw.get_locations()), 182)
        for access in range(4):
            self.assertEqual(
                location_groups(default),
                location_groups(dict(default, starting_cup_unlocks=access)),
            )

    def test_medal_tier_and_cup_filters(self):
        for tier in range(3):
            groups = location_groups(
                {"included_cups": ["Super Bowser Cup"], "milestone_max_tier": tier}
            )
            self.assertEqual(len(groups["Milestone Trophies"]), 5 * (tier + 1))
            self.assertIn("Super Bowser Cup", groups)
            self.assertNotIn("Mushroom Cup", groups)
        self.assertNotIn("Milestone Trophies", location_groups({"milestone_checks": False}))

    def test_trophy_goal_every_mask_and_target(self):
        for mask, target in itertools.product(range(256), range(1, 9)):
            self.assertEqual(
                goal_reached(
                    {"goal": "battle_trophies", "required_battle_trophies": target},
                    mask,
                    0,
                    set(),
                    set(),
                ),
                mask.bit_count() >= target,
            )
        options = {
            "goal": "battle_trophies",
            "required_battle_trophies": 1,
            "included_cups": ["Mushroom Cup"],
        }
        self.assertFalse(goal_reached(options, 254, 99, set(), set()))
        self.assertTrue(goal_reached(options, 1, 0, set(), set()))

    def test_other_goal_boundaries(self):
        options = {"goal": "selected_cups", "required_cups": ["Mushroom Cup", "Super Bowser Cup"]}
        for mask in range(256):
            self.assertEqual(goal_reached(options, mask, 0, set(), set()), mask & 129 == 129)
        options = {"goal": "match_wins", "required_match_wins": 25}
        self.assertFalse(goal_reached(options, 255, 24, {1}, {1}))
        self.assertTrue(goal_reached(options, 0, 25, set(), {1}))
        options = {"goal": "all_enabled_checks"}
        self.assertFalse(goal_reached(options, 255, 100, {1}, {1, 2}))
        self.assertTrue(goal_reached(options, 0, 0, {1, 2}, {1, 2}))
        self.assertFalse(goal_reached(options, 0, 0, set(), set()))

    def test_cup_end_transition_both_sides_and_exclusions(self):
        for side, mode in itertools.product((0, 1), range(1, 9)):
            match = Match((3, 2), (0, 1), 0, (side, -1, -1, -1), (3, 1) if side == 0 else (1, 3))
            live = LiveMatch((mode,), match, False, (0, 0), True)
            tracker = FriendlyTracker()
            tracker.observe(live)
            self.assertTrue(tracker.observe(replace(live, ended=True)))
            self.assertFalse(tracker.observe(replace(live, ended=True)))
            self.assertFalse(FriendlyTracker().observe(replace(live, ended=True)))
            tracker.observe(live)
            self.assertFalse(tracker.observe(replace(live, identity=(99,), ended=True)))
        for scores in ((0, 0), (1, 3), (-5, 3)):
            live = LiveMatch(
                (1,), Match((3, 2), (0, 1), 0, (0, -1, -1, -1), scores), False, (0, 0), True
            )
            tracker = FriendlyTracker()
            tracker.observe(live)
            self.assertFalse(tracker.observe(replace(live, ended=True)))


# Reuse the real client fixture without inheriting/repeating its old test suite.
class RunClientTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.ClientChecks.asyncSetUp
    asyncTearDown = fixtures.ClientChecks.asyncTearDown
    connect = fixtures.ClientChecks.connect

    async def test_first_unlock_check_works_before_any_received_items(self):
        from worlds.strikers.Items import item_table

        self.connect(protocol_version=5, randomize_captains=True, randomize_cups=True)
        data = blank()
        data[TROPHIES] = 255
        self.game_memory(data)
        # A stale inventory must not open checks before the new index-zero packet.
        self.ctx.items_received = [SimpleNamespace(item=item_table["Flower Cup Unlock"])]
        candidates = {"Mushroom Cup - Match 1", "Flower Cup - Match 1", "First Win - Peach"}
        with (
            patch.object(Client, "read_friendly", return_value=None),
            patch.object(Client, "saved_locations", side_effect=lambda *_: set(candidates)),
        ):
            await Client.check_expansion_locations(self.ctx)
            self.ctx.check_locations.assert_awaited_once_with(
                {location_table["Mushroom Cup - Match 1"]}
            )
            self.assertNotIn(location_table["All Eight Battle Trophies"], self.ctx.observed_checks)
            self.ctx.on_package("ReceivedItems", {"index": 0, "items": []})
            await Client.check_expansion_locations(self.ctx)
            self.assertIn(location_table["Flower Cup - Match 1"], self.ctx.observed_checks)
            self.assertNotIn(location_table["First Win - Peach"], self.ctx.observed_checks)

    def game_memory(self, data):
        memory = {MANAGER_ADDRESS: struct.pack(">I", 0x80800000), 0x80800000: data}
        mock = patch(
            "worlds.strikers.Client.dolphin_memory_engine.read_bytes",
            side_effect=lambda address, size: bytes(memory[address][:size]),
            create=True,
        )
        mock.start()
        self.addCleanup(mock.stop)

    async def test_match_wins_persist_once_and_ignore_saved_trophies(self):
        self.connect(protocol_version=3, goal="match_wins", required_match_wins=2)
        data = blank()
        data[TROPHIES] = 255
        self.game_memory(data)
        self.ctx.server = SimpleNamespace(socket=SimpleNamespace(open=True, closed=False))
        live = LiveMatch(
            (1,), Match((3, 2), (0, 1), 0, (0, -1, -1, -1), (3, 1)), False, (0, 0), True
        )
        with patch.object(Client, "read_friendly", return_value=live) as read:
            await Client.check_expansion_locations(self.ctx)
            self.assertNotIn(location_table["Goal Complete"], self.ctx.observed_checks)
            self.ctx.send_msgs.assert_not_awaited()
            read.return_value = replace(live, ended=True)
            await Client.check_expansion_locations(self.ctx)
            await Client.check_expansion_locations(self.ctx)
            self.assertEqual(self.ctx.match_wins, 1)
            self.assertEqual(self.storage["strikers_match_wins_v3"][self.ctx.progress_key], 1)
            self.ctx.server_seed_name = "seed-b"
            self.connect(protocol_version=3, goal="match_wins")
            self.assertEqual(self.ctx.match_wins, 0)
            self.ctx.server_seed_name = "seed-a"
            self.connect(protocol_version=3, goal="match_wins", required_match_wins=2)
            self.assertEqual(self.ctx.match_wins, 1)
            await Client.check_expansion_locations(self.ctx)
            self.assertEqual(self.ctx.match_wins, 1)
            read.return_value = live
            await Client.check_expansion_locations(self.ctx)
            read.return_value = replace(live, ended=True)
            with patch("Utils.persistent_store", side_effect=OSError("disk")):
                with self.assertRaises(OSError):
                    await Client.check_expansion_locations(self.ctx)
            await Client.check_expansion_locations(self.ctx)
            self.assertEqual(self.ctx.match_wins, 2)
            self.assertIn(location_table["Goal Complete"], self.ctx.observed_checks)
            await Client.check_expansion_locations(self.ctx)
            self.assertTrue(self.ctx.finished_game)
            self.ctx.send_msgs.assert_awaited_once()

    async def test_all_checks_excludes_goal_and_disabled_locations(self):
        self.connect(
            protocol_version=3,
            goal="all_enabled_checks",
            included_cups=[],
            milestone_checks=False,
            stadium_win_checks=False,
            combo_checks=0,
        )
        self.game_memory(blank())
        with patch.object(Client, "read_friendly", return_value=None):
            await Client.check_expansion_locations(self.ctx)
            self.assertNotIn(location_table["Goal Complete"], self.ctx.observed_checks)
            self.ctx.locations_checked.update(
                self.ctx.active_checks - {location_table["Goal Complete"]}
            )
            await Client.check_expansion_locations(self.ctx)
            self.assertIn(location_table["Goal Complete"], self.ctx.observed_checks)

    async def test_required_trophies_and_selected_goal_client(self):
        for goal, extra, mask in (
            ("battle_trophies", {"required_battle_trophies": 2}, 3),
            ("selected_cups", {"required_cups": ["Super Bowser Cup"]}, 128),
        ):
            self.ctx.server_seed_name = goal
            self.connect(protocol_version=3, goal=goal, **extra)
            data = blank()
            self.game_memory(data)
            with patch.object(Client, "read_friendly", return_value=None):
                await Client.check_expansion_locations(self.ctx)
                self.assertNotIn(location_table["Goal Complete"], self.ctx.observed_checks)
                data[TROPHIES] = mask
                await Client.check_expansion_locations(self.ctx)
                self.assertIn(location_table["Goal Complete"], self.ctx.observed_checks)
