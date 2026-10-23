"""Run with AP_SRC pointing to an Archipelago 0.6.8 source checkout."""

import os
import sys
from pathlib import Path
import unittest

if os.environ.get("AP_SRC"):
    sys.path.insert(0, os.environ["AP_SRC"])
# Load framework fixtures first. Including strikers here lets an older apworld
# in the AP checkout load before our source directory is added below.
os.environ["AP_TEST_WORLDS"] = "generic"
import ModuleUpdate

# Tests use explicitly installed dependencies; never run AP's interactive updater.
ModuleUpdate.update = lambda *args, **kwargs: None
import worlds

worlds.__path__.insert(0, str(Path(__file__).resolve().parents[1] / "Archipelago-Source"))
