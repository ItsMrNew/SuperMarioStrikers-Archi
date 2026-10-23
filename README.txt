Super Mario Strikers Archipelago

Play cup matches and complete challenges to earn Archipelago items.
Choose your goal, starting roster and cup access in your YAML settings.

WHAT YOU NEED
- Archipelago and Dolphin.
- Your own USA copy of Super Mario Strikers (game ID G4QE01).
- Both parts of this mod: strikers.apworld and the supplied Riivolution patch.
  A game image is not included.

1. INSTALL THE MOD
Close the game and Strikers client before copying files.

- Copy Archipelago/strikers.apworld into Archipelago's custom_worlds folder.
  On a standard Windows installation:
  C:/ProgramData/Archipelago/custom_worlds/

- In Dolphin, choose File > Open User Folder.
  Copy the contents of this package's Riivolution/Riivolution/ folder into
  that user folder's Load/Riivolution/ folder. The finished paths should be:
    Load/Riivolution/StrikersAP/main.dol
    Load/Riivolution/riivolution/StrikersAP.xml

- Restart Archipelago Launcher.

2. CHOOSE YOUR SETTINGS
Copy ONE YAML for your player from the examples folder and change its name field to your player name.
Alternatively, use the Options Creator within the Archipelago launcher to create your own.  

- Strikers.yaml: earn all eight cup trophies; roster/cup randomization is off.
- examples/Strikers-Randomized-Unlocks.yaml: earn four trophies while finding
  captain, sidekick and cup unlock items.
- examples/Strikers-Short.yaml: win Mushroom and Flower Cups.
- examples/Strikers-Medium.yaml: win all four regular cups.
- examples/Strikers-Long.yaml: complete every enabled check.
- examples/Strikers-Match-Wins.yaml: win ten cup or Grudge matches.
- examples/Strikers-Custom-Quick.yaml: two cups with fewer match checks and
  easier milestone targets.

Give your YAML to the multiworld host. To generate locally, put it in
Archipelago's Players folder and run Generate, then host the generated game.

The full settings reference is Archipelago-Source/strikers/README.md.

3. CONNECT AND PLAY
- Use a fresh game save for each new seed. Keep a separate Dolphin memory card
  or user profile for each run.
- Right-click the USA game in Dolphin and choose Start with Riivolution Patches.
  Enable "Completion mailbox and DeathLink goals", then start the game.
- Open Super Mario Strikers Client from Archipelago Launcher.
  Connect using the room address and your YAML player name.
- Wait at the title or main menu until the client confirms the save is ready.
  The game's next normal save records which seed and player it belongs to.
- Keep the client running while you play. Use normal in-game saves.
- Choose your preferred difficulty when creating a cup. To change an existing
  cup's difficulty, start a new cup.

HOW CHECKS WORK
A check is a completed challenge that sends an item through Archipelago.

- Cup match checks count completed matches, including losses.
- Captain, stadium and combination checks require wins.
- Placements are cumulative: first awards Champion, Top 2 and Top 3;
  second awards Top 2 and Top 3; third awards Top 3.
  You do not need to replay a cup to earn its lower placements.
- Cup-win bonuses depend on your YAML and are awarded once per cup.
- Milestones use cup statistics. If your YAML scales their requirements,
  /progress shows the AP targets; the game's medal display keeps its own targets.
- Grudge wins count while the client is running and observing the match end.
- Human-versus-human, CPU-only, training and custom-tournament games do not
  award win challenges. Human teammates on the same side are supported.
- Winning the same cup again does not add another distinct cup trophy.
  Milestone medals do not count toward a battle-trophy goal.

USEFUL CLIENT COMMANDS
/progress          Show your goal, remaining checks, unlocks and queued rewards.
/missing Flower    List missing checks containing "Flower" (any name works).
/dolphin           Show the connection and save status.

IF SOMETHING IS BLOCKED
- Client missing from Launcher: check the apworld location and restart Launcher.
- Game or patch not recognized: use G4QE01, install both mod components and
  boot through Riivolution again. Avoid loading an old Dolphin save state.
- Save belongs to another seed/player: load the matching save or a fresh one.
- Unbound save already has progress: use a fresh save for a new run.
  Only to intentionally credit existing progress, return to the main menu
  and enter /adoptsave confirm. A save bound to another slot cannot be adopted.
- Cup or roster locked: check /progress for the unlock items you still need.
  A saved cup requires its captain and sidekick to be available before resuming.
- Rewards waiting: full inventories hold boosts until there is room.
- Network disconnected: keep the client open and reconnect to the same slot.
  Recorded checks and unused rewards are retained.
- Missing dolphin-memory-engine: install requirements.txt from
  Archipelago-Source/strikers/ into the Python environment used by the client.
- Run one Dolphin instance and one Strikers client at a time on the same PC.

For the optional installer and source/build details, see DEVELOPING.md.

AI USE NOTICE
Parts of this mod's code and documentation were developed with assistance from OpenAI's ChatGPT, including Codex coding assistance. 