from dataclasses import dataclass

from Options import (
    Choice,
    DeathLink,
    DefaultOnToggle,
    OptionSet,
    PerGameCommonOptions,
    Range,
    Toggle,
)

from .Data import CAPTAINS, CUPS, SIDEKICKS, STADIUMS
from .Items import CHEAT_UNLOCKS


class Goal(Choice):
    """Win a number of distinct included cup trophies, win every required cup,
    win a number of matches while connected to Dolphin, or finish every enabled check.
    Milestone medals do not count as battle trophies.
    """

    display_name = "Goal"
    option_battle_trophies = 0
    option_selected_cups = 1
    option_match_wins = 2
    option_all_enabled_checks = 3
    default = 0


class RequiredBattleTrophies(Range):
    """Distinct included cup trophies needed for the battle_trophies goal."""

    display_name = "Required Battle Trophies"
    range_start = 1
    range_end = 8
    default = 8


class CupSet(OptionSet):
    valid_keys = {cup.name for cup in CUPS} | {"all"}

    def __init__(self, value, random_str=None):
        super().__init__(value, random_str)
        unknown = self.value - self.valid_keys
        if unknown:
            raise ValueError(f"Unknown cup(s): {', '.join(sorted(unknown))}")
        if "all" in self.value:
            self.value = {cup.name for cup in CUPS}

    def verify(self, world, player_name, plando_options):
        super().verify(world, player_name, plando_options)
        if "all" in self.value:
            self.value = {cup.name for cup in CUPS}


class IncludedCups(CupSet):
    """Cups that contain match, placement and cup bonus locations. Use all or a
    list of cup names. Does not unlock or hide cups in the game.
    """

    display_name = "Included Cups"
    default = frozenset({"all"})


class RequiredCups(CupSet):
    """Win every listed cup for selected_cups. Must be nonempty and included.
    Ignored by other goals.
    """

    display_name = "Required Cups"
    default = frozenset({"Super Bowser Cup"})


class RequiredMatchWins(Range):
    """Wins needed for match_wins. Counts cup and Grudge wins observed by the
    running client, including replays. Existing save results do not add wins.
    """

    display_name = "Required Match Wins"
    range_start = 1
    range_end = 100
    default = 25


class MilestoneMaxTier(Choice):
    """Highest enabled milestone tier; includes all lower tiers.
    Ignored when milestone_checks is false.
    """

    display_name = "Maximum Milestone Tier"
    option_bronze = 0
    option_silver = 1
    option_gold = 2
    default = 2


class StartingCupUnlocks(Choice):
    """Extra cup access when the client connects: none keeps natural progression;
    regular opens all four regular cups; super opens the Super Cup menu (all four
    Super Cups); all opens both. Never awards trophies or checks. Independent of
    included_cups and the goal. With randomize_cups, these groups are added to
    starting_cups and remaining cups require items. Otherwise natural access is retained.
    """

    display_name = "Starting Cup Unlocks"
    option_none = 0
    alias_natural = 0
    option_regular = 1
    option_super = 2
    option_all = 3
    default = 0


class PlacementChecks(DefaultOnToggle):
    """Top three, top two, and champion checks in included cups.
    Better finishes award lower checks too. Bowser semifinalists tie for third.
    """

    display_name = "Cup Placement Checks"


class CupMatchChecks(DefaultOnToggle):
    """Include individual match-completion checks in included cups."""

    display_name = "Cup Match Checks"


class CupWinBonusCount(Range):
    """Number of item checks awarded for winning each included cup, independent of placements."""

    display_name = "Cup Win Bonus Count"
    range_start = 0
    range_end = 5
    default = 5


class MilestoneRequirementPercent(Range):
    """Scale AP milestone requirements, rounded up. 50 halves them; 200 doubles them.
    The game's native medal requirements and displays remain unchanged.
    """

    display_name = "AP Milestone Requirement Percent"
    range_start = 10
    range_end = 200
    default = 100


class NamedSelection(OptionSet):
    default = frozenset({"all"})

    def __init__(self, value, random_str=None):
        super().__init__(value, random_str)
        unknown = self.value - self.valid_keys
        if unknown:
            raise ValueError(f"Unknown selection(s): {', '.join(sorted(unknown))}")
        if "all" in self.value:
            self.value = self.valid_keys - {"all"}


class IncludedCaptains(NamedSelection):
    """Captains included in first-win and combination checks. Does not lock the roster."""

    display_name = "Included Captains"
    valid_keys = set(CAPTAINS.values()) | {"all"}


class IncludedStadiums(NamedSelection):
    """Stadiums included in first-win and captain/stadium checks. Does not restrict cup venues."""

    display_name = "Included Stadiums"
    valid_keys = set(STADIUMS.values()) | {"all"}


class CustomSidekickCombos(NamedSelection):
    """Exact challenge names used when combo_checks is custom, e.g. Win with Yoshi + Birdo."""

    display_name = "Custom Captain and Sidekick Checks"
    valid_keys = {f"Win with {CAPTAINS[c]} + {s}" for c in range(8) for s in SIDEKICKS.values()}
    default = frozenset()


class CustomStadiumCombos(NamedSelection):
    """Exact challenge names used when combo_checks is custom, e.g. Win with Peach at The Palace."""

    display_name = "Custom Captain and Stadium Checks"
    valid_keys = {f"Win with {c} at {s}" for c in CAPTAINS.values() for s in STADIUMS.values()}
    default = frozenset()


class CheatUnlocks(NamedSelection):
    """Cheat unlock items allowed in the pool. all includes every cheat; [] includes none.
    All Strikers Unlock is the item name for Perfect Strike.
    Natural in-game unlocks remain available.
    """

    display_name = "Cheat Unlock Items"
    valid_keys = set(CHEAT_UNLOCKS) | {"all"}


class PowerupWeight(Range):
    """Percentage of non-trap filler that gives power-ups. Remaining filler is Nothing."""

    display_name = "Power-Up Filler Percent"
    range_start = 0
    range_end = 100
    default = 100


class DoublePowerupWeight(Range):
    """Percentage of helpful power-up items that are double boosts."""

    display_name = "Double Power-Up Percent"
    range_start = 0
    range_end = 100
    default = 50


class MilestoneChecks(DefaultOnToggle):
    """Checks for all five milestone awards, up to milestone_max_tier."""

    display_name = "Milestone Trophy Checks"


class CaptainWinChecks(DefaultOnToggle):
    """First win with each of the eight captains and the Super Team."""

    display_name = "Captain Win Checks"


class StadiumWinChecks(DefaultOnToggle):
    """First win at each of the seven stadiums."""

    display_name = "Stadium Win Checks"


class ComboChecks(Choice):
    """Themed adds eight captain/sidekick and eight captain/stadium challenges.
    All adds all 32 normal captain/sidekick and 63 captain/stadium combinations.
    Custom uses the two custom combo lists. Included captain/stadium filters
    also apply. Super Team is excluded from sidekick combinations.
    """

    display_name = "Combination Win Checks"
    option_off = 0
    option_themed = 1
    option_all = 2
    option_custom = 3
    default = 1


class CharacterUnlockChecks(Toggle):
    """Add a check for unlocking the game's hidden Super Team."""

    display_name = "Character Unlock Checks"
    default = 0


class EnableTraps(Toggle):
    """Allow opponent power-up traps to replace helpful filler items."""

    display_name = "Enable Power-Up Traps"
    default = 0


class TrapWeight(Range):
    """Percentage of helpful power-up filler items replaced by traps."""

    display_name = "Power-Up Trap Weight"
    range_start = 0
    range_end = 100
    default = 50


class RandomizeCaptains(Toggle):
    """Lock selectable captains behind AP items. Cup CPU opponents stay unrestricted.
    Grudge Match applies the same roster to both selection grids.
    """

    display_name = "Randomize Captain Unlocks"


class RandomizeSidekicks(Toggle):
    """Lock selectable sidekicks behind AP items. Super Team keeps its robots."""

    display_name = "Randomize Sidekick Unlocks"


class RandomizeCups(Toggle):
    """Lock each of the eight cups behind its AP item, overriding natural qualification.
    starting_cups and starting_cup_unlocks grant starting access without items.
    included_cups still controls checks, not which cup unlock items exist.
    """

    display_name = "Randomize Cup Unlocks"


class StartingCaptains(OptionSet):
    """Captains available immediately with randomize_captains. Choose at least two."""

    display_name = "Starting Captains"
    valid_keys = set(CAPTAINS.values())
    default = {"Mario", "Luigi"}


class StartingSidekicks(OptionSet):
    """Sidekicks available immediately with randomize_sidekicks. Choose at least one."""

    display_name = "Starting Sidekicks"
    valid_keys = set(SIDEKICKS.values())
    default = {"Toad"}


class StartingCups(OptionSet):
    """Cups available immediately with randomize_cups. Choose at least one.
    starting_cup_unlocks also adds its regular/super groups to this list.
    """

    display_name = "Starting Cups"
    valid_keys = {cup.name for cup in CUPS}
    default = {"Mushroom Cup"}


@dataclass
class StrikersOptions(PerGameCommonOptions):
    randomize_captains: RandomizeCaptains
    randomize_sidekicks: RandomizeSidekicks
    randomize_cups: RandomizeCups
    starting_captains: StartingCaptains
    starting_sidekicks: StartingSidekicks
    starting_cups: StartingCups
    goal: Goal
    required_battle_trophies: RequiredBattleTrophies
    required_cups: RequiredCups
    required_match_wins: RequiredMatchWins
    included_cups: IncludedCups
    milestone_max_tier: MilestoneMaxTier
    starting_cup_unlocks: StartingCupUnlocks
    cup_match_checks: CupMatchChecks
    cup_win_bonus_count: CupWinBonusCount
    milestone_requirement_percent: MilestoneRequirementPercent
    included_captains: IncludedCaptains
    included_stadiums: IncludedStadiums
    custom_sidekick_combos: CustomSidekickCombos
    custom_stadium_combos: CustomStadiumCombos
    cheat_unlocks: CheatUnlocks
    powerup_weight: PowerupWeight
    double_powerup_weight: DoublePowerupWeight
    placement_checks: PlacementChecks
    milestone_checks: MilestoneChecks
    captain_win_checks: CaptainWinChecks
    stadium_win_checks: StadiumWinChecks
    combo_checks: ComboChecks
    character_unlock_checks: CharacterUnlockChecks
    enable_traps: EnableTraps
    trap_weight: TrapWeight
    death_link: DeathLink
