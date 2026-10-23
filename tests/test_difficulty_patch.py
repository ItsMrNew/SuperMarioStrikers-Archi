import hashlib
from pathlib import Path
import unittest

from tools.patch_difficulty import (
    ORIGINAL_SHA256,
    PATCHES,
    file_offset,
    unlock_difficulty,
)
from tools.patch_cup_access import remove_cup_access
from tools.patch_unlocks import remove_unlocks


class DifficultyPatchTests(unittest.TestCase):
    def setUp(self):
        self.data = remove_cup_access(
            remove_unlocks(
                (
                    Path(__file__).resolve().parents[1]
                    / "Riivolution/Riivolution/StrikersAP/main.dol"
                ).read_bytes()
            )
        )

    def test_packaged_binary_changes_only_the_difficulty_branch(self):
        original = bytearray(self.data)
        for address, old, new in PATCHES:
            offset = file_offset(self.data, address)
            self.assertEqual(self.data[offset : offset + 4], new)
            original[offset : offset + 4] = old
        self.assertEqual(hashlib.sha256(original).hexdigest(), ORIGINAL_SHA256)
        self.assertEqual(unlock_difficulty(original), self.data)
        self.assertEqual(unlock_difficulty(self.data), self.data)

    def test_rejects_unrelated_executable_changes(self):
        altered = bytearray(self.data)
        altered[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "Unsupported executable"):
            unlock_difficulty(altered)

    def test_rejects_unknown_difficulty_instruction(self):
        altered = bytearray(self.data)
        offset = file_offset(self.data, PATCHES[0][0])
        altered[offset : offset + 4] = bytes.fromhex("60000000")
        with self.assertRaisesRegex(ValueError, "Unexpected difficulty instruction"):
            unlock_difficulty(altered)
