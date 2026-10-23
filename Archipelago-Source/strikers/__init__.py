from BaseClasses import Entrance, ItemClassification, Region
from worlds.AutoWorld import World
from worlds.LauncherComponents import Component, Type, components, launch

from .Data import PROTOCOL_VERSION
from .Goals import goal_location, validate_options
from .Items import CHEAT_UNLOCKS, StrikersItem, item_flag_addresses, item_table
from .Locations import StrikersLocation, location_groups, location_table
from .Options import StrikersOptions
from .Unlocks import goal_access, location_access, progression_items, validate_unlocks


class StrikersWorld(World):
    """Super Mario Strikers for Nintendo GameCube."""

    game = "Super Mario Strikers"
    topology_present = True
    options_dataclass = StrikersOptions
    item_name_to_id = item_table
    location_name_to_id = location_table

    def generate_early(self):
        options = self.fill_slot_data()
        validate_options(options)
        count = sum(
            len(names) for name, names in location_groups(options).items() if name != "Goal"
        )
        validate_unlocks(options, count)
        if (
            sum(len(names) for name, names in location_groups(options).items() if name != "Goal")
            == 0
        ):
            raise ValueError("Enable at least one non-goal location")

    def create_regions(self):
        menu = Region("Menu", self.player, self.multiworld)
        self.multiworld.regions.append(menu)
        for name, locations in location_groups(self.fill_slot_data()).items():
            region = Region(name, self.player, self.multiworld)
            self.multiworld.regions.append(region)
            entrance = Entrance(self.player, f"Menu -> {name}", menu)
            menu.exits.append(entrance)
            entrance.connect(region)
            for location_name in locations:
                region.locations.append(
                    StrikersLocation(
                        self.player,
                        location_name,
                        location_table[location_name],
                        region,
                    )
                )
        options = self.fill_slot_data()
        checks = [
            location
            for location in self.multiworld.get_locations(self.player)
            if location.name != goal_location(options)
        ]
        for location in checks:
            location.access_rule = lambda state, name=location.name: location_access(
                options, name, lambda item: state.has(item, self.player)
            )
        self.multiworld.get_location(goal_location(options), self.player).access_rule = (
            lambda state: goal_access(
                options, [loc.name for loc in checks], lambda item: state.has(item, self.player)
            )
        )
        self.multiworld.get_location(
            goal_location(self.fill_slot_data()), self.player
        ).place_locked_item(self.create_item("Victory"))
        self.multiworld.completion_condition[self.player] = lambda state: state.has(
            "Victory", self.player
        )

    def create_item(self, name: str) -> StrikersItem:
        if name == "Victory" or name in progression_items(self.fill_slot_data()):
            classification = ItemClassification.progression
        elif name in item_flag_addresses:
            classification = ItemClassification.useful
        elif name == "Power-Up Boost Trap":
            classification = ItemClassification.trap
        else:
            classification = ItemClassification.filler
        return StrikersItem(name, classification, item_table[name], self.player)

    def create_items(self):
        count = len(self.multiworld.get_unfilled_locations(self.player))
        unlocks = [
            name
            for name in item_flag_addresses
            if name not in CHEAT_UNLOCKS or name in self.options.cheat_unlocks.value
        ]
        required = sorted(progression_items(self.fill_slot_data()))
        optional = [name for name in unlocks if name not in required]
        # Starting randomized Super Team must not leave a duplicate useful item.
        if self.options.randomize_captains and "Super Team" in self.options.starting_captains.value:
            optional = [name for name in optional if name != "Super Team Unlock"]
        if count - len(required) < len(optional):
            optional = self.random.sample(optional, count - len(required))
        unlocks = required + optional
        for name in unlocks:
            self.multiworld.itempool.append(self.create_item(name))
        filler_count = count - len(unlocks)
        weight = self.options.trap_weight.value if self.options.enable_traps.value else 0
        traps = (filler_count * weight + 50) // 100
        helpful_count = filler_count - traps
        boosts = (helpful_count * self.options.powerup_weight.value + 50) // 100
        doubles = boosts * self.options.double_powerup_weight.value // 100
        self.multiworld.itempool.extend(
            self.create_item("Nothing") for _ in range(helpful_count - boosts)
        )
        self.multiworld.itempool.extend(
            self.create_item("Power-Up Boost") for _ in range(boosts - doubles)
        )
        self.multiworld.itempool.extend(
            self.create_item("Double Power-Up Boost") for _ in range(doubles)
        )
        self.multiworld.itempool.extend(
            self.create_item("Power-Up Boost Trap") for _ in range(traps)
        )

    def fill_slot_data(self):
        names = (
            "placement_checks",
            "milestone_checks",
            "captain_win_checks",
            "stadium_win_checks",
            "combo_checks",
            "character_unlock_checks",
            "enable_traps",
            "trap_weight",
            "death_link",
            "required_battle_trophies",
            "required_match_wins",
            "milestone_max_tier",
            "starting_cup_unlocks",
            "cup_match_checks",
            "cup_win_bonus_count",
            "milestone_requirement_percent",
            "powerup_weight",
            "double_powerup_weight",
            "randomize_captains",
            "randomize_sidekicks",
            "randomize_cups",
        )
        return {
            "protocol_version": PROTOCOL_VERSION,
            "game_id": "G4QE01",
            "goal": self.options.goal.current_key,
            "included_cups": sorted(self.options.included_cups.value),
            "required_cups": sorted(self.options.required_cups.value),
            **{
                name: sorted(getattr(self.options, name).value)
                for name in (
                    "included_captains",
                    "included_stadiums",
                    "custom_sidekick_combos",
                    "custom_stadium_combos",
                    "cheat_unlocks",
                    "starting_captains",
                    "starting_sidekicks",
                    "starting_cups",
                )
            },
            **{name: getattr(self.options, name).value for name in names},
        }


def run_client(*args: str) -> None:
    from .Client import main

    launch(main, name="StrikersClient", args=args)


components.append(
    Component("Super Mario Strikers Client", func=run_client, component_type=Type.CLIENT)
)
