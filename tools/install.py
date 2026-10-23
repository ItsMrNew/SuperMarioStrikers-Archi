"""Install both release components, preserving replaced files as hashed backups."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def install(root, archipelago, dolphin, *, check=False):
    manifest = json.loads((root / "release-manifest.json").read_text())
    targets = {
        "Archipelago/strikers.apworld": archipelago / "custom_worlds/strikers.apworld",
        "Riivolution/Riivolution/StrikersAP/main.dol": dolphin
        / "Load/Riivolution/StrikersAP/main.dol",
        "Riivolution/Riivolution/riivolution/StrikersAP.xml": dolphin
        / "Load/Riivolution/riivolution/StrikersAP.xml",
    }
    # Verify every input before touching either destination.
    for source in targets:
        if digest(root / source) != manifest["sha256"][source]:
            raise ValueError(
                f"Damaged or mixed release: {source}. Rebuild or extract the complete release."
            )
    results = []
    for source, destination in targets.items():
        expected = manifest["sha256"][source]
        if destination.exists() and digest(destination) == expected:
            results.append({"path": str(destination), "status": "verified"})
            continue
        if check:
            raise ValueError(f"Missing or outdated installation: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        backup = None
        if destination.exists():
            backup = destination.with_name(destination.name + ".before-" + digest(destination)[:12])
            if backup.exists() and digest(backup) != digest(destination):
                raise ValueError(f"Backup collision: {backup}")
            if not backup.exists():
                shutil.copy2(destination, backup)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=destination.parent, prefix="strikers-", delete=False
            ) as stream:
                temporary = Path(stream.name)
                stream.write((root / source).read_bytes())
            if digest(temporary) != expected:
                raise ValueError("Installation copy failed verification")
            os.replace(temporary, destination)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
        results.append(
            {
                "path": str(destination),
                "status": "installed",
                "backup": str(backup) if backup else None,
            }
        )
    return {"version": manifest["version"], "files": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archipelago",
        type=Path,
        default=Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "Archipelago",
    )
    parser.add_argument(
        "--dolphin-user",
        type=Path,
        default=Path(os.environ.get("APPDATA", Path.home())) / "Dolphin Emulator",
    )
    parser.add_argument(
        "--check", action="store_true", help="Verify installed files without changing anything"
    )
    args = parser.parse_args()
    print(
        json.dumps(
            install(
                ROOT, args.archipelago.resolve(), args.dolphin_user.resolve(), check=args.check
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
