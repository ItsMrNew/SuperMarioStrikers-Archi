# Super Mario Strikers YAML reference

See the package's root `README.txt` for installation and play instructions.
Edit one player YAML before generating a seed. Changing the YAML does not change
an already generated game.

## Choose a goal

| `goal` | Requirement |
| --- | --- |
| `battle_trophies` | Earn `required_battle_trophies` distinct included cup trophies (1–8; default 8) |
| `selected_cups` | Win every cup in `required_cups` |
| `match_wins` | Reach `required_match_wins` observed cup or Grudge wins (1–100; default 25) |
| `all_enabled_checks` | Complete every enabled check except the goal itself |

`required_cups` defaults to `[Super Bowser Cup]` and is used only for
`selected_cups`. Every required cup must be included. Each other target setting
is also used only by its corresponding goal.

Trophy goals count distinct cup trophies in the same save. Rewinning a cup does
not increase the count, and milestone medals do not count as cup trophies.
Match-win goals allow replays and wins in cups excluded from the check pool;
the client must observe each match end. Existing saved results do not add wins.

A goal can finish before all optional checks are collected. In a multiworld,
other players may still need the items at those remaining checks.

## Randomize unlocks

| Option | Default | Meaning |
| --- | --- | --- |
| `randomize_captains` | false | Require AP items to select captains outside the starting list |
| `randomize_sidekicks` | false | Require AP items to select sidekicks outside the starting list |
| `randomize_cups` | false | Require AP items to enter cups outside the starting access |
| `starting_captains` | [Mario, Luigi] | At least two captains, when captain randomization is enabled |
| `starting_sidekicks` | [Toad] | At least one sidekick, when sidekick randomization is enabled |
| `starting_cups` | [Mushroom Cup] | At least one cup, when cup randomization is enabled |
| `starting_cup_unlocks` | none | Extra access: `none`, `regular`, `super` or `all` |

`starting_cup_unlocks` adds its cup groups to `starting_cups`. Use `none` to
start only with the explicit list when randomizing cups. With randomization off,
natural progression remains available alongside any extra starting access.
Starting access never awards trophies or checks.

Receiving any Super Cup opens the Super Cup menu; each cup still needs its own
unlock if randomized. Cup CPU opponents use the full roster. Both Grudge roster
grids use your available choices. A saved cup requires its captain and sidekick
before it can be resumed. Super Team uses fixed robotic sidekicks.

Examples of items are `Peach Captain Unlock`, `Birdo Sidekick Unlock` and
`Flower Cup Unlock`. `Yoshi Captain Unlock` unlocks Yoshi; `Yoshi Unlock`
unlocks Crater Field.

Required progression items must fit in the check pool. If generation reports
too few locations, enable more checks or provide more starting unlocks.
Use `/progress` to see your available roster and cups.

## Choose checks

| Option | Default | Meaning |
| --- | --- | --- |
| `included_cups` | all | Cups with match, placement and cup-win bonus checks |
| `cup_match_checks` | true | Checks for completing individual cup matches |
| `placement_checks` | true | Top 3, Top 2 and Champion checks |
| `cup_win_bonus_count` | 5 | 0–5 bonus checks for winning each included cup |
| `milestone_checks` | true | Checks for the five milestone awards |
| `milestone_max_tier` | gold | Highest included tier: `bronze`, `silver` or `gold` |
| `milestone_requirement_percent` | 100 | Scale AP milestone targets to 10–200%, rounded up |
| `captain_win_checks` | true | First win with each included captain |
| `stadium_win_checks` | true | First win at each included stadium |
| `included_captains` | all | Captain names used for first-win and combination checks |
| `included_stadiums` | all | Stadium names used for first-win and combination checks |
| `combo_checks` | themed | `off`, `themed`, `all` or `custom` combinations |
| `custom_sidekick_combos` | [] | Full sidekick challenge names for `custom` |
| `custom_stadium_combos` | [] | Full stadium challenge names for `custom` |
| `character_unlock_checks` | false | Check for permanently unlocking Super Team |

The included lists accept `all` or exact names, such as
`included_cups: [Mushroom Cup, Flower Cup]`. They filter challenges; they do not
unlock cups, lock characters or restrict cup venues. Required trophy cups must
be included. An empty cup list is allowed for other goals if checks remain.

Cup match checks count completed games, including losses. Win challenges require
a human team's win in a cup or Grudge Match. Human teammates are supported.
Human-versus-human, CPU-only, training, demonstrations and custom tournaments do
not award win challenges.

Placements are cumulative: first awards Champion, Top 2 and Top 3; second awards
Top 2 and Top 3; third awards Top 3. Bowser semifinalists tie for third, and final
participation qualifies for Top 2. Championship checks require the championship
record or trophy. Replays do not repeat already collected checks.

| Cup | Match checks |
| --- | ---: |
| Mushroom Cup | 3 |
| Flower Cup | 5 |
| Star Cup | 7 |
| Bowser Cup | 9 |
| Super Mushroom Cup | 6 |
| Super Flower Cup | 10 |
| Super Star Cup | 14 |
| Super Bowser Cup | 16 |

Bowser totals include the semifinal and final. Regular Bowser's conditional
Super Team challenge has no separate match check because the Super Team item
can bypass it. Its result can still award win challenges; earning the trophy
follows the game's rules.

## Combinations and milestones

Themed combinations are separate sidekick and stadium challenges:

| Captain | Sidekick | Stadium |
| --- | --- | --- |
| Daisy | Birdo | Konga Coliseum |
| Donkey Kong | Hammer Bro | Konga Coliseum |
| Luigi | Koopa Troopa | Pipeline Central |
| Mario | Toad | Pipeline Central |
| Peach | Toad | The Palace |
| Waluigi | Hammer Bro | The Underground |
| Wario | Koopa Troopa | The Underground |
| Yoshi | Birdo | Crater Field |

`all` includes 32 ordinary captain/sidekick and 63 captain/stadium combinations.
Super Team has no ordinary sidekick combinations. For `custom`, use full names
such as `Win with Yoshi + Birdo` or `Win with Peach at The Palace`.
Captain and stadium filters also apply to custom combinations.

Milestones use the game's saved cup statistics:

| Award | Counter | Bronze | Silver | Gold |
| --- | --- | ---: | ---: | ---: |
| Veteran | Cup matches played | 25 | 50 | 100 |
| Sniper | Cup goals scored | 75 | 150 | 300 |
| Super Striker | Cup Super Strike attempts | 25 | 50 | 100 |
| Tactician | Cup perfect passes | 75 | 150 | 300 |
| Paramedic | Cup hits | 250 | 500 | 1000 |

`milestone_requirement_percent` changes AP check targets only. At 25%, Veteran
targets become 7/13/25 matches. The game's own medals and display keep their
native requirements; `/progress` shows the AP targets.

## Rewards and DeathLink

| Option | Default | Meaning |
| --- | --- | --- |
| `cheat_unlocks` | all | Allowed cheat item names, or `[]` for none |
| `powerup_weight` | 100 | Percentage of non-trap filler that gives boosts; the rest is Nothing |
| `double_powerup_weight` | 50 | Percentage of helpful boosts that give two power-ups |
| `enable_traps` | false | Include power-up traps for the opponent |
| `trap_weight` | 50 | Percentage of filler allocated to traps when enabled |
| `death_link` | false | Cup losses send DeathLink; incoming DeathLinks queue a goal against the human team |

`All Strikers Unlock` is the item name for Perfect Strike. Other cheat item
names are `Tilt Control Cheat`, `Goalie Control Cheat`, `Unlimited Cheat`,
`Shells Cheat`, `Enhance Cheat`, `Giant Cheat`, `Explosive Cheat` and
`Freezing Cheat`. Omitting cheat items does not disable natural game unlocks.

A Power-Up Boost gives one power-up to the player; a Double Power-Up Boost gives
two. A Power-Up Boost Trap gives two to the opponent. Full inventories retain
unused rewards until room becomes available. Trap allocation happens first,
then helpful filler is divided into boosts and Nothing.

## Saves and connection

Use a fresh save for each seed and keep separate memory cards or profiles.
The client binds the save to your seed, team and player slot at the title/main
menu. The next normal save persists that binding. A save belonging to another
slot blocks synchronization and new match starts.

To intentionally use an unbound save with existing achievements, enter
`/adoptsave confirm` at the main menu. Those achievements will count.
A save already bound to another slot cannot be adopted.

Keep the client running through match ends. Recorded checks and unused rewards
are stored per slot and survive restarts. After an initial connection, the running
client records checks during server outages and sends them after reconnecting.
Grudge wins cannot be reconstructed if the client missed the match end.

Use `/progress` for goal, unlock and reward status; `/missing` with a name
filter for individual checks; and `/dolphin` for connection/save status.
