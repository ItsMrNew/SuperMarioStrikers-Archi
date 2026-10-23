import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.install import install


class InstallTests(unittest.TestCase):
    def test_clean_install_verification_backups_and_corrupt_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "release"
            files = {
                "Archipelago/strikers.apworld": b"world",
                "Riivolution/Riivolution/StrikersAP/main.dol": b"dol",
                "Riivolution/Riivolution/riivolution/StrikersAP.xml": b"xml",
            }
            for name, value in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(value)
            (root / "release-manifest.json").write_text(
                json.dumps(
                    {
                        "version": "test",
                        "sha256": {
                            name: hashlib.sha256(data).hexdigest() for name, data in files.items()
                        },
                    }
                )
            )
            ap, dolphin = Path(directory) / "ap", Path(directory) / "dolphin"
            result = install(root, ap, dolphin)
            self.assertEqual([entry["status"] for entry in result["files"]], ["installed"] * 3)
            self.assertEqual(
                [entry["status"] for entry in install(root, ap, dolphin, check=True)["files"]],
                ["verified"] * 3,
            )
            old = ap / "custom_worlds/strikers.apworld"
            old.write_bytes(b"old")
            with self.assertRaises(ValueError):
                install(root, ap, dolphin, check=True)
            backup = install(root, ap, dolphin)["files"][0]["backup"]
            self.assertEqual(Path(backup).read_bytes(), b"old")
            (root / next(iter(files))).write_bytes(b"corrupt")
            fresh_ap, fresh_dolphin = (
                Path(directory) / "untouched-ap",
                Path(directory) / "untouched-dolphin",
            )
            with self.assertRaises(ValueError):
                install(root, fresh_ap, fresh_dolphin)
            self.assertFalse(fresh_ap.exists())
            self.assertFalse(fresh_dolphin.exists())
